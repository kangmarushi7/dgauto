from __future__ import annotations

from datetime import datetime
from urllib.parse import quote
from urllib.request import urlopen
import json
import re
from typing import Any

from app.db import list_bets, resolve_bet_entry

SEARCH_URL = "https://www.thesportsdb.com/api/v1/json/123/searchevents.php?e="
FINAL_STATUSES = {"match finished", "ft", "aet", "pen"}
TEAM_ALIASES: dict[str, list[str]] = {
    "inter miami": ["miami", "inter miami cf"],
    "new england revolution": ["new england", "new england revs"],
    "sporting kansas city": ["kansas city", "sporting kc"],
    "chicago fire": ["chicago", "chicago fire fc"],
    "nashville sc": ["nashville"],
    "charlotte fc": ["charlotte"],
    "cd guadalajara": ["guadalajara", "chivas"],
    "mazatlan": ["mazatlan fc", "mazatlan"],
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "+00:00"


def _normalize(text: str) -> str:
    lowered = (text or "").strip().lower()
    lowered = lowered.replace("á", "a")
    lowered = lowered.replace("é", "e")
    lowered = lowered.replace("í", "i")
    lowered = lowered.replace("ó", "o")
    lowered = lowered.replace("ú", "u")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    return lowered


def _team_variants(name: str) -> set[str]:
    norm = _normalize(name)
    variants = {norm}
    for canonical, aliases in TEAM_ALIASES.items():
        options = {_normalize(canonical), *(_normalize(a) for a in aliases)}
        if norm in options:
            variants |= options
    return variants


def _team_match(a: str, b: str) -> bool:
    return bool(_team_variants(a) & _team_variants(b))


def _parse_fixture(fixture: str) -> tuple[str, str]:
    raw = (fixture or "").strip()
    if " vs " in raw:
        home, away = raw.split(" vs ", 1)
        return home.strip(), away.strip()
    if " v " in raw:
        home, away = raw.split(" v ", 1)
        return home.strip(), away.strip()
    return "", ""


def _parse_entry_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fetch_events(query: str) -> list[dict[str, Any]]:
    url = SEARCH_URL + quote(query)
    with urlopen(url, timeout=15) as resp:
        payload = json.load(resp)
    events = payload.get("event") if isinstance(payload, dict) else None
    return events if isinstance(events, list) else []


def _event_is_final(event: dict[str, Any]) -> bool:
    status = _normalize(str(event.get("strStatus") or ""))
    return status in FINAL_STATUSES


def _parse_score(event: dict[str, Any]) -> tuple[int, int] | None:
    home = event.get("intHomeScore")
    away = event.get("intAwayScore")
    if home is None or away is None:
        return None
    try:
        return int(home), int(away)
    except (TypeError, ValueError):
        return None


def _find_best_event(entry: dict[str, Any]) -> dict[str, Any] | None:
    home, away = _parse_fixture(str(entry.get("fixture") or ""))
    if not home or not away:
        return None

    queries = [f"{home} vs {away}"]
    # Add alias-expanded alternatives.
    for hv in _team_variants(home):
        for av in _team_variants(away):
            queries.append(f"{hv} vs {av}")

    seen = set()
    candidates: list[dict[str, Any]] = []
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        try:
            candidates.extend(_fetch_events(q))
        except Exception:
            continue

    if not candidates:
        return None

    entry_date = _parse_entry_date(entry.get("fixture_date"))
    best: dict[str, Any] | None = None
    best_score = -1
    for event in candidates:
        ev_home = str(event.get("strHomeTeam") or "")
        ev_away = str(event.get("strAwayTeam") or "")
        if not (_team_match(home, ev_home) and _team_match(away, ev_away)):
            continue

        score = 10
        event_date_str = str(event.get("dateEvent") or "")
        if entry_date and event_date_str:
            try:
                event_date = datetime.fromisoformat(event_date_str).date()
                day_delta = abs((event_date - entry_date.date()).days)
                if day_delta <= 1:
                    score += 3
                else:
                    score -= 2
            except ValueError:
                pass

        league_name = _normalize(str(entry.get("league_name") or ""))
        event_league = _normalize(str(event.get("strLeague") or ""))
        if league_name and event_league and league_name in event_league:
            score += 2

        if score > best_score:
            best = event
            best_score = score
    return best


def _compute_pnl(entry: dict[str, Any], result: str) -> float:
    odds = float(entry.get("odds") or 0)
    units = float(entry.get("units") or 1)
    if result == "won":
        return round((odds - 1) * units, 3) if odds > 0 else round(1.0 * units, 3)
    if result == "lost":
        return round(-1.0 * units, 3)
    return 0.0


def _resolve_result(entry: dict[str, Any], event: dict[str, Any]) -> str | None:
    score = _parse_score(event)
    if score is None:
        return None
    home_goals, away_goals = score
    bet_type = str(entry.get("bet_type") or "").strip().lower()

    if bet_type == "over1.5":
        return "won" if home_goals + away_goals >= 2 else "lost"

    if bet_type == "moneyline":
        team_name = str(entry.get("team_name") or "")
        home_team = str(event.get("strHomeTeam") or "")
        away_team = str(event.get("strAwayTeam") or "")
        if home_goals == away_goals:
            return "lost"
        winner = home_team if home_goals > away_goals else away_team
        return "won" if _team_match(team_name, winner) else "lost"

    return None


def auto_resolve_open_bets(log_type: str) -> dict[str, Any]:
    rows = list_bets(log_type)
    open_rows = [r for r in rows if str(r.get("status") or "").lower() == "open"]
    resolved = 0
    skipped_not_found = 0
    skipped_not_final = 0
    skipped_unresolved = 0

    for entry in open_rows:
        event = _find_best_event(entry)
        if not event:
            skipped_not_found += 1
            continue
        if not _event_is_final(event):
            skipped_not_final += 1
            continue
        result = _resolve_result(entry, event)
        if result not in {"won", "lost", "push"}:
            skipped_unresolved += 1
            continue
        pnl = _compute_pnl(entry, result)
        updated = resolve_bet_entry(log_type, str(entry.get("id")), result, pnl, _now_iso())
        if updated:
            resolved += 1

    return {
        "open_checked": len(open_rows),
        "resolved": resolved,
        "skipped_not_found": skipped_not_found,
        "skipped_not_final": skipped_not_final,
        "skipped_unresolved": skipped_unresolved,
    }
