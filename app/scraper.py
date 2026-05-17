from __future__ import annotations

from datetime import datetime, timezone
import json
from urllib.request import urlopen

from app.config import settings


def _pct(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _team_name(team_val) -> str:
    if isinstance(team_val, dict):
        return str(team_val.get("name") or "").strip()
    return str(team_val or "").strip()


def _parse_goal_rows(fixtures: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for fx in fixtures:
        perc = (fx.get("sim_stats") or {}).get("percents") or {}
        league = fx.get("league") or {}
        odds = fx.get("book_odds") or {}
        rows.append(
            {
                "fixture_id": fx.get("fixture_id"),
                "home": _team_name(fx.get("home")),
                "away": _team_name(fx.get("away")),
                "home_team_id": fx.get("home_id"),
                "away_team_id": fx.get("away_id"),
                "fixture_date": fx.get("date"),
                "league_name": league.get("name") or "",
                "over_25_pct": _pct(perc.get("over_2_5_pct")),
                "btts_pct": _pct(perc.get("btts_pct")),
                "home_projected_goals": _pct(((fx.get("sim_stats") or {}).get("xg") or {}).get("home")),
                "away_projected_goals": _pct(((fx.get("sim_stats") or {}).get("xg") or {}).get("away")),
                "projected_total_goals": _pct(((fx.get("sim_stats") or {}).get("xg") or {}).get("total")),
                "over_1_5_odds": _pct(odds.get("over_1_5")),
                "over_2_5_odds": _pct(odds.get("over_2_5")),
                "over_3_5_odds": _pct(odds.get("over_3_5")),
                "under_2_5_odds": _pct(odds.get("under_2_5")),
                "under_3_5_odds": _pct(odds.get("under_3_5")),
                "btts_yes_odds": _pct(odds.get("btts_yes")),
                "home_o0_5_odds": _pct(odds.get("home_o0_5")),
                "away_o0_5_odds": _pct(odds.get("away_o0_5")),
                "home_o1_5_odds": _pct(odds.get("home_o1_5")),
                "away_o1_5_odds": _pct(odds.get("away_o1_5")),
            }
        )
    return rows


def _parse_win_rows(fixtures: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for fx in fixtures:
        perc = (fx.get("sim_stats") or {}).get("percents") or {}
        league = fx.get("league") or {}
        odds = fx.get("book_odds") or {}
        rows.append(
            {
                "fixture_id": fx.get("fixture_id"),
                "home": _team_name(fx.get("home")),
                "away": _team_name(fx.get("away")),
                "home_team_id": fx.get("home_id"),
                "away_team_id": fx.get("away_id"),
                "fixture_date": fx.get("date"),
                "league_name": league.get("name") or "",
                "home_win_pct": _pct(perc.get("home_win_pct")),
                "draw_pct": _pct(perc.get("draw_pct")),
                "away_win_pct": _pct(perc.get("away_win_pct")),
                "home_ml_odds": _pct(odds.get("home_win")),
                "away_ml_odds": _pct(odds.get("away_win")),
            }
        )
    return rows


def scrape_datagaffer_sync() -> dict:
    # DataGaffer renders these views client-side from this feed.
    # Pulling the JSON directly is more reliable than scraping dynamic HTML tables.
    feed_url = "https://www.datagaffer.com/fixtures.json"
    with urlopen(feed_url, timeout=30) as resp:
        fixtures = json.load(resp)

    goal_rows = _parse_goal_rows(fixtures)
    win_rows = _parse_win_rows(fixtures)

    return {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "goal_rows": goal_rows,
        "win_rows": win_rows,
    }
