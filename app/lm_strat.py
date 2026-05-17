from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from urllib.request import urlopen
from typing import Any

from app.bet_log import compute_bet_stats
from app.db import insert_bets, list_bets, resolve_bet_entry

TEAM_ACTUALS_URL = "https://www.datagaffer.com/team_actuals.json"
H2H_FORM_URL = "https://www.datagaffer.com/h2h_form_combined.json"
LOG_TYPE = "lm"


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
    return list_bets(LOG_TYPE)


def sync_lm_bets(picks: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for p in picks:
        candidates.append(
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
    inserted = insert_bets(LOG_TYPE, candidates)
    return {"inserted": inserted, "total": len(load_lm_bet_log())}


def resolve_lm_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entries = load_lm_bet_log()
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


def lm_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return compute_bet_stats(entries)
