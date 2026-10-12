"""Honest xGOT research metrics — never treat null odds as 2.0."""
from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def financial_pnl(entry: dict[str, Any]) -> float | None:
    """PnL in units using real decimal odds only.

    Returns None when odds are missing/invalid — never synthetic +1u.
    """
    status = str(entry.get("status") or "").lower()
    if status not in {"won", "lost", "push", "void"}:
        return None
    if status in {"push", "void"}:
        return 0.0
    units = _num(entry.get("units"))
    if units is None:
        units = 1.0
    if status == "lost":
        return -abs(units)
    odds = _num(entry.get("odds"))
    if odds is None or odds <= 1.0:
        return None
    return (odds - 1.0) * units


def outcome_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """W/L/P counts regardless of odds pricing."""
    won = lost = push = open_n = other = 0
    for e in entries:
        st = str(e.get("status") or "").lower()
        if st == "won":
            won += 1
        elif st == "lost":
            lost += 1
        elif st in {"push", "void"}:
            push += 1
        elif st == "open":
            open_n += 1
        else:
            other += 1
    settled = won + lost + push
    decided = won + lost
    win_rate = (won / decided) if decided else None
    return {
        "placed": len(entries),
        "open": open_n,
        "settled": settled,
        "won": won,
        "lost": lost,
        "push": push,
        "other": other,
        "win_rate": win_rate,
    }


def financial_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Financial stats only over settled rows with valid odds.

    ROI is None (unavailable) when there are no priced settled bets.
    """
    priced: list[dict[str, Any]] = []
    pnls: list[float] = []
    odds_vals: list[float] = []
    for e in entries:
        st = str(e.get("status") or "").lower()
        if st not in {"won", "lost", "push", "void"}:
            continue
        pnl = financial_pnl(e)
        if pnl is None:
            continue
        priced.append(e)
        pnls.append(pnl)
        o = _num(e.get("odds"))
        if o is not None and o > 1.0:
            odds_vals.append(o)

    turnover = 0.0
    for e in priced:
        u = _num(e.get("units"))
        turnover += abs(u if u is not None else 1.0)

    net = sum(pnls) if pnls else 0.0
    roi = (net / turnover) if turnover > 0 else None
    avg_odds = (sum(odds_vals) / len(odds_vals)) if odds_vals else None

    # Max drawdown on priced settlement order (created_at then id).
    ordered = sorted(
        zip(priced, pnls),
        key=lambda pair: (
            str(pair[0].get("resolved_at") or pair[0].get("created_at") or ""),
            str(pair[0].get("id") or ""),
        ),
    )
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    streak = 0
    max_lose_streak = 0
    for _e, pnl in ordered:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
        if pnl < 0:
            streak += 1
            max_lose_streak = max(max_lose_streak, streak)
        else:
            streak = 0

    return {
        "priced_settled": len(priced),
        "turnover_units": turnover,
        "net_pnl_units": net if priced else None,
        "roi": roi,
        "avg_entry_odds": avg_odds,
        "max_drawdown_units": max_dd if priced else None,
        "max_losing_streak": max_lose_streak if priced else None,
        "financial_roi_available": roi is not None,
    }


def fixture_cluster_note(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_fx: dict[str, int] = {}
    for e in entries:
        fid = str(e.get("fixture_id") or "").strip()
        if not fid:
            fid = f"{e.get('fixture_date')}|{e.get('fixture')}"
        by_fx[fid] = by_fx.get(fid, 0) + 1
    max_bets = max(by_fx.values()) if by_fx else 0
    return {
        "unique_fixtures": len(by_fx),
        "max_bets_per_fixture": max_bets,
        "correlated": max_bets > 1,
    }
