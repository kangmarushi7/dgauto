"""Fair market probability helpers (margin-aware when opposite prices exist)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def fair_two_way(odds_yes: float, odds_no: float) -> tuple[float, float] | None:
    if odds_yes is None or odds_no is None:
        return None
    if not (odds_yes > 1 and odds_no > 1):
        return None
    raw_yes = 1.0 / odds_yes
    raw_no = 1.0 / odds_no
    total = raw_yes + raw_no
    if total <= 0:
        return None
    return raw_yes / total, raw_no / total


def fair_1x2(home: float, draw: float, away: float) -> tuple[float, float, float] | None:
    if not all(x and x > 1 for x in (home, draw, away)):
        return None
    raw = [1.0 / home, 1.0 / draw, 1.0 / away]
    s = sum(raw)
    return raw[0] / s, raw[1] / s, raw[2] / s


def attach_fair_market_probability(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach fair_market_probability when opposite prices are available.

    Season 2 +EV bet log does not include opposite-side or full 1X2 books per row.
    In that case fair_market_probability is NaN and availability is flagged.
    """
    out = df.copy()
    fair = []
    available = []
    method = []

    for _, row in out.iterrows():
        opp = row.get("opposite_odds")
        odds = row.get("odds")
        if pd.notna(opp) and float(opp) > 1 and pd.notna(odds) and float(odds) > 1:
            pair = fair_two_way(float(odds), float(opp))
            if pair is not None:
                fair.append(pair[0])
                available.append(True)
                method.append("two_way_overround")
                continue
        # No fabricated fair probability from single price.
        fair.append(np.nan)
        available.append(False)
        method.append("unavailable_no_opposite_price")

    out["fair_market_probability"] = fair
    out["fair_market_available"] = available
    out["fair_market_method"] = method
    out["raw_implied_not_fair"] = out["raw_market_implied_probability"]
    return out


def fair_market_report(df: pd.DataFrame) -> dict[str, Any]:
    n = len(df)
    avail = int(df["fair_market_available"].sum()) if n else 0
    return {
        "rows": n,
        "fair_market_available_n": avail,
        "fair_market_available_pct": avail / n if n else 0.0,
        "statement": (
            "Fair market probability (margin-removed) is available for rows with opposite prices."
            if avail
            else "Fair market probability unavailable for this dataset: opposite-side / full-book "
            "prices are not present. Raw 1/odds is retained as bookmaker-implied probability only "
            "and is NOT treated as margin-free fair probability."
        ),
    }
