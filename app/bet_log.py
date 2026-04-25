from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from app.db import insert_bets, list_bets, resolve_bet_entry

LOG_TYPE = "main"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def _make_moneyline_bets(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for m in matches:
        home_win = float(m.get("win_pct") or 0)
        away_win = float(m.get("away_win_pct") or 0)
        if home_win <= 61 and away_win <= 61:
            continue

        if home_win >= away_win:
            team = m.get("home_team") or ""
            win_pct = home_win
            odds = m.get("home_ml_odds")
        else:
            team = m.get("away_team") or ""
            win_pct = away_win
            odds = m.get("away_ml_odds")

        bets.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": m.get("fixture_date"),
                "fixture": m.get("fixture", ""),
                "league_name": m.get("league_name", ""),
                "bet_type": "moneyline",
                "team_name": team,
                "qualifier_pct": round(win_pct, 1),
                "odds": odds,
                "units": 1.0,
                "status": "open",
                "pnl_units": None,
            }
        )
    return bets


def _make_over15_bets(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for m in matches:
        proj = float(m.get("projected_total_goals") or 0)
        if proj < 3.51:
            continue
        bets.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": m.get("fixture_date"),
                "fixture": m.get("fixture", ""),
                "league_name": m.get("league_name", ""),
                "bet_type": "over1.5",
                "team_name": "",
                "qualifier_pct": round(proj, 2),
                "odds": m.get("over_1_5_odds"),
                "units": 1.0,
                "status": "open",
                "pnl_units": None,
            }
        )
    return bets


def sync_recommended_bets(matches: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = _make_moneyline_bets(matches) + _make_over15_bets(matches)
    inserted = insert_bets(LOG_TYPE, candidates)
    return {"inserted": inserted, "total": len(load_bet_log())}


def resolve_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entries = load_bet_log()
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


def _compute_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    placed = len(entries)
    won = sum(1 for e in entries if e.get("status") == "won")
    lost = sum(1 for e in entries if e.get("status") == "lost")
    pushes = sum(1 for e in entries if e.get("status") == "push")
    decided = won + lost
    win_pct = round((won / decided) * 100, 1) if decided else 0.0
    pnl = round(sum(float(e.get("pnl_units") or 0.0) for e in entries), 3)
    return {
        "placed": placed,
        "won": won,
        "lost": lost,
        "push": pushes,
        "win_pct": win_pct,
        "unit_pnl": pnl,
    }


def bet_log_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    moneyline = [e for e in entries if e.get("bet_type") == "moneyline"]
    over15 = [e for e in entries if e.get("bet_type") == "over1.5"]
    return {
        "all": _compute_stats(entries),
        "moneyline": _compute_stats(moneyline),
        "over1_5": _compute_stats(over15),
    }
