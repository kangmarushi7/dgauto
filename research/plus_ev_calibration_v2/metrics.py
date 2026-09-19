"""Shared metrics for probability / betting research."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
BOOTSTRAP_N = 2000

PROB_BINS = [
    (0.50, 0.55),
    (0.55, 0.60),
    (0.60, 0.65),
    (0.65, 0.70),
    (0.70, 0.75),
    (0.75, 0.80),
    (0.80, 0.85),
    (0.85, 0.90),
    (0.90, 0.95),
    (0.95, 1.01),
]

EDGE_BUCKETS = [
    (-10.0, 0.0, "<0%"),
    (0.0, 0.01, "0–1%"),
    (0.01, 0.02, "1–2%"),
    (0.02, 0.03, "2–3%"),
    (0.03, 0.05, "3–5%"),
    (0.05, 0.10, "5–10%"),
    (0.10, 10.0, "10%+"),
]

ODDS_BANDS = [
    (1.0, 1.30, "1.00–1.30"),
    (1.30, 1.50, "1.30–1.50"),
    (1.50, 1.70, "1.50–1.70"),
    (1.70, 1.90, "1.70–1.90"),
    (1.90, 2.10, "1.90–2.10"),
    (2.10, 2.50, "2.10–2.50"),
    (2.50, 3.00, "2.50–3.00"),
    (3.00, 999.0, "3.00+"),
]

EDGE_THRESHOLDS = (0.01, 0.02, 0.03, 0.05)


def clip_prob(p: float, eps: float = 1e-6) -> float:
    return float(min(1.0 - eps, max(eps, p)))


def normalize_status(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in {"won", "win", "w"}:
        return "WON"
    if s in {"lost", "loss", "l"}:
        return "LOST"
    if s in {"push", "void"}:
        return "PUSH"
    if s in {"open", "pending", ""}:
        return "OPEN"
    return s.upper()


def pnl_flat(result: str, odds: float, units: float = 1.0) -> float:
    r = str(result).upper()
    if r == "WON":
        return (float(odds) - 1.0) * units if odds > 0 else units
    if r == "LOST":
        return -units
    if r == "PUSH":
        return 0.0
    return float("nan")


def ev_from_probability(p: float, odds: float) -> float:
    return float(p) * float(odds) - 1.0


def brier_score(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss_safe(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(y)
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (p >= lo) & (p < hi if i < n_bins - 1 else p <= hi)
        if not mask.any():
            continue
        ece += mask.sum() / n * abs(y[mask].mean() - p[mask].mean())
    return float(ece)


def calibration_slope_intercept(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    """Logistic calibration slope/intercept of outcomes on logit(p)."""
    from sklearn.linear_model import LogisticRegression

    p = np.clip(p, 1e-6, 1 - 1e-6)
    logit = np.log(p / (1 - p)).reshape(-1, 1)
    if len(np.unique(y)) < 2:
        return float("nan"), float("nan")
    lr = LogisticRegression(fit_intercept=True, max_iter=500)
    lr.fit(logit, y.astype(int))
    return float(lr.coef_[0][0]), float(lr.intercept_[0])


def probability_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    slope, intercept = calibration_slope_intercept(y, p)
    return {
        "n": int(len(y)),
        "brier": brier_score(y, p),
        "log_loss": log_loss_safe(y, p),
        "ece": expected_calibration_error(y, p),
        "calibration_slope": slope,
        "calibration_intercept": intercept,
    }


def performance_metrics(sub: pd.DataFrame, pnl_col: str = "pnl_calc") -> dict[str, Any]:
    if sub is None or len(sub) == 0:
        return {"bets": 0}
    wins = int((sub["status_norm"] == "WON").sum())
    losses = int((sub["status_norm"] == "LOST").sum())
    pushes = int((sub["status_norm"] == "PUSH").sum())
    pnl = sub[pnl_col].astype(float)
    total = float(pnl.sum())
    stake = float(len(sub))
    cum = pnl.cumsum()
    dd = float((cum - cum.cummax()).min()) if len(pnl) else 0.0
    gains = float(pnl[pnl > 0].sum())
    losses_abs = abs(float(pnl[pnl < 0].sum()))
    std = float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0
    return {
        "bets": int(len(sub)),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate_ex_push": wins / (wins + losses) if (wins + losses) else float("nan"),
        "average_odds": float(sub["odds"].mean()),
        "total_pnl": total,
        "roi": total / stake if stake else float("nan"),
        "max_drawdown": dd,
        "profit_factor": gains / losses_abs if losses_abs > 0 else float("inf"),
        "pnl_std": std,
        "sharpe_like": float(pnl.mean() / std * math.sqrt(len(pnl))) if std > 0 else float("nan"),
    }


def bootstrap_mean_ci(values: np.ndarray, n: int = BOOTSTRAP_N) -> dict[str, float]:
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    samples = [float(RNG.choice(values, size=len(values), replace=True).mean()) for _ in range(n)]
    return {
        "mean": float(np.mean(samples)),
        "ci_low": float(np.percentile(samples, 2.5)),
        "ci_high": float(np.percentile(samples, 97.5)),
    }


def bin_probability_table(df: pd.DataFrame, prob_col: str) -> pd.DataFrame:
    rows = []
    for lo, hi in PROB_BINS:
        sub = df[(df[prob_col] >= lo) & (df[prob_col] < hi)].copy()
        y = sub["outcome_win"].dropna()
        if len(sub) == 0:
            rows.append(
                {
                    "bin": f"{lo:.2f}–{hi:.2f}",
                    "n": 0,
                    "mean_predicted": float("nan"),
                    "actual_win_rate": float("nan"),
                    "calibration_error": float("nan"),
                    "total_pnl": 0.0,
                    "roi": float("nan"),
                }
            )
            continue
        pred = float(sub[prob_col].mean())
        wr = float(y.mean()) if len(y) else float("nan")
        pnl = float(sub["pnl_calc"].sum())
        rows.append(
            {
                "bin": f"{lo:.2f}–{hi:.2f}",
                "n": int(len(sub)),
                "mean_predicted": pred,
                "actual_win_rate": wr,
                "calibration_error": (wr - pred) if not math.isnan(wr) else float("nan"),
                "total_pnl": pnl,
                "roi": pnl / len(sub),
            }
        )
    return pd.DataFrame(rows)
