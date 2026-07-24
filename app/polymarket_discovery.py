"""Map a DataGaffer fixture to its Polymarket primary event slug.

Polymarket football events are slugged ``{league}-{home}-{away}-{YYYY-MM-DD}``
(e.g. ``mex-tij-leo-2026-07-24``) with sibling events ``…-exact-score`` and
``…-more-markets``. The abbreviations are not derivable from team names, so we
resolve the slug through Gamma's search endpoint and score candidates on team
name similarity plus kickoff proximity.

Polymarket's kickoff date is local to the venue while DataGaffer stores UTC, so
candidates within one day of the fixture date are accepted.
"""
from __future__ import annotations

from datetime import date, datetime
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

from app.auto_resolve import _team_similarity

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

# Only dated head-to-head events carry exact-score siblings; this rejects
# futures ("liga-mx-2026-apertura-champion") and the sibling events themselves.
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


def search_events(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
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


def parse_kickoff_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
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


def _score_candidate(
    event: dict[str, Any],
    *,
    home: str,
    away: str,
    kickoff: date | None,
    max_day_delta: int,
) -> dict[str, Any] | None:
    slug = str(event.get("slug") or "")
    if not slug or slug.endswith(_SIBLING_SUFFIXES):
        return None
    slug_date = _slug_date(slug)
    if slug_date is None:
        return None
    if kickoff is not None and abs((slug_date - kickoff).days) > max_day_delta:
        return None

    teams = _title_teams(str(event.get("title") or ""))
    if teams is None:
        return None
    pm_home, pm_away = teams

    straight = min(_team_similarity(home, pm_home), _team_similarity(away, pm_away))
    flipped = min(_team_similarity(home, pm_away), _team_similarity(away, pm_home))
    if max(straight, flipped) < MIN_TEAM_SIMILARITY:
        return None

    is_flipped = flipped > straight
    similarity = flipped if is_flipped else straight
    day_delta = abs((slug_date - kickoff).days) if kickoff is not None else 0
    return {
        "slug": slug,
        "title": event.get("title"),
        "event_id": event.get("id"),
        "slug_date": slug_date.isoformat(),
        "day_delta": day_delta,
        "similarity": round(similarity, 3),
        # True when Polymarket lists the fixture with sides reversed, meaning a
        # DataGaffer "2-1" is Polymarket's "1-2".
        "flipped": is_flipped,
        "pm_home": pm_home,
        "pm_away": pm_away,
        "score": round(similarity - day_delta * 0.05 - (0.05 if is_flipped else 0.0), 4),
    }


def find_primary_event(
    home: str,
    away: str,
    kickoff: Any = None,
    *,
    max_day_delta: int = 1,
    use_cache: bool = True,
) -> dict[str, Any] | None:
    """Best-matching Polymarket fixture event, or None when not listed."""
    home, away = str(home or "").strip(), str(away or "").strip()
    if not home or not away:
        return None
    kickoff_date = parse_kickoff_date(kickoff)
    cache_key = f"{home}|{away}|{kickoff_date}"

    if use_cache:
        with _cache_lock:
            hit = _cache.get(cache_key)
        if hit and (time.time() - hit[0]) < SLUG_CACHE_TTL_SEC:
            return hit[1]

    candidates: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    # Combined query first (highest precision); single names catch cases where
    # DataGaffer and Polymarket disagree on one club's naming.
    for query in (f"{home} {away}", home, away):
        for event in search_events(query):
            slug = str(event.get("slug") or "")
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            scored = _score_candidate(
                event,
                home=home,
                away=away,
                kickoff=kickoff_date,
                max_day_delta=max_day_delta,
            )
            if scored:
                candidates.append(scored)
        if candidates:
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
