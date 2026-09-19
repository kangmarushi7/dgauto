"""Arahus OOS v1 pipeline — chronological holdout evaluation."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

import numpy as np

from research.arahus_oos_v1.config import (
    CONF_BANDS_ANALYSIS,
    FROZEN_CONFIG,
    LEAGUE_WHITELIST_STATUS,
    ODDS_BANDS_ANALYSIS,
    FrozenCandidateConfig,
)
from research.arahus_oos_v1.filters import assign_periods, filter_strategy, qualifies_candidate
from research.arahus_oos_v1.integrity import audit_rows
from research.arahus_oos_v1.load import load_csv, load_from_database
from research.arahus_oos_v1.metrics import (
    bets_needed_for_precision,
    sample_size_label,
    summarize_bets,
)


def _iso_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def reconcile_full_log(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare computed totals to Arahus dashboard-style summary on full log."""
    settled = [r for r in rows if r.get("status") in {"won", "lost", "push"}]
    # Existing summary style: all statuses in placed; pnl sum of logged
    placed = len(rows)
    won = sum(1 for r in rows if r.get("status") == "won")
    lost = sum(1 for r in rows if r.get("status") == "lost")
    push = sum(1 for r in rows if r.get("status") == "push")
    open_n = sum(1 for r in rows if r.get("status") == "open")
    logged_pnl = round(
        sum(float(r.get("pnl_units_logged") or 0.0) for r in rows if r.get("status") != "open"),
        3,
    )
    # Recalculated from odds/units
    from research.arahus_oos_v1.metrics import pnl_for_bet

    recalc = 0.0
    for r in settled:
        p = pnl_for_bet(
            r["status"],
            r.get("odds"),
            float(r.get("units") or 1.0),
            prefer_logged=False,
        )
        if p is not None:
            recalc += p
    return {
        "existing_style_summary": {
            "bets": placed,
            "won": won,
            "lost": lost,
            "push": push,
            "open": open_n,
            "pnl_logged_sum": logged_pnl,
        },
        "calculated": {
            "settled_bets": len(settled),
            "won": won,
            "lost": lost,
            "push": push,
            "pnl_recomputed_from_odds_units": round(recalc, 3),
            "pnl_logged_sum": logged_pnl,
        },
        "match_logged_vs_recomputed": abs(logged_pnl - round(recalc, 3)) < 0.02,
        "delta": round(logged_pnl - round(recalc, 3), 3),
    }


def _sort_chrono(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]) -> tuple:
        return (r.get("fixture_date") or "", r.get("id") or "")

    return sorted(rows, key=key)


def league_breakdown(rows: list[dict[str, Any]], *, stake_mode: str = "logged_units") -> list[dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[str(r.get("league_name") or "(blank)")].append(r)
    out = []
    for league, group in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        m = summarize_bets(group, stake_mode=stake_mode)
        out.append(
            {
                "league": league,
                "bets": m["n"],
                "w_l_p": f"{m['won']}-{m['lost']}-{m['push']}",
                "win_pct": m["win_pct"],
                "avg_odds": m["avg_odds"],
                "staked": m["staked"],
                "pnl": m["pnl"],
                "roi": m["roi"],
                "max_dd": m["max_dd_units"],
                "sample_label": m["sample_label"],
            }
        )
    return out


def odds_band_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for lo, hi, label in ODDS_BANDS_ANALYSIS:
        group = [
            r
            for r in rows
            if r.get("odds") is not None and lo <= float(r["odds"]) <= hi
        ]
        m = summarize_bets(group)
        out.append(
            {
                "band": label,
                "bets": m["n"],
                "w_l_p": f"{m['won']}-{m['lost']}-{m['push']}",
                "win_pct": m["win_pct"],
                "pnl": m["pnl"],
                "roi": m["roi"],
            }
        )
    return out


def conf_band_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for lo, hi, label in CONF_BANDS_ANALYSIS:
        group = []
        for r in rows:
            c = r.get("confidence")
            if c is None:
                continue
            c = float(c)
            if lo <= c <= hi if hi < 200 else c >= lo:
                group.append(r)
        m = summarize_bets(group)
        out.append(
            {
                "band": label,
                "bets": m["n"],
                "w_l_p": f"{m['won']}-{m['lost']}-{m['push']}",
                "win_pct": m["win_pct"],
                "pnl": m["pnl"],
                "roi": m["roi"],
            }
        )
    return out


def weekly_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _sort_chrono(rows)
    by_week: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        d = r.get("fixture_date_d")
        if not d:
            continue
        dt = date.fromisoformat(d)
        iso = dt.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        by_week[key].append(r)
    out = []
    for week in sorted(by_week):
        m = summarize_bets(by_week[week])
        out.append(
            {
                "week": week,
                "bets": m["n"],
                "win_pct": m["win_pct"],
                "pnl": m["pnl"],
                "roi": m["roi"],
            }
        )
    return out


def rolling_windows(rows: list[dict[str, Any]], window: int) -> list[dict[str, Any]]:
    rows = _sort_chrono([r for r in rows if r.get("status") in {"won", "lost", "push"}])
    out = []
    for i in range(window, len(rows) + 1):
        chunk = rows[i - window : i]
        m = summarize_bets(chunk)
        out.append(
            {
                "end_index": i,
                "end_date": chunk[-1].get("fixture_date_d"),
                "window": window,
                "roi": m["roi"],
                "cumulative_pnl": m["pnl"],
                "win_pct": m["win_pct"],
            }
        )
    return out


def clv_section(rows: list[dict[str, Any]]) -> dict[str, Any]:
    with_close = [r for r in rows if r.get("closing_odds") is not None]
    if not with_close:
        return {
            "available": False,
            "message": "CLV unavailable in current dataset.",
            "n_with_closing_odds": 0,
        }
    # If ever present:
    details = []
    for r in with_close:
        entry = float(r["odds"])
        close = float(r["closing_odds"])
        details.append(
            {
                "id": r.get("id"),
                "entry_odds": entry,
                "closing_odds": close,
                "implied_entry": 1.0 / entry if entry else None,
                "implied_close": 1.0 / close if close else None,
                "clv": (1.0 / close) - (1.0 / entry) if entry and close else None,
            }
        )
    return {"available": True, "n_with_closing_odds": len(details), "rows": details}


def leakage_audit(cfg: FrozenCandidateConfig) -> dict[str, Any]:
    return {
        "oos_used_for_league_selection": False,
        "oos_used_for_odds_band_selection": False,
        "oos_used_for_confidence_threshold": False,
        "oos_used_for_staking_changes": False,
        "future_closing_odds_used_for_qualification": False,
        "settled_outcomes_used_for_qualification": False,
        "qualification_fields": ["market", "odds", "league_name (pass-through; no whitelist)"],
        "evaluation_fields": ["status", "pnl_units", "units"],
        "chronological_key": "fixture_date (Excel export lacks created_at)",
        "residual_limitations": [
            "Excel export has no created_at — cannot prove bet was placed before kickoff.",
            "No closing odds — CLV not measurable.",
            "Multiple markets per fixture historically in v1 log; candidate keeps O2.5 only.",
            "League whitelist absent — cannot test league-filter value-add until defined.",
        ],
        "config_frozen_before_oos": True,
        "frozen_config_id": cfg.candidate_id,
        "verdict": (
            "No intentional look-ahead into OOS for parameter selection. "
            "Configuration was fixed prior to September evaluation. "
            "Qualification does not use status/pnl/closing odds."
        ),
    }


def run_pipeline(
    *,
    csv_path: str | None = None,
    from_db: bool = False,
    log_type: str = "arahus",
    cfg: FrozenCandidateConfig = FROZEN_CONFIG,
) -> dict[str, Any]:
    if from_db:
        raw = load_from_database(log_type=log_type)
        data_source = f"database:{log_type}"
    else:
        from pathlib import Path

        from research.arahus_oos_v1.load import DEFAULT_CSV

        path = Path(csv_path) if csv_path else DEFAULT_CSV
        raw = load_csv(path)
        data_source = str(path)

    integrity = audit_rows(raw)
    rows = assign_periods(raw, cfg)
    reconciliation = reconcile_full_log(rows)

    # Missing odds among O2.5 (report separately)
    o25_all = [r for r in rows if r.get("market") == "over_2_5"]
    missing_odds_o25 = [r for r in o25_all if r.get("odds") is None]

    # Strategy subsets on OOS
    strat_a = filter_strategy(
        rows, period="oos", require_o25=True, odds_band=False, apply_league_whitelist=False, cfg=cfg
    )
    strat_c = filter_strategy(
        rows, period="oos", require_o25=True, odds_band=True, apply_league_whitelist=False, cfg=cfg
    )
    # B: with whitelist — identical to C when selected_leagues is None
    strat_b = filter_strategy(
        rows, period="oos", require_o25=True, odds_band=True, apply_league_whitelist=True, cfg=cfg
    )

    # Also development-period candidate (context only; NOT used to tune)
    strat_b_dev = filter_strategy(
        rows, period="development", require_o25=True, odds_band=True, apply_league_whitelist=True, cfg=cfg
    )

    primary = summarize_bets(strat_b, stake_mode="logged_units")
    primary_flat = summarize_bets(strat_b, stake_mode="flat_1u")

    # Drop heavy equity curves from nested JSON copies used in tables
    def slim(m: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in m.items() if k != "equity_curve"}

    comparison = [
        {
            "strategy": "All Arahus O2.5",
            "id": "A",
            **{k: slim(summarize_bets(strat_a)).get(k) for k in (
                "n", "win_pct", "avg_odds", "staked", "pnl", "roi", "max_dd_units"
            )},
        },
        {
            "strategy": "O2.5 + selected leagues + odds 1.30–1.49",
            "id": "B",
            "note": "Identical to C — league whitelist undefined in repo",
            **{k: slim(summarize_bets(strat_b)).get(k) for k in (
                "n", "win_pct", "avg_odds", "staked", "pnl", "roi", "max_dd_units"
            )},
        },
        {
            "strategy": "O2.5 + odds 1.30–1.49 (no league filter)",
            "id": "C",
            **{k: slim(summarize_bets(strat_c)).get(k) for k in (
                "n", "win_pct", "avg_odds", "staked", "pnl", "roi", "max_dd_units"
            )},
        },
    ]

    oos_dates = [r.get("fixture_date_d") for r in strat_b if r.get("fixture_date_d")]
    oos_end = max(oos_dates) if oos_dates else None

    reject_reasons = defaultdict(int)
    for r in rows:
        if r.get("period") == "oos" and not r.get("candidate_ok"):
            reject_reasons[str(r.get("reject_reason"))] += 1

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_date": _iso_today(),
        "data_source": data_source,
        "research_only": True,
        "can_place_real_bet": False,
        "frozen_config": cfg.to_dict(),
        "league_whitelist_status": LEAGUE_WHITELIST_STATUS,
        "periods": {
            "development": f"{cfg.development_start} → {cfg.development_end}",
            "oos": f"{cfg.oos_start} → {oos_end or 'latest settled'}",
            "oos_end_observed": oos_end,
        },
        "integrity": integrity,
        "reconciliation": reconciliation,
        "missing_odds_o25_count": len(missing_odds_o25),
        "oos_reject_reason_counts": dict(reject_reasons),
        "main_result_logged_stake": slim(primary),
        "main_result_flat_1u": slim(primary_flat),
        "main_result_equity_curve": primary.get("equity_curve"),
        "development_candidate_context_only": slim(summarize_bets(strat_b_dev)),
        "baseline_comparison": comparison,
        "league_breakdown_oos_candidate": league_breakdown(strat_b),
        "non_selected_leagues": {
            "applicable": False,
            "reason": LEAGUE_WHITELIST_STATUS["ambiguity"],
            "note": "All leagues in O2.5+odds band are included; see league_breakdown for volume.",
        },
        "odds_band_breakdown_oos": odds_band_breakdown(strat_b),
        "confidence_band_breakdown_oos": conf_band_breakdown(strat_b),
        "weekly_oos": weekly_series(strat_b),
        "rolling_25": rolling_windows(strat_b, 25),
        "rolling_50": rolling_windows(strat_b, 50),
        "clv": clv_section(strat_b),
        "leakage_audit": leakage_audit(cfg),
        "future_sample_size": bets_needed_for_precision(
            observed_std=primary.get("std_per_bet_return")
        ),
        "n_raw": len(rows),
        "n_oos_candidate_settled": primary["n"],
    }
    return payload
