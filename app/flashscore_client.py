"""Flashscore live-score client via the internal ninja pipe-delimited feed.

Primary path: https://global.flashscore.ninja/2/x/feed/f_{sport}_{dayOffset}_3_en_1
Do NOT scrape public HTML for core scores. Optional Playwright is football-only
for minute/stats when SCRAPE_SOURCE requests it.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

SPORT_FOOTBALL = 1
SPORT_TENNIS = 2

ROW_SEP = "~"
CELL_SEP = "¬"  # U+00AC
KV_SEP = "÷"  # U+00F7

HOME_SET_KEYS = ("BA", "BC", "BE", "BG", "BI")
AWAY_SET_KEYS = ("BB", "BD", "BF", "BH", "BJ")

FOOTBALL_FINISH_AB = frozenset({"3", "4", "5"})
# Common AC finish / award codes observed on the feed.
FOOTBALL_FINISH_AC = frozenset({"3", "10", "11", "12", "13"})

YOUTH_HINTS = re.compile(
    r"\b(u1[5-9]|u2[0-3]|youth|reserve|res\.?|ii\b|women|wfc|ladies|feminin)\b",
    re.I,
)

# Generic tokens that must not alone prove a side match.
_MATCH_STOPWORDS = frozenset(
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
        "association",
        "associação",
    }
)

DEFAULT_FSIGN = "SW9D1eZo"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CACHE_TTL_SEC = float(os.getenv("FLASHSCORE_CACHE_TTL_SEC", "180"))
DEFAULT_DAY_OFFSETS = (-1, 0, 1, 2)
# Flashscore daily feeds usually empty beyond ~7–10 days; keep settlement window bounded.
SETTLE_MIN_OFFSET = int(os.getenv("FLASHSCORE_SETTLE_MIN_OFFSET", "-10"))
SETTLE_MAX_OFFSET = int(os.getenv("FLASHSCORE_SETTLE_MAX_OFFSET", "2"))

# League → tournament substring hints (lowercase). Prefer country-qualified names.
LEAGUE_HINTS: dict[str, tuple[str, ...]] = {
    "mls": ("mls", "major league soccer", "usa: mls"),
    "liga mx": ("liga mx", "mexico: liga mx", "mexico"),
    "serie a": ("serie a", "brazil", "italy"),
    "brasileirao": ("serie a", "brazil", "brasileiro"),
    "allsvenskan": ("allsvenskan", "sweden: allsvenskan", "sweden"),
    "eliteserien": ("eliteserien", "norway: eliteserien", "norway"),
    "superliga": ("denmark: superliga", "danish superliga", "denmark"),
    "superligaen": ("denmark: superliga", "denmark"),
    "premier league": ("premier league", "england"),
    "la liga": ("laliga", "la liga", "spain"),
    "bundesliga": ("bundesliga", "germany"),
    "eredivisie": ("eredivisie", "netherlands"),
    "liga portugal": ("liga portugal", "primeira"),
    "championship": ("championship", "england"),
    "süper lig": ("super lig", "turkey"),
    "super lig": ("super lig", "turkey"),
}

# Disambiguate leagues that share a short name (e.g. Superliga DK vs RO).
LEAGUE_REQUIRED_TOURNAMENT: dict[str, tuple[str, ...]] = {
    "superliga": ("denmark",),
    "superligaen": ("denmark",),
    "liga mx": ("mexico", "liga mx"),
    "allsvenskan": ("sweden", "allsvenskan"),
    "eliteserien": ("norway", "eliteserien"),
}


@dataclass
class FlashscoreTennisMatch:
    id: str
    player1: str
    player2: str
    tournament: str
    sets: list[tuple[int, int]] = field(default_factory=list)
    games_p1: int | str | None = None
    games_p2: int | str | None = None
    is_live: bool = False
    is_finished: bool = False
    stage: str = ""
    slug1: str = ""
    slug2: str = ""
    url: str = ""
    kickoff_ts: int | None = None

    @property
    def sets_won(self) -> tuple[int, int]:
        return _sets_won(self.sets)

    def winner(self) -> str | None:
        if not self.is_finished:
            return None
        w1, w2 = self.sets_won
        if w1 >= 2 and w1 > w2:
            return self.player1
        if w2 >= 2 and w2 > w1:
            return self.player2
        return None


@dataclass
class FlashscoreFootballMatch:
    id: str
    home: str
    away: str
    tournament: str
    home_goals: int | None = None
    away_goals: int | None = None
    is_live: bool = False
    is_finished: bool = False
    slug_home: str = ""
    slug_away: str = ""
    url: str = ""
    kickoff_ts: int | None = None
    stage_ab: str = ""
    stage_ac: str = ""

    def to_event_dict(self) -> dict[str, Any]:
        """Shape compatible with app.auto_resolve._resolve_result."""
        status = "FT" if self.is_finished else ("LIVE" if self.is_live else "NS")
        date_event = ""
        if self.kickoff_ts:
            date_event = datetime.fromtimestamp(self.kickoff_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return {
            "strHomeTeam": self.home,
            "strAwayTeam": self.away,
            "intHomeScore": self.home_goals,
            "intAwayScore": self.away_goals,
            "strStatus": status,
            "dateEvent": date_event,
            "strLeague": self.tournament,
            "fixtureId": self.id,
            "flashscoreUrl": self.url,
            "flashscoreMatchId": self.id,
            "source": "flashscore",
        }


def _fsign() -> str:
    return (os.getenv("FLASHSCORE_FSIGN") or DEFAULT_FSIGN).strip() or DEFAULT_FSIGN


def _headers() -> dict[str, str]:
    return {
        "X-Fsign": _fsign(),
        "Referer": "https://www.flashscore.com/",
        "Origin": "https://www.flashscore.com",
        "User-Agent": os.getenv("FLASHSCORE_UA", DEFAULT_UA),
        "Accept": "*/*",
    }


def feed_url(sport: int, day_offset: int = 0) -> str:
    return f"https://global.flashscore.ninja/2/x/feed/f_{sport}_{day_offset}_3_en_1"


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _football_url(match_id: str, slug_home: str, slug_away: str) -> str:
    if slug_home and slug_away:
        return f"https://www.flashscore.com/match/football/{slug_home}/{slug_away}/?mid={match_id}"
    return f"https://www.flashscore.com/match/?mid={match_id}"


def _tennis_url(match_id: str, slug1: str, slug2: str) -> str:
    if slug1 and slug2:
        return f"https://www.flashscore.com/match/tennis/{slug1}/{slug2}/?mid={match_id}"
    return f"https://www.flashscore.com/match/?mid={match_id}"


def _set_complete(home_games: int, away_games: int) -> bool:
    """True when a tennis set score looks finished (not the in-progress set)."""
    hi = max(home_games, away_games)
    lo = min(home_games, away_games)
    if hi >= 7:
        return True
    if hi >= 6 and (hi - lo) >= 2:
        return True
    return False


def _parse_tennis_sets(cells: dict[str, str]) -> list[tuple[int, int]]:
    sets: list[tuple[int, int]] = []
    for hk, ak in zip(HOME_SET_KEYS, AWAY_SET_KEYS):
        if hk not in cells or ak not in cells:
            continue
        hg = _safe_int(cells.get(hk))
        ag = _safe_int(cells.get(ak))
        if hg is None or ag is None:
            continue
        sets.append((hg, ag))
    return sets


def _sets_won(sets: list[tuple[int, int]]) -> tuple[int, int]:
    p1 = p2 = 0
    for a, b in sets:
        if not _set_complete(a, b):
            continue
        if a > b:
            p1 += 1
        elif b > a:
            p2 += 1
    return p1, p2


def _tennis_finished(sets: list[tuple[int, int]], ab: str, ac: str) -> bool:
    p1, p2 = _sets_won(sets)
    if p1 >= 2 or p2 >= 2:
        return True
    if ab in FOOTBALL_FINISH_AB or ac in FOOTBALL_FINISH_AC:
        return True
    return False


def _football_finished(ab: str, ac: str) -> bool:
    return ab in FOOTBALL_FINISH_AB or ac in FOOTBALL_FINISH_AC


def _football_live(ab: str, ai: str) -> bool:
    return ab == "2" or ai.lower() == "y"


def cells_to_football(cells: dict[str, str], tournament: str) -> FlashscoreFootballMatch:
    mid = str(cells.get("AA") or "")
    home = str(cells.get("CX") or "")
    away = str(cells.get("AF") or "")
    slug_home = str(cells.get("WU") or "")
    slug_away = str(cells.get("WV") or "")
    ab = str(cells.get("AB") or "")
    ac = str(cells.get("AC") or "")
    ai = str(cells.get("AI") or "")
    finished = _football_finished(ab, ac)
    live = (not finished) and _football_live(ab, ai)
    return FlashscoreFootballMatch(
        id=mid,
        home=home,
        away=away,
        tournament=tournament,
        home_goals=_safe_int(cells.get("AG")),
        away_goals=_safe_int(cells.get("AH")),
        is_live=live,
        is_finished=finished,
        slug_home=slug_home,
        slug_away=slug_away,
        url=_football_url(mid, slug_home, slug_away),
        kickoff_ts=_safe_int(cells.get("AD")),
        stage_ab=ab,
        stage_ac=ac,
    )


def cells_to_tennis(cells: dict[str, str], tournament: str) -> FlashscoreTennisMatch:
    mid = str(cells.get("AA") or "")
    p1 = str(cells.get("CX") or "")
    p2 = str(cells.get("AF") or "")
    slug1 = str(cells.get("WU") or "")
    slug2 = str(cells.get("WV") or "")
    ab = str(cells.get("AB") or "")
    ac = str(cells.get("AC") or "")
    ai = str(cells.get("AI") or "")
    sets = _parse_tennis_sets(cells)
    finished = _tennis_finished(sets, ab, ac)
    live = (not finished) and (ab == "2" or ai.lower() == "y")
    games_p1 = cells.get("AG")
    games_p2 = cells.get("AH") or cells.get("AT")
    return FlashscoreTennisMatch(
        id=mid,
        player1=p1,
        player2=p2,
        tournament=tournament,
        sets=sets,
        games_p1=_safe_int(games_p1) if games_p1 not in (None, "") else games_p1,
        games_p2=_safe_int(games_p2) if games_p2 not in (None, "") else games_p2,
        is_live=live,
        is_finished=finished,
        stage=ab or ac,
        slug1=slug1,
        slug2=slug2,
        url=_tennis_url(mid, slug1, slug2),
        kickoff_ts=_safe_int(cells.get("AD")),
    )


def parse_feed(raw: str, *, sport: int = SPORT_FOOTBALL) -> list[Any]:
    """Parse ninja pipe-delimited body into match objects."""
    matches: list[Any] = []
    tournament = ""
    if not raw:
        return matches

    for row in raw.split(ROW_SEP):
        if not row:
            continue

        cells: dict[str, str] = {}
        for cell in row.split(CELL_SEP):
            if KV_SEP not in cell:
                continue
            key, value = cell.split(KV_SEP, 1)
            cells[key] = value

        if "ZA" in cells:
            tournament = cells["ZA"]
            # Tournament section rows usually lack AA; still allow AA on same row.
            if "AA" not in cells:
                continue

        if "AA" not in cells or "CX" not in cells or "AF" not in cells:
            continue

        if sport == SPORT_TENNIS:
            matches.append(cells_to_tennis(cells, tournament))
        else:
            matches.append(cells_to_football(cells, tournament))
    return matches


def fetch_feed_raw(sport: int, day_offset: int = 0, *, timeout: float = 25.0) -> str:
    """HTTP GET ninja feed. Prefer curl_cffi chrome impersonation; fall back to urllib."""
    url = feed_url(sport, day_offset)
    headers = _headers()

    try:
        from curl_cffi import requests as cffi_requests  # type: ignore

        resp = cffi_requests.get(
            url,
            headers=headers,
            timeout=timeout,
            impersonate="chrome",
        )
        resp.raise_for_status()
        text = resp.text or ""
        if not text.strip():
            logger.error(
                "Flashscore feed empty for sport=%s day=%s — X-Fsign may have rotated "
                "(set FLASHSCORE_FSIGN). url=%s",
                sport,
                day_offset,
                url,
            )
        return text
    except Exception as exc:
        logger.warning("curl_cffi fetch failed (%s); falling back to urllib", exc)

    from urllib.request import Request, urlopen

    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed Flashscore host
        text = resp.read().decode("utf-8", errors="replace")
    if not text.strip():
        logger.error(
            "Flashscore feed empty for sport=%s day=%s — X-Fsign may have rotated "
            "(set FLASHSCORE_FSIGN). url=%s",
            sport,
            day_offset,
            url,
        )
    return text


# ── Fuzzy matching ──────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    lowered = (text or "").strip().lower()
    for src, dst in (
        ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
        ("ö", "o"), ("ü", "u"), ("ş", "s"), ("ç", "c"), ("ğ", "g"),
        ("ø", "o"), ("æ", "ae"), ("å", "a"), ("ä", "a"), ("ñ", "n"),
    ):
        lowered = lowered.replace(src, dst)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    return lowered


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in _normalize(text).split()
        if len(t) >= 3 and t not in _MATCH_STOPWORDS
    }


def _token_overlap(a: set[str], b: set[str]) -> bool:
    return bool(a & b)


def _prefix_overlap(a: set[str], b: set[str]) -> bool:
    """True when a truncated DG token prefixes a Flashscore token (or vice versa)."""
    for ta in a:
        for tb in b:
            if len(ta) < 5 or len(tb) < 5:
                continue
            if ta == tb or ta.startswith(tb) or tb.startswith(ta):
                return True
    return False


def _side_hit(query: set[str], candidate: set[str]) -> bool:
    return _token_overlap(query, candidate) or _prefix_overlap(query, candidate)


def _league_key(league: str | None) -> str:
    return _normalize(league or "")


def _tournament_allowed(league: str | None, tournament: str) -> bool:
    key = _league_key(league)
    required = LEAGUE_REQUIRED_TOURNAMENT.get(key)
    if not required:
        return True
    tourney = _normalize(tournament)
    return any(r in tourney for r in required)


def match_score_football(
    home: str,
    away: str,
    fs: FlashscoreFootballMatch,
    league: str | None = None,
) -> int:
    """Side overlaps only. Accept requires BOTH home and away hits (score >= 2).

    League hints are ranking bonuses and hard filters — they never replace a missing side.
    """
    qh, qa = _tokens(home), _tokens(away)
    fh, fa = _tokens(fs.home), _tokens(fs.away)
    if not qh or not qa or not fh or not fa:
        return -99

    if not _tournament_allowed(league, fs.tournament):
        return -50

    home_hit = _side_hit(qh, fh)
    away_hit = _side_hit(qa, fa)
    crossed = _side_hit(qh, fa) or _side_hit(qa, fh)

    score = 0
    if home_hit:
        score += 1
    if away_hit:
        score += 1
    if crossed and not (home_hit and away_hit):
        score -= 1

    # Ranking only — does not satisfy the ≥2 accept threshold alone.
    if league and home_hit and away_hit:
        hints = LEAGUE_HINTS.get(_league_key(league), ())
        tourney = _normalize(fs.tournament)
        if hints and any(h in tourney for h in hints):
            score += 1

    blob = f"{fs.home} {fs.away} {fs.tournament}"
    if YOUTH_HINTS.search(blob) and not YOUTH_HINTS.search(f"{home} {away} {league or ''}"):
        score -= 2

    return score


def match_score_tennis(p1: str, p2: str, fs: FlashscoreTennisMatch) -> int:
    query = _tokens(p1) | _tokens(p2)
    pool = _tokens(fs.player1) | _tokens(fs.player2)
    return len(query & pool)


def day_offsets_for_dates(
    fixture_dates: list[datetime | date | None],
    *,
    today: date | None = None,
    min_offset: int = SETTLE_MIN_OFFSET,
    max_offset: int = SETTLE_MAX_OFFSET,
    base: tuple[int, ...] = DEFAULT_DAY_OFFSETS,
) -> tuple[int, ...]:
    """Map open-bet kickoffs to Flashscore day offsets (bounded window)."""
    today_d = today or datetime.now(timezone.utc).date()
    offsets: set[int] = set(base)
    for value in fixture_dates:
        if value is None:
            continue
        if isinstance(value, datetime):
            day = value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
        elif isinstance(value, date):
            day = value
        else:
            continue
        base_off = (day - today_d).days
        for delta in (-1, 0, 1):
            off = base_off + delta
            if min_offset <= off <= max_offset:
                offsets.add(off)
    return tuple(sorted(offsets))


# ── Client / cache ──────────────────────────────────────────────────────────


@dataclass
class _CacheBucket:
    matches: list[Any] = field(default_factory=list)
    fetched_at: float = 0.0
    last_error: str | None = None


class FlashscoreClient:
    """In-process Flashscore ninja feed client with soft-fail cache."""

    def __init__(
        self,
        *,
        sport: int = SPORT_FOOTBALL,
        day_offsets: tuple[int, ...] = DEFAULT_DAY_OFFSETS,
        cache_ttl_sec: float = CACHE_TTL_SEC,
    ) -> None:
        self.sport = sport
        self.day_offsets = day_offsets
        self.cache_ttl_sec = cache_ttl_sec
        self._by_day: dict[int, _CacheBucket] = {}
        self._merged: list[Any] = []
        self._merged_at: float = 0.0
        self._id_index: dict[str, Any] = {}

    def _merge(self) -> None:
        by_id: dict[str, Any] = {}
        for offset, bucket in self._by_day.items():
            for m in bucket.matches:
                mid = getattr(m, "id", None)
                if mid:
                    by_id[str(mid)] = m
        self._merged = list(by_id.values())
        self._id_index = by_id
        self._merged_at = time.monotonic()

    def refresh_cache(
        self,
        *,
        force: bool = False,
        extra_offsets: tuple[int, ...] | list[int] | None = None,
    ) -> list[Any]:
        if extra_offsets:
            merged_offsets = tuple(sorted(set(self.day_offsets) | {int(o) for o in extra_offsets}))
            self.day_offsets = merged_offsets

        now = time.monotonic()
        if (
            not force
            and self._merged
            and (now - self._merged_at) < self.cache_ttl_sec
            and all(off in self._by_day for off in self.day_offsets)
        ):
            return self._merged

        def _one(offset: int) -> tuple[int, list[Any] | None, str | None]:
            try:
                raw = fetch_feed_raw(self.sport, offset)
                parsed = parse_feed(raw, sport=self.sport)
                return offset, parsed, None
            except Exception as exc:  # noqa: BLE001 — soft-fail to last cache
                return offset, None, str(exc).strip() or repr(exc)

        workers = min(8, max(1, len(self.day_offsets)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, off) for off in self.day_offsets]
            for fut in as_completed(futures):
                offset, parsed, err = fut.result()
                bucket = self._by_day.setdefault(offset, _CacheBucket())
                if parsed is not None:
                    bucket.matches = parsed
                    bucket.fetched_at = time.monotonic()
                    bucket.last_error = None
                    if not parsed:
                        # Far-back offsets often empty (Flashscore retention ~7d); only alert near today.
                        if offset in (-1, 0, 1, 2):
                            logger.error(
                                "Flashscore day=%s returned 0 matches after HTTP success — "
                                "check FLASHSCORE_FSIGN rotation",
                                offset,
                            )
                        else:
                            logger.info(
                                "Flashscore day=%s empty (outside retention window)",
                                offset,
                            )
                else:
                    bucket.last_error = err
                    logger.warning(
                        "Flashscore fetch failed day=%s (%s) — keeping previous cache (%d matches)",
                        offset,
                        err,
                        len(bucket.matches),
                    )

        self._merge()
        return self._merged

    def ensure_fresh(self) -> list[Any]:
        return self.refresh_cache(force=False)

    def all_matches(self) -> list[Any]:
        return self.ensure_fresh()

    def find_match(
        self,
        home: str,
        away: str,
        league: str | None = None,
    ) -> FlashscoreFootballMatch | None:
        if self.sport != SPORT_FOOTBALL:
            return None
        matches = self.ensure_fresh()
        best: FlashscoreFootballMatch | None = None
        best_score = -99
        for m in matches:
            if not isinstance(m, FlashscoreFootballMatch):
                continue
            score = match_score_football(home, away, m, league=league)
            if score > best_score:
                best = m
                best_score = score
        if best is not None and best_score >= 2:
            return best
        return None

    def find_tennis_match(self, p1: str, p2: str) -> FlashscoreTennisMatch | None:
        if self.sport != SPORT_TENNIS:
            return None
        matches = self.ensure_fresh()
        best: FlashscoreTennisMatch | None = None
        best_score = -1
        for m in matches:
            if not isinstance(m, FlashscoreTennisMatch):
                continue
            score = match_score_tennis(p1, p2, m)
            if score > best_score:
                best = m
                best_score = score
        if best is not None and best_score >= 2:
            return best
        return None

    def score_for_fixture(
        self,
        home: str,
        away: str,
        league: str | None = None,
    ) -> dict[str, Any] | None:
        m = self.find_match(home, away, league=league)
        if m is None:
            return None
        return {
            "home_goals": m.home_goals,
            "away_goals": m.away_goals,
            "is_live": m.is_live,
            "is_finished": m.is_finished,
            "flashscore_match_id": m.id,
            "flashscore_url": m.url,
            "tournament": m.tournament,
            "home": m.home,
            "away": m.away,
        }

    def score_for_players(self, p1: str, p2: str) -> dict[str, Any] | None:
        m = self.find_tennis_match(p1, p2)
        if m is None:
            return None
        return {
            "player1": m.player1,
            "player2": m.player2,
            "sets": m.sets,
            "sets_won": m.sets_won,
            "games_p1": m.games_p1,
            "games_p2": m.games_p2,
            "is_live": m.is_live,
            "is_finished": m.is_finished,
            "flashscore_match_id": m.id,
            "flashscore_url": m.url,
            "tournament": m.tournament,
        }

    def finished_winner_for_settlement(self, p1: str, p2: str) -> str | None:
        m = self.find_tennis_match(p1, p2)
        if m is None or not m.is_finished:
            return None
        return m.winner()


# Module-level football client used by settlement.
_football_client: FlashscoreClient | None = None
_tennis_client: FlashscoreClient | None = None


def get_football_client() -> FlashscoreClient:
    global _football_client
    if _football_client is None:
        # Settlement default: last 10 days through +2 so Nordic/MX weekend cards are covered.
        offsets_raw = os.getenv("FLASHSCORE_DAY_OFFSETS", "-10,-9,-8,-7,-6,-5,-4,-3,-2,-1,0,1,2")
        offsets = tuple(int(x.strip()) for x in offsets_raw.split(",") if x.strip())
        _football_client = FlashscoreClient(
            sport=SPORT_FOOTBALL,
            day_offsets=offsets or DEFAULT_DAY_OFFSETS,
        )
    return _football_client


def get_tennis_client() -> FlashscoreClient:
    global _tennis_client
    if _tennis_client is None:
        _tennis_client = FlashscoreClient(sport=SPORT_TENNIS, day_offsets=(-1, 0, 1))
    return _tennis_client


def refresh_cache(
    *,
    force: bool = False,
    extra_offsets: tuple[int, ...] | list[int] | None = None,
) -> list[Any]:
    return get_football_client().refresh_cache(force=force, extra_offsets=extra_offsets)


def refresh_cache_for_fixture_dates(
    fixture_dates: list[datetime | date | None],
    *,
    force: bool = True,
) -> list[Any]:
    """Refresh feeds covering the kickoff dates of open bets (plus default window)."""
    offsets = day_offsets_for_dates(fixture_dates)
    logger.info("Flashscore settlement day offsets: %s", offsets)
    return refresh_cache(force=force, extra_offsets=offsets)


def ensure_fresh() -> list[Any]:
    return get_football_client().ensure_fresh()


def find_match(home: str, away: str, league: str | None = None) -> FlashscoreFootballMatch | None:
    return get_football_client().find_match(home, away, league=league)


def score_for_fixture(
    home: str,
    away: str,
    league: str | None = None,
) -> dict[str, Any] | None:
    return get_football_client().score_for_fixture(home, away, league=league)


def score_for_players(p1: str, p2: str) -> dict[str, Any] | None:
    return get_tennis_client().score_for_players(p1, p2)


def finished_winner_for_settlement(p1: str, p2: str) -> str | None:
    return get_tennis_client().finished_winner_for_settlement(p1, p2)
