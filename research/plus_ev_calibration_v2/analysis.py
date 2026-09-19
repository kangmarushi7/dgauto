"""Edge / market / odds / league / threshold analyses (no filter mining)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from research.plus_ev_calibration_v2.metrics import (
    EDGE_BUCKETS,
    EDGE_THRESHOLDS,
    ODDS_BANDS,
    bootstrap_mean_ci,
    ev_from_probability,
    performance_metrics,
)


def attach_edges(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["platt_EV"] = [
        ev_from_probability(p, o) if pd.notna(p) else np.nan
        for p, o in zip(out["platt_probability"], out["odds"])
    ]
    out["isotonic_EV"] = [
        ev_from_probability(p, o) if pd.notna(p) else np.nan
        for p, o in zip(out["isotonic_probability"], out["odds"])
    ]
    # Prefer fair market when available; otherwise mark edge vs fair as NaN.
    out["model_edge_vs_fair_market_platt"] = np.where(
        out["fair_market_available"],
        out["platt_probability"] - out["fair_market_probability"],
        np.nan,
    )
    out["model_edge_vs_fair_market_isotonic"] = np.where(
        out["fair_market_available"],
        out["isotonic_probability"] - out["fair_market_probability"],
        np.nan,
    )
    # Proxy edge vs raw bookmaker-implied (NOT margin-free fair). Documented as such.
    out["model_edge_vs_raw_implied_platt"] = out["platt_probability"] - out["raw_market_implied_probability"]
    out["model_edge_vs_raw_implied_isotonic"] = (
        out["isotonic_probability"] - out["raw_market_implied_probability"]
    )
    return out


def edge_bucket_table(df: pd.DataFrame, edge_col: str, label: str) -> pd.DataFrame:
    rows = []
    for lo, hi, name in EDGE_BUCKETS:
        sub = df[(df[edge_col] >= lo) & (df[edge_col] < hi)]
        m = performance_metrics(sub)
        roi_ci = bootstrap_mean_ci(sub["pnl_calc"].values) if len(sub) else {}
        rows.append(
            {
                "edge_bucket": name,
                "edge_definition": label,
                "n": m.get("bets", 0),
                "avg_edge": float(sub[edge_col].mean()) if len(sub) else float("nan"),
                "win_rate_ex_push": m.get("win_rate_ex_push"),
                "total_pnl": m.get("total_pnl", 0.0),
                "roi": m.get("roi"),
                "roi_ci_low": roi_ci.get("ci_low"),
                "roi_ci_high": roi_ci.get("ci_high"),
                "clv": None,
            }
        )
    return pd.DataFrame(rows)


def market_table(df: pd.DataFrame, edge_col: str) -> pd.DataFrame:
    rows = []
    for mg, g in df.groupby("market_group"):
        m = performance_metrics(g)
        rows.append(
            {
                "market": mg,
                "n": m.get("bets", 0),
                "win_rate_ex_push": m.get("win_rate_ex_push"),
                "avg_odds": m.get("average_odds"),
                "total_pnl": m.get("total_pnl"),
                "roi": m.get("roi"),
                "avg_edge": float(g[edge_col].mean()) if edge_col in g else float("nan"),
                "avg_platt_prob": float(g["platt_probability"].mean()),
                "avg_raw_prob": float(g["raw_model_probability"].mean()),
                "clv": None,
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def odds_table(df: pd.DataFrame, edge_col: str) -> pd.DataFrame:
    rows = []
    for lo, hi, name in ODDS_BANDS:
        g = df[(df["odds"] >= lo) & (df["odds"] < hi)]
        m = performance_metrics(g)
        cal_err = float((g["outcome_win"] - g["platt_probability"]).mean()) if len(g) else float("nan")
        rows.append(
            {
                "odds_band": name,
                "n": m.get("bets", 0),
                "roi": m.get("roi"),
                "avg_edge": float(g[edge_col].mean()) if len(g) else float("nan"),
                "calibration_error_platt": cal_err,
                "avg_odds": m.get("average_odds"),
                "total_pnl": m.get("total_pnl"),
                "clv": None,
            }
        )
    return pd.DataFrame(rows)


def league_table(df: pd.DataFrame, edge_col: str, min_n: int = 30) -> pd.DataFrame:
    rows = []
    for league, g in df.groupby("league_name"):
        m = performance_metrics(g)
        rows.append(
            {
                "league": league,
                "n": m.get("bets", 0),
                "win_rate_ex_push": m.get("win_rate_ex_push"),
                "roi": m.get("roi"),
                "total_pnl": m.get("total_pnl"),
                "avg_odds": m.get("average_odds"),
                "avg_edge": float(g[edge_col].mean()) if len(g) else float("nan"),
                "sample_flag": "sufficient" if m.get("bets", 0) >= min_n else "insufficient_n",
                "clv": None,
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def monthly_table(df: pd.DataFrame, edge_col: str) -> pd.DataFrame:
    s = df.copy()
    s["month"] = s["fixture_date"].dt.tz_convert("UTC").dt.to_period("M").astype(str)
    rows = []
    for month, g in s.groupby("month"):
        m = performance_metrics(g)
        rows.append(
            {
                "month": month,
                "n": m.get("bets", 0),
                "roi": m.get("roi"),
                "win_rate_ex_push": m.get("win_rate_ex_push"),
                "avg_edge": float(g[edge_col].mean()) if len(g) else float("nan"),
                "total_pnl": m.get("total_pnl"),
                "clv": None,
            }
        )
    return pd.DataFrame(rows)


def threshold_sensitivity(df: pd.DataFrame, edge_col: str) -> pd.DataFrame:
    """Predefined sensitivity tests: take bet if edge > fixed threshold. Report all."""
    rows = []
    for thr in EDGE_THRESHOLDS:
        sub = df[df[edge_col] > thr]
        m = performance_metrics(sub)
        roi_ci = bootstrap_mean_ci(sub["pnl_calc"].values) if len(sub) else {}
        rows.append(
            {
                "rule": f"{edge_col} > {thr:.0%}",
                "threshold": thr,
                "n": m.get("bets", 0),
                "roi": m.get("roi"),
                "total_pnl": m.get("total_pnl"),
                "win_rate_ex_push": m.get("win_rate_ex_push"),
                "avg_odds": m.get("average_odds"),
                "max_drawdown": m.get("max_drawdown"),
                "roi_ci_low": roi_ci.get("ci_low"),
                "roi_ci_high": roi_ci.get("ci_high"),
            }
        )
    # Also report all-bets baseline for comparison
    base = performance_metrics(df)
    rows.insert(
        0,
        {
            "rule": "all OOS bets (no edge filter)",
            "threshold": None,
            "n": base.get("bets", 0),
            "roi": base.get("roi"),
            "total_pnl": base.get("total_pnl"),
            "win_rate_ex_push": base.get("win_rate_ex_push"),
            "avg_odds": base.get("average_odds"),
            "max_drawdown": base.get("max_drawdown"),
            "roi_ci_low": bootstrap_mean_ci(df["pnl_calc"].values).get("ci_low"),
            "roi_ci_high": bootstrap_mean_ci(df["pnl_calc"].values).get("ci_high"),
        },
    )
    return pd.DataFrame(rows)


def spearman(edge: pd.Series, roi_by_bucket_mids: pd.Series) -> float:
    d = pd.DataFrame({"e": edge, "r": roi_by_bucket_mids}).dropna()
    if len(d) < 3:
        return float("nan")
    return float(d["e"].corr(d["r"], method="spearman"))


def edge_roi_relationship(edge_df: pd.DataFrame) -> dict[str, Any]:
    mids = []
    for name in edge_df["edge_bucket"]:
        if name == "<0%":
            mids.append(-0.01)
        elif name.endswith("+"):
            mids.append(0.12)
        else:
            a, b = name.replace("%", "").split("–")
            mids.append((float(a) + float(b)) / 200.0)
    return {
        "spearman_edge_mid_vs_roi": spearman(pd.Series(mids), edge_df["roi"]),
        "buckets": edge_df.to_dict(orient="records"),
    }
