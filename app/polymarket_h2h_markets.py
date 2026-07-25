"""Polymarket prices for H2H Strat markets (Goals + Win/Draw).

Primary event: moneyline (home / draw / away) as Yes/No binaries.
More-markets sibling ``{primary}-more-markets``: goal totals + BTTS.

Corners / SOT are not listed on Polymarket soccer today — those picks stay unpriced.

No HTML scraping — Gamma for market/token catalog, CLOB for live book tops.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.auto_resolve import _team_similarity
from app.polymarket_discovery import find_primary_event
from app.polymarket_exact_score import (
    _parse_json_field,
    _safe_float,
    books_for_tokens,
    fetch_gamma_event_by_slug,
    normalize_primary_slug,
)

logger = logging.getLogger(__name__)

MORE_MARKETS_SUFFIX = "-more-markets"

# H2H bet_types we can price on Polymarket
PRICEABLE_BET_TYPES = frozenset(
    {"h2h_home", "h2h_draw", "h2h_away", "h2h_o25", "h2h_o35", "h2h_btts"}
)

_TOTAL_LINE = {
    "h2h_o25": "2pt5",
    "h2h_o35": "3pt5",
}
_TOTAL_SLUG_RE = re.compile(r"-total-(?P<line>\d+pt\d+)\s*$", re.I)


def more_markets_event_slug(primary_slug: str) -> str:
    base = normalize_primary_slug(primary_slug or "")
    if base.endswith(MORE_MARKETS_SUFFIX):
        base = base[: -len(MORE_MARKETS_SUFFIX)]
    if not base:
        return ""
    return f"{base}{MORE_MARKETS_SUFFIX}"


def _markets(event: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not event:
        return []
    raw = event.get("markets") or []
    return [m for m in raw if isinstance(m, dict)]


def outcome_token_id(market: dict[str, Any], outcome_name: str) -> str | None:
    """CLOB token for a named outcome (Yes / Over / Under / …)."""
    outcomes = _parse_json_field(market.get("outcomes"))
    token_ids = _parse_json_field(market.get("clobTokenIds"))
    if not isinstance(outcomes, list) or not isinstance(token_ids, list):
        return None
    want = outcome_name.strip().lower()
    for i, name in enumerate(outcomes):
        if str(name).strip().lower() == want and i < len(token_ids):
            tid = token_ids[i]
            return str(tid) if tid is not None else None
    return None


def gamma_outcome_price(market: dict[str, Any], outcome_name: str) -> float | None:
    outcomes = _parse_json_field(market.get("outcomes"))
    prices = _parse_json_field(market.get("outcomePrices"))
    if not isinstance(outcomes, list) or not isinstance(prices, list):
        return None
    want = outcome_name.strip().lower()
    for i, name in enumerate(outcomes):
        if str(name).strip().lower() == want and i < len(prices):
            return _safe_float(prices[i])
    return None


def decimal_odds_from_ask(ask: float | None) -> float | None:
    if ask is None or ask <= 0 or ask >= 1:
        return None
    return round(1.0 / ask, 3)


def _mtype(market: dict[str, Any]) -> str:
    return str(market.get("sportsMarketType") or "").strip().lower()


def _slug(market: dict[str, Any]) -> str:
    return str(market.get("slug") or "").strip().lower()


def _title_blob(market: dict[str, Any]) -> str:
    return " ".join(
        str(market.get(k) or "")
        for k in ("groupItemTitle", "question", "slug")
    ).lower()


def match_moneyline_market(
    markets: list[dict[str, Any]],
    *,
    side: str,
    home: str,
    away: str,
) -> dict[str, Any] | None:
    """Pick the Yes/No moneyline market for home / draw / away (DG orientation)."""
    mlines = [m for m in markets if _mtype(m) == "moneyline"]
    if not mlines:
        return None

    side = side.lower().strip()
    if side == "draw":
        for m in mlines:
            blob = _title_blob(m)
            slug = _slug(m)
            if "draw" in slug or "draw" in blob:
                return m
        return None

    target = home if side == "home" else away
    best: dict[str, Any] | None = None
    best_score = 0.0
    for m in mlines:
        blob = _title_blob(m)
        if "draw" in _slug(m) or "draw" in blob:
            continue
        # Prefer groupItemTitle (usually just the team name).
        title = str(m.get("groupItemTitle") or "").strip() or str(m.get("question") or "")
        score = _team_similarity(target, title)
        # Also try against the slug tail / question.
        score = max(score, _team_similarity(target, blob))
        if score > best_score:
            best_score = score
            best = m
    if best is not None and best_score >= 0.35:
        return best
    return None


def match_totals_over(
    markets: list[dict[str, Any]],
    *,
    line_token: str,
) -> dict[str, Any] | None:
    """Full-match goal total for a line like ``2pt5`` / ``3pt5``."""
    want = line_token.lower().strip()
    for m in markets:
        if _mtype(m) != "totals":
            continue
        slug = _slug(m)
        # Skip half totals which use different sportsMarketType, but be defensive.
        if "first-half" in slug or "second-half" in slug or "team-total" in slug:
            continue
        m_slug = _TOTAL_SLUG_RE.search(slug)
        if m_slug and m_slug.group("line").lower() == want:
            return m
        # Fallback: group title "O/U 2.5"
        title = str(m.get("groupItemTitle") or "")
        pretty = want.replace("pt", ".")
        if pretty in title.replace(" ", "") or f"o/u {pretty}" in title.lower():
            return m
    return None


def match_btts(markets: list[dict[str, Any]]) -> dict[str, Any] | None:
    for m in markets:
        if _mtype(m) == "both_teams_to_score":
            return m
        slug = _slug(m)
        if slug.endswith("-btts") and "half" not in slug:
            return m
    return None


def resolve_h2h_market(
    *,
    bet_type: str,
    primary_markets: list[dict[str, Any]],
    more_markets: list[dict[str, Any]],
    home: str,
    away: str,
    flipped: bool = False,
) -> tuple[dict[str, Any] | None, str, str]:
    """Return (market, outcome_name, event_kind) for a H2H bet_type.

    ``event_kind`` is ``primary`` or ``more`` (for URL selection).
    ``flipped`` is informational — we match moneyline by team name, not seat.
    """
    del flipped  # matching is by team name; DG home/away already correct
    bt = (bet_type or "").strip().lower()

    if bt == "h2h_home":
        return match_moneyline_market(primary_markets, side="home", home=home, away=away), "Yes", "primary"
    if bt == "h2h_away":
        return match_moneyline_market(primary_markets, side="away", home=home, away=away), "Yes", "primary"
    if bt == "h2h_draw":
        return match_moneyline_market(primary_markets, side="draw", home=home, away=away), "Yes", "primary"
    if bt in _TOTAL_LINE:
        m = match_totals_over(more_markets, line_token=_TOTAL_LINE[bt])
        return m, "Over", "more"
    if bt == "h2h_btts":
        return match_btts(more_markets), "Yes", "more"
    return None, "", ""


def _fill_price(
    market: dict[str, Any],
    outcome: str,
    books: dict[str, dict[str, float | None]],
) -> tuple[float | None, str]:
    token = outcome_token_id(market, outcome)
    if token:
        top = books.get(token) or {}
        ask = _safe_float(top.get("ask"))
        if ask is not None and 0 < ask < 1:
            return ask, "clob_ask"
    gamma = gamma_outcome_price(market, outcome)
    if gamma is not None and 0 < gamma < 1:
        return gamma, "gamma_ask"
    # Gamma bestAsk is often for the Yes/first outcome — only trust when outcome is Yes/Over idx0
    best_ask = _safe_float(market.get("bestAsk"))
    if best_ask is not None and 0 < best_ask < 1 and outcome.lower() in {"yes", "over"}:
        outcomes = _parse_json_field(market.get("outcomes"))
        if isinstance(outcomes, list) and outcomes and str(outcomes[0]).strip().lower() == outcome.lower():
            return best_ask, "gamma_best_ask"
    return None, ""


def price_h2h_fixture(
    *,
    home: str,
    away: str,
    kickoff: Any,
    picks: list[dict[str, Any]],
    use_clob: bool = True,
) -> dict[str, Any]:
    """Price a list of H2H picks for one fixture against Polymarket.

    Returns::
        {
          error, polymarket_slug, more_markets_slug, polymarket_url,
          flipped, priced: {bet_type|key: {odds, price, …}}
        }
    """
    event = find_primary_event(home, away, kickoff)
    if not event:
        return {"error": "not yet listed on Polymarket", "priced": {}}

    primary_slug = normalize_primary_slug(str(event.get("slug") or ""))
    more_slug = more_markets_event_slug(primary_slug)
    primary_event = fetch_gamma_event_by_slug(primary_slug) or event
    more_event = fetch_gamma_event_by_slug(more_slug) if more_slug else None

    primary_markets = _markets(primary_event)
    more_mkts = _markets(more_event)
    flipped = bool(event.get("flipped"))

    # Resolve markets first so we can batch CLOB fetches.
    resolved: list[tuple[dict[str, Any], dict[str, Any], str, str]] = []
    for pick in picks:
        bt = str(pick.get("bet_type") or "")
        if bt not in PRICEABLE_BET_TYPES:
            continue
        market, outcome, kind = resolve_h2h_market(
            bet_type=bt,
            primary_markets=primary_markets,
            more_markets=more_mkts,
            home=home,
            away=away,
            flipped=flipped,
        )
        if market is None:
            continue
        resolved.append((pick, market, outcome, kind))

    books: dict[str, dict[str, float | None]] = {}
    if use_clob and resolved:
        tokens = []
        for _, market, outcome, _ in resolved:
            tid = outcome_token_id(market, outcome)
            if tid:
                tokens.append(tid)
        books = books_for_tokens(tokens)

    priced: dict[str, dict[str, Any]] = {}
    for pick, market, outcome, kind in resolved:
        ask, source = _fill_price(market, outcome, books)
        odds = decimal_odds_from_ask(ask)
        if odds is None:
            continue
        event_slug = more_slug if kind == "more" and more_slug else primary_slug
        key = _pick_key(pick)
        priced[key] = {
            "bet_type": pick.get("bet_type"),
            "odds": odds,
            "price": ask,
            "price_source": source,
            "outcome": outcome,
            "market_slug": market.get("slug"),
            "polymarket_url": f"https://polymarket.com/event/{event_slug}" if event_slug else None,
            "event_kind": kind,
        }

    return {
        "error": "" if priced else "no tradeable H2H markets",
        "polymarket_slug": primary_slug,
        "more_markets_slug": more_slug,
        "polymarket_url": f"https://polymarket.com/event/{primary_slug}" if primary_slug else None,
        "flipped": flipped,
        "priced": priced,
    }


def _pick_key(pick: dict[str, Any]) -> str:
    """Stable key within a fixture group."""
    return "|".join(
        [
            str(pick.get("bet_type") or ""),
            str(pick.get("team_name") or ""),
            str(pick.get("label") or ""),
        ]
    )


def attach_polymarket_odds(
    picks: list[dict[str, Any]],
    *,
    use_clob: bool = True,
) -> list[dict[str, Any]]:
    """Mutate-copy picks with Polymarket decimal odds + URL when available."""
    if not picks:
        return []

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    order: list[tuple[str, str, str]] = []
    for p in picks:
        home = str(p.get("home") or "").strip()
        away = str(p.get("away") or "").strip()
        kickoff = str(p.get("fixture_date") or "")
        key = (home, away, kickoff)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(dict(p))

    out: list[dict[str, Any]] = []
    for key in order:
        group = groups[key]
        home, away, kickoff = key
        if not home or not away:
            out.extend(group)
            continue
        try:
            result = price_h2h_fixture(
                home=home,
                away=away,
                kickoff=kickoff or None,
                picks=group,
                use_clob=use_clob,
            )
        except Exception as exc:  # noqa: BLE001 — one fixture must not kill the batch
            logger.warning("H2H Polymarket pricing failed for %s vs %s: %s", home, away, exc)
            out.extend(group)
            continue

        priced = result.get("priced") or {}
        for pick in group:
            row = priced.get(_pick_key(pick))
            if row:
                pick["odds"] = row.get("odds")
                pick["polymarket_url"] = row.get("polymarket_url")
                pick["pm_price"] = row.get("price")
                pick["pm_price_source"] = row.get("price_source")
            elif not pick.get("polymarket_url") and result.get("polymarket_url"):
                # Still surface the event page even when this market isn't listed.
                if str(pick.get("bet_type") or "") in PRICEABLE_BET_TYPES:
                    pick["polymarket_url"] = (
                        f"https://polymarket.com/event/{result['more_markets_slug']}"
                        if result.get("more_markets_slug")
                        and str(pick.get("bet_type") or "") in {"h2h_o25", "h2h_o35", "h2h_btts"}
                        else result.get("polymarket_url")
                    )
            out.append(pick)
    return out
