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


def expected_value_pct(model_pct: Any, odds: Any) -> float | None:
    """EV% for a single outcome: stake 1 unit, win (odds-1) with prob p, lose 1 with (1-p)."""
    p = num(model_pct)
    o = num(odds)
    if p is None or o is None or o <= 1:
        return None
    p_frac = p / 100.0
    ev = p_frac * o - 1.0
    return round(ev * 100.0, 1)


def kelly_fraction(model_pct: Any, odds: Any) -> float | None:
    """Full Kelly fraction of bankroll (0–1+); None if undefined."""
    p = num(model_pct)
    o = num(odds)
    if p is None or o is None or o <= 1:
        return None
    p_frac = p / 100.0
    q = 1.0 - p_frac
    b = o - 1.0
    if b <= 0:
        return None
    k = (p_frac * b - q) / b
    return round(max(0.0, k), 4)


def grade_label(grade: str | None) -> str:
    if not grade or grade == "—":
        return "—"
    return {
        "A+": "ELITE",
        "A": "STRONG",
        "B": "GOOD",
        "C": "MODERATE",
        "D": "WEAK",
    }.get(str(grade).strip(), str(grade))


def verdict_from_edge_strict(edge_val: float | None) -> str:
    """Strict edge buckets; no model-probability fallback."""
    e = num(edge_val)
    if e is None:
        return "NO EDGE"
    if e >= 8:
        return "STRONG VALUE"
    if e >= 4:
        return "VALUE"
    if e >= 2:
        return "LEAN"
    if e <= -2:
        return "AVOID"
    return "NO EDGE"


def certainty_score(
    *,
    edge_val: float | None,
    model_pct: float | None,
    draw_pct: float | None,
    total_xg: float | None,
    signal_score: float | None,
) -> tuple[int, str]:
    """0–100 score and HIGH/MEDIUM/LOW label."""
    e = abs(num(edge_val) or 0)
    m = num(model_pct) or 50
    d = num(draw_pct) or 0
    tx = num(total_xg) or 2.5
    sig = num(signal_score) or 50

    edge_pts = min(35, e * 3.5)
    model_pts = min(25, abs(m - 50) * 0.5)
    stability_pts = max(0, 20 - d * 0.35)
    xg_pts = 10 if 2.2 <= tx <= 3.4 else 5
    sig_pts = min(20, sig * 0.22)

    raw = edge_pts + model_pts + stability_pts + xg_pts + sig_pts
    score = int(max(0, min(100, round(raw))))
    if score >= 72:
        return score, "HIGH"
    if score >= 48:
        return score, "MEDIUM"
    return score, "LOW"
