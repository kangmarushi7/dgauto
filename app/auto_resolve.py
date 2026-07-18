from __future__ import annotations

from datetime import datetime, timedelta
import os
import re
import time
from typing import Any

from app.api_football import (
    api_football_configured,
    fetch_fixtures_by_date,
    fetch_head_to_head,
    fetch_team_recent,
    fixture_is_final,
    search_teams,
)
from app.bet_scenarios import resolve_kind_for_entry
from app.db import list_bets, resolve_bet_entry

# Allow enough time for date lookups + fallback team/H2H searches on large open books.
MAX_RUNTIME_SEC = int(os.getenv("AUTO_RESOLVE_MAX_RUNTIME_SEC", "240"))

# Generic club suffixes / tokens ignored when comparing core team names.
_TEAM_STOPWORDS = frozenset(
    {
        "fc",
        "cf",
        "sc",
        "afc",
        "fk",
        "bk",
        "if",
        "sk",
        "ff",
        "sv",
        "ac",
        "as",
        "rc",
        "cd",
        "ud",
        "sd",
        "club",
        "de",
        "the",
        "united",
        "city",
        "town",
        "sporting",
        "sports",
        "calcio",
    }
)

TEAM_ALIASES: dict[str, list[str]] = {
    "inter miami": ["miami", "inter miami cf"],
    "new england revolution": ["new england", "new england revs"],
    "sporting kansas city": ["kansas city", "sporting kc"],
    "chicago fire": ["chicago", "chicago fire fc"],
    "nashville sc": ["nashville"],
    "charlotte fc": ["charlotte"],
    "cd guadalajara": ["guadalajara", "chivas"],
    "mazatlan": ["mazatlan fc", "mazatlan"],
    "atlas": ["atla"],
    "psg": ["paris saint germain", "paris sg"],
    "fortuna sittard": ["sittard"],
    "fc twente": ["twente"],
    "nec nijmegen": ["nijmegen"],
    "eintracht frankfurt": ["frankfurt"],
    "central coast mariners": ["central coast"],
    "manchester city": ["man city"],
    "odense": ["ob"],
    "bodoe glimt": ["bodo glimt", "bodo/glimt"],
    "nordsjaelland": ["fc nordsjaelland", "nordjaelland"],
    "gil vicente": ["gil vicente", "gill vicente"],
    "club america": ["america", "club america"],
    "vancouver whitecaps": ["vancouver", "vancouver whitecaps fc"],
    "colorado rapids": ["colorado", "colorado rapids fc"],
    "karlsruher sc": ["karlsruher", "karlsruher sc"],
    "hannover 96": ["hannover", "hannover 96"],
    "heracles almelo": ["heracles", "heracles almelo"],
    "fc volendam": ["volendam"],
    "aalesunds fk": ["aalesund", "aalesunds"],
    "kristiansund bk": ["kristiansund"],
    "lillestrom sk": ["lillestrom"],
    "fc nordsjaelland": ["nordsjaelland", "nordsjaelland fc"],
    "fc fredericia": ["fredericia"],
    "odense boldklub": ["odense", "ob"],
    "st louis city": ["st. louis", "st louis"],
    "san jose earthquakes": ["san jose"],
    "hamburg": ["hamburger", "hamburger sv", "hamburg sv"],
    "toronto fc": ["toronto"],
    "atlanta united": ["atlanta"],
    "wsg tirol": ["wattens"],
    "pumas unam": ["puma", "pumas"],
    "lausanne sport": ["lausanne"],
    "fc zurich": ["zurich", "zuerich"],
    "western sydney wanderers": ["western sydney"],
    "sheffield united": ["sheffield utd", "sheffield u"],
    "preston north end": ["preston"],
    "ad ceuta": ["ceuta"],
    "racing santander": ["santander"],
    "kfum oslo": ["kfum"],
    "real salt lake": ["salt lake"],
    "agf aarhus": ["aarhus", "agf"],
    "fc kobenhavn": ["copenhagen", "fc copenhagen", "kobenhavn", "kobenhavn"],
    "vejle boldklub": ["vejle", "vejle bk"],
    "racing de santander": ["racing santander", "santander"],
    "kfum kameratene oslo": ["kfum oslo", "kfum"],
    "sarpsborg 08 ff": ["sarpsborg", "sarpsborg 08"],
    "melbourne victory": ["melbourne victory fc"],
    "western sydney wanderers fc": ["western sydney"],
    "fc lausanne sport": ["lausanne", "lausanne sport"],
    "vasteras sk": ["vasteras sk fk", "vasteras"],
    "nottingham forest": ["n forest", "n. forest", "forest"],
    "sc paderborn 07": ["paderborn"],
    "schalke 04": ["schalke"],
    "if brommapojkarna": ["brommapojkarna"],
    "borussia moenchengladbach": ["borussia m", "gladbach"],
    "bk haecken": ["bk hacken", "hacken"],
    "sirius": ["siriu", "ik sirius"],
    "oergyte is": ["orgryte is", "orgryte"],
    "degerfors": ["degerfor", "degerfors if"],
    "den bosch": ["fc den bosch"],
    "almere city": ["almere city fc"],
    "hammarby": ["hammarby if", "hammarby fotboll"],
    "kalmar ff": ["kalmar"],
    "tigres": ["tigres uanl", "uanl", "tigre"],
    "tijuana": ["club tijuana", "xolos"],
    "vitoria": ["ec vitoria", "vitoria ba"],
    "botafogo": ["botafogo rj", "botafogo fr"],
    "santos": ["santos fc"],
    "brann": ["sk brann"],
    "molde": ["molde fk"],
    "bodo glimt": ["bodoe glimt", "bodo/glimt", "fk bodo glimt"],
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "+00:00"


def _normalize(text: str) -> str:
    lowered = (text or "").strip().lower()
    for src, dst in (
        ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
        ("ö", "o"), ("ü", "u"), ("ş", "s"), ("ç", "c"), ("ğ", "g"),
        ("ø", "o"), ("æ", "ae"), ("å", "a"), ("ä", "a"),
    ):
        lowered = lowered.replace(src, dst)
    lowered = lowered.replace("/", " ")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    return lowered


def _significant_tokens(norm: str) -> set[str]:
    return {t for t in norm.split() if t and t not in _TEAM_STOPWORDS and len(t) >= 3}


def _team_variants(name: str) -> set[str]:
    norm = _normalize(name)
    variants = {norm}
    tokens = _significant_tokens(norm)
    for canonical, aliases in TEAM_ALIASES.items():
        options = {_normalize(canonical), *(_normalize(a) for a in aliases)}
        if norm in options:
            variants |= options
            continue
        # Expand when a truncated / partial DG name hits an alias token.
        hit = False
        for option in options:
            if not option:
                continue
            option_tokens = _significant_tokens(option) or {option}
            if tokens & option_tokens:
                hit = True
                break
            for token in tokens:
                for option_token in option_tokens:
                    if len(token) >= 5 and len(option_token) >= 5 and (
                        token.startswith(option_token) or option_token.startswith(token)
                    ):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            variants |= options
    return variants


def _prefix_token_score(a_tokens: set[str], b_tokens: set[str]) -> float:
    best = 0.0
    for ta in a_tokens:
        for tb in b_tokens:
            if len(ta) < 5 or len(tb) < 5:
                continue
            if ta == tb:
                best = max(best, 1.0)
            elif ta.startswith(tb) or tb.startswith(ta):
                best = max(best, 0.92)
            elif ta[:6] == tb[:6]:
                best = max(best, 0.85)
    return best


def _team_match(a: str, b: str) -> bool:
    return _team_similarity(a, b) >= 0.45


def _team_similarity(a: str, b: str) -> float:
    av = _team_variants(a)
    bv = _team_variants(b)
    if av & bv:
        return 1.0
    na = _normalize(a)
    nb = _normalize(b)
    if not na or not nb:
        return 0.0

    sa = _significant_tokens(na) or set(na.split())
    sb = _significant_tokens(nb) or set(nb.split())
    if not sa or not sb:
        return 0.0

    # Core name contained (Hammarby vs Hammarby IF, Tigres vs Tigres UANL).
    if sa <= sb or sb <= sa:
        return 0.95

    inter = len(sa & sb)
    union = len(sa | sb)
    jaccard = inter / union if union else 0.0
    prefix = _prefix_token_score(sa, sb)
    return max(jaccard, prefix)


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


def _parse_score(event: dict[str, Any]) -> tuple[int, int] | None:
    home = event.get("intHomeScore")
    away = event.get("intAwayScore")
    if home is None or away is None:
        return None
    try:
        return int(home), int(away)
    except (TypeError, ValueError):
        return None


def _candidates_for_entry(
    entry: dict[str, Any],
    date_cache: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Lazy date-window lookup for one fixture (avoids burning the runtime budget upfront)."""
    entry_date = _parse_entry_date(entry.get("fixture_date"))
    if not entry_date:
        return []
    pool: list[dict[str, Any]] = []
    for day_offset in (-1, 0, 1):
        date_key = (entry_date.date() + timedelta(days=day_offset)).isoformat()
        if date_key not in date_cache:
            date_cache[date_key] = fetch_fixtures_by_date(date_key)
        pool.extend(date_cache[date_key])
    return pool


def _match_event_from_candidates(
    entry: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    home, away = _parse_fixture(str(entry.get("fixture") or ""))
    if not home or not away or not candidates:
        return None

    entry_date = _parse_entry_date(entry.get("fixture_date"))
    league_name = _normalize(str(entry.get("league_name") or ""))
    best: dict[str, Any] | None = None
    best_score = -1
    for event in candidates:
        ev_home = str(event.get("strHomeTeam") or "")
        ev_away = str(event.get("strAwayTeam") or "")
        home_sim = _team_similarity(home, ev_home)
        away_sim = _team_similarity(away, ev_away)
        if home_sim < 0.45 or away_sim < 0.45:
            continue

        score = 10 + int(home_sim * 4) + int(away_sim * 4)
        event_date_str = str(event.get("dateEvent") or "")
        if entry_date and event_date_str:
            try:
                event_date = datetime.fromisoformat(event_date_str).date()
                day_delta = abs((event_date - entry_date.date()).days)
                if day_delta <= 1:
                    score += 3
                elif day_delta <= 2:
                    score += 1
                else:
                    score -= 2
            except ValueError:
                pass

        event_league = _normalize(str(event.get("strLeague") or ""))
        if league_name and event_league and league_name in event_league:
            score += 2

        if score > best_score:
            best = event
            best_score = score
    return best


def _resolve_team_id(team_name: str, cache: dict[str, int | None]) -> int | None:
    key = _normalize(team_name)
    if not key:
        return None
    if key in cache:
        return cache[key]

    best_id: int | None = None
    best_score = -1.0
    for team in search_teams(team_name):
        cand_name = str(team.get("name") or "")
        score = _team_similarity(team_name, cand_name)
        if score > best_score:
            best_score = score
            raw_id = team.get("id")
            try:
                best_id = int(raw_id) if raw_id is not None else None
            except (TypeError, ValueError):
                best_id = None

    cache[key] = best_id if best_score >= 0.45 and best_id else None
    return cache[key]


def _find_best_event(
    entry: dict[str, Any],
    date_cache: dict[str, list[dict[str, Any]]],
    team_id_cache: dict[str, int | None],
    h2h_cache: dict[str, list[dict[str, Any]]],
    team_recent_cache: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    home, away = _parse_fixture(str(entry.get("fixture") or ""))
    if not home or not away:
        return None

    shared_candidates = _candidates_for_entry(entry, date_cache)
    event = _match_event_from_candidates(entry, shared_candidates)
    if event:
        return event

    home_id = _resolve_team_id(home, team_id_cache)
    away_id = _resolve_team_id(away, team_id_cache)
    if home_id and away_id:
        h2h_key = f"{min(home_id, away_id)}-{max(home_id, away_id)}"
        if h2h_key not in h2h_cache:
            h2h_cache[h2h_key] = fetch_head_to_head(home_id, away_id, last=20)
        event = _match_event_from_candidates(entry, h2h_cache[h2h_key])
        if event:
            return event

    if home_id:
        tid = str(home_id)
        if tid not in team_recent_cache:
            team_recent_cache[tid] = fetch_team_recent(home_id, last=20)
        event = _match_event_from_candidates(entry, team_recent_cache[tid])
        if event:
            return event

    if away_id:
        tid = str(away_id)
        if tid not in team_recent_cache:
            team_recent_cache[tid] = fetch_team_recent(away_id, last=20)
        event = _match_event_from_candidates(entry, team_recent_cache[tid])
        if event:
            return event

    return None


def _compute_pnl(entry: dict[str, Any], result: str) -> float:
    odds = float(entry.get("odds") or 0)
    units = float(entry.get("units") or 1)
    if result == "won":
        return round((odds - 1) * units, 3) if odds > 0 else round(1.0 * units, 3)
    if result == "lost":
        return round(-1.0 * units, 3)
    return 0.0


def _team_goals_scored(entry: dict[str, Any], event: dict[str, Any]) -> int | None:
    team_name = str(entry.get("team_name") or "")
    home_team = str(event.get("strHomeTeam") or "")
    away_team = str(event.get("strAwayTeam") or "")
    if _team_match(team_name, home_team):
        return int(event.get("intHomeScore") or 0)
    if _team_match(team_name, away_team):
        return int(event.get("intAwayScore") or 0)
    return None


def _resolve_result(entry: dict[str, Any], event: dict[str, Any]) -> str | None:
    score = _parse_score(event)
    if score is None:
        return None
    home_goals, away_goals = score
    total = home_goals + away_goals
    kind = resolve_kind_for_entry(entry).lower()

    if kind in {"over1.5", "over 1.5"}:
        return "won" if total >= 2 else "lost"

    if kind in {"over2.5", "over 2.5"}:
        return "won" if total >= 3 else "lost"

    if kind in {"over3.5", "over 3.5"}:
        return "won" if total >= 4 else "lost"

    if kind in {"under2.5", "under 2.5"}:
        return "won" if total <= 2 else "lost"

    if kind in {"under3.5", "under 3.5"}:
        return "won" if total <= 3 else "lost"

    if kind == "btts":
        return "won" if home_goals >= 1 and away_goals >= 1 else "lost"

    if kind in {"team_o0.5", "team o0.5"}:
        scored = _team_goals_scored(entry, event)
        if scored is None:
            return None
        return "won" if scored >= 1 else "lost"

    if kind in {"team_o1.5", "team o1.5"}:
        scored = _team_goals_scored(entry, event)
        if scored is None:
            return None
        return "won" if scored >= 2 else "lost"

    if kind == "moneyline":
        team_name = str(entry.get("team_name") or "")
        home_team = str(event.get("strHomeTeam") or "")
        away_team = str(event.get("strAwayTeam") or "")
        if home_goals == away_goals:
            return "lost"
        winner = home_team if home_goals > away_goals else away_team
        return "won" if _team_match(team_name, winner) else "lost"

    if kind == "win_or_draw":
        team_name = str(entry.get("team_name") or "")
        home_team = str(event.get("strHomeTeam") or "")
        away_team = str(event.get("strAwayTeam") or "")
        if _team_match(team_name, home_team):
            return "won" if home_goals >= away_goals else "lost"
        if _team_match(team_name, away_team):
            return "won" if away_goals >= home_goals else "lost"
        return None

    if kind == "not_win":
        team_name = str(entry.get("team_name") or "")
        home_team = str(event.get("strHomeTeam") or "")
        away_team = str(event.get("strAwayTeam") or "")
        if _team_match(team_name, home_team):
            return "won" if home_goals <= away_goals else "lost"
        if _team_match(team_name, away_team):
            return "won" if away_goals <= home_goals else "lost"
        return None

    if kind == "draw":
        return "won" if home_goals == away_goals else "lost"

    if kind == "dc_1x":
        return "won" if home_goals >= away_goals else "lost"

    if kind == "dc_x2":
        return "won" if away_goals >= home_goals else "lost"

    return None


def auto_resolve_open_bets(log_type: str) -> dict[str, Any]:
    rows = list_bets(log_type)
    open_rows = [r for r in rows if str(r.get("status") or "").lower() == "open"]
    if not api_football_configured():
        return {
            "open_checked": len(open_rows),
            "resolved": 0,
            "skipped_not_found": 0,
            "skipped_not_final": 0,
            "skipped_unresolved": 0,
            "skipped_timeout": 0,
            "stopped_early": False,
            "error": "API_FOOTBALL_KEY not set. Add your key from dashboard.api-football.com to .env",
        }

    resolved = 0
    skipped_not_found = 0
    skipped_not_final = 0
    skipped_unresolved = 0
    stopped_early = False
    started = time.monotonic()

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for entry in open_rows:
        key = (
            str(entry.get("fixture_date") or ""),
            str(entry.get("fixture") or ""),
            str(entry.get("league_name") or ""),
        )
        grouped.setdefault(key, []).append(entry)

    date_cache: dict[str, list[dict[str, Any]]] = {}
    team_id_cache: dict[str, int | None] = {}
    h2h_cache: dict[str, list[dict[str, Any]]] = {}
    team_recent_cache: dict[str, list[dict[str, Any]]] = {}

    # Oldest kickoffs first so stale open bets are not starved by the runtime budget.
    groups = sorted(
        grouped.values(),
        key=lambda entries: str((entries[0] if entries else {}).get("fixture_date") or ""),
    )
    skipped_timeout = 0
    for idx, group_entries in enumerate(groups):
        if time.monotonic() - started > MAX_RUNTIME_SEC:
            stopped_early = True
            for remaining in groups[idx:]:
                skipped_timeout += len(remaining)
            break

        seed = group_entries[0]
        # Skip deep API lookups for matches that cannot be finished yet.
        kickoff = _parse_entry_date(seed.get("fixture_date"))
        if kickoff is not None:
            kick_naive = kickoff.replace(tzinfo=None) if kickoff.tzinfo else kickoff
            age_sec = (datetime.utcnow() - kick_naive).total_seconds()
            if age_sec < 95 * 60:
                skipped_not_final += len(group_entries)
                continue

        event = _find_best_event(
            seed,
            date_cache,
            team_id_cache,
            h2h_cache,
            team_recent_cache,
        )
        if not event:
            skipped_not_found += len(group_entries)
            continue
        if not fixture_is_final(event, kickoff=kickoff):
            skipped_not_final += len(group_entries)
            continue
        for entry in group_entries:
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
        "skipped_timeout": skipped_timeout,
        "stopped_early": stopped_early,
        "max_runtime_sec": MAX_RUNTIME_SEC,
    }
