"""Correct-score baskets: buy DataGaffer's top scorelines on Polymarket.

Strategy
--------
Take the top N (5, else 4) scorelines from the DataGaffer Dixon–Coles grid,
price each on Polymarket's ``…-exact-score`` event, then stake the basket so
**every** leg returns the same payout. With equal payouts a single winning leg
covers the whole basket, so the basket is profitable whenever at least one of
the bought scorelines lands.

Why equal payouts guarantee it
------------------------------
Buying a leg at Polymarket price ``p`` (dollars per share, share settles at $1)
with stake ``s`` yields ``s / p`` on a hit. Setting ``s_i = B · p_i / Σp`` makes
every payout ``B / Σp``, so a single hit nets ``B · (1 − Σp) / Σp`` regardless of
*which* leg hit. That is positive exactly when ``Σp < 1``, which becomes the
qualifying condition: a basket is only played when the summed ask prices leave a
margin (``CS_MIN_GUARANTEED_ROI``) after slippage.

Between the top-5 and top-4 baskets the higher expected value wins, with ties
going to the wider basket; the guarantee is enforced as a hard constraint on
both.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import os
import re
import uuid
from typing import Any

from app.bet_log import compute_bet_stats
from app.db import insert_bets, list_bets, resolve_bet_entry
from app.dg_feeds import build_correct_score_matrix
from app.polymarket_discovery import find_primary_event, parse_kickoff_date
from app.polymarket_exact_score import (
    books_for_tokens,
    exact_score_event_slug,
    fetch_exact_score_sibling,
    map_exact_score_markets,
)

logger = logging.getLogger(__name__)

LOG_TYPE = "cs"
BET_TYPE = "correct_score"

# Basket sizes to try, widest first (user rule: top 5, else top 4).
BASKET_SIZES: tuple[int, ...] = (5, 4)
# EV gap (in units) under which the wider basket is preferred.
EV_TIE_TOLERANCE = float(os.getenv("CS_EV_TIE_TOLERANCE", "0.01"))
# Total stake per basket, in units, so unit PnL is comparable across baskets.
BASKET_UNITS = float(os.getenv("CS_BASKET_UNITS", "1.0"))
# Minimum guaranteed return on the basket stake when any single leg hits.
MIN_GUARANTEED_ROI = float(os.getenv("CS_MIN_GUARANTEED_ROI", "0.05"))
# Padding added to each ask to stay honest about slippage / thin books.
PRICE_BUFFER = float(os.getenv("CS_PRICE_BUFFER", "0.005"))
# A single leg pricing above this is treated as a favourite, not a scoreline dart.
MAX_LEG_PRICE = float(os.getenv("CS_MAX_LEG_PRICE", "0.60"))
# Skip legs with less than this many shares resting at the best ask (0 = off).
MIN_ASK_SHARES = float(os.getenv("CS_MIN_ASK_SHARES", "0"))
# Only price fixtures kicking off inside this window.
MAX_HOURS_AHEAD = float(os.getenv("CS_MAX_HOURS_AHEAD", "72"))
# Require the model to price the basket above the market before logging it.
REQUIRE_POSITIVE_EV = (os.getenv("CS_REQUIRE_POSITIVE_EV", "false").strip().lower()
                       in {"1", "true", "yes"})
FIXTURE_WORKERS = int(os.getenv("CS_FIXTURE_WORKERS", "4"))
# DataGaffer scorelines considered per fixture before liquidity filtering.
CANDIDATE_POOL = int(os.getenv("CS_CANDIDATE_POOL", "10"))

_SCORE_LABEL_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_score_label(label: Any) -> tuple[int, int] | None:
    m = _SCORE_LABEL_RE.match(str(label or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _flip_label(label: str) -> str:
    parsed = parse_score_label(label)
    if parsed is None:
        return label
    return f"{parsed[1]}-{parsed[0]}"


def dutch_basket(legs: list[dict[str, Any]], *, budget: float = BASKET_UNITS) -> dict[str, Any] | None:
    """Size legs for equal payout so any single hit profits.

    ``legs`` need ``label``, ``price`` (Polymarket ask) and ``dg_pct``. Prices are
    padded by ``PRICE_BUFFER`` before sizing, and the returned guarantee is
    recomputed from the rounded stakes rather than the ideal ones.
    """
    if not legs:
        return None

    priced: list[dict[str, Any]] = []
    for leg in legs:
        price = _num(leg.get("price"))
        if price is None or price <= 0:
            return None
        priced.append({**leg, "fill_price": min(0.999, round(price + PRICE_BUFFER, 6))})

    # Above 100% the equal payout lands below the stake, so the guarantee (and
    # the ROI floor below) fails on its own — no special case needed.
    total_price = sum(leg["fill_price"] for leg in priced)
    if total_price <= 0:
        return None

    sized: list[dict[str, Any]] = []
    for leg in priced:
        stake = round(budget * leg["fill_price"] / total_price, 4)
        payout = round(stake / leg["fill_price"], 4) if stake > 0 else 0.0
        sized.append(
            {
                **leg,
                "stake_units": stake,
                "payout_units": payout,
                "decimal_odds": round(1 / leg["fill_price"], 3),
            }
        )

    staked = round(sum(leg["stake_units"] for leg in sized), 4)
    if staked <= 0:
        return None
    worst_payout = min(leg["payout_units"] for leg in sized)
    guaranteed = round(worst_payout - staked, 4)
    roi = guaranteed / staked

    model_pct = sum(_num(leg.get("dg_pct")) or 0.0 for leg in sized)
    implied_pct = total_price * 100
    # Every leg pays the same, so EV only needs the basket-level hit chance.
    ev_units = round((model_pct / 100) * worst_payout - staked, 4)

    for leg in sized:
        leg["profit_if_hits"] = round(leg["payout_units"] - staked, 4)

    return {
        "legs": sized,
        "qualified": roi >= MIN_GUARANTEED_ROI,
        "size": len(sized),
        "total_price": round(total_price, 4),
        "staked_units": staked,
        "payout_units": worst_payout,
        "guaranteed_profit_units": guaranteed,
        "guaranteed_roi_pct": round(roi * 100, 2),
        "model_hit_pct": round(model_pct, 2),
        "implied_hit_pct": round(implied_pct, 2),
        "edge_pct": round(model_pct - implied_pct, 2),
        "ev_units": ev_units,
        "reason": (
            ""
            if roi >= MIN_GUARANTEED_ROI
            else (
                f"top {len(sized)} price at {total_price * 100:.1f}% — no margin left"
                if total_price >= 1
                else f"guaranteed ROI {roi * 100:.1f}% below {MIN_GUARANTEED_ROI * 100:.0f}% floor"
            )
        ),
    }


def _price_for_market(row: dict[str, Any], book: dict[str, float | None]) -> tuple[float | None, str, float | None]:
    """Best ask to buy Yes, preferring the live CLOB book over Gamma."""
    ask = _num(book.get("ask"))
    if ask is not None and 0 < ask < 1:
        return ask, "clob_ask", _num(book.get("askSize"))
    gamma_ask = _num(row.get("gammaAsk"))
    if gamma_ask is not None and 0 < gamma_ask < 1:
        return gamma_ask, "gamma_ask", None
    return None, "", None


def price_fixture_scorelines(
    *,
    home_team: str,
    away_team: str,
    kickoff: Any,
    top_scores: list[dict[str, Any]],
    use_clob: bool = True,
) -> dict[str, Any]:
    """Resolve the Polymarket exact-score book for one fixture's top scorelines."""
    event = find_primary_event(home_team, away_team, kickoff)
    if not event:
        return {"error": "fixture not listed on Polymarket", "legs": []}

    sibling = fetch_exact_score_sibling(str(event["slug"]))
    if not sibling:
        return {
            "error": f"no exact-score market ({exact_score_event_slug(str(event['slug']))})",
            "legs": [],
            "polymarket": event,
        }

    catalog = map_exact_score_markets(sibling)
    by_label = {str(row["label"]): row for row in catalog}
    flipped = bool(event.get("flipped"))

    wanted: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for score in top_scores[:CANDIDATE_POOL]:
        label = str(score.get("score") or "")
        pm_label = _flip_label(label) if flipped else label
        row = by_label.get(pm_label)
        if row:
            wanted.append((score, row))

    books: dict[str, dict[str, float | None]] = {}
    if use_clob and wanted:
        books = books_for_tokens([str(row["yesTokenId"]) for _, row in wanted])

    legs: list[dict[str, Any]] = []
    for score, row in wanted:
        token = str(row["yesTokenId"])
        price, source, ask_size = _price_for_market(row, books.get(token) or {})
        if price is None or price > MAX_LEG_PRICE:
            continue
        if MIN_ASK_SHARES > 0 and ask_size is not None and ask_size < MIN_ASK_SHARES:
            continue
        legs.append(
            {
                "label": str(score.get("score")),
                "pm_label": str(row["label"]),
                "dg_pct": _num(score.get("pct")) or 0.0,
                "price": price,
                "price_source": source,
                "ask_shares": ask_size,
                "token_id": token,
                "market_slug": row.get("marketSlug"),
            }
        )

    return {
        "error": "" if legs else "no tradeable exact-score legs",
        "legs": legs,
        "polymarket": event,
        "exact_score_slug": exact_score_event_slug(str(event["slug"])),
        "market_count": len(catalog),
    }


def _best_basket(legs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick between the top-5 and top-4 baskets.

    Both risk the same budget, so expected value compares directly: a fifth leg
    priced above its model probability drags the basket down and is dropped. When
    the two are within ``EV_TIE_TOLERANCE`` the wider basket wins, since it hits
    more often for the same money.
    """
    ordered = sorted(legs, key=lambda leg: leg.get("dg_pct") or 0.0, reverse=True)
    attempts: list[dict[str, Any]] = []
    for size in BASKET_SIZES:
        if len(ordered) < size:
            continue
        basket = dutch_basket(ordered[:size])
        if basket:
            attempts.append(basket)
    if not attempts:
        return None

    qualified = [b for b in attempts if b.get("qualified")]
    if not qualified:
        return max(attempts, key=lambda b: b.get("guaranteed_roi_pct") or -999)

    best_ev = max(b.get("ev_units") or 0.0 for b in qualified)
    contenders = [b for b in qualified if best_ev - (b.get("ev_units") or 0.0) <= EV_TIE_TOLERANCE]
    return max(contenders, key=lambda b: (b.get("size") or 0, b.get("ev_units") or 0.0))


def _within_window(kickoff: Any) -> bool:
    text = str(kickoff or "").strip()
    if not text:
        return False
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        day = parse_kickoff_date(kickoff)
        if day is None:
            return False
        dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return now <= dt <= now + timedelta(hours=MAX_HOURS_AHEAD)


def _evaluate_match(match: dict[str, Any], *, use_clob: bool) -> dict[str, Any] | None:
    home_xg = _num(match.get("home_projected_goals"))
    away_xg = _num(match.get("away_projected_goals"))
    home_team = str(match.get("home_team") or "")
    away_team = str(match.get("away_team") or "")
    if not home_xg or not away_xg or not home_team or not away_team:
        return None

    matrix = build_correct_score_matrix(home_xg, away_xg)
    top_scores = matrix.get("top_scores") or []

    base = {
        "fixture_id": match.get("fixture_id"),
        "fixture": match.get("fixture") or f"{home_team} vs {away_team}",
        "fixture_date": match.get("fixture_date"),
        "league_name": match.get("league_name") or "",
        "home_team": home_team,
        "away_team": away_team,
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "model": matrix.get("model"),
        "dg_top_scores": top_scores[:6],
    }

    try:
        priced = price_fixture_scorelines(
            home_team=home_team,
            away_team=away_team,
            kickoff=match.get("fixture_date"),
            top_scores=top_scores,
            use_clob=use_clob,
        )
    except Exception as exc:  # noqa: BLE001 — one bad fixture must not kill the scan
        logger.warning("Polymarket pricing failed for %s: %s", base["fixture"], exc)
        return {**base, "qualified": False, "reason": f"pricing error: {exc}", "legs": []}

    pm = priced.get("polymarket") or {}
    base.update(
        {
            "polymarket_slug": pm.get("slug"),
            "polymarket_title": pm.get("title"),
            "polymarket_flipped": bool(pm.get("flipped")),
            "exact_score_slug": priced.get("exact_score_slug"),
            "polymarket_url": (
                f"https://polymarket.com/event/{priced['exact_score_slug']}"
                if priced.get("exact_score_slug")
                else None
            ),
        }
    )

    if not priced.get("legs"):
        return {**base, "qualified": False, "reason": priced.get("error") or "no legs", "legs": []}

    basket = _best_basket(priced["legs"])
    if not basket:
        return {**base, "qualified": False, "reason": "unable to size basket", "legs": []}

    qualified = bool(basket.get("qualified"))
    reason = basket.get("reason") or ""
    if qualified and REQUIRE_POSITIVE_EV and (basket.get("ev_units") or 0.0) <= 0:
        qualified = False
        reason = f"negative EV ({basket.get('ev_units')} units)"

    return {
        **base,
        **{k: v for k, v in basket.items() if k not in {"qualified", "reason"}},
        "qualified": qualified,
        "reason": reason,
        "verdict": "value" if (basket.get("ev_units") or 0.0) > 0 else "guaranteed only",
    }


def build_correct_score_picks(
    state: dict[str, Any],
    *,
    use_clob: bool = True,
    max_fixtures: int | None = None,
    include_rejected: bool = True,
) -> list[dict[str, Any]]:
    """Price every upcoming fixture's top scorelines and size the baskets."""
    matches = [m for m in (state.get("matches") or []) if _within_window(m.get("fixture_date"))]
    matches.sort(key=lambda m: str(m.get("fixture_date") or ""))
    if max_fixtures:
        matches = matches[:max_fixtures]
    if not matches:
        return []

    workers = max(1, min(FIXTURE_WORKERS, len(matches)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda m: _evaluate_match(m, use_clob=use_clob), matches))

    picks = [r for r in results if r]
    if not include_rejected:
        picks = [p for p in picks if p.get("qualified")]
    picks.sort(
        key=lambda p: (
            bool(p.get("qualified")),
            _num(p.get("ev_units")) or -99,
            _num(p.get("guaranteed_roi_pct")) or -99,
        ),
        reverse=True,
    )
    return picks


def load_correct_score_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def _basket_key(entry: dict[str, Any]) -> tuple[str, str]:
    return str(entry.get("fixture_date") or ""), str(entry.get("fixture") or "")


def sync_correct_score_bets(picks: list[dict[str, Any]]) -> dict[str, Any]:
    """Log qualified baskets. Fixtures already in the log are left untouched so a
    re-sync at different prices cannot break an existing basket's guarantee."""
    logged_fixtures = {_basket_key(e) for e in load_correct_score_bet_log()}
    candidates: list[dict[str, Any]] = []
    baskets = 0
    skipped_existing = 0

    for pick in picks:
        if not pick.get("qualified"):
            continue
        key = (str(pick.get("fixture_date") or ""), str(pick.get("fixture") or ""))
        if key in logged_fixtures:
            skipped_existing += 1
            continue
        logged_fixtures.add(key)
        baskets += 1
        for leg in pick.get("legs") or []:
            candidates.append(
                {
                    "id": str(uuid.uuid4()),
                    "created_at": _now_iso(),
                    "fixture_date": pick.get("fixture_date"),
                    "fixture": pick.get("fixture", ""),
                    "league_name": pick.get("league_name", ""),
                    "bet_type": BET_TYPE,
                    "team_name": leg.get("label") or "",
                    "qualifier_pct": leg.get("dg_pct"),
                    "odds": leg.get("decimal_odds"),
                    "units": leg.get("stake_units"),
                    "status": "open",
                    "pnl_units": None,
                }
            )

    inserted = insert_bets(LOG_TYPE, candidates)
    return {
        "inserted": inserted,
        "baskets": baskets,
        "skipped_existing": skipped_existing,
        "total": len(load_correct_score_bet_log()),
    }


def resolve_correct_score_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entry = next((e for e in load_correct_score_bet_log() if e.get("id") == bet_id), None)
    if not entry:
        raise ValueError("Bet not found.")
    odds = float(entry.get("odds") or 0)
    units = float(entry.get("units") or 1)
    if result == "won":
        pnl = round((odds - 1) * units, 3) if odds > 0 else round(1.0 * units, 3)
    elif result == "lost":
        pnl = round(-1.0 * units, 3)
    else:
        pnl = 0.0
    updated = resolve_bet_entry(LOG_TYPE, bet_id, result, pnl, _now_iso())
    if not updated:
        raise ValueError("Bet not found.")
    return updated


def group_into_baskets(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse legs back into per-fixture baskets for analysis."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(_basket_key(entry), []).append(entry)

    baskets: list[dict[str, Any]] = []
    for (fixture_date, fixture), legs in grouped.items():
        legs = sorted(legs, key=lambda e: str(e.get("team_name") or ""))
        staked = round(sum(_num(e.get("units")) or 0.0 for e in legs), 4)
        statuses = [str(e.get("status") or "open").lower() for e in legs]
        settled = all(s != "open" for s in statuses)
        winners = [e for e in legs if str(e.get("status") or "").lower() == "won"]
        pnl = round(sum(_num(e.get("pnl_units")) or 0.0 for e in legs), 3)
        payouts = [
            round((_num(e.get("odds")) or 0.0) * (_num(e.get("units")) or 0.0), 4) for e in legs
        ]
        baskets.append(
            {
                "fixture": fixture,
                "fixture_date": fixture_date,
                "league_name": legs[0].get("league_name") if legs else "",
                "legs": legs,
                "size": len(legs),
                "scores": [str(e.get("team_name") or "") for e in legs],
                "staked_units": staked,
                "payout_units": min(payouts) if payouts else 0.0,
                "guaranteed_profit_units": round((min(payouts) if payouts else 0.0) - staked, 4),
                "model_hit_pct": round(sum(_num(e.get("qualifier_pct")) or 0.0 for e in legs), 2),
                "settled": settled,
                "hit_score": winners[0].get("team_name") if winners else None,
                "status": ("open" if not settled else ("won" if pnl > 0 else "lost")),
                "pnl_units": pnl,
            }
        )
    baskets.sort(key=lambda b: str(b.get("fixture_date") or ""), reverse=True)
    return baskets


def correct_score_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Leg-level stats (shared shape) plus basket-level performance."""
    stats = compute_bet_stats(entries)
    baskets = group_into_baskets(entries)
    settled = [b for b in baskets if b["settled"]]
    hit = [b for b in settled if b["pnl_units"] > 0]
    settled_staked = round(sum(b["staked_units"] for b in settled), 3)
    pnl = round(sum(b["pnl_units"] for b in settled), 3)
    return {
        **stats,
        "baskets": len(baskets),
        "baskets_open": len(baskets) - len(settled),
        "baskets_settled": len(settled),
        "baskets_hit": len(hit),
        "basket_hit_pct": round(len(hit) / len(settled) * 100, 1) if settled else 0.0,
        "basket_staked_units": round(sum(b["staked_units"] for b in baskets), 3),
        "basket_settled_staked_units": settled_staked,
        "basket_roi_pct": round(pnl / settled_staked * 100, 1) if settled_staked else 0.0,
        "avg_basket_size": (
            round(sum(b["size"] for b in baskets) / len(baskets), 2) if baskets else 0.0
        ),
    }


def enrich_correct_score_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in entries:
        row = dict(entry)
        price = _num(row.get("odds"))
        row["market_label"] = f"Correct score {row.get('team_name') or '?'}"
        row["price_cents"] = round(100 / price, 1) if price else None
        row["model_pct_fmt"] = (
            f"{_num(row.get('qualifier_pct')):.2f}%" if _num(row.get("qualifier_pct")) is not None else "—"
        )
        out.append(row)
    return out
