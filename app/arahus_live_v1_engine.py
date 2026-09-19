"""Arahus Live Candidate V1 — frozen forward-validation filter.

Isolated from Arahus v1 (multi-market) and Arahus v2 (conf/edge gates).

Frozen rules (do NOT change from OOS outcomes):
- Market: Over 2.5 ONLY
- Odds: 1.30 <= odds <= 1.49 inclusive (no rounding)
- League: unrestricted (no whitelist)
- Confidence: calculated and logged; NOT a qualification gate
- BTTS / O3.5 / other markets: excluded
- Stake: existing Arahus v1 ladder (0.75 / 1.0 / 1.5) — no new money management

Qualification is exactly:
    market == Over 2.5 AND odds is not None AND 1.30 <= odds <= 1.49
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid
from typing import Any

from app.bet_log import compute_bet_stats
from app.arahus_engine import (
    _clamp,
    build_fixture_profile,
    project_match,
)
from app.arahus_v2_engine import _overs_signals
from app.db import (
    insert_arahus_live_v1_decision_log,
    insert_bets,
    list_arahus_live_v1_decision_log,
    list_bets,
    resolve_bet_entry,
)
from app.dg_feeds import lookup_extra_for_fixture
from app.fixture_detail import find_raw_fixture
from app.fixture_math import edge as calc_edge
from app.fixture_math import expected_value_pct, implied_prob, num

LOG_TYPE = "arahus_live_v1"
ENGINE_VERSION = "arahus-live-v1"
STRATEGY_LABEL = "Arahus Live V1"

# Single configuration object — do not scatter magic numbers.
ARAHUS_LIVE_V1: dict[str, Any] = {
    "strategy_version": ENGINE_VERSION,
    "label": STRATEGY_LABEL,
    "market": "Over 2.5",
    "bet_type": "arahus_o25",
    "odds_min": float(os.getenv("ARAHUS_LIVE_V1_ODDS_MIN", "1.30")),
    "odds_max": float(os.getenv("ARAHUS_LIVE_V1_ODDS_MAX", "1.49")),
    "league_whitelist": None,  # unrestricted — do NOT invent leagues
    "confidence_min": None,  # informational only
    "btts": False,
    "over_3_5": False,
    "stake_mode": "arahus_v1_ladder",
}

# Safety: auto-sync / scheduler inclusion. Manual UI sync still allowed when false.
ENABLED = os.getenv("ARAHUS_LIVE_V1_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

ODDS_MIN = float(ARAHUS_LIVE_V1["odds_min"])
ODDS_MAX = float(ARAHUS_LIVE_V1["odds_max"])

BET_LABELS = {"arahus_o25": "Over 2.5"}

# Deterministic rejection reasons (never generic "not eligible")
REJECT_MARKET = "market_not_o25"
REJECT_MISSING_ODDS = "missing_odds"
REJECT_ODDS_BELOW = "odds_below_min"
REJECT_ODDS_ABOVE = "odds_above_max"
REJECT_INVALID_ODDS = "invalid_odds"
QUALIFIED = "qualified"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def engine_config_snapshot() -> dict[str, Any]:
    return {
        **ARAHUS_LIVE_V1,
        "enabled_auto_sync": ENABLED,
        "engine_version": ENGINE_VERSION,
        "oos_reference": {
            "period": "2026-09-01 → 2026-09-19",
            "n": 62,
            "pnl_units": 4.231,
            "roi": 0.0776,
            "note": "Historical OOS validation — not a guarantee of future performance",
        },
    }


def stake_units_arahus_v1_ladder(confidence: float, edge: float | None) -> float:
    """Existing Arahus v1 stake sizing (not a qualification gate)."""
    units = 1.0
    if confidence >= 78 and (edge or 0) >= 5:
        units = 1.5
    elif confidence < 68:
        units = 0.75
    return float(units)


def qualifies_for_arahus_live_v1(
    *,
    market: str | None = None,
    bet_type: str | None = None,
    odds: float | None,
) -> tuple[bool, str]:
    """
    Exact frozen gate. Confidence and league are intentionally ignored.
    Odds are compared without rounding.
    """
    label = str(market or "").strip().lower()
    bt = str(bet_type or "").strip().lower()
    is_o25 = (
        bt == "arahus_o25"
        or label in {"over 2.5", "o2.5", "over2.5"}
        or (label == ARAHUS_LIVE_V1["market"].lower())
    )
    if not is_o25:
        return False, REJECT_MARKET
    if odds is None:
        return False, REJECT_MISSING_ODDS
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return False, REJECT_INVALID_ODDS
    if o != o or o <= 1.0:  # NaN / impossible
        return False, REJECT_INVALID_ODDS
    if o < ODDS_MIN:
        return False, REJECT_ODDS_BELOW
    if o > ODDS_MAX:
        return False, REJECT_ODDS_ABOVE
    return True, QUALIFIED


def _build_o25_decision(
    profile: dict[str, Any],
    proj: dict[str, Any],
    *,
    signal_timestamp: str,
) -> dict[str, Any]:
    odds_raw = (profile.get("odds") or {}).get("over_2_5")
    odds = num(odds_raw) if odds_raw is not None else None
    model_pct = proj.get("over_2_5_pct")
    signals = _overs_signals(profile, proj, for_o35=False)
    confidence = round(sum(float(s.get("weight") or 0) for s in signals), 1)
    confidence = _clamp(confidence, 0.0, 100.0)
    if model_pct is None:
        # Still allow odds-only qualification; confidence stays from signals (may be 0).
        model_pct_f = None
        edge_val = None
        ev_val = None
    else:
        model_pct_f = float(model_pct)
        edge_val = calc_edge(model_pct_f, odds)
        ev_val = expected_value_pct(model_pct_f, odds)

    ok, reason = qualifies_for_arahus_live_v1(
        market="Over 2.5",
        bet_type="arahus_o25",
        odds=odds,
    )
    units = stake_units_arahus_v1_ladder(confidence, edge_val) if ok else None
    return {
        "strategy_version": ENGINE_VERSION,
        "bet_type": "arahus_o25",
        "market_label": "Over 2.5",
        "market": "Over 2.5",
        "team_name": "",
        "model_pct": round(model_pct_f, 1) if model_pct_f is not None else None,
        "odds": odds,
        "entry_odds": odds,
        "implied_pct": implied_prob(odds),
        "edge": edge_val,
        "ev": ev_val,
        "confidence": confidence,
        "signals": signals,
        "signal_summary": " · ".join(s["detail"] for s in signals[:4]),
        "qualification_result": bool(ok),
        "rejection_reason": None if ok else reason,
        "decision": "BET" if ok else "SKIP",
        "skip_reason": QUALIFIED if ok else reason,
        "units": units,
        "stake": units,
        "status": "picked" if ok else "skipped",
        "signal_timestamp": signal_timestamp,
        "closing_odds": None,
        "closing_timestamp": None,
        "clv": None,
        "odds_source": "datagaffer",
        "bookmaker": "datagaffer",
        "league_whitelist_applied": False,
        "confidence_gate_applied": False,
    }


def evaluate_fixture_live_v1(
    raw: dict[str, Any],
    match: dict[str, Any] | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    signal_timestamp = _now_iso()
    profile = build_fixture_profile(raw, match, extra)
    proj = project_match(profile)
    decision = _build_o25_decision(profile, proj, signal_timestamp=signal_timestamp)
    for key in (
        "fixture_id",
        "fixture",
        "fixture_date",
        "league_name",
        "home_team",
        "away_team",
    ):
        decision[key] = profile.get(key)
    decision["kickoff_timestamp"] = profile.get("fixture_date")
    decision["archetype"] = proj.get("archetype")

    picks = [decision] if decision.get("qualification_result") else []
    return {
        "fixture_id": profile.get("fixture_id"),
        "fixture": profile.get("fixture"),
        "fixture_date": profile.get("fixture_date"),
        "league_name": profile.get("league_name"),
        "home_team": profile.get("home_team"),
        "away_team": profile.get("away_team"),
        "projections": proj,
        "profile": profile,
        "decisions": [decision],
        "picks": picks,
        "has_picks": bool(picks),
        "top_confidence": picks[0]["confidence"] if picks else 0,
        "engine_version": ENGINE_VERSION,
        "signal_timestamp": signal_timestamp,
    }


def build_arahus_live_v1_slate(state: dict[str, Any]) -> list[dict[str, Any]]:
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
            cards.append(evaluate_fixture_live_v1(raw, match, extra))
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
            out.append(row)
    out.sort(
        key=lambda p: (
            str(p.get("fixture_date") or "9999"),
            -(p.get("confidence") or 0),
            str(p.get("fixture") or ""),
        )
    )
    return out


def build_decision_rows_from_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cfg = engine_config_snapshot()
    rows: list[dict[str, Any]] = []
    for card in cards:
        for d in card.get("decisions") or []:
            signals = d.get("signals") or []
            signal_strs = [
                str(s.get("detail") or s.get("name") or "")
                for s in signals
                if isinstance(s, dict)
            ]
            rows.append(
                {
                    "strategy_version": ENGINE_VERSION,
                    "fixture_id": str(card.get("fixture_id") or "") or None,
                    "signal_timestamp": d.get("signal_timestamp") or card.get("signal_timestamp") or _now_iso(),
                    "kickoff_timestamp": d.get("kickoff_timestamp") or card.get("fixture_date"),
                    "synced_at": _now_iso(),
                    "match_date": card.get("fixture_date"),
                    "league": card.get("league_name") or "",
                    "home_team": card.get("home_team") or "",
                    "away_team": card.get("away_team") or "",
                    "fixture": card.get("fixture") or "",
                    "bet_type": d.get("bet_type") or "arahus_o25",
                    "market": d.get("market_label") or "Over 2.5",
                    "team_name": d.get("team_name") or "",
                    "confidence": d.get("confidence"),
                    "entry_odds": d.get("entry_odds") if d.get("entry_odds") is not None else d.get("odds"),
                    "odds": d.get("odds"),
                    "odds_source": d.get("odds_source") or "datagaffer",
                    "bookmaker": d.get("bookmaker") or "datagaffer",
                    "qualification_result": bool(d.get("qualification_result")),
                    "rejection_reason": d.get("rejection_reason"),
                    "decision": d.get("decision") or ("BET" if d.get("qualification_result") else "SKIP"),
                    "stake": d.get("stake"),
                    "units": d.get("units"),
                    "model_pct": d.get("model_pct"),
                    "implied_pct": d.get("implied_pct"),
                    "edge_pct": d.get("edge"),
                    "ev": d.get("ev"),
                    "status": d.get("status") or "skipped",
                    "signals": signal_strs,
                    "closing_odds": d.get("closing_odds"),
                    "closing_timestamp": d.get("closing_timestamp"),
                    "clv": d.get("clv"),
                    "engine_config_snapshot": cfg,
                    "engine_version": ENGINE_VERSION,
                    "result": None,
                    "pnl": None,
                    "flat_1u_pnl": None,
                    "resolved_at": None,
                }
            )
    return rows


def load_arahus_live_v1_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def sync_arahus_live_v1_bets(
    picks: list[dict[str, Any]],
    *,
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Insert qualifying bets into isolated log_type=arahus_live_v1.

    Dedup: insert_bets skips rows with the same
    (fixture_date, fixture, bet_type, team_name) within this log_type.
    A later scan with odds still in-band does NOT create a duplicate bet.
    A fixture that was out-of-band and later enters the band can insert once
    (no prior key). Odds changes inside the band do not create a second row.
    """
    candidates: list[dict[str, Any]] = []
    for p in picks:
        units = p.get("units")
        if units is None:
            units = stake_units_arahus_v1_ladder(
                float(p.get("confidence") or 0),
                p.get("edge"),
            )
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": p.get("signal_timestamp") or _now_iso(),
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": p.get("bet_type") or "arahus_o25",
                "team_name": p.get("team_name") or "",
                "qualifier_pct": p.get("confidence"),
                "odds": p.get("entry_odds") if p.get("entry_odds") is not None else p.get("odds"),
                "units": float(units),
                "status": "open",
                "pnl_units": None,
            }
        )
    inserted = insert_bets(LOG_TYPE, candidates)
    decision_rows = build_decision_rows_from_cards(cards or [])
    decision_inserted = insert_arahus_live_v1_decision_log(decision_rows)
    return {
        "inserted": inserted,
        "decision_log_inserted": decision_inserted,
        "total": len(load_arahus_live_v1_bet_log()),
        "decision_log_total": len(list_arahus_live_v1_decision_log()),
        "enabled_auto_sync": ENABLED,
        "engine_version": ENGINE_VERSION,
    }


def resolve_arahus_live_v1_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")
    entry = next((e for e in load_arahus_live_v1_bet_log() if e.get("id") == bet_id), None)
    if not entry:
        raise ValueError("Bet not found.")
    odds = float(entry.get("odds") or 0)
    units = float(entry.get("units") or 1.0)
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


def enrich_arahus_live_v1_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in entries:
        conf = e.get("qualifier_pct")
        row = {
            **e,
            "market_label": BET_LABELS.get(str(e.get("bet_type") or ""), e.get("bet_type")),
            "confidence_fmt": f"{float(conf):.0f}" if conf is not None else "—",
            "strategy_version": ENGINE_VERSION,
        }
        # Research helper: flat 1u PnL without changing execution stake
        status = str(e.get("status") or "").lower()
        odds = e.get("odds")
        if status in {"won", "lost", "push"} and odds is not None:
            o = float(odds)
            if status == "won":
                row["flat_1u_pnl"] = round(o - 1.0, 3)
            elif status == "lost":
                row["flat_1u_pnl"] = -1.0
            else:
                row["flat_1u_pnl"] = 0.0
        else:
            row["flat_1u_pnl"] = None
        out.append(row)
    return out


def _max_drawdown_units(entries: list[dict[str, Any]]) -> float:
    settled = [e for e in entries if e.get("status") in {"won", "lost", "push"}]
    settled = sorted(settled, key=lambda e: str(e.get("fixture_date") or e.get("created_at") or ""))
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for e in settled:
        equity += float(e.get("pnl_units") or 0.0)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 3)


def arahus_live_v1_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    stats = compute_bet_stats(entries)
    open_n = sum(1 for e in entries if str(e.get("status") or "").lower() == "open")
    decided = int(stats.get("won") or 0) + int(stats.get("lost") or 0)
    staked = round(
        sum(float(e.get("units") or 0) for e in entries if e.get("status") in {"won", "lost", "push"}),
        3,
    )
    pnl = float(stats.get("unit_pnl") or 0.0)
    roi = (pnl / staked) if staked else None
    decisions = list_arahus_live_v1_decision_log()
    qualified = sum(1 for d in decisions if d.get("qualification_result"))
    rejected = sum(1 for d in decisions if not d.get("qualification_result"))
    return {
        **stats,
        "open": open_n,
        "signals": len(decisions),
        "qualified": qualified,
        "rejected": rejected,
        "staked": staked,
        "roi": roi,
        "max_drawdown": _max_drawdown_units(entries),
        "engine_version": ENGINE_VERSION,
        "config": engine_config_snapshot(),
        "by_type": {
            "arahus_o25": {
                **compute_bet_stats([e for e in entries if e.get("bet_type") == "arahus_o25"]),
                "bet_type": "arahus_o25",
                "label": "Over 2.5",
            }
        },
    }
