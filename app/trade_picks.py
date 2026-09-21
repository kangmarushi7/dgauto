"""Trade Picks — open (default) bets that match LIVE capital categories."""
from __future__ import annotations

from typing import Any

from app.db import list_bets
from app.strategy_buckets import (
    CATEGORIES,
    FLAT_STAKE_USD,
    STATE_LIVE,
    assign_live_category,
    enrich_bet_row,
    get_runtime_states,
    normalize_strategy,
)
from app.unified_bets import STRATEGY_META, _normalize_entry, _ui_status

PIPELINE_LOG_TYPES: tuple[str, ...] = (
    "main",
    "cs",
    "ev",
    "h2h",
    "arahus",
    "arahus_v2",
    "arahus_live_v1",
)

DISPLAY_STRATEGY: dict[str, str] = {
    "main": "main",
    "cs": "cs",
    "ev": "ev",
    "h2h": "h2h",
    "arahus": "arahus_v2",  # reuse Over 2.5 market labeling
    "arahus_v2": "arahus_v2",
    "arahus_live_v1": "arahus_live_v1",
}

TRADE_PICK_CSV_FIELDS = [
    "live_category",
    "strategy",
    "strategy_label",
    "date",
    "time",
    "fixture",
    "league",
    "market",
    "odds",
    "stake_usd",
    "status",
    "result",
    "pnl_units",
    "id",
]


def _pipeline_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for log_type in PIPELINE_LOG_TYPES:
        for raw in list_bets(log_type):
            strat = normalize_strategy(log_type) or normalize_strategy(raw.get("strategy"))
            if not strat:
                continue
            rows.append({**raw, "strategy": strat, "log_type": log_type})
    return rows


def _is_open_tradeable(entry: dict[str, Any]) -> bool:
    return _ui_status(entry) == "open"


def _is_settled(entry: dict[str, Any]) -> bool:
    status = str(entry.get("status") or entry.get("result") or "").lower()
    return status in {"won", "lost", "push"}


def _display_row(raw: dict[str, Any], live_category: str) -> dict[str, Any] | None:
    pipeline_strat = raw["strategy"]
    meta_key = DISPLAY_STRATEGY.get(pipeline_strat)
    if not meta_key or meta_key not in STRATEGY_META:
        return None

    norm = _normalize_entry({**raw, "units": FLAT_STAKE_USD}, meta_key)
    if pipeline_strat == "arahus":
        norm["strategy"] = "arahus"
        norm["strategy_label"] = "Arahus"
        norm["strategy_short"] = "Arahus"

    enriched = enrich_bet_row(raw)
    return {
        **norm,
        "live_category": live_category,
        "market": enriched.get("market") or norm.get("market"),
        "stake_usd": FLAT_STAKE_USD,
        "stake_units": FLAT_STAKE_USD,
        "stake_inr": None,
    }


def trade_picks_payload(*, include_settled: bool = False) -> dict[str, Any]:
    """LIVE-category picks. Default: open only; optional settled history."""
    states = get_runtime_states()
    live_ids = [
        cid
        for cid, cat in CATEGORIES.items()
        if states.get(cid, cat.initial_state) == STATE_LIVE
    ]
    live_set = set(live_ids)

    picks: list[dict[str, Any]] = []
    for raw in _pipeline_rows():
        if include_settled:
            if not (_is_open_tradeable(raw) or _is_settled(raw)):
                continue
        elif not _is_open_tradeable(raw):
            continue

        cid = assign_live_category(raw, states=states)
        if not cid or cid not in live_set:
            continue

        row = _display_row(raw, cid)
        if row:
            picks.append(row)

    picks.sort(
        key=lambda b: (
            str(b.get("live_category") or ""),
            str(b.get("time") or "9999"),
            str(b.get("fixture") or ""),
            str(b.get("market") or ""),
        )
    )

    by_category: dict[str, int] = {}
    for p in picks:
        by_category[p["live_category"]] = by_category.get(p["live_category"], 0) + 1

    return {
        "include_settled": include_settled,
        "flat_stake_usd": FLAT_STAKE_USD,
        "live_category_ids": live_ids,
        "entries": picks,
        "n": len(picks),
        "open_n": sum(1 for p in picks if p.get("status") == "open"),
        "settled_n": sum(1 for p in picks if p.get("result") in {"won", "lost", "push"}),
        "by_category": by_category,
        "categories": [{"id": cid, "n": by_category.get(cid, 0)} for cid in live_ids],
    }


def trade_pick_csv_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "live_category": b.get("live_category"),
            "strategy": b.get("strategy"),
            "strategy_label": b.get("strategy_label"),
            "date": b.get("date_label"),
            "time": b.get("time_label"),
            "fixture": b.get("fixture"),
            "league": b.get("league"),
            "market": b.get("market"),
            "odds": b.get("odds"),
            "stake_usd": b.get("stake_usd", FLAT_STAKE_USD),
            "status": b.get("status"),
            "result": b.get("result") or "",
            "pnl_units": b.get("pnl_units"),
            "id": b.get("id"),
        }
        for b in entries
    ]
