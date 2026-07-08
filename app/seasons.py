"""Football season boundaries for bet log segregation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Season 1: fixtures through 30 Jun 2026 (IST). Season 2: from 1 Jul 2026.
SEASON_1_END = date(2026, 6, 30)
DEFAULT_SEASON_ID = 2

SEASONS: dict[int, dict[str, Any]] = {
    1: {
        "id": 1,
        "label": "Season 1",
        "description": "Through 30 Jun 2026",
    },
    2: {
        "id": 2,
        "label": "Season 2",
        "description": "From 1 Jul 2026",
    },
}


def parse_season(value: str | int | None = None) -> int:
    if value is None:
        return DEFAULT_SEASON_ID
    try:
        season_id = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SEASON_ID
    return season_id if season_id in SEASONS else DEFAULT_SEASON_ID


def seasons_meta() -> list[dict[str, Any]]:
    return [SEASONS[i] for i in sorted(SEASONS)]


def _parse_fixture_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def fixture_date_ist(entry: dict[str, Any]) -> date | None:
    dt = _parse_fixture_date(entry.get("fixture_date"))
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST).date()


def season_for_entry(entry: dict[str, Any]) -> int:
    """Assign bet to season by fixture kickoff date (IST)."""
    d = fixture_date_ist(entry)
    if d is None:
        return DEFAULT_SEASON_ID
    if d <= SEASON_1_END:
        return 1
    return 2


def filter_entries_by_season(entries: list[dict[str, Any]], season_id: int) -> list[dict[str, Any]]:
    season_id = parse_season(season_id)
    return [e for e in entries if season_for_entry(e) == season_id]


def season_context(season_id: int | None = None) -> dict[str, Any]:
    sid = parse_season(season_id)
    meta = SEASONS[sid]
    return {
        "season": sid,
        "season_label": meta["label"],
        "season_description": meta["description"],
        "seasons": seasons_meta(),
        "default_season": DEFAULT_SEASON_ID,
    }
