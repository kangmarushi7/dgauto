"""
Live research collector — records +EV qualifying signals WITHOUT placing bets.

Uses read-only access to latest DG state / plus_ev pick builder.
Never calls insert_bets or production sync.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research.plus_ev_forward_test.clv import clv_from_odds
from research.plus_ev_forward_test.fair_market import fair_from_outcome_odds, fair_probability_for_selection
from research.plus_ev_forward_test.portfolios import portfolio_membership
from research.plus_ev_forward_test.storage import (
    DEFAULT_DATA_DIR,
    append_jsonl,
    load_signals,
    make_signal,
    snapshots_path,
    upsert_signals,
)

# Map bet_type -> book_odds keys for opposite / full market when available on fixture.
OUTCOME_KEYS: dict[str, list[tuple[str, str]]] = {
    "over2.5": [("over", "over_2_5"), ("under", "under_2_5")],
    "over3.5": [("over", "over_3_5"), ("under", "under_3_5")],
    "over1.5": [("over", "over_1_5"), ("under", "under_1_5")],
    "under2.5": [("under", "under_2_5"), ("over", "over_2_5")],
    "btts": [("yes", "btts_yes"), ("no", "btts_no")],
    "moneyline": [("home", "home_win"), ("draw", "draw"), ("away", "away_win")],
    "draw": [("home", "home_win"), ("draw", "draw"), ("away", "away_win")],
    "dc_1x": [("dc_1x", "dc_home_draw"), ("dc_x2", "dc_draw_away"), ("dc_12", "dc_home_away")],
    "dc_x2": [("dc_1x", "dc_home_draw"), ("dc_x2", "dc_draw_away"), ("dc_12", "dc_home_away")],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _book_from_state(state: dict[str, Any], fixture_id: Any) -> dict[str, Any]:
    fixtures = state.get("fixtures_by_id") or {}
    raw = fixtures.get(str(fixture_id)) or fixtures.get(fixture_id) or {}
    book = raw.get("book_odds") if isinstance(raw.get("book_odds"), dict) else {}
    return book or {}


def _outcome_odds_for_pick(bet_type: str, book: dict[str, Any]) -> dict[str, float]:
    keys = OUTCOME_KEYS.get(str(bet_type).lower(), [])
    out: dict[str, float] = {}
    for label, key in keys:
        val = book.get(key)
        try:
            o = float(val) if val is not None else None
        except (TypeError, ValueError):
            o = None
        if o and o > 1:
            out[label] = o
    return out


def _opposite_odds(bet_type: str, book: dict[str, Any]) -> float | None:
    bt = str(bet_type).lower()
    mapping = {
        "over2.5": "under_2_5",
        "over3.5": "under_3_5",
        "over1.5": "under_1_5",
        "under2.5": "over_2_5",
        "btts": "btts_no",
    }
    key = mapping.get(bt)
    if not key:
        return None
    try:
        o = float(book.get(key)) if book.get(key) is not None else None
    except (TypeError, ValueError):
        return None
    return o if o and o > 1 else None


def _signal_dedupe_key(pick: dict[str, Any]) -> str:
    return "|".join(
        [
            str(pick.get("fixture_id") or ""),
            str(pick.get("bet_type") or ""),
            str(pick.get("market") or ""),
            str(pick.get("team_name") or ""),
            str(pick.get("fixture_date") or "")[:16],
        ]
    )


def collect_from_live_state(data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
    """
    Build current +EV picks and append new research signals for matching portfolios.
    Read-only vs production bet log.
    """
    from app.dg_state import read_latest  # type: ignore
    from app.plus_ev_strat import build_plus_ev_picks

    state = read_latest()
    picks = build_plus_ev_picks(state)
    existing = load_signals(data_dir)
    seen = {
        _signal_dedupe_key(
            {
                "fixture_id": s.get("fixture_id"),
                "bet_type": s.get("bet_type"),
                "market": s.get("market"),
                "team_name": s.get("selection"),
                "fixture_date": s.get("kickoff_time"),
            }
        )
        for s in existing
        if s.get("sample_kind") == "live_forward"
    }

    new_rows: list[dict[str, Any]] = []
    for p in picks:
        odds = p.get("odds")
        try:
            odds_f = float(odds) if odds is not None else None
        except (TypeError, ValueError):
            odds_f = None
        if not odds_f or odds_f <= 1:
            continue
        # Production market EV is percentage points (e.g. 10.2 => 10.2%).
        try:
            ev_raw = float(p.get("ev"))
            ev_f = ev_raw / 100.0 if abs(ev_raw) > 1.5 else ev_raw
        except (TypeError, ValueError):
            continue
        model_p = (1.0 + ev_f) / odds_f
        book = _book_from_state(state, p.get("fixture_id"))
        outcome_odds = _outcome_odds_for_pick(str(p.get("bet_type") or ""), book)
        fair_info = fair_from_outcome_odds(outcome_odds)
        bt = str(p.get("bet_type") or "").lower()
        sel_key = (
            "over"
            if bt.startswith("over")
            else "under"
            if bt.startswith("under")
            else "yes"
            if bt == "btts"
            else None
        )
        fair_p = fair_probability_for_selection(sel_key or "", outcome_odds) if sel_key else None
        if fair_p is None and fair_info.get("fair_available") and len(outcome_odds) == 2 and sel_key:
            fair_p = (fair_info["fair_probabilities"] or {}).get(sel_key)

        draft = {
            "bet_type": p.get("bet_type"),
            "market": p.get("market"),
            "league": p.get("league_name"),
            "odds_at_signal": odds_f,
        }
        portfolios = portfolio_membership(draft)
        if not portfolios:
            continue
        dedupe = _signal_dedupe_key(p)
        if dedupe in seen:
            continue

        signal = make_signal(
            fixture_id=p.get("fixture_id"),
            kickoff_time=p.get("fixture_date"),
            timestamp_signal_created=_now(),
            league=p.get("league_name"),
            market=p.get("market"),
            bet_type=p.get("bet_type"),
            selection=p.get("team_name") or p.get("market"),
            bookmaker="datagaffer",
            odds_at_signal=odds_f,
            model_probability=model_p,
            raw_EV=ev_f,
            calibrated_probability=None,
            calibrated_EV=None,
            result="open",
            pnl_units=None,
            opposite_odds=_opposite_odds(str(p.get("bet_type") or ""), book),
            outcome_odds=outcome_odds,
            fair_probability=fair_p,
            fair_market_edge=(model_p - fair_p) if fair_p is not None else None,
            odds_timestamp=_now(),
            closing_odds=None,
            sample_kind="live_forward",
            source="live_state_collect",
            portfolios=portfolios,
            notes=[
                "research_only=true",
                "can_place_real_bet=false",
                f"fixture={p.get('fixture')}",
            ],
        )
        # Keep fixture name for settlement joins
        signal["fixture"] = p.get("fixture")
        new_rows.append(signal)
        seen.add(dedupe)

    stats = upsert_signals(data_dir, new_rows)
    stats["new_candidates"] = len(new_rows)
    return stats


def snapshot_pre_kickoff_odds(data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
    """
    For open live_forward signals whose kickoff is soon/past, record latest book odds
    as closing_odds if still null. Minimum requirement: signal odds + latest before kickoff.
    """
    from app.dg_state import read_latest

    state = read_latest()
    signals = load_signals(data_dir)
    snap_rows: list[dict[str, Any]] = []
    updated = 0
    now = datetime.now(timezone.utc)

    for s in signals:
        if s.get("sample_kind") != "live_forward":
            continue
        if s.get("closing_odds") is not None:
            continue
        if not s.get("fixture_id"):
            continue
        kickoff = s.get("kickoff_time")
        try:
            kd = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
        except Exception:
            kd = None
        # Capture whenever we are within 24h of kickoff or past kickoff without close.
        if kd is not None and kd.tzinfo and (kd - now).total_seconds() > 24 * 3600:
            continue
        book = _book_from_state(state, s.get("fixture_id"))
        outcome_odds = _outcome_odds_for_pick(str(s.get("bet_type") or ""), book)
        # Prefer selection price from outcome map / primary odds key
        price = None
        bt = str(s.get("bet_type") or "").lower()
        primary = {
            "over2.5": "over_2_5",
            "over3.5": "over_3_5",
            "over1.5": "over_1_5",
            "under2.5": "under_2_5",
            "btts": "btts_yes",
            "moneyline": "home_win",
            "draw": "draw",
            "dc_1x": "dc_home_draw",
            "dc_x2": "dc_draw_away",
        }.get(bt)
        if primary and book.get(primary) is not None:
            try:
                price = float(book.get(primary))
            except (TypeError, ValueError):
                price = None
        if price is None and outcome_odds:
            price = next(iter(outcome_odds.values()), None)
        snap = {
            "research_only": True,
            "signal_id": s.get("signal_id"),
            "fixture_id": s.get("fixture_id"),
            "snapshot_at": _now(),
            "odds": price,
            "outcome_odds": outcome_odds,
            "horizon": "latest_before_or_near_kickoff",
        }
        snap_rows.append(snap)
        if price and price > 1:
            s["closing_odds"] = price
            s["closing_odds_timestamp"] = _now()
            clv = clv_from_odds(float(s.get("odds_at_signal") or 0), price)
            s["clv"] = clv.get("clv")
            if outcome_odds:
                s["outcome_odds"] = outcome_odds
                s["opposite_odds"] = _opposite_odds(bt, book)
                fair_p = fair_probability_for_selection(
                    "over" if bt.startswith("over") else ("yes" if bt == "btts" else ""),
                    outcome_odds,
                )
                s["fair_probability"] = fair_p
                if fair_p is not None and s.get("model_probability") is not None:
                    s["fair_market_edge"] = float(s["model_probability"]) - float(fair_p)
            updated += 1

    if snap_rows:
        append_jsonl(snapshots_path(data_dir), snap_rows)
    upsert_signals(data_dir, signals)
    return {"snapshots": len(snap_rows), "signals_updated_closing": updated}
