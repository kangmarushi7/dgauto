from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from urllib.request import urlopen
from typing import Any


TEAM_ACTUALS_URL = "https://www.datagaffer.com/team_actuals.json"
H2H_FORM_URL = "https://www.datagaffer.com/h2h_form_combined.json"
LM_BET_LOG_FILE = Path("data") / "lm_bet_log.json"


def _load_json(url: str) -> dict | list:
    with urlopen(url, timeout=30) as resp:
        return json.load(resp)


def _fetch_team_actuals() -> dict[str, dict[str, Any]]:
    data = _load_json(TEAM_ACTUALS_URL)
    return data if isinstance(data, dict) else {}


def _fetch_h2h_form_map() -> dict[tuple[int, int], dict[str, Any]]:
    data = _load_json(H2H_FORM_URL)
    matches = data.get("matches", []) if isinstance(data, dict) else []
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for m in matches:
        h = int(m.get("home_team_id") or 0)
        a = int(m.get("away_team_id") or 0)
        if h and a:
            out[(h, a)] = m
            out[(a, h)] = m
    return out


def build_lm_strat_picks(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    team_actuals = _fetch_team_actuals()
    h2h_form_map = _fetch_h2h_form_map()

    picks: list[dict[str, Any]] = []
    for m in matches:
        home_id = int(m.get("home_team_id") or 0)
        away_id = int(m.get("away_team_id") or 0)
        if not home_id or not away_id:
            continue

        home_stats = team_actuals.get(str(home_id), {})
        away_stats = team_actuals.get(str(away_id), {})
        home_gf = float(home_stats.get("goals_for") or 0.0)
        away_gf = float(away_stats.get("goals_for") or 0.0)

        h2h_row = h2h_form_map.get((home_id, away_id), {})
        h2h = h2h_row.get("h2h", {}) if isinstance(h2h_row, dict) else {}
        h2h_o15 = float(h2h.get("over_1_5_pct") or 0.0)
        home_form_o15 = float(h2h_row.get("home_form_o15") or 0.0)
        away_form_o15 = float(h2h_row.get("away_form_o15") or 0.0)

        if home_gf < 1.0 or away_gf < 1.0:
            continue
        if h2h_o15 < 80.0:
            continue
        if home_form_o15 < 80.0 or away_form_o15 < 80.0:
            continue

        picks.append(
            {
                "fixture_id": m.get("fixture_id"),
                "fixture_date": m.get("fixture_date"),
                "fixture": m.get("fixture", ""),
                "league_name": m.get("league_name", ""),
                "bet_type": "over1.5",
                "odds": m.get("over_1_5_odds"),
                "units": 1.0,
                "home_team": m.get("home_team", ""),
                "away_team": m.get("away_team", ""),
                "home_gf": round(home_gf, 2),
                "away_gf": round(away_gf, 2),
                "h2h_over15_pct": round(h2h_o15, 1),
                "home_form_o15_pct": round(home_form_o15, 1),
                "away_form_o15_pct": round(away_form_o15, 1),
            }
        )

    picks.sort(
        key=lambda x: (
            x.get("h2h_over15_pct", 0),
            x.get("home_form_o15_pct", 0) + x.get("away_form_o15_pct", 0),
            x.get("home_gf", 0) + x.get("away_gf", 0),
        ),
        reverse=True,
    )
    return picks


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_lm_bet_log() -> list[dict[str, Any]]:
    if not LM_BET_LOG_FILE.exists():
        return []
    return json.loads(LM_BET_LOG_FILE.read_text(encoding="utf-8"))


def save_lm_bet_log(entries: list[dict[str, Any]]) -> None:
    LM_BET_LOG_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _entry_key(entry: dict[str, Any]) -> tuple[str | None, str]:
    return (entry.get("fixture_date"), entry.get("fixture", ""))


def sync_lm_bets(picks: list[dict[str, Any]]) -> dict[str, Any]:
    existing = load_lm_bet_log()
    existing_keys = {_entry_key(e) for e in existing}
    inserted = 0

    for p in picks:
        k = _entry_key(p)
        if k in existing_keys:
            continue
        existing.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": "over1.5",
                "team_name": "",
                "odds": p.get("odds"),
                "units": 1.0,
                "status": "open",
                "pnl_units": None,
            }
        )
        existing_keys.add(k)
        inserted += 1

    save_lm_bet_log(existing)
    return {"inserted": inserted, "total": len(existing)}


def resolve_lm_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entries = load_lm_bet_log()
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
    save_lm_bet_log(entries)
    return updated


def lm_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    placed = len(entries)
    won = sum(1 for e in entries if e.get("status") == "won")
    lost = sum(1 for e in entries if e.get("status") == "lost")
    push = sum(1 for e in entries if e.get("status") == "push")
    decided = won + lost
    win_pct = round((won / decided) * 100, 1) if decided else 0.0
    pnl = round(sum(float(e.get("pnl_units") or 0.0) for e in entries), 3)
    return {
        "placed": placed,
        "won": won,
        "lost": lost,
        "push": push,
        "win_pct": win_pct,
        "unit_pnl": pnl,
    }
