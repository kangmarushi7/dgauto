"""Arahus Engine v2 — frozen forward-test protocol (isolated from v1).

Live rules (do not change mid-test):
- Market: Over 2.5 only (O3.5 research/watch, never live)
- Odds required; primary band 1.30–1.49 (outside = skip)
- Edge: model_pct − implied ≥ 3pp (v2A live); ≥ 5pp tagged as v2B
- EV > 0 where EV% = (model_pct/100)×odds − 1  (stored as percent ×100)
- Confidence ≥ 66 for eligibility
- BTTS off; missing odds off
- Rank live picks: EV → edge → confidence
- Flat 1.0 unit stake

Every O2.5/O3.5 candidate is logged with eligible_v2A / eligible_v2B / skip_reason
for counterfactual analysis without changing live rules.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid
from typing import Any

from app.bet_log import compute_bet_stats
from app.arahus_engine import (
    _clamp,
    _signal,
    build_fixture_profile,
    project_match,
)
from app.db import (
    insert_arahus_v2_report_log,
    insert_bets,
    list_arahus_v2_report_log,
    list_bets,
    resolve_bet_entry,
)
from app.dg_feeds import lookup_extra_for_fixture
from app.fixture_detail import find_raw_fixture
from app.fixture_math import edge as calc_edge
from app.fixture_math import expected_value_pct, implied_prob, num

LOG_TYPE = "arahus_v2"
ENGINE_VERSION = "arahus-v2"
FLAT_STAKE = float(os.getenv("ARAHUS_V2_FLAT_STAKE", "1.0"))

# Frozen thresholds
MIN_CONFIDENCE = float(os.getenv("ARAHUS_V2_MIN_CONFIDENCE", "66"))
MIN_EDGE_A = float(os.getenv("ARAHUS_V2_MIN_EDGE_A", "3.0"))
MIN_EDGE_B = float(os.getenv("ARAHUS_V2_MIN_EDGE_B", "5.0"))
ODDS_MIN = float(os.getenv("ARAHUS_V2_ODDS_MIN", "1.30"))
ODDS_MAX = float(os.getenv("ARAHUS_V2_ODDS_MAX", "1.49"))

# Secondary cohort floor (logged only — never mixes into live / primary eligibility)
SECONDARY_CONFIDENCE = float(os.getenv("ARAHUS_V2_SECONDARY_CONFIDENCE", "62"))

BET_LABELS = {
    "arahus_o25": "Over 2.5",
    "arahus_o35": "Over 3.5 (watch)",
}

SKIP_MISSING_ODDS = "missing_odds"
SKIP_ODDS_RANGE = "odds_out_of_range"
SKIP_LOW_CONF = "low_confidence"
SKIP_LOW_EDGE = "low_edge"
SKIP_NON_POS_EV = "non_positive_ev"
SKIP_MARKET = "market_disabled"
SKIP_NOT_SELECTED = "not_selected_rank"
SKIP_ELIGIBLE = "eligible"  # taken live


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def engine_config_snapshot() -> dict[str, Any]:
    return {
        "engine_version": ENGINE_VERSION,
        "min_confidence": MIN_CONFIDENCE,
        "secondary_confidence": SECONDARY_CONFIDENCE,
        "min_edge_a": MIN_EDGE_A,
        "min_edge_b": MIN_EDGE_B,
        "odds_min": ODDS_MIN,
        "odds_max": ODDS_MAX,
        "flat_stake": FLAT_STAKE,
        "live_market": "arahus_o25",
        "watch_markets": ["arahus_o35"],
        "btts": False,
        "allow_no_odds": False,
        "rank": ["ev", "edge", "confidence"],
    }


def _overs_signals(
    profile: dict[str, Any],
    proj: dict[str, Any],
    *,
    for_o35: bool = False,
) -> list[dict[str, Any]]:
    """Reuse v1-style signal stack so confidence stays comparable."""
    idx = profile.get("indexes") or {}
    highlights = {str(h).lower() for h in (profile.get("highlights") or [])}

    def pace_sig() -> dict[str, Any] | None:
        pace = proj.get("pace")
        if pace is not None and pace >= 60:
            return _signal("pace", 12, f"Pace {pace:.0f} supports volume")
        bucket = idx.get("pace_bucket_o25")
        if bucket is not None and bucket >= 58:
            return _signal("pace_hist", 10, f"Pace bucket O2.5 hist {bucket:.0f}%")
        return None

    def nec_sig() -> dict[str, Any] | None:
        nec = proj.get("nec")
        if nec is not None and nec >= 58:
            return _signal("nec", 10, f"NEC {nec:.0f} attacking identity")
        return None

    def highlight_sig(*keys: str) -> dict[str, Any] | None:
        for k in keys:
            for h in highlights:
                if k in h:
                    return _signal("highlight", 8, f"Slate highlight: {h}")
        return None

    def sim_sig(pct: float | None, floor: float, label: str) -> dict[str, Any] | None:
        if pct is not None and pct >= floor:
            return _signal("sim", min(28, 10 + (pct - floor) * 0.6), f"Sim {label} {pct:.0f}%")
        return None

    def luck_ok() -> dict[str, Any] | None:
        luck = proj.get("luck") or 0
        if luck <= 0.35:
            return _signal("regression", 8, "Finishing not heavily inflated")
        return None

    if for_o35:
        raw = (
            sim_sig(proj.get("over_3_5_pct"), 48, "O3.5"),
            _signal("xg", 16, f"Total xG {proj.get('total_xg')}")
            if (proj.get("total_xg") or 0) >= 3.4
            else None,
            pace_sig(),
            nec_sig(),
            luck_ok(),
            highlight_sig("pace", "score", "goal"),
        )
    else:
        raw = (
            sim_sig(proj.get("over_2_5_pct"), 58, "O2.5"),
            _signal("xg", 14, f"Projected total xG {proj.get('total_xg')}")
            if (proj.get("total_xg") or 0) >= 2.7
            else None,
            pace_sig(),
            nec_sig(),
            luck_ok(),
            highlight_sig("over", "btts", "pace", "score", "goal"),
        )
    return [s for s in raw if s]


def _classify_candidate(
    *,
    bet_type: str,
    label: str,
    model_pct: float | None,
    odds: float | None,
    signals: list[dict[str, Any]],
    live_market: bool,
) -> dict[str, Any] | None:
    """Score one market; always return a row when model_pct exists."""
    if model_pct is None:
        return None

    confidence = _clamp(round(sum(s["weight"] for s in signals), 1), 0.0, 100.0)
    edge_val = calc_edge(model_pct, odds)
    ev_val = expected_value_pct(model_pct, odds)
    imp = implied_prob(odds)

    # Fixed gate order for primary skip_reason (counterfactual-stable).
    skip_reason: str | None = None
    if not live_market:
        skip_reason = SKIP_MARKET
    elif odds is None or odds <= 1:
        skip_reason = SKIP_MISSING_ODDS
    elif not (ODDS_MIN <= float(odds) <= ODDS_MAX):
        skip_reason = SKIP_ODDS_RANGE
    elif confidence < MIN_CONFIDENCE:
        skip_reason = SKIP_LOW_CONF
    elif edge_val is None or edge_val < MIN_EDGE_A:
        skip_reason = SKIP_LOW_EDGE
    elif ev_val is None or ev_val <= 0:
        skip_reason = SKIP_NON_POS_EV
    else:
        skip_reason = SKIP_ELIGIBLE

    odds_ok = odds is not None and odds > 1 and ODDS_MIN <= float(odds) <= ODDS_MAX
    base_ok = (
        live_market
        and odds_ok
        and confidence >= MIN_CONFIDENCE
        and ev_val is not None
        and ev_val > 0
        and edge_val is not None
    )
    eligible_v2a = bool(base_ok and edge_val >= MIN_EDGE_A)
    eligible_v2b = bool(base_ok and edge_val >= MIN_EDGE_B)
    # Loose cohort (conf ≥ 62) for later counterfactual — not live.
    eligible_secondary = bool(
        live_market
        and odds_ok
        and confidence >= SECONDARY_CONFIDENCE
        and ev_val is not None
        and ev_val > 0
        and edge_val is not None
        and edge_val >= MIN_EDGE_A
    )

    return {
        "bet_type": bet_type,
        "market_label": label,
        "market": bet_type,
        "team_name": "",
        "model_pct": round(model_pct, 1),
        "odds": odds,
        "implied_pct": imp,
        "edge": edge_val,
        "edge_pct": edge_val,
        "ev": ev_val,
        "confidence": confidence,
        "signals": signals,
        "signal_summary": " · ".join(s["detail"] for s in signals[:4]),
        "eligible_v2A": eligible_v2a,
        "eligible_v2B": eligible_v2b,
        "eligible_secondary": eligible_secondary,
        "skip_reason": skip_reason,
        "units": None,
        "stake": None,
        "status": "skipped",
    }


def evaluate_fixture_v2(
    raw: dict[str, Any],
    match: dict[str, Any] | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    profile = build_fixture_profile(raw, match, extra)
    proj = project_match(profile)
    odds = profile.get("odds") or {}

    decisions: list[dict[str, Any]] = []
    o25 = _classify_candidate(
        bet_type="arahus_o25",
        label="Over 2.5",
        model_pct=proj.get("over_2_5_pct"),
        odds=odds.get("over_2_5"),
        signals=_overs_signals(profile, proj, for_o35=False),
        live_market=True,
    )
    if o25:
        decisions.append(o25)

    o35 = _classify_candidate(
        bet_type="arahus_o35",
        label="Over 3.5 (watch)",
        model_pct=proj.get("over_3_5_pct"),
        odds=odds.get("over_3_5"),
        signals=_overs_signals(profile, proj, for_o35=True),
        live_market=False,
    )
    if o35:
        decisions.append(o35)

    # Rank eligible v2A O2.5 by EV → edge → confidence (at most one live pick).
    live_candidates = [d for d in decisions if d.get("eligible_v2A") and d["bet_type"] == "arahus_o25"]
    live_candidates.sort(
        key=lambda p: (p.get("ev") or -99, p.get("edge") or -99, p.get("confidence") or 0),
        reverse=True,
    )
    picks: list[dict[str, Any]] = []
    if live_candidates:
        chosen = live_candidates[0]
        chosen["status"] = "picked"
        chosen["units"] = FLAT_STAKE
        chosen["stake"] = FLAT_STAKE
        chosen["skip_reason"] = SKIP_ELIGIBLE
        picks.append(chosen)
        for d in live_candidates[1:]:
            d["skip_reason"] = SKIP_NOT_SELECTED
            d["status"] = "skipped"

    for d in decisions:
        d["fixture_id"] = profile.get("fixture_id")
        d["fixture"] = profile.get("fixture")
        d["fixture_date"] = profile.get("fixture_date")
        d["league_name"] = profile.get("league_name")
        d["home_team"] = profile.get("home_team")
        d["away_team"] = profile.get("away_team")
        d["archetype"] = proj.get("archetype")

    return {
        "fixture_id": profile.get("fixture_id"),
        "fixture": profile.get("fixture"),
        "fixture_date": profile.get("fixture_date"),
        "league_name": profile.get("league_name"),
        "home_team": profile.get("home_team"),
        "away_team": profile.get("away_team"),
        "projections": proj,
        "profile": profile,
        "decisions": decisions,
        "picks": picks,
        "has_picks": bool(picks),
        "top_confidence": picks[0]["confidence"] if picks else 0,
        "engine_version": ENGINE_VERSION,
    }


def build_arahus_v2_slate(state: dict[str, Any]) -> list[dict[str, Any]]:
    fixtures_by_id = state.get("fixtures_by_id") or {}
    indexes = state.get("dg_extra_indexes") or {}
    matches_by_id = {
        str(m.get("fixture_id")): m for m in (state.get("matches") or []) if m.get("fixture_id")
    }
    ids = [str(m.get("fixture_id")) for m in (state.get("matches") or []) if m.get("fixture_id")]
    if not ids:
        ids = list(fixtures_by_id.keys())

    cards: list[dict[str, Any]] = []
    for fid in ids:
        raw = find_raw_fixture(fixtures_by_id, fid)
        if not raw:
            continue
        match = matches_by_id.get(str(fid))
        extra = lookup_extra_for_fixture(raw, indexes, include_player_sims=False) if indexes else {}
        try:
            cards.append(evaluate_fixture_v2(raw, match, extra))
        except Exception:
            continue

    cards.sort(
        key=lambda c: (str(c.get("fixture_date") or "9999"), str(c.get("fixture") or ""))
    )
    return cards


def flatten_picks(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in cards:
        for p in c.get("picks") or []:
            row = dict(p)
            row.setdefault("fixture_id", c.get("fixture_id"))
            row.setdefault("fixture", c.get("fixture"))
            row.setdefault("fixture_date", c.get("fixture_date"))
            row.setdefault("league_name", c.get("league_name"))
            row.setdefault("home_team", c.get("home_team"))
            row.setdefault("away_team", c.get("away_team"))
            row.setdefault("archetype", (c.get("projections") or {}).get("archetype"))
            out.append(row)
    out.sort(
        key=lambda p: (
            -(p.get("ev") or -99),
            -(p.get("edge") or -99),
            -(p.get("confidence") or 0),
            str(p.get("fixture_date") or "9999"),
        )
    )
    return out


def build_report_rows_from_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cfg = engine_config_snapshot()
    now = _now_iso()
    rows: list[dict[str, Any]] = []
    for card in cards:
        proj = card.get("projections") if isinstance(card.get("projections"), dict) else {}
        for d in card.get("decisions") or []:
            signals = d.get("signals") or []
            signal_strs = [
                str(s.get("detail") or s.get("name") or "")
                for s in signals
                if isinstance(s, dict)
            ]
            status = "picked" if d.get("status") == "picked" else "skipped"
            rows.append(
                {
                    "fixture_id": str(card.get("fixture_id") or "") or None,
                    "synced_at": now,
                    "match_date": card.get("fixture_date"),
                    "league": card.get("league_name") or "",
                    "home_team": card.get("home_team") or "",
                    "away_team": card.get("away_team") or "",
                    "fixture": card.get("fixture") or "",
                    "bet_type": d.get("bet_type") or "",
                    "market": d.get("bet_type") or "",
                    "team_name": d.get("team_name") or "",
                    "status": status,
                    "model_pct": d.get("model_pct"),
                    "confidence": d.get("confidence"),
                    "odds": d.get("odds"),
                    "implied_pct": d.get("implied_pct"),
                    "edge_pct": d.get("edge"),
                    "ev": d.get("ev"),
                    "stake": d.get("stake") if status == "picked" else 0.0,
                    "eligible_v2A": bool(d.get("eligible_v2A")),
                    "eligible_v2B": bool(d.get("eligible_v2B")),
                    "eligible_secondary": bool(d.get("eligible_secondary")),
                    "skip_reason": d.get("skip_reason") or "",
                    "signals": signal_strs,
                    "xg_home": proj.get("home_xg"),
                    "xg_away": proj.get("away_xg"),
                    "xg_total": proj.get("total_xg"),
                    "pace_score": proj.get("pace"),
                    "nec_index": proj.get("nec"),
                    "agix_index": proj.get("agix"),
                    "dgrtg_gap": proj.get("dgrtg_gap"),
                    "archetype": proj.get("archetype"),
                    "engine_config_snapshot": cfg,
                    "engine_version": ENGINE_VERSION,
                    "result": None,
                    "pnl": None,
                    "resolved_at": None,
                }
            )
    return rows


def load_arahus_v2_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def sync_arahus_v2_bets(
    picks: list[dict[str, Any]],
    *,
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for p in picks:
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": p.get("bet_type") or "arahus_o25",
                "team_name": p.get("team_name") or "",
                "qualifier_pct": p.get("confidence"),
                "odds": p.get("odds"),
                "units": FLAT_STAKE,
                "status": "open",
                "pnl_units": None,
            }
        )
    inserted = insert_bets(LOG_TYPE, candidates)
    report_rows = build_report_rows_from_cards(cards or [])
    report_inserted = insert_arahus_v2_report_log(report_rows)
    return {
        "inserted": inserted,
        "report_log_inserted": report_inserted,
        "total": len(load_arahus_v2_bet_log()),
        "report_log_total": len(list_arahus_v2_report_log()),
    }


def ensure_arahus_v2_report_from_slate() -> int:
    """If report log empty, score current slate once (export helper)."""
    existing = list_arahus_v2_report_log()
    if existing:
        return 0
    from app.db import load_state

    state = load_state(
        "latest_data",
        {"scraped_at": None, "matches": [], "fixtures_by_id": {}, "dg_extra_indexes": {}},
    )
    cards = build_arahus_v2_slate(state)
    rows = build_report_rows_from_cards(cards)
    return insert_arahus_v2_report_log(rows)


def resolve_arahus_v2_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")
    entry = next((e for e in load_arahus_v2_bet_log() if e.get("id") == bet_id), None)
    if not entry:
        raise ValueError("Bet not found.")
    odds = float(entry.get("odds") or 0)
    units = float(entry.get("units") or FLAT_STAKE)
    if result == "won":
        pnl = round((odds - 1) * units, 3) if odds > 0 else round(1.0 * units, 3)
    elif result == "lost":
        pnl = round(-1.0 * units, 3)
    else:
        pnl = 0.0
    updated = resolve_bet_entry(LOG_TYPE, bet_id, result, pnl, _now_iso())
    if not updated:
        raise ValueError("Bet not found.")
    return updated


def arahus_v2_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    stats = compute_bet_stats(entries)
    by_type: dict[str, dict[str, Any]] = {}
    for bt in sorted({str(e.get("bet_type") or "") for e in entries} - {""}):
        subset = [e for e in entries if e.get("bet_type") == bt]
        row = compute_bet_stats(subset)
        row["bet_type"] = bt
        row["label"] = BET_LABELS.get(bt, bt)
        by_type[bt] = row

    # Report-log counterfactual tallies (latest sync snapshot style: all rows).
    report = list_arahus_v2_report_log()
    v2a = [r for r in report if r.get("eligible_v2A")]
    v2b = [r for r in report if r.get("eligible_v2B")]
    return {
        **stats,
        "by_type": by_type,
        "report": {
            "rows": len(report),
            "eligible_v2A": len(v2a),
            "eligible_v2B": len(v2b),
            "picked": sum(1 for r in report if r.get("status") == "picked"),
        },
    }


def enrich_arahus_v2_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in entries:
        row = dict(e)
        bt = str(row.get("bet_type") or "")
        row["market_label"] = BET_LABELS.get(bt, bt)
        conf = num(row.get("qualifier_pct"))
        row["confidence_fmt"] = f"{conf:.0f}" if conf is not None else "—"
        out.append(row)
    return out
