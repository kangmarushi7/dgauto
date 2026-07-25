"""Cross-strategy bet views for Today's Bets and the unified Bet Log."""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.bet_scenarios import scenario_meta_for_entry
from app.db import list_bets
from app.h2h_strat import H2H_MARKETS
from app.plus_ev_strat import market_label_for_entry as plus_ev_market_label
from app.prop_model_bets import list_prop_bets
from app.seasons import fixture_date_ist
from app.slate import _is_in_todays_slate_ist, _parse_dt

_H2H_LABELS = {bt: label for _, _, bt, label, _, _ in H2H_MARKETS}

IST = ZoneInfo("Asia/Kolkata")

# 1 unit → INR display (stakes / P&L on the unified pages).
STAKE_UNIT_INR = float(os.getenv("STAKE_UNIT_INR", "100"))

_FLAGGED_EV_CACHE: dict[str, Any] = {"at": 0.0, "value": 0}
_FLAGGED_EV_TTL_SEC = 120.0


def count_flagged_ev(state: dict[str, Any] | None = None, *, force: bool = False) -> int:
    """Count live +EV picks with a short TTL cache (home page / slate)."""
    now = time.monotonic()
    if not force and now - float(_FLAGGED_EV_CACHE["at"]) < _FLAGGED_EV_TTL_SEC:
        return int(_FLAGGED_EV_CACHE["value"])
    try:
        from app.plus_ev_strat import build_plus_ev_picks

        if state is None:
            from app.db import load_state

            state = load_state("latest_data", {"scraped_at": None, "matches": []})
        value = len(build_plus_ev_picks(state))
    except Exception:
        value = sum(
            1 for e in list_bets("ev") if str(e.get("status") or "").lower() == "open"
        )
    _FLAGGED_EV_CACHE["at"] = now
    _FLAGGED_EV_CACHE["value"] = value
    return value


STRATEGY_META: dict[str, dict[str, str]] = {
    "main": {"id": "main", "label": "Recommended", "short": "Main"},
    "lm": {"id": "lm", "label": "Line Movement", "short": "LM"},
    "no": {"id": "no", "label": "No-Vig Model", "short": "NO"},
    "h2h": {"id": "h2h", "label": "Head to Head", "short": "H2H"},
    "ev": {"id": "ev", "label": "+EV Finder", "short": "+EV"},
    "cs": {"id": "cs", "label": "Closing Steam", "short": "CS"},
    "prop": {"id": "prop", "label": "Prop Model", "short": "Prop"},
}

LOG_TYPES = ("main", "lm", "no", "h2h", "ev", "cs")


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _to_ist(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def _today_ist(now: datetime | None = None) -> date:
    now = now or datetime.now(IST)
    return _to_ist(now).date()


def units_to_inr(units: float | None) -> float:
    return round(float(units or 0) * STAKE_UNIT_INR, 2)


def _market_for_entry(entry: dict[str, Any], strategy: str) -> str:
    if strategy == "ev":
        return plus_ev_market_label(entry)
    if strategy == "h2h":
        bt = str(entry.get("bet_type") or "")
        label = _H2H_LABELS.get(bt, bt)
        team = str(entry.get("team_name") or "").strip()
        # Avoid duplicating numeric lines already in the label.
        if team and team not in str(label) and not team.replace(".", "", 1).isdigit():
            return f"{team} · {label}"
        return str(label)
    if strategy == "cs":
        score = str(entry.get("team_name") or "").strip() or "?"
        return f"Correct score {score}"
    if strategy == "lm":
        return "Over 1.5 Goals"
    if strategy == "no":
        team = str(entry.get("team_name") or "").strip()
        return f"{team} not to win" if team else "Not to win"
    if strategy == "prop":
        player = str(entry.get("player_name") or entry.get("team_name") or "Player").strip()
        side = str(entry.get("side") or "").upper()
        stat = str(entry.get("stat_type") or "").strip()
        line = entry.get("line")
        bits = [player]
        if side:
            bits.append(side)
        if stat:
            bits.append(stat)
        if line is not None and line != "":
            bits.append(str(line))
        return " ".join(bits)

    meta = scenario_meta_for_entry(entry)
    label = str(meta.get("label") or entry.get("bet_type") or "")
    team = str(entry.get("team_name") or "").strip()
    if team and team.lower() not in label.lower():
        return f"{team} · {label}" if label else team
    return label or "—"


def _ui_status(entry: dict[str, Any]) -> str:
    raw = str(entry.get("status") or entry.get("result") or "open").lower().strip()
    if raw in {"won", "lost", "push"}:
        return "settled"
    if raw == "open":
        odds = entry.get("odds")
        if odds is None or odds == "" or float(odds or 0) <= 0:
            return "pending"
        return "open"
    return "pending"


def _result_pill(entry: dict[str, Any]) -> str | None:
    raw = str(entry.get("status") or entry.get("result") or "").lower().strip()
    if raw in {"won", "lost", "push"}:
        return raw
    return None


def _normalize_entry(entry: dict[str, Any], strategy: str) -> dict[str, Any]:
    meta = STRATEGY_META[strategy]
    kick = _parse_dt(entry.get("fixture_date")) or _parse_iso(entry.get("created_at"))
    kick_ist = _to_ist(kick)
    units = float(entry.get("units") if entry.get("units") is not None else entry.get("stake") or 1.0)
    odds = entry.get("odds")
    try:
        odds_f = float(odds) if odds is not None and odds != "" else None
    except (TypeError, ValueError):
        odds_f = None

    # +EV stores EV in qualifier_pct; prop may use clv_pct.
    ev = None
    if strategy == "ev":
        ev = entry.get("qualifier_pct")
    elif strategy == "prop":
        ev = entry.get("clv_pct")
    try:
        ev_f = float(ev) if ev is not None and ev != "" else None
    except (TypeError, ValueError):
        ev_f = None

    pnl_units = entry.get("pnl_units")
    if pnl_units is None and strategy == "prop":
        # Derive prop P&L when settled.
        result = str(entry.get("result") or "").lower()
        if result == "lost":
            pnl_units = -units
        elif result == "push":
            pnl_units = 0.0
        elif result == "won" and odds_f is not None:
            # American odds on prop log.
            if odds_f > 0:
                pnl_units = units * (odds_f / 100.0)
            elif odds_f < 0:
                pnl_units = units * (100.0 / abs(odds_f))
    try:
        pnl_f = float(pnl_units) if pnl_units is not None else None
    except (TypeError, ValueError):
        pnl_f = None

    fixture = str(entry.get("fixture") or "").strip()
    if strategy == "prop" and not fixture:
        player = str(entry.get("player_name") or "Player")
        team = str(entry.get("team") or "")
        fixture = f"{player}" + (f" ({team})" if team else "")

    status = _ui_status(entry)
    result = _result_pill(entry)

    return {
        "id": str(entry.get("id")),
        "strategy": strategy,
        "strategy_label": meta["label"],
        "strategy_short": meta["short"],
        "time": kick_ist.isoformat() if kick_ist else None,
        "time_label": kick_ist.strftime("%H:%M") if kick_ist else "—",
        "date_label": kick_ist.strftime("%Y-%m-%d") if kick_ist else "—",
        "fixture": fixture or "—",
        "league": str(entry.get("league_name") or entry.get("sport") or "").strip(),
        "market": _market_for_entry(entry, strategy),
        "stake_units": round(units, 3),
        "stake_inr": units_to_inr(units),
        "odds": odds_f,
        "ev": round(ev_f, 2) if ev_f is not None else None,
        "status": status,
        "result": result,
        "pnl_units": round(pnl_f, 3) if pnl_f is not None else None,
        "pnl_inr": units_to_inr(pnl_f) if pnl_f is not None else None,
        "fixture_date": entry.get("fixture_date"),
        "created_at": entry.get("created_at"),
    }


def _collect_raw() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for log_type in LOG_TYPES:
        for row in list_bets(log_type):
            out.append((log_type, row))
    for row in list_prop_bets():
        # Map prop result field onto status for shared helpers.
        mapped = dict(row)
        mapped["status"] = mapped.get("result") or "open"
        mapped["units"] = mapped.get("stake")
        mapped["fixture"] = mapped.get("fixture") or ""
        mapped["league_name"] = (mapped.get("sport") or "").upper()
        mapped["fixture_date"] = mapped.get("created_at")
        out.append(("prop", mapped))
    return out


def collect_unified_bets() -> list[dict[str, Any]]:
    return [_normalize_entry(row, strategy) for strategy, row in _collect_raw()]


def _is_today_bet(bet: dict[str, Any], *, now: datetime | None = None) -> bool:
    """True if kickoff falls in today's slate window, else if created today IST."""
    kick = _parse_dt(bet.get("fixture_date")) or _parse_iso(bet.get("time"))
    if kick is not None and _is_in_todays_slate_ist(kick, now=now):
        return True
    created = _parse_iso(bet.get("created_at")) or _parse_iso(bet.get("time"))
    if created is None:
        return False
    return _to_ist(created).date() == _today_ist(now)


def todays_bets(*, strategy: str | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
    rows = [b for b in collect_unified_bets() if _is_today_bet(b, now=now)]
    if strategy and strategy in STRATEGY_META:
        rows = [b for b in rows if b["strategy"] == strategy]
    rows.sort(key=lambda b: (b.get("time") or "9999", b.get("fixture") or "", b.get("market") or ""))
    return rows


def bet_log_entries(
    *,
    strategy: str | None = None,
    result: str | None = None,
    days: int | None = 30,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Settled bets only, newest first, with optional filters + pagination."""
    settled = [b for b in collect_unified_bets() if b.get("result") in {"won", "lost", "push"}]

    if strategy and strategy in STRATEGY_META:
        settled = [b for b in settled if b["strategy"] == strategy]
    if result and result.lower() in {"won", "lost", "push"}:
        settled = [b for b in settled if b.get("result") == result.lower()]

    range_start: date | None = None
    range_end = _today_ist()
    if days is not None and days > 0:
        range_start = range_end - timedelta(days=days - 1)
        filtered: list[dict[str, Any]] = []
        for b in settled:
            d = fixture_date_ist({"fixture_date": b.get("time") or b.get("fixture_date")})
            if d is None:
                d = fixture_date_ist({"fixture_date": b.get("created_at")})
            if d is None or d < range_start or d > range_end:
                continue
            filtered.append(b)
        settled = filtered

    settled.sort(key=lambda b: (b.get("time") or "", b.get("fixture") or ""), reverse=True)

    net_pnl = round(sum(float(b.get("pnl_inr") or 0) for b in settled), 2)
    if range_start:
        range_label = f"Last {days} days · {'+' if net_pnl >= 0 else ''}{net_pnl:.0f}₹"
    else:
        range_label = f"All time · {'+' if net_pnl >= 0 else ''}{net_pnl:.0f}₹"

    page = max(1, int(page or 1))
    page_size = max(1, min(200, int(page_size or 50)))
    total = len(settled)
    start = (page - 1) * page_size
    page_rows = settled[start : start + page_size]

    return {
        "entries": page_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "net_pnl_inr": net_pnl,
        "range_label": range_label,
        "range_days": days,
        "strategies": list(STRATEGY_META.values()),
        "unit_inr": STAKE_UNIT_INR,
    }


def todays_bets_payload(*, strategy: str | None = None) -> dict[str, Any]:
    rows = todays_bets(strategy=strategy)
    open_n = sum(1 for b in rows if b["status"] == "open")
    pending_n = sum(1 for b in rows if b["status"] == "pending")
    settled_n = sum(1 for b in rows if b["status"] == "settled")
    staked = round(sum(float(b.get("stake_inr") or 0) for b in rows if b["status"] != "settled"), 2)
    return {
        "entries": rows,
        "count": len(rows),
        "open": open_n,
        "pending": pending_n,
        "settled": settled_n,
        "open_stake_inr": staked,
        "strategies": list(STRATEGY_META.values()),
        "unit_inr": STAKE_UNIT_INR,
    }


def home_summary_stats(
    *,
    match_count: int,
    flagged_ev: int,
) -> dict[str, Any]:
    return {
        "fixtures_today": match_count,
        "flagged_ev": flagged_ev,
    }
