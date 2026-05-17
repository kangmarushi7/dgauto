"""API-Football (api-sports.io) client for fixture lookup and final scores."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import time

from app.config import settings

BASE_URL = "https://v3.football.api-sports.io"
API_THROTTLE_SEC = 0.35
FINAL_STATUS_SHORT = frozenset({"FT", "AET", "PEN", "AWD", "WO"})


def api_football_configured() -> bool:
    return bool(settings.api_football_key.strip())


def _headers() -> dict[str, str]:
    return {"x-apisports-key": settings.api_football_key.strip()}


def _get(path: str, params: dict[str, Any] | None = None, retries: int = 3) -> dict[str, Any]:
    if not api_football_configured():
        return {"errors": ["API_FOOTBALL_KEY not configured"], "response": []}

    query = urlencode({k: v for k, v in (params or {}).items() if v is not None and v != ""})
    url = f"{BASE_URL}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{query}"

    for attempt in range(retries):
        try:
            req = Request(url, headers=_headers(), method="GET")
            with urlopen(req, timeout=20) as resp:
                payload = json.load(resp)
            if not isinstance(payload, dict):
                return {"errors": ["invalid response"], "response": []}
            errors = payload.get("errors")
            if isinstance(errors, dict) and errors:
                return {"errors": [str(errors)], "response": []}
            if isinstance(errors, list) and errors:
                return {"errors": [str(e) for e in errors], "response": []}
            return payload
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return {"errors": [f"HTTP {exc.code}"], "response": []}
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(0.4 * (attempt + 1))
                continue
            return {"errors": [str(exc)], "response": []}
    return {"errors": ["request failed"], "response": []}


def throttle() -> None:
    time.sleep(API_THROTTLE_SEC)


def normalize_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    """Map API-Football fixture object to auto_resolve event shape."""
    fixture = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
    teams = raw.get("teams") if isinstance(raw.get("teams"), dict) else {}
    goals = raw.get("goals") if isinstance(raw.get("goals"), dict) else {}
    league = raw.get("league") if isinstance(raw.get("league"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
    date_raw = str(fixture.get("date") or "")
    date_event = date_raw[:10] if len(date_raw) >= 10 else date_raw

    return {
        "strHomeTeam": str(home.get("name") or ""),
        "strAwayTeam": str(away.get("name") or ""),
        "intHomeScore": goals.get("home"),
        "intAwayScore": goals.get("away"),
        "strStatus": str(status.get("short") or status.get("long") or ""),
        "dateEvent": date_event,
        "strLeague": str(league.get("name") or ""),
        "idHomeTeam": home.get("id"),
        "idAwayTeam": away.get("id"),
        "fixtureId": fixture.get("id"),
    }


def fixture_is_final(event: dict[str, Any]) -> bool:
    status = str(event.get("strStatus") or "").strip().upper()
    return status in FINAL_STATUS_SHORT


def fetch_fixtures_by_date(date_str: str) -> list[dict[str, Any]]:
    """All fixtures on a calendar day (YYYY-MM-DD)."""
    payload = _get("fixtures", {"date": date_str})
    throttle()
    rows = payload.get("response")
    if not isinstance(rows, list):
        return []
    return [normalize_fixture(row) for row in rows if isinstance(row, dict)]


def search_teams(name: str) -> list[dict[str, Any]]:
    payload = _get("teams", {"search": name})
    throttle()
    rows = payload.get("response")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        team = row.get("team") if isinstance(row.get("team"), dict) else row
        if isinstance(team, dict) and team.get("name"):
            out.append(team)
    return out


def fetch_head_to_head(team_id_a: int | str, team_id_b: int | str, last: int = 15) -> list[dict[str, Any]]:
    h2h = f"{team_id_a}-{team_id_b}"
    payload = _get("fixtures/headtohead", {"h2h": h2h, "last": last})
    throttle()
    rows = payload.get("response")
    if not isinstance(rows, list):
        return []
    return [normalize_fixture(row) for row in rows if isinstance(row, dict)]


def fetch_team_recent(team_id: int | str, last: int = 15) -> list[dict[str, Any]]:
    payload = _get("fixtures", {"team": team_id, "last": last})
    throttle()
    rows = payload.get("response")
    if not isinstance(rows, list):
        return []
    return [normalize_fixture(row) for row in rows if isinstance(row, dict)]
