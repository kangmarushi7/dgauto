"""Settle research signals from production bet log (read-only) or explicit results."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from research.plus_ev_forward_test.storage import DEFAULT_DATA_DIR, load_signals, upsert_signals


def _pnl(result: str, odds: float) -> float:
    if result == "won":
        return round(float(odds) - 1.0, 4)
    if result == "lost":
        return -1.0
    if result == "push":
        return 0.0
    return float("nan")


def settle_from_production_bet_log(data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, Any]:
    """
    Read-only join against production +EV bet log to fill results for open live signals.
    Does not write to production.
    """
    from app.plus_ev_strat import load_plus_ev_bet_log

    prod = load_plus_ev_bet_log()
    index: dict[str, dict[str, Any]] = {}
    for e in prod:
        key = "|".join(
            [
                str(e.get("fixture") or ""),
                str(e.get("bet_type") or ""),
                str(e.get("fixture_date") or "")[:16],
            ]
        )
        index[key] = e

    signals = load_signals(data_dir)
    updated = 0
    for s in signals:
        if s.get("result") in {"won", "lost", "push"}:
            continue
        key = "|".join(
            [
                str(s.get("fixture") or ""),
                str(s.get("bet_type") or ""),
                str(s.get("kickoff_time") or "")[:16],
            ]
        )
        match = index.get(key)
        if not match and s.get("fixture_id"):
            for e in prod:
                if str(e.get("bet_type")) != str(s.get("bet_type")):
                    continue
                if str(e.get("fixture_date") or "")[:16] != str(s.get("kickoff_time") or "")[:16]:
                    continue
                if str(e.get("fixture_id") or "") == str(s.get("fixture_id")):
                    match = e
                    break
        if not match:
            continue
        status = str(match.get("status") or "").lower()
        if status not in {"won", "lost", "push"}:
            continue
        s["result"] = status
        s["pnl_units"] = _pnl(status, float(s.get("odds_at_signal") or match.get("odds") or 0))
        s["settled_from"] = "production_bet_log_readonly"
        updated += 1

    upsert_signals(data_dir, signals)
    return {"updated": updated, "total_signals": len(signals)}
