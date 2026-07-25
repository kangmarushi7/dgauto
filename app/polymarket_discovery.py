"""Map a DataGaffer fixture to its Polymarket primary event slug.

Polymarket football events are slugged ``{league}-{home}-{away}-{YYYY-MM-DD}``
(e.g. ``mex-tij-leo-2026-07-24``) with sibling events ``…-exact-score`` and
``…-more-markets``. The abbreviations are not derivable from team names, so we
resolve the slug through Gamma's search endpoint and score candidates on team
name similarity plus kickoff proximity.

Two quirks the matcher has to survive:

* The date in the slug is unreliable — it can trail the real kickoff by a day or
  two (``mex-tig-asl-2026-07-24`` actually kicks off ``2026-07-26 03:00Z``). Each
  event payload carries the true kickoff (``markets[].gameStartTime`` /
  ``startTime`` / ``endDate``), so proximity is scored against that, not the slug.
* DataGaffer often uses short club names ("NYCFC", "Chicago") that Gamma's search
  will not surface. Queries are expanded through the alias table so the fuller
  Polymarket names ("New York City FC", "Chicago Fire FC") are searched too.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import logging
import os
import re
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.auto_resolve import _team_similarity, _team_variants

logger = logging.getLogger(__name__)

GAMMA_BASE = (os.getenv("POLYMARKET_GAMMA_URL") or "https://gamma-api.polymarket.com").rstrip("/")
USER_AGENT = os.getenv(
    "POLYMARKET_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)
HTTP_TIMEOUT = float(os.getenv("POLYMARKET_HTTP_TIMEOUT", "20"))
SLUG_CACHE_TTL_SEC = int(os.getenv("POLYMARKET_SLUG_CACHE_TTL", "1800"))
MIN_TEAM_SIMILARITY = float(os.getenv("POLYMARKET_MIN_TEAM_SIMILARITY", "0.45"))
# Max gap between DataGaffer's kickoff and the Polymarket event's real kickoff.
# Wide enough to absorb clock/rounding differences, tight enough not to grab the
# same pairing from an adjacent week.
KICKOFF_WINDOW_HOURS = float(os.getenv("POLYMARKET_KICKOFF_WINDOW_HOURS", "30"))

# Head-to-head slugs end in a date; this pulls it out for the fallback path when
# the event carries no kickoff timestamp.
_DATED_SLUG_RE = re.compile(r"^[a-z0-9-]+-(?P<date>\d{4}-\d{2}-\d{2})$")
_SIBLING_SUFFIXES = ("-exact-score", "-more-markets")
_TITLE_SPLIT_RE = re.compile(r"\s+vs\.?\s+", re.I)

_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_cache_lock = threading.Lock()


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


def _http_get_json(url: str) -> Any:
    req = Request(url, headers=_headers(), method="GET")
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 — fixed Polymarket host
        return json.load(resp)


def search_events(query: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """Gamma full-text search restricted to events."""
    if not query.strip():
        return []
    url = f"{GAMMA_BASE}/public-search?q={quote(query.strip())}&limit_per_type={int(limit)}"
    try:
        payload = _http_get_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Gamma search failed q=%r: %s", query, exc)
        return []
    events = (payload or {}).get("events") if isinstance(payload, dict) else None
    return [e for e in (events or []) if isinstance(e, dict)]


def parse_kickoff_dt(value: Any) -> datetime | None:
    """Parse Gamma / DataGaffer timestamps to an aware UTC datetime.

    Handles ISO 8601 with ``Z``, space-separated stamps, and short ``+00`` zone
    offsets (``2026-07-26 03:00:00+00``) that Polymarket returns on markets.
    """
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    # "+00" / "-06" short offsets → "+00:00" / "-06:00"
    if re.search(r"[+-]\d{2}$", text):
        text += ":00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_kickoff_date(value: Any) -> date | None:
    dt = parse_kickoff_dt(value)
    return dt.date() if dt else None


def _event_kickoff(event: dict[str, Any]) -> datetime | None:
    """Real kickoff from the event payload (not the slug date).

    ``startDate`` is the listing/creation time, so it is deliberately skipped;
    ``gameStartTime`` on a market is the authoritative kickoff.
    """
    for market in event.get("markets") or []:
        if isinstance(market, dict):
            dt = parse_kickoff_dt(market.get("gameStartTime"))
            if dt:
                return dt
    for key in ("startTime", "endDate", "eventDate"):
        dt = parse_kickoff_dt(event.get(key))
        if dt:
            return dt
    return None


def _slug_date(slug: str) -> date | None:
    m = _DATED_SLUG_RE.match(slug)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("date"), "%Y-%m-%d").date()
    except ValueError:
        return None


def _title_teams(title: str) -> tuple[str, str] | None:
    parts = _TITLE_SPLIT_RE.split(str(title or "").strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    home, away = parts[0].strip(), parts[1].strip()
    if not home or not away:
        return None
    return home, away


def _longest_variant(name: str) -> str:
    """Fullest alias for a club name — the best term to hand Gamma's search."""
    variants = _team_variants(name)
    return max(variants, key=len) if variants else name


def _search_queries(home: str, away: str) -> list[list[str]]:
    """Query tiers, tried in order until one yields candidates.

    Tier 1 is the raw names as DataGaffer gives them; tier 2 expands both sides to
    their fullest alias (rescues short names like "NYCFC"); tier 3 falls back to
    single-team searches for when the two feeds disagree on one club's name.
    """
    home_long, away_long = _longest_variant(home), _longest_variant(away)
    tiers: list[list[str]] = [[f"{home} {away}"]]
    expanded = f"{home_long} {away_long}"
    if expanded.lower() != f"{home} {away}".lower():
        tiers.append([expanded])
    singles = list(dict.fromkeys([home_long, away_long, home, away]))
    tiers.append(singles)
    return tiers


def _score_candidate(
    event: dict[str, Any],
    *,
    home: str,
    away: str,
    kickoff: datetime | None,
) -> dict[str, Any] | None:
    slug = str(event.get("slug") or "")
    if not slug or slug.endswith(_SIBLING_SUFFIXES):
        return None

    teams = _title_teams(str(event.get("title") or ""))
    if teams is None:  # futures ("MLS Cup Winner") have no "vs" — skip them
        return None
    pm_home, pm_away = teams

    # Reject the wrong week/leg using the event's real kickoff; fall back to the
    # slug date only when the payload has no kickoff timestamp.
    event_kickoff = _event_kickoff(event)
    hours_off: float | None = None
    if kickoff is not None:
        if event_kickoff is not None:
            hours_off = abs((event_kickoff - kickoff).total_seconds()) / 3600.0
            if hours_off > KICKOFF_WINDOW_HOURS:
                return None
        else:
            slug_date = _slug_date(slug)
            if slug_date is None:
                return None
            if abs((slug_date - kickoff.date()).days) > 1:
                return None
            hours_off = abs((slug_date - kickoff.date()).days) * 24.0

    straight = min(_team_similarity(home, pm_home), _team_similarity(away, pm_away))
    flipped = min(_team_similarity(home, pm_away), _team_similarity(away, pm_home))
    if max(straight, flipped) < MIN_TEAM_SIMILARITY:
        return None

    is_flipped = flipped > straight
    similarity = flipped if is_flipped else straight
    proximity_penalty = (hours_off or 0.0) / 24.0 * 0.05
    return {
        "slug": slug,
        "title": event.get("title"),
        "event_id": event.get("id"),
        "slug_date": _slug_date(slug).isoformat() if _slug_date(slug) else None,
        "kickoff": event_kickoff.isoformat() if event_kickoff else None,
        "hours_off": round(hours_off, 1) if hours_off is not None else None,
        "similarity": round(similarity, 3),
        # True when Polymarket lists the fixture with sides reversed, meaning a
        # DataGaffer "2-1" is Polymarket's "1-2".
        "flipped": is_flipped,
        "pm_home": pm_home,
        "pm_away": pm_away,
        "score": round(similarity - proximity_penalty - (0.05 if is_flipped else 0.0), 4),
    }


def find_primary_event(
    home: str,
    away: str,
    kickoff: Any = None,
    *,
    use_cache: bool = True,
) -> dict[str, Any] | None:
    """Best-matching Polymarket fixture event, or None when not listed."""
    home, away = str(home or "").strip(), str(away or "").strip()
    if not home or not away:
        return None
    kickoff_dt = parse_kickoff_dt(kickoff)
    cache_key = f"{home}|{away}|{kickoff_dt.isoformat() if kickoff_dt else None}"

    if use_cache:
        with _cache_lock:
            hit = _cache.get(cache_key)
        if hit and (time.time() - hit[0]) < SLUG_CACHE_TTL_SEC:
            return hit[1]

    candidates: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for tier in _search_queries(home, away):
        for query in tier:
            for event in search_events(query):
                slug = str(event.get("slug") or "")
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                scored = _score_candidate(event, home=home, away=away, kickoff=kickoff_dt)
                if scored:
                    candidates.append(scored)
        if candidates:  # a tier produced matches — no need to widen the search
            break

    best = max(candidates, key=lambda c: c["score"]) if candidates else None
    with _cache_lock:
        _cache[cache_key] = (time.time(), best)
    return best


def find_primary_slug(home: str, away: str, kickoff: Any = None, **kwargs: Any) -> str | None:
    event = find_primary_event(home, away, kickoff, **kwargs)
    return str(event["slug"]) if event else None


def clear_slug_cache() -> None:
    with _cache_lock:
        _cache.clear()
