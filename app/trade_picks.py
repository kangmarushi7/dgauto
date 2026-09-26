"""Trade Picks — open (default) bets that match LIVE capital categories."""
from __future__ import annotations

from datetime import date, datetime, timezone
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
    "arahus": "arahus_v2",
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


def parse_pick_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _pipeline_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for log_type in PIPELINE_LOG_TYPES:
        for raw in list_bets(log_type):
            strat = normalize_strategy(log_type) or normalize_strategy(raw.get("strategy"))
            if not strat:
                continue
            # Deduplicate: same bet may be stored in both "arahus" and "arahus_v2" tables.
            row_id = str(raw.get("id") or "")
            dedup_key = row_id or f"{raw.get('fixture')}|{raw.get('bet_type')}|{raw.get('odds')}|{raw.get('fixture_date')}"
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)
            rows.append({**raw, "strategy": strat, "log_type": log_type})
    return rows


def _is_open_tradeable(entry: dict[str, Any]) -> bool:
    return _ui_status(entry) == "open"


def _is_settled(entry: dict[str, Any]) -> bool:
    status = str(entry.get("status") or entry.get("result") or "").lower()
    return status in {"won", "lost", "push"}


def _row_ts(raw: dict[str, Any]) -> str:
    """Best available ISO timestamp for a raw DB row (for sync_since comparison)."""
    return (
        str(raw.get("synced_at") or "")
        or str(raw.get("created_at") or "")
        or str(raw.get("signal_timestamp") or "")
    )


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
    enriched_market = str(enriched.get("market") or "").strip()
    norm_market = str(norm.get("market") or "").strip()
    # Prefer canonical bucket label; fall back to scenario label if enrich still says "other".
    if enriched_market and enriched_market.lower() != "other":
        market = enriched_market
    else:
        market = norm_market or enriched_market or "other"
    return {
        **norm,
        "live_category": live_category,
        "market": market,
        "stake_usd": FLAT_STAKE_USD,
        "stake_units": FLAT_STAKE_USD,
        "stake_inr": None,
        "bet_type": str(raw.get("bet_type") or ""),
        "team_name": str(raw.get("team_name") or "").strip() or None,
        "log_type": str(raw.get("log_type") or pipeline_strat),
        "fixture_id": raw.get("fixture_id"),
    }


def _row_pnl_usd(row: dict[str, Any]) -> float | None:
    """Flat $1 PnL for a settled pick; None if not settled."""
    result = str(row.get("result") or "").lower()
    if result not in {"won", "lost", "push"}:
        status = str(row.get("status") or "").lower()
        if status not in {"won", "lost", "push"}:
            return None
        result = status
    pnl = row.get("pnl_units")
    if pnl is not None:
        try:
            return float(pnl)
        except (TypeError, ValueError):
            pass
    if result == "lost":
        return -FLAT_STAKE_USD
    if result == "push":
        return 0.0
    odds = row.get("odds")
    try:
        o = float(odds) if odds is not None else None
    except (TypeError, ValueError):
        o = None
    if o and o > 1.0:
        return (o - 1.0) * FLAT_STAKE_USD
    return FLAT_STAKE_USD


def _summary_metrics(picks: list[dict[str, Any]]) -> dict[str, Any]:
    settled_pnls: list[float] = []
    for p in picks:
        pnl = _row_pnl_usd(p)
        if pnl is None:
            continue
        settled_pnls.append(pnl)
        p["pnl_usd"] = round(pnl, 4)
    settled_n = len(settled_pnls)
    pnl_total = sum(settled_pnls) if settled_pnls else 0.0
    # ROI on settled stake only (flat $1 each).
    roi = (pnl_total / settled_n) if settled_n else None
    return {
        "settled_n": settled_n,
        "open_n": sum(1 for p in picks if p.get("status") == "open"),
        "pnl_usd": round(pnl_total, 2),
        "roi": round(roi, 4) if roi is not None else None,
        "roi_pct": round(roi * 100, 1) if roi is not None else None,
    }


def trade_picks_payload(
    *,
    include_settled: bool = False,
    pick_date: str | date | None = None,
    sync_since: str | None = None,
) -> dict[str, Any]:
    """LIVE-category picks.

    Default: all open LIVE bets.
    With pick_date (YYYY-MM-DD): bets whose kickoff date (IST) matches that day
    — includes open and settled for that day.
    With sync_since (ISO timestamp): all open picks PLUS any settled picks whose
    DB timestamp is >= sync_since, so reconnecting clients can replay missed events.
    """
    day = parse_pick_date(pick_date)
    states = get_runtime_states()
    live_ids = [
        cid
        for cid, cat in CATEGORIES.items()
        if states.get(cid, cat.initial_state) == STATE_LIVE
    ]
    live_set = set(live_ids)

    # Day view always includes settled for that fixture date.
    want_settled = include_settled or day is not None

    picks: list[dict[str, Any]] = []
    for raw in _pipeline_rows():
        is_open = _is_open_tradeable(raw)
        is_settled = _is_settled(raw)

        if sync_since:
            # Include open picks always + any row (open or settled) updated since sync_since.
            row_ts = _row_ts(raw)
            if not is_open and not (is_settled and row_ts >= sync_since):
                continue
        elif want_settled:
            if not (is_open or is_settled):
                continue
        elif not is_open:
            continue

        cid = assign_live_category(raw, states=states)
        if not cid or cid not in live_set:
            continue

        row = _display_row(raw, cid)
        if not row:
            continue

        if day is not None:
            row_day = parse_pick_date(row.get("date_label"))
            if row_day != day:
                continue

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

    metrics = _summary_metrics(picks)

    return {
        "include_settled": want_settled,
        "pick_date": day.isoformat() if day else None,
        "flat_stake_usd": FLAT_STAKE_USD,
        "live_category_ids": live_ids,
        "entries": picks,
        "n": len(picks),
        "open_n": metrics["open_n"],
        "settled_n": metrics["settled_n"],
        "pnl_usd": metrics["pnl_usd"],
        "roi": metrics["roi"],
        "roi_pct": metrics["roi_pct"],
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


BOT_TRADE_PICKS_SCHEMA = 1


def _split_fixture_teams(fixture: str) -> tuple[str | None, str | None]:
    text = str(fixture or "").strip()
    for sep in (" vs ", " v ", " VS ", " V "):
        if sep in text:
            home, _, away = text.partition(sep)
            home, away = home.strip(), away.strip()
            return (home or None, away or None)
    return (None, None)


def _fixture_id_lookup() -> dict[str, Any]:
    """Map normalized 'home vs away' → fixture_id from latest slate."""
    try:
        from app.db import load_state

        state = load_state("latest_data", {"matches": []})
    except Exception:
        return {}
    out: dict[str, Any] = {}
    for m in state.get("matches") or []:
        fid = m.get("fixture_id")
        if not fid:
            continue
        home = str(m.get("home_team") or m.get("home") or "").strip()
        away = str(m.get("away_team") or m.get("away") or "").strip()
        if isinstance(m.get("home"), dict):
            home = str(m["home"].get("name") or home).strip()
        if isinstance(m.get("away"), dict):
            away = str(m["away"].get("name") or away).strip()
        if home and away:
            out[f"{home.lower()} vs {away.lower()}"] = fid
        label = str(m.get("fixture") or "").strip().lower()
        if label:
            out[label] = fid
    return out


def build_bot_trade_picks_feed(
    *,
    open_only: bool = True,
    pick_date: str | date | None = None,
    category: str | None = None,
    strategy: str | None = None,
    sync_since: str | None = None,
) -> dict[str, Any]:
    """Stable JSON feed for polybot / Polymarket placement.

    Default: open LIVE picks only (placeable queue).
    With sync_since: open picks + any settled picks updated since that ISO timestamp.
    """
    day = parse_pick_date(pick_date)

    if sync_since:
        base = trade_picks_payload(include_settled=False, pick_date=day, sync_since=sync_since)
        entries = list(base.get("entries") or [])
        live_ids = base.get("live_category_ids") or []
    elif open_only and day is not None:
        # Open LIVE bets kicking on that IST day.
        base = trade_picks_payload(include_settled=True, pick_date=day)
        entries = [e for e in (base.get("entries") or []) if e.get("status") == "open"]
        live_ids = base.get("live_category_ids") or []
    elif open_only:
        base = trade_picks_payload(include_settled=False, pick_date=None)
        entries = list(base.get("entries") or [])
        live_ids = base.get("live_category_ids") or []
    else:
        base = trade_picks_payload(include_settled=True, pick_date=day)
        entries = list(base.get("entries") or [])
        live_ids = base.get("live_category_ids") or []

    if category:
        entries = [e for e in entries if e.get("live_category") == category]
    if strategy:
        strat = strategy.strip().lower()
        if strat == "arahus":
            entries = [
                e
                for e in entries
                if str(e.get("strategy") or "").startswith("arahus") or e.get("strategy") == "arahus"
            ]
        else:
            entries = [e for e in entries if e.get("strategy") == strat]

    id_lookup = _fixture_id_lookup()
    picks: list[dict[str, Any]] = []
    for e in entries:
        fixture = str(e.get("fixture") or "")
        home, away = _split_fixture_teams(fixture)
        fid = e.get("fixture_id") or id_lookup.get(fixture.lower())
        if not fid and home and away:
            fid = id_lookup.get(f"{home.lower()} vs {away.lower()}")
        picks.append(
            {
                "id": e.get("id"),
                "live_category": e.get("live_category"),
                "strategy": e.get("strategy"),
                "strategy_label": e.get("strategy_label"),
                "log_type": e.get("log_type"),
                "fixture_id": fid,
                "fixture": fixture,
                "home_team": home,
                "away_team": away,
                "league": e.get("league") or "",
                "kickoff": e.get("fixture_date") or e.get("time"),
                "kickoff_ist_date": e.get("date_label"),
                "kickoff_ist_time": e.get("time_label"),
                "market": e.get("market"),
                "bet_type": e.get("bet_type") or "",
                "team": e.get("team_name"),
                "odds": e.get("odds"),
                "stake_usd": float(e.get("stake_usd") or FLAT_STAKE_USD),
                "currency": "USD",
                "status": e.get("status"),
                "result": e.get("result"),
            }
        )

    return {
        "schema_version": BOT_TRADE_PICKS_SCHEMA,
        "kind": "trade_picks",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flat_stake_usd": FLAT_STAKE_USD,
        "currency": "USD",
        "open_only": bool(open_only),
        "pick_date": day.isoformat() if day else None,
        "live_category_ids": live_ids,
        "filters": {
            "category": category,
            "strategy": strategy,
        },
        "count": len(picks),
        "picks": picks,
    }
