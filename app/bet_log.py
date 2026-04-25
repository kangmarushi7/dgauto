from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from typing import Any


BET_LOG_FILE = Path("data") / "bet_log.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_bet_log() -> list[dict[str, Any]]:
    if not BET_LOG_FILE.exists():
        return []
    return json.loads(BET_LOG_FILE.read_text(encoding="utf-8"))


def save_bet_log(entries: list[dict[str, Any]]) -> None:
    BET_LOG_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _entry_key(entry: dict[str, Any]) -> tuple[str | None, str, str, str]:
    return (
        entry.get("fixture_date"),
        entry.get("fixture", ""),
        entry.get("bet_type", ""),
        entry.get("team_name", ""),
    )


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
    existing = load_bet_log()
    existing_keys = {_entry_key(e) for e in existing}

    candidates = _make_moneyline_bets(matches) + _make_over15_bets(matches)
    inserted = 0
    for c in candidates:
        key = _entry_key(c)
        if key in existing_keys:
            continue
        existing.append(c)
        existing_keys.add(key)
        inserted += 1

    save_bet_log(existing)
    return {"inserted": inserted, "total": len(existing)}


def resolve_bet(bet_id: str, result: str) -> dict[str, Any]:
    entries = load_bet_log()
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    updated: dict[str, Any] | None = None
    for e in entries:
        if e.get("id") != bet_id:
            continue
        e["status"] = result
        odds = float(e.get("odds") or 0)
        units = float(e.get("units") or 1)
        if result == "won":
            e["pnl_units"] = round((odds - 1) * units, 3) if odds > 0 else round(1.0 * units, 3)
        elif result == "lost":
            e["pnl_units"] = round(-1.0 * units, 3)
        else:
            e["pnl_units"] = 0.0
        e["resolved_at"] = _now_iso()
        updated = e
        break

    if not updated:
        raise ValueError("Bet not found.")

    save_bet_log(entries)
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
