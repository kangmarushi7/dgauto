"""Shared numeric helpers for fixture analysis."""
from __future__ import annotations

from typing import Any


def num(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def fmt(val: Any, suffix: str = "", digits: int = 1) -> str:
    n = num(val)
    if n is None:
        return "—"
    if suffix == "%":
        return f"{n:.{digits}f}%"
    return f"{n:.{digits}f}{suffix}"


def implied_prob(odds: Any) -> float | None:
    o = num(odds)
    if o is None or o <= 1:
        return None
    return round(100.0 / o, 1)


def edge(sim_pct: Any, odds: Any) -> float | None:
    s = num(sim_pct)
    imp = implied_prob(odds)
    if s is None or imp is None:
        return None
    return round(s - imp, 1)
