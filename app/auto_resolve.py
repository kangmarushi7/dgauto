from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote
from urllib.request import urlopen
import json
import re
import time
from typing import Any

from app.db import list_bets, resolve_bet_entry

SEARCH_URL = "https://www.thesportsdb.com/api/v1/json/123/searchevents.php?e="
EVENTS_DAY_URL = "https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d="
SEARCH_TEAMS_URL = "https://www.thesportsdb.com/api/v1/json/123/searchteams.php?t="
SEARCH_ALL_TEAMS_URL = "https://www.thesportsdb.com/api/v1/json/123/search_all_teams.php?l="
EVENTS_LAST_URL = "https://www.thesportsdb.com/api/v1/json/123/eventslast.php?id="
SEARCH_ALL_LEAGUES_URL = "https://www.thesportsdb.com/api/v1/json/123/search_all_leagues.php?s=Soccer"
EVENTS_SEASON_URL = "https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id="
FINAL_STATUSES = {"match finished", "ft", "aet", "pen"}
LEAGUE_NAME_MAP = {
    "major league soccer": "American Major League Soccer",
    "liga mx": "Mexican Primera League",
    "eredivisie": "Dutch Eredivisie",
    "superliga": "Danish Superliga",
    "eliteserien": "Norwegian Eliteserien",
    "premiership": "Scottish Premiership",
    "bundesliga": "German Bundesliga",
    "2 bundesliga": "German 2. Bundesliga",
    "2. bundesliga": "German 2. Bundesliga",
    "ligue 1": "French Ligue 1",
    "serie a": "Italian Serie A",
    "primeira liga": "Portuguese Primeira Liga",
    "super league": "Swiss Super League",
    "a league": "Australian A-League",
    "sueper lig": "Turkish Super Lig",
    "super lig": "Turkish Super Lig",
    "jupiler pro league": "Belgian First Division A",
    "la liga": "Spanish La Liga",
    "segunda division": "Spanish Segunda Division",
    "allsvenskan": "Swedish Allsvenskan",
    "bundesliga austria": "Austrian Bundesliga",
}
LEAGUE_LOOKUP_FALLBACKS = [
    "American Major League Soccer",
    "Mexican Primera League",
    "Dutch Eredivisie",
    "Danish Superliga",
    "Norwegian Eliteserien",
    "Scottish Premiership",
    "German Bundesliga",
    "German 2. Bundesliga",
    "French Ligue 1",
    "Italian Serie A",
    "Portuguese Primeira Liga",
    "Swiss Super League",
    "Australian A-League",
    "Turkish Super Lig",
    "Belgian First Division A",
    "Spanish La Liga",
    "Spanish Segunda Division",
    "Swedish Allsvenskan",
    "Austrian Bundesliga",
]
FIXTURE_QUERY_OVERRIDES: dict[str, list[str]] = {
    "st louis vs san jose": ["St. Louis City SC vs San Jose Earthquakes"],
    "toronto vs atlanta": ["Toronto FC vs Atlanta United"],
    "wattens vs ried": ["WSG Wattens vs Ried"],
    "pachuca vs puma": ["Pachuca vs U.N.A.M. - Pumas", "Pachuca vs Pumas UNAM"],
    "lausanne vs zurich": ["Lausanne vs FC Zurich", "Lausanne Sport vs FC Zurich"],
    "western sydney vs melbourne victory": ["Western Sydney Wanderers vs Melbourne Victory"],
    "sheffield utd vs preston": ["Sheffield Utd vs Preston", "Sheffield United vs Preston North End"],
    "ad ceuta vs santander": ["AD Ceuta FC vs Racing Santander", "AD Ceuta vs Santander"],
    "kfum oslo vs sarpsborg": ["KFUM Oslo vs Sarpsborg 08 FF", "KFUM Oslo vs Sarpsborg"],
    "heracles vs volendam": ["Heracles Almelo vs FC Volendam", "Heracles vs Volendam"],
    "la galaxy vs salt lake": ["LA Galaxy vs Real Salt Lake"],
    "aarhus vs midtjylland": ["Aarhus vs FC Midtjylland", "AGF Aarhus vs Midtjylland"],
    "paderborn vs schalke": ["SC Paderborn 07 vs FC Schalke 04", "Paderborn vs Schalke"],
    "brommapojkarna vs vasteras sk fk": ["IF Brommapojkarna vs Vasteras SK FK"],
    "copenhagen vs vejle": ["FC Copenhagen vs Vejle", "Copenhagen vs Vejle"],
    "den bosch vs almere city": ["Den Bosch vs Almere City FC", "FC Den Bosch vs Almere City FC"],
    "club america vs atla": ["Club América vs Atlas", "Club America vs Atlas"],
    "karlsruher vs hannover": ["Karlsruhe vs Hannover", "Karlsruher SC vs Hannover 96"],
    "viborg vs nordsjaelland": ["Viborg vs FC Nordsjælland", "Viborg vs FC Nordsjaelland"],
    "aalesund vs kristiansund": ["Aalesund vs Kristiansund"],
    "lillestrom vs bodo glimt": ["Lillestrøm vs Bodø/Glimt", "Lillestrom vs Bodo/Glimt"],
    "fredericia vs odense": ["Fredericia vs Odense BK", "FC Fredericia vs Odense"],
}
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
    "fc twente": ["twente"],
    "nec nijmegen": ["nijmegen", "nec"],
    "heracles almelo": ["heracles", "heracles almelo"],
    "fc volendam": ["volendam"],
    "aalesunds fk": ["aalesund", "aalesunds"],
    "kristiansund bk": ["kristiansund"],
    "lillestrom sk": ["lillestrom"],
    "bodoe glimt": ["bodo glimt", "bodo/glimt", "bodo"],
    "fc nordsjaelland": ["nordsjaelland", "nordsjaelland fc"],
    "fc fredericia": ["fredericia"],
    "odense boldklub": ["odense", "ob"],
    "atlas": ["atla", "atlas"],
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
    "sc paderborn 07": ["paderborn"],
    "schalke 04": ["schalke"],
    "if brommapojkarna": ["brommapojkarna"],
    "vasteras sk": ["vasteras sk fk", "vasteras"],
    "borussia moenchengladbach": ["borussia m", "gladbach"],
    "bk haecken": ["bk hacken", "hacken"],
    "sirius": ["siriu", "ik sirius"],
    "oergyte is": ["orgryte is", "orgryte"],
    "degerfors": ["degerfor"],
    "odense boldklub": ["odense", "ob", "odense bk"],
    "den bosch": ["fc den bosch"],
    "almere city": ["almere city fc"],
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
    lowered = lowered.replace("ö", "o")
    lowered = lowered.replace("ü", "u")
    lowered = lowered.replace("ş", "s")
    lowered = lowered.replace("ç", "c")
    lowered = lowered.replace("ğ", "g")
    lowered = lowered.replace("ø", "o")
    lowered = lowered.replace("æ", "ae")
    lowered = lowered.replace("/", " ")
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


def _canonical_team_name(name: str) -> str:
    norm = _normalize(name)
    for canonical, aliases in TEAM_ALIASES.items():
        options = {_normalize(canonical), *(_normalize(a) for a in aliases)}
        if norm in options:
            return canonical
    return norm


def _team_match(a: str, b: str) -> bool:
    return bool(_team_variants(a) & _team_variants(b))


def _team_similarity(a: str, b: str) -> float:
    av = _team_variants(a)
    bv = _team_variants(b)
    if av & bv:
        return 1.0
    na = _normalize(a)
    nb = _normalize(b)
    if not na or not nb:
        return 0.0
    sa = set(na.split())
    sb = set(nb.split())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _parse_fixture(fixture: str) -> tuple[str, str]:
    raw = (fixture or "").strip()
    if " vs " in raw:
        home, away = raw.split(" vs ", 1)
        return home.strip(), away.strip()
    if " v " in raw:
        home, away = raw.split(" v ", 1)
        return home.strip(), away.strip()
    return "", ""


def _fixture_queries(entry: dict[str, Any]) -> list[str]:
    fixture = str(entry.get("fixture") or "")
    home, away = _parse_fixture(fixture)
    if not home or not away:
        return []
    key = _normalize(fixture)
    overrides = FIXTURE_QUERY_OVERRIDES.get(key, [])
    raw_query = f"{home} vs {away}"
    canonical_query = f"{_canonical_team_name(home)} vs {_canonical_team_name(away)}"
    queries = [*overrides, raw_query, canonical_query]
    # Keep order, drop empties/duplicates.
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        qn = q.strip()
        if not qn:
            continue
        if qn in seen:
            continue
        seen.add(qn)
        out.append(qn)
    return out


def _parse_entry_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fetch_events(query: str, retries: int = 3) -> list[dict[str, Any]]:
    url = SEARCH_URL + quote(query)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=15) as resp:
                payload = json.load(resp)
            events = payload.get("event") if isinstance(payload, dict) else None
            return events if isinstance(events, list) else []
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(0.35 * (attempt + 1))
    if last_error:
        raise last_error
    return []


def _fetch_events_for_date(date_str: str, retries: int = 3) -> list[dict[str, Any]]:
    url = EVENTS_DAY_URL + quote(date_str) + "&s=Soccer"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=15) as resp:
                payload = json.load(resp)
            events = payload.get("events") if isinstance(payload, dict) else None
            return events if isinstance(events, list) else []
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(0.35 * (attempt + 1))
    if last_error:
        raise last_error
    return []


def _fetch_team_id(team_name: str, retries: int = 2) -> str | None:
    candidates = sorted(_team_variants(team_name), key=len, reverse=True)
    if team_name and _normalize(team_name) not in candidates:
        candidates.insert(0, _normalize(team_name))

    best_id = None
    best_score = -1.0
    for candidate_name in candidates:
        url = SEARCH_TEAMS_URL + quote(candidate_name)
        for attempt in range(retries):
            try:
                with urlopen(url, timeout=12) as resp:
                    payload = json.load(resp)
                teams = payload.get("teams") if isinstance(payload, dict) else None
                if not isinstance(teams, list):
                    break
                for t in teams:
                    cand = str(t.get("strTeam") or "")
                    score = _team_similarity(team_name, cand)
                    if score > best_score:
                        best_score = score
                        best_id = str(t.get("idTeam") or "")
                break
            except Exception:
                if attempt < retries - 1:
                    time.sleep(0.25 * (attempt + 1))
        if best_score >= 0.8 and best_id:
            return best_id
    if best_score >= 0.45 and best_id:
        return best_id
    return None


def _fetch_team_last_events(team_id: str, retries: int = 2) -> list[dict[str, Any]]:
    url = EVENTS_LAST_URL + quote(team_id)
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=12) as resp:
                payload = json.load(resp)
            events = payload.get("results") if isinstance(payload, dict) else None
            return events if isinstance(events, list) else []
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.25 * (attempt + 1))
    return []


def _league_to_sportsdb_name(league_name: str) -> str:
    normalized = _normalize(league_name)
    return LEAGUE_NAME_MAP.get(normalized, league_name.strip())


def _fetch_teams_for_league(league_name: str, retries: int = 2) -> list[dict[str, Any]]:
    if not league_name:
        return []
    url = SEARCH_ALL_TEAMS_URL + quote(league_name)
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=15) as resp:
                payload = json.load(resp)
            teams = payload.get("teams") if isinstance(payload, dict) else None
            return teams if isinstance(teams, list) else []
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.3 * (attempt + 1))
    return []


def _fetch_all_leagues(retries: int = 2) -> list[dict[str, Any]]:
    for attempt in range(retries):
        try:
            with urlopen(SEARCH_ALL_LEAGUES_URL, timeout=20) as resp:
                payload = json.load(resp)
            countries = payload.get("countries") if isinstance(payload, dict) else None
            return countries if isinstance(countries, list) else []
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.3 * (attempt + 1))
    return []


def _guess_league_id(league_name: str, leagues: list[dict[str, Any]]) -> str | None:
    needle = _normalize(league_name)
    if not needle or not leagues:
        return None
    best_id = None
    best_score = -1.0
    for l in leagues:
        lname = str(l.get("strLeague") or "")
        score = _team_similarity(needle, lname)
        if score > best_score:
            best_score = score
            best_id = str(l.get("idLeague") or "")
    if best_score >= 0.45 and best_id:
        return best_id
    return None


def _season_candidates(entry_date: datetime | None) -> list[str]:
    if not entry_date:
        return []
    y = entry_date.year
    return [
        str(y),
        f"{y-1}-{y}",
        f"{y}-{y+1}",
    ]


def _fetch_events_for_league_season(league_id: str, season: str, retries: int = 2) -> list[dict[str, Any]]:
    url = f"{EVENTS_SEASON_URL}{quote(league_id)}&s={quote(season)}"
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=20) as resp:
                payload = json.load(resp)
            events = payload.get("events") if isinstance(payload, dict) else None
            return events if isinstance(events, list) else []
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.3 * (attempt + 1))
    return []


def _league_team_id_lookup(
    entry: dict[str, Any],
    league_team_cache: dict[str, list[dict[str, Any]]],
) -> tuple[str | None, str | None]:
    home, away = _parse_fixture(str(entry.get("fixture") or ""))
    league_name = _league_to_sportsdb_name(str(entry.get("league_name") or ""))
    if not home or not away or not league_name:
        return None, None
    leagues_to_try = [league_name]
    for league in LEAGUE_LOOKUP_FALLBACKS:
        if league not in leagues_to_try:
            leagues_to_try.append(league)

    def _best_id(team_name: str, teams: list[dict[str, Any]]) -> tuple[str | None, float]:
        best_id = None
        best_score = -1.0
        for t in teams:
            cand = str(t.get("strTeam") or "")
            score = _team_similarity(team_name, cand)
            if score > best_score:
                best_score = score
                best_id = str(t.get("idTeam") or "")
        return best_id, best_score

    best_pair: tuple[str | None, str | None] = (None, None)
    best_pair_score = -1.0

    for league in leagues_to_try:
        if league not in league_team_cache:
            league_team_cache[league] = _fetch_teams_for_league(league)
        teams = league_team_cache[league]
        if not teams:
            continue
        home_id, home_score = _best_id(home, teams)
        away_id, away_score = _best_id(away, teams)
        pair_score = home_score + away_score
        if home_id and away_id and home_score >= 0.45 and away_score >= 0.45 and pair_score > best_pair_score:
            best_pair = (home_id, away_id)
            best_pair_score = pair_score
            if home_score >= 0.9 and away_score >= 0.9:
                break

    return best_pair


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


def _find_best_event(
    entry: dict[str, Any],
    query_cache: dict[str, list[dict[str, Any]]],
    date_cache: dict[str, list[dict[str, Any]]],
    team_id_cache: dict[str, str | None],
    team_last_cache: dict[str, list[dict[str, Any]]],
    league_team_cache: dict[str, list[dict[str, Any]]],
    league_list_cache: dict[str, list[dict[str, Any]]],
    season_events_cache: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    home, away = _parse_fixture(str(entry.get("fixture") or ""))
    if not home or not away:
        return None

    canonical_home = _canonical_team_name(home)
    canonical_away = _canonical_team_name(away)
    queries = _fixture_queries(entry)
    if not queries:
        raw_query = f"{home} vs {away}"
        canonical_query = f"{canonical_home} vs {canonical_away}"
        queries = [raw_query] if canonical_query == raw_query else [raw_query, canonical_query]

    candidates: list[dict[str, Any]] = []
    for q in queries:
        if q not in query_cache:
            try:
                query_cache[q] = _fetch_events(q)
            except Exception:
                query_cache[q] = []
        candidates.extend(query_cache[q])

    entry_date = _parse_entry_date(entry.get("fixture_date"))
    if entry_date:
        day_offsets = (-1, 0, 1)
        for day_offset in day_offsets:
            date_key = (entry_date.date() + timedelta(days=day_offset)).isoformat()
            if date_key not in date_cache:
                try:
                    date_cache[date_key] = _fetch_events_for_date(date_key)
                except Exception:
                    date_cache[date_key] = []
            candidates.extend(date_cache[date_key])

    # Robust fallback for older fixtures: pull whole league-season fixtures once.
    league_name = _league_to_sportsdb_name(str(entry.get("league_name") or ""))
    if "all" not in league_list_cache:
        league_list_cache["all"] = _fetch_all_leagues()
    league_id = _guess_league_id(league_name, league_list_cache["all"])
    if league_id:
        for season in _season_candidates(entry_date):
            cache_key = f"{league_id}:{season}"
            if cache_key not in season_events_cache:
                season_events_cache[cache_key] = _fetch_events_for_league_season(league_id, season)
            candidates.extend(season_events_cache[cache_key])

    # League-level team directory is more reliable and less rate-limited than searchteams.
    home_id, away_id = _league_team_id_lookup(entry, league_team_cache)
    for team_id in (home_id, away_id):
        if not team_id:
            continue
        if team_id not in team_last_cache:
            team_last_cache[team_id] = _fetch_team_last_events(team_id)
        candidates.extend(team_last_cache[team_id])

    # Final fallback: team-level recent events (works better on free tier for some leagues).
    for team in (home, away, canonical_home, canonical_away):
        tn = _normalize(team)
        if not tn:
            continue
        if tn not in team_id_cache:
            team_id_cache[tn] = _fetch_team_id(team)
        team_id = team_id_cache[tn]
        if not team_id:
            continue
        if team_id not in team_last_cache:
            team_last_cache[team_id] = _fetch_team_last_events(team_id)
        candidates.extend(team_last_cache[team_id])

    if not candidates:
        return None

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

    # Resolve multiple bets on the same fixture from one lookup to avoid rate limiting.
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for entry in open_rows:
        key = (
            str(entry.get("fixture_date") or ""),
            str(entry.get("fixture") or ""),
            str(entry.get("league_name") or ""),
        )
        grouped.setdefault(key, []).append(entry)

    query_cache: dict[str, list[dict[str, Any]]] = {}
    date_cache: dict[str, list[dict[str, Any]]] = {}
    team_id_cache: dict[str, str | None] = {}
    team_last_cache: dict[str, list[dict[str, Any]]] = {}
    league_team_cache: dict[str, list[dict[str, Any]]] = {}
    league_list_cache: dict[str, list[dict[str, Any]]] = {}
    season_events_cache: dict[str, list[dict[str, Any]]] = {}
    for group_entries in grouped.values():
        seed = group_entries[0]
        event = _find_best_event(
            seed,
            query_cache,
            date_cache,
            team_id_cache,
            team_last_cache,
            league_team_cache,
            league_list_cache,
            season_events_cache,
        )
        if not event:
            skipped_not_found += len(group_entries)
            continue
        if not _event_is_final(event):
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
    }
