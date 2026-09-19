"""CLV helpers — only when closing odds exist."""
from __future__ import annotations

from typing import Any

import numpy as np


def clv_from_odds(signal_odds: float, closing_odds: float | None) -> dict[str, Any]:
    """
    Methodology (documented):

    bet_implied = 1 / signal_odds
    close_implied = 1 / closing_odds

    clv_probability_points = close_implied - bet_implied
      > 0 means we obtained a better (longer) price than the close
        (our implied probability was lower than the closing implied).

    clv_odds_ratio = signal_odds / closing_odds - 1
      > 0 means our decimal odds were longer than close.

    Primary reported CLV metric: clv_probability_points.
    """
    try:
        so = float(signal_odds)
    except (TypeError, ValueError):
        return {"clv_available": False, "clv": None, "reason": "bad_signal_odds"}
    if closing_odds is None:
        return {"clv_available": False, "clv": None, "reason": "no_closing_odds"}
    try:
        co = float(closing_odds)
    except (TypeError, ValueError):
        return {"clv_available": False, "clv": None, "reason": "bad_closing_odds"}
    if so <= 1 or co <= 1:
        return {"clv_available": False, "clv": None, "reason": "odds_must_exceed_1"}
    bet_imp = 1.0 / so
    close_imp = 1.0 / co
    return {
        "clv_available": True,
        "bet_implied": bet_imp,
        "close_implied": close_imp,
        "clv": close_imp - bet_imp,
        "clv_odds_ratio": so / co - 1.0,
        "reason": "ok",
    }


def summarize_clv(values: list[float]) -> dict[str, Any]:
    arr = np.asarray([v for v in values if v is not None and not np.isnan(v)], dtype=float)
    if len(arr) == 0:
        return {
            "n": 0,
            "mean_clv": None,
            "median_clv": None,
            "pct_positive_clv": None,
        }
    return {
        "n": int(len(arr)),
        "mean_clv": float(arr.mean()),
        "median_clv": float(np.median(arr)),
        "pct_positive_clv": float((arr > 0).mean()),
        "std_clv": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
    }
