from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from app.bet_log import compute_bet_stats
from app.db import insert_bets, list_bets, resolve_bet_entry


LOG_TYPE = "no"


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_side(
    match: dict[str, Any],
    *,
    side: str,
    team_name: str,
    win_pct: float | None,
    projected_goals: float | None,
    odds: Any,
) -> dict[str, Any] | None:
    if not team_name or win_pct is None or projected_goals is None:
        return None
    if win_pct >= 50.0 or projected_goals >= 1.0:
        return None

    if side == "home":
        bet_type = f"{team_name} not to win (X2)"
        protection = "Draw or Away"
        opponent = match.get("away_team", "")
    else:
        bet_type = f"{team_name} not to win (1X)"
        protection = "Home or Draw"
        opponent = match.get("home_team", "")

    return {
        "fixture_id": match.get("fixture_id"),
        "fixture_date": match.get("fixture_date"),
        "fixture": match.get("fixture", ""),
        "league_name": match.get("league_name", ""),
        "team": team_name,
        "opponent": opponent,
        "side": side,
        "bet_type": bet_type,
        "protection": protection,
        "win_pct": round(win_pct, 1),
        "not_win_pct": round(100.0 - win_pct, 1),
        "projected_goals": round(projected_goals, 2),
        "odds": odds,
    }


def build_no_strat_picks(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find teams to oppose when win chance and team goal projection are both low."""
    picks: list[dict[str, Any]] = []
    for match in matches:
        home_pick = _pick_side(
            match,
            side="home",
            team_name=str(match.get("home_team") or ""),
            win_pct=_float_or_none(match.get("win_pct")),
            projected_goals=_float_or_none(match.get("home_projected_goals")),
            odds=match.get("dc_draw_away_odds"),
        )
        away_pick = _pick_side(
            match,
            side="away",
            team_name=str(match.get("away_team") or ""),
            win_pct=_float_or_none(match.get("away_win_pct")),
            projected_goals=_float_or_none(match.get("away_projected_goals")),
            odds=match.get("dc_home_draw_odds"),
        )
        if home_pick:
            picks.append(home_pick)
        if away_pick:
            picks.append(away_pick)

    picks.sort(
        key=lambda x: (
            x.get("not_win_pct", 0),
            1.0 - float(x.get("projected_goals") or 0),
            -float(x.get("win_pct") or 0),
        ),
        reverse=True,
    )
    return picks


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_no_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def sync_no_bets(picks: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for p in picks:
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": "not_win",
                "team_name": p.get("team", ""),
                "qualifier_pct": p.get("not_win_pct"),
                "odds": p.get("odds"),
                "units": 1.0,
                "status": "open",
                "pnl_units": None,
            }
        )
    inserted = insert_bets(LOG_TYPE, candidates)
    return {"inserted": inserted, "total": len(load_no_bet_log())}


def resolve_no_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entries = load_no_bet_log()
    entry = next((e for e in entries if e.get("id") == bet_id), None)
    if not entry:
        raise ValueError("Bet not found.")
    odds = float(entry.get("odds") or 0)
    units = float(entry.get("units") or 1)
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


def no_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return compute_bet_stats(entries)
