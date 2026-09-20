"""CSV export helpers for strategy bet logs (not Arahus)."""

from __future__ import annotations

import csv
import io
from typing import Any, Callable, Iterable

from app.bet_scenarios import scenario_meta_for_entry

STANDARD_BET_FIELDS = [
    "id",
    "created_at",
    "fixture_date",
    "fixture",
    "league_name",
    "bet_type",
    "category",
    "market",
    "team_name",
    "qualifier_pct",
    "odds",
    "units",
    "status",
    "pnl_units",
    "resolved_at",
]

UNIFIED_BET_FIELDS = [
    "date",
    "time",
    "fixture",
    "league",
    "strategy",
    "strategy_label",
    "market",
    "stake_units",
    "stake_inr",
    "odds",
    "status",
    "result",
    "pnl_units",
    "pnl_inr",
    "id",
]


PROP_BET_FIELDS = [
    "id",
    "created_at",
    "sport",
    "player_name",
    "team",
    "stat_type",
    "line",
    "side",
    "stake",
    "odds",
    "result",
    "clv_pct",
]

CS_BASKET_FIELDS = [
    "fixture_date",
    "fixture",
    "league_name",
    "lines",
    "staked_units",
    "payout_units",
    "guaranteed_profit_units",
    "model_hit_pct",
    "status",
    "pnl_units",
    "hit_score",
]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        return str(value)
    return str(value)


def dicts_to_csv(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(row.get(k)) for k in fieldnames})
    return buf.getvalue()


def standard_bet_rows(
    entries: Iterable[dict[str, Any]],
    *,
    category_key: str | None = None,
    market_key: str | None = None,
) -> list[dict[str, Any]]:
    """Flatten bet_entries rows for spreadsheet export."""
    out: list[dict[str, Any]] = []
    for entry in entries:
        row = dict(entry)
        meta = scenario_meta_for_entry(row)
        category = row.get(category_key) if category_key else None
        if not category:
            category = row.get("category_label") or row.get("scenario_category") or meta.get("category")
        market = row.get(market_key) if market_key else None
        if not market:
            market = row.get("market_label") or row.get("scenario_label") or meta.get("label") or row.get("bet_type")
        out.append(
            {
                "id": row.get("id"),
                "created_at": row.get("created_at"),
                "fixture_date": row.get("fixture_date"),
                "fixture": row.get("fixture"),
                "league_name": row.get("league_name"),
                "bet_type": row.get("bet_type"),
                "category": category,
                "market": market,
                "team_name": row.get("team_name"),
                "qualifier_pct": row.get("qualifier_pct"),
                "odds": row.get("odds"),
                "units": row.get("units"),
                "status": row.get("status"),
                "pnl_units": row.get("pnl_units"),
                "resolved_at": row.get("resolved_at"),
            }
        )
    return out


def cs_basket_rows(baskets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for b in baskets:
        scores = b.get("scores") or []
        rows.append(
            {
                "fixture_date": b.get("fixture_date"),
                "fixture": b.get("fixture"),
                "league_name": b.get("league_name"),
                "lines": ", ".join(str(s) for s in scores),
                "staked_units": b.get("staked_units"),
                "payout_units": b.get("payout_units"),
                "guaranteed_profit_units": b.get("guaranteed_profit_units"),
                "model_hit_pct": b.get("model_hit_pct"),
                "status": b.get("status"),
                "pnl_units": b.get("pnl_units"),
                "hit_score": b.get("hit_score"),
            }
        )
    return rows


def cs_leg_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        row = dict(entry)
        rows.append(
            {
                "id": row.get("id"),
                "created_at": row.get("created_at"),
                "fixture_date": row.get("fixture_date"),
                "fixture": row.get("fixture"),
                "league_name": row.get("league_name"),
                "scoreline": row.get("team_name"),
                "bet_type": row.get("bet_type"),
                "model_pct": row.get("qualifier_pct"),
                "price_cents": row.get("price_cents"),
                "odds": row.get("odds"),
                "units": row.get("units"),
                "status": row.get("status"),
                "pnl_units": row.get("pnl_units"),
                "resolved_at": row.get("resolved_at"),
            }
        )
    return rows


CS_LEG_FIELDS = [
    "id",
    "created_at",
    "fixture_date",
    "fixture",
    "league_name",
    "scoreline",
    "bet_type",
    "model_pct",
    "price_cents",
    "odds",
    "units",
    "status",
    "pnl_units",
    "resolved_at",
]


def prop_bet_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": e.get("id"),
            "created_at": e.get("created_at"),
            "sport": e.get("sport"),
            "player_name": e.get("player_name"),
            "team": e.get("team"),
            "stat_type": e.get("stat_type"),
            "line": e.get("line"),
            "side": e.get("side"),
            "stake": e.get("stake"),
            "odds": e.get("odds"),
            "result": e.get("result"),
            "clv_pct": e.get("clv_pct"),
        }
        for e in entries
    ]


def unified_bet_rows(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten unified Bet Log rows for spreadsheet export."""
    out: list[dict[str, Any]] = []
    for entry in entries:
        result = entry.get("result")
        if not result:
            result = entry.get("status")
        out.append(
            {
                "date": entry.get("date_label"),
                "time": entry.get("time_label"),
                "fixture": entry.get("fixture"),
                "league": entry.get("league"),
                "strategy": entry.get("strategy_short") or entry.get("strategy"),
                "strategy_label": entry.get("strategy_label"),
                "market": entry.get("market"),
                "stake_units": entry.get("stake_units"),
                "stake_inr": entry.get("stake_inr"),
                "odds": entry.get("odds"),
                "status": entry.get("status"),
                "result": result,
                "pnl_units": entry.get("pnl_units"),
                "pnl_inr": entry.get("pnl_inr"),
                "id": entry.get("id"),
            }
        )
    return out


EnrichFn = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
