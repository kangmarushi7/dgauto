"""Polymarket football exact-score prices via Gamma catalog + CLOB books.

Primary event slug example: ``bra-san-cha-2026-07-25``
Exact-score sibling: ``{primarySlug}-exact-score``

~17 binary Yes/No markets (``sportsMarketType=soccer_exact_score``):
scorelines 0-0 .. 3-3 plus ``any-other``.

No HTML scraping — Gamma for market/token catalog, CLOB for live book tops.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import json
import logging
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

GAMMA_BASE = (os.getenv("POLYMARKET_GAMMA_URL") or "https://gamma-api.polymarket.com").rstrip("/")
CLOB_BASE = (os.getenv("POLYMARKET_CLOB_URL") or "https://clob.polymarket.com").rstrip("/")
USER_AGENT = os.getenv(
    "POLYMARKET_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)
HTTP_TIMEOUT = float(os.getenv("POLYMARKET_HTTP_TIMEOUT", "20"))
CLOB_WORKERS = int(os.getenv("POLYMARKET_CLOB_WORKERS", "8"))

EXACT_SCORE_SUFFIX = "-exact-score"
SPORTS_TYPE = "soccer_exact_score"

# Slug ends with -exact-score-{h}-{a} or -exact-score-any-other
_SCORE_SLUG_RE = re.compile(
    r"exact-score-(?:(?P<h>\d+)-(?P<a>\d+)|(?P<other>any-other))\s*$",
    re.I,
)
# Question / group title: "… 2 - 1 …" or "Exact Score: Home 0 - 0 Away?"
_SCORE_DIGITS_RE = re.compile(r"(\d+)\s*[-–:]\s*(\d+)")


@dataclass
class ExactScorePrice:
    label: str
    home_goals: int | None
    away_goals: int | None
    yes_token_id: str
    bid: float | None
    ask: float | None
    mid: float | None
    gamma_yes: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "homeGoals": self.home_goals,
            "awayGoals": self.away_goals,
            "yesTokenId": self.yes_token_id,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "gammaYes": self.gamma_yes,
        }


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


def _http_get_json(url: str) -> Any:
    req = Request(url, headers=_headers(), method="GET")
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 — fixed Polymarket hosts
        return json.load(resp)


def _parse_json_field(value: Any) -> Any:
    """Gamma often returns outcomes / clobTokenIds / outcomePrices as JSON strings."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value
    return value


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mid(bid: float | None, ask: float | None) -> float | None:
    if bid is not None and ask is not None:
        return round((bid + ask) / 2.0, 6)
    return bid if bid is not None else ask


def normalize_primary_slug(slug: str) -> str:
    """Strip trailing ``-exact-score`` (and scoreline suffix) down to the fixture slug."""
    text = (slug or "").strip().strip("/")
    if not text:
        return ""
    # If caller passed a market slug like …-exact-score-1-0, cut at -exact-score
    idx = text.find(EXACT_SCORE_SUFFIX)
    if idx >= 0:
        return text[:idx]
    return text


def exact_score_event_slug(primary_slug: str) -> str:
    base = normalize_primary_slug(primary_slug)
    return f"{base}{EXACT_SCORE_SUFFIX}"


def fetch_gamma_event_by_slug(slug: str) -> dict[str, Any] | None:
    """GET /events?slug=… → first event dict or None."""
    url = f"{GAMMA_BASE}/events?slug={quote(slug, safe='')}"
    try:
        payload = _http_get_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Gamma event fetch failed slug=%s: %s", slug, exc)
        return None
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else None
    if isinstance(payload, dict):
        # Some gateways wrap as {events:[…]} or return a single object
        events = payload.get("events")
        if isinstance(events, list) and events and isinstance(events[0], dict):
            return events[0]
        if payload.get("slug") or payload.get("markets") is not None:
            return payload
    return None


def discover_primary_event(primary_slug: str) -> dict[str, Any] | None:
    return fetch_gamma_event_by_slug(normalize_primary_slug(primary_slug))


def fetch_exact_score_sibling(primary_slug: str) -> dict[str, Any] | None:
    return fetch_gamma_event_by_slug(exact_score_event_slug(primary_slug))


def parse_scoreline(
    *,
    slug: str = "",
    question: str = "",
    group_item_title: str = "",
) -> tuple[str, int | None, int | None]:
    """Return (label, homeGoals, awayGoals). any-other → (label, None, None)."""
    slug_l = (slug or "").strip()
    m = _SCORE_SLUG_RE.search(slug_l)
    if m:
        if m.group("other"):
            return "Any Other Score", None, None
        h, a = int(m.group("h")), int(m.group("a"))
        return f"{h}-{a}", h, a

    for text in (group_item_title, question):
        low = (text or "").strip().lower()
        if "any other" in low:
            return "Any Other Score", None, None
        dm = _SCORE_DIGITS_RE.search(text or "")
        if dm:
            h, a = int(dm.group(1)), int(dm.group(2))
            return f"{h}-{a}", h, a

    label = (group_item_title or question or slug_l or "unknown").strip()
    return label, None, None


def yes_token_id_from_market(market: dict[str, Any]) -> str | None:
    """Pick Yes CLOB token: clobTokenIds[index of outcomes 'Yes']."""
    outcomes = _parse_json_field(market.get("outcomes"))
    token_ids = _parse_json_field(market.get("clobTokenIds"))
    if not isinstance(outcomes, list) or not isinstance(token_ids, list):
        return None
    yes_idx = None
    for i, name in enumerate(outcomes):
        if str(name).strip().lower() == "yes":
            yes_idx = i
            break
    if yes_idx is None or yes_idx >= len(token_ids):
        return None
    tid = token_ids[yes_idx]
    return str(tid) if tid is not None else None


def gamma_yes_price(market: dict[str, Any]) -> float | None:
    outcomes = _parse_json_field(market.get("outcomes"))
    prices = _parse_json_field(market.get("outcomePrices"))
    if isinstance(outcomes, list) and isinstance(prices, list):
        for i, name in enumerate(outcomes):
            if str(name).strip().lower() == "yes" and i < len(prices):
                return _safe_float(prices[i])
    # Fallbacks often present on Gamma market objects
    for key in ("bestBid", "lastTradePrice"):
        val = _safe_float(market.get(key))
        if val is not None and key == "lastTradePrice":
            return val
    return None


def get_orderbook_top(token_id: str) -> tuple[float | None, float | None]:
    """Best bid = max bid price, best ask = min ask price from CLOB book."""
    if not token_id:
        return None, None
    url = f"{CLOB_BASE}/book?token_id={quote(str(token_id), safe='')}"
    try:
        book = _http_get_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("CLOB book failed token=%s…: %s", str(token_id)[:12], exc)
        return None, None
    if not isinstance(book, dict):
        return None, None

    bids = book.get("bids") or []
    asks = book.get("asks") or []
    bid_prices = [_safe_float(level.get("price")) for level in bids if isinstance(level, dict)]
    ask_prices = [_safe_float(level.get("price")) for level in asks if isinstance(level, dict)]
    bid_prices = [p for p in bid_prices if p is not None]
    ask_prices = [p for p in ask_prices if p is not None]
    best_bid = max(bid_prices) if bid_prices else None
    best_ask = min(ask_prices) if ask_prices else None
    return best_bid, best_ask


def _gamma_book_fallback(market: dict[str, Any]) -> tuple[float | None, float | None]:
    return _safe_float(market.get("bestBid")), _safe_float(market.get("bestAsk"))


def iter_exact_score_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    markets = event.get("markets") or []
    out: list[dict[str, Any]] = []
    for m in markets:
        if not isinstance(m, dict):
            continue
        mtype = str(m.get("sportsMarketType") or "").strip().lower()
        slug = str(m.get("slug") or "")
        if mtype == SPORTS_TYPE or EXACT_SCORE_SUFFIX in slug:
            out.append(m)
    return out


def _sort_key(row: ExactScorePrice) -> tuple:
    if row.home_goals is None or row.away_goals is None:
        return (1, 99, 99, row.label)
    return (0, row.home_goals + row.away_goals, row.home_goals, row.away_goals, row.label)


def map_exact_score_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Catalog rows: label, goals, yes token, gamma price (no CLOB yet)."""
    rows: list[dict[str, Any]] = []
    for market in iter_exact_score_markets(event):
        yes_id = yes_token_id_from_market(market)
        if not yes_id:
            continue
        label, hg, ag = parse_scoreline(
            slug=str(market.get("slug") or ""),
            question=str(market.get("question") or ""),
            group_item_title=str(market.get("groupItemTitle") or ""),
        )
        g_bid, g_ask = _gamma_book_fallback(market)
        rows.append(
            {
                "label": label,
                "homeGoals": hg,
                "awayGoals": ag,
                "yesTokenId": yes_id,
                "gammaYes": gamma_yes_price(market),
                "gammaBid": g_bid,
                "gammaAsk": g_ask,
                "marketSlug": market.get("slug"),
                "conditionId": market.get("conditionId"),
            }
        )
    rows.sort(
        key=lambda r: (
            1 if r["homeGoals"] is None else 0,
            (r["homeGoals"] if r["homeGoals"] is not None else 99)
            + (r["awayGoals"] if r["awayGoals"] is not None else 99),
            r["homeGoals"] if r["homeGoals"] is not None else 99,
            r["awayGoals"] if r["awayGoals"] is not None else 99,
            r["label"],
        )
    )
    return rows


def pull_exact_score_prices(
    primary_slug: str,
    *,
    use_clob: bool = True,
    clob_workers: int | None = None,
) -> dict[str, Any]:
    """Discover primary → fetch sibling → map Yes tokens → CLOB tops.

    Returns::
        {
          primarySlug, exactScoreSlug, eventTitle, eventId,
          prices: [{label, homeGoals, awayGoals, yesTokenId, bid, ask, mid, gammaYes}, ...]
        }
    """
    primary = normalize_primary_slug(primary_slug)
    if not primary:
        return {
            "ok": False,
            "error": "empty primary slug",
            "primarySlug": "",
            "exactScoreSlug": "",
            "prices": [],
        }

    sibling_slug = exact_score_event_slug(primary)
    # Optional: confirm primary exists (soccer-live-bot discover step)
    primary_event = discover_primary_event(primary)
    event = fetch_exact_score_sibling(primary)
    if event is None:
        return {
            "ok": False,
            "error": f"exact-score event not found for slug={sibling_slug}",
            "primarySlug": primary,
            "exactScoreSlug": sibling_slug,
            "primaryFound": primary_event is not None,
            "prices": [],
        }

    catalog = map_exact_score_markets(event)
    workers = clob_workers if clob_workers is not None else CLOB_WORKERS
    book_by_token: dict[str, tuple[float | None, float | None]] = {}

    if use_clob and catalog:
        tokens = [str(r["yesTokenId"]) for r in catalog]

        def _one(tid: str) -> tuple[str, float | None, float | None]:
            bid, ask = get_orderbook_top(tid)
            return tid, bid, ask

        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tokens)))) as pool:
            futs = [pool.submit(_one, tid) for tid in tokens]
            for fut in as_completed(futs):
                tid, bid, ask = fut.result()
                book_by_token[tid] = (bid, ask)

    prices: list[ExactScorePrice] = []
    for row in catalog:
        tid = str(row["yesTokenId"])
        bid, ask = book_by_token.get(tid, (None, None))
        if bid is None and ask is None:
            bid, ask = row.get("gammaBid"), row.get("gammaAsk")
        prices.append(
            ExactScorePrice(
                label=str(row["label"]),
                home_goals=row["homeGoals"],
                away_goals=row["awayGoals"],
                yes_token_id=tid,
                bid=bid,
                ask=ask,
                mid=_mid(bid, ask),
                gamma_yes=row.get("gammaYes"),
            )
        )

    prices.sort(key=_sort_key)
    return {
        "ok": True,
        "primarySlug": primary,
        "exactScoreSlug": sibling_slug,
        "eventId": event.get("id"),
        "eventTitle": event.get("title"),
        "primaryFound": primary_event is not None,
        "primaryTitle": (primary_event or {}).get("title"),
        "marketCount": len(prices),
        "prices": [p.to_dict() for p in prices],
    }


def exact_score_prices_array(primary_slug: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Convenience: just the prices array (empty on failure)."""
    result = pull_exact_score_prices(primary_slug, **kwargs)
    return list(result.get("prices") or [])
