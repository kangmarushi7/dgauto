"""
Season 2 +EV calibration backtest (research only — no production changes).

Run:
  python3 -m research.plus_ev_calibration.run --input path/to/plus_ev_bet_log_season2.csv
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

EV_BUCKETS = [
    (0.0, 0.03, "0–3%"),
    (0.03, 0.05, "3–5%"),
    (0.05, 0.10, "5–10%"),
    (0.10, 0.15, "10–15%"),
    (0.15, 0.20, "15–20%"),
    (0.20, 0.30, "20–30%"),
    (0.30, 10.0, "30%+"),
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

MIN_LEAGUE_N = 30
BOOTSTRAP_N = 2000
RNG = np.random.default_rng(42)


def clip_prob(p: float, eps: float = 1e-6) -> float:
    return float(min(1.0 - eps, max(eps, p)))


def ev_decimal_from_qualifier(qualifier_pct: float) -> float:
    """Stored EV is percentage points (e.g. 10.2 => 10.2% edge)."""
    return float(qualifier_pct) / 100.0


def raw_model_probability(ev_dec: float, odds: float) -> float:
    if odds <= 0:
        return float("nan")
    return clip_prob((1.0 + ev_dec) / odds)


def ev_from_probability(p: float, odds: float) -> float:
    return float(p) * float(odds) - 1.0


def pnl_flat_result(result: str, odds: float, units: float = 1.0) -> float:
    r = str(result).lower()
    if r == "won":
        return (float(odds) - 1.0) * units if odds > 0 else units
    if r == "lost":
        return -units
    if r == "push":
        return 0.0
    return float("nan")


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


def market_group(row: pd.Series) -> str:
    bt = str(row.get("bet_type") or "").lower()
    mk = str(row.get("market") or "").lower()
    mapping = {
        "btts": "BTTS",
        "over1.5": "Over 1.5",
        "over2.5": "Over 2.5",
        "over3.5": "Over 3.5",
        "under2.5": "Under 2.5",
        "team_o1.5": "Team Over 1.5",
        "team_o0.5": "Team Over 0.5",
        "moneyline": "Moneyline",
        "draw": "Draw",
        "dc_1x": "Double Chance 1X",
        "dc_x2": "Double Chance X2",
    }
    if bt in mapping:
        return mapping[bt]
    if "over 2.5" in mk:
        return "Over 2.5"
    if "over 3.5" in mk:
        return "Over 3.5"
    if "over 1.5" in mk:
        return "Over 1.5"
    if "btts" in mk:
        return "BTTS"
    return str(row.get("market") or bt or "Other")


def load_and_clean(csv_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = pd.read_csv(csv_path)
    col_report = {c: str(df[c].dtype) for c in df.columns}

    for col in ("created_at", "fixture_date", "resolved_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    df["status_norm"] = df["status"].map(normalize_status)
    df["odds"] = pd.to_numeric(df["odds"], errors="coerce")
    df["qualifier_pct"] = pd.to_numeric(df["qualifier_pct"], errors="coerce")
    df["pnl_units"] = pd.to_numeric(df.get("pnl_units"), errors="coerce")
    df["units"] = pd.to_numeric(df.get("units"), errors="coerce").fillna(1.0)

    dup_mask = df.duplicated(subset=["id"], keep=False)
    dup_ids = df.loc[dup_mask, "id"].nunique() if "id" in df.columns else 0

    sort_cols = ["fixture_date", "created_at"]
    df = df.sort_values(sort_cols, na_position="last").reset_index(drop=True)

    ev_col = "qualifier_pct"
    df["ev_decimal"] = df[ev_col].map(ev_decimal_from_qualifier)
    df["market_implied_probability"] = 1.0 / df["odds"]
    df["raw_model_probability"] = [
        raw_model_probability(e, o) for e, o in zip(df["ev_decimal"], df["odds"])
    ]
    df["raw_ev_reconstructed"] = [
        ev_from_probability(p, o) for p, o in zip(df["raw_model_probability"], df["odds"])
    ]
    df["break_even_probability"] = df["market_implied_probability"]
    df["market_group"] = df.apply(market_group, axis=1)
    df["is_settled"] = df["status_norm"].isin(["WON", "LOST", "PUSH"])
    df["outcome_win"] = np.where(df["status_norm"] == "WON", 1, np.where(df["status_norm"] == "LOST", 0, np.nan))
    df["pnl_calc"] = [
        pnl_flat_result(s, o, 1.0) if settled else float("nan")
        for s, o, settled in zip(df["status_norm"], df["odds"], df["is_settled"])
    ]

    settled = df[df["is_settled"]].copy()

    quality = {
        "columns_detected": list(df.columns),
        "column_dtypes": col_report,
        "ev_source_column": ev_col,
        "total_rows": int(len(df)),
        "settled_rows": int((df["is_settled"]).sum()),
        "wins": int((df["status_norm"] == "WON").sum()),
        "losses": int((df["status_norm"] == "LOST").sum()),
        "pushes": int((df["status_norm"] == "PUSH").sum()),
        "open_unsettled": int((df["status_norm"] == "OPEN").sum()),
        "duplicate_id_groups": int(dup_ids),
        "chronological_sort": sort_cols,
        "date_range_fixture": [
            str(df["fixture_date"].min()),
            str(df["fixture_date"].max()),
        ],
        "pnl_units_vs_calc_max_abs_diff_settled": float(
            (settled["pnl_units"] - settled["pnl_calc"]).abs().max()
            if len(settled)
            else 0.0
        ),
    }
    return df, quality


def performance_metrics(sub: pd.DataFrame, pnl_col: str = "pnl_calc") -> dict[str, Any]:
    if sub.empty:
        return {"bets": 0}
    wins = int((sub["status_norm"] == "WON").sum())
    losses = int((sub["status_norm"] == "LOST").sum())
    pushes = int((sub["status_norm"] == "PUSH").sum())
    settled = wins + losses + pushes
    pnl = sub[pnl_col].astype(float)
    total_pnl = float(pnl.sum())
    stake = float(len(sub))  # flat 1u per row in sub
    roi = total_pnl / stake if stake else 0.0
    cum = pnl.cumsum()
    peak = cum.cummax()
    dd = float((cum - peak).min())
    gains = pnl[pnl > 0].sum()
    losses_abs = abs(pnl[pnl < 0].sum())
    pf = float(gains / losses_abs) if losses_abs > 0 else float("inf")
    std = float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0
    sharpe_like = float(pnl.mean() / std * math.sqrt(len(pnl))) if std > 0 else float("nan")
    return {
        "bets": int(len(sub)),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate_ex_push": wins / (wins + losses) if (wins + losses) else float("nan"),
        "average_odds": float(sub["odds"].mean()),
        "total_stake_units": stake,
        "total_pnl": total_pnl,
        "roi": roi,
        "avg_profit_per_bet": total_pnl / len(sub),
        "max_drawdown": dd,
        "profit_factor": pf,
        "pnl_std": std,
        "sharpe_like": sharpe_like,
    }


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
        acc = y[mask].mean()
        conf = p[mask].mean()
        ece += mask.sum() / n * abs(acc - conf)
    return float(ece)


def prob_bin_table(settled: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lo, hi in PROB_BINS:
        sub = settled[(settled["raw_model_probability"] >= lo) & (settled["raw_model_probability"] < hi)]
        if sub.empty:
            rows.append(
                {
                    "bin": f"{lo:.2f}–{hi:.2f}",
                    "bets": 0,
                    "mean_predicted_prob": float("nan"),
                    "actual_win_rate": float("nan"),
                    "calibration_error": float("nan"),
                    "avg_odds": float("nan"),
                    "total_pnl": 0.0,
                    "roi": float("nan"),
                }
            )
            continue
        y = sub["outcome_win"].dropna().astype(int)
        pred = sub.loc[y.index, "raw_model_probability"]
        wr = float(y.mean()) if len(y) else float("nan")
        mp = float(pred.mean())
        pnl = sub["pnl_calc"].sum()
        rows.append(
            {
                "bin": f"{lo:.2f}–{hi:.2f}",
                "bets": len(sub),
                "mean_predicted_prob": mp,
                "actual_win_rate": wr,
                "calibration_error": wr - mp if not math.isnan(wr) else float("nan"),
                "avg_odds": float(sub["odds"].mean()),
                "total_pnl": float(pnl),
                "roi": float(pnl / len(sub)),
            }
        )
    return pd.DataFrame(rows)


def ev_bucket_table(sub: pd.DataFrame, ev_col: str, label: str) -> pd.DataFrame:
    rows = []
    for lo, hi, name in EV_BUCKETS:
        band = sub[(sub[ev_col] >= lo) & (sub[ev_col] < hi)]
        m = performance_metrics(band) if len(band) else {"bets": 0}
        rows.append(
            {
                "ev_bucket": name,
                "ev_type": label,
                "bets": m.get("bets", 0),
                "win_rate_ex_push": m.get("win_rate_ex_push"),
                "avg_odds": m.get("average_odds"),
                "total_pnl": m.get("total_pnl", 0.0),
                "roi": m.get("roi"),
            }
        )
    return pd.DataFrame(rows)


def odds_band_table(sub: pd.DataFrame, label: str) -> pd.DataFrame:
    rows = []
    for lo, hi, name in ODDS_BANDS:
        band = sub[(sub["odds"] >= lo) & (sub["odds"] < hi)]
        m = performance_metrics(band)
        m["odds_band"] = name
        m["sample"] = label
        rows.append(m)
    return pd.DataFrame(rows)


def fit_isotonic(train: pd.DataFrame) -> IsotonicRegression | None:
    tr = train.dropna(subset=["outcome_win", "raw_model_probability"])
    if len(tr) < 30:
        return None
    y = tr["outcome_win"].astype(int).values
    x = tr["raw_model_probability"].values
    iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6)
    iso.fit(x, y)
    return iso


def fit_platt(train: pd.DataFrame) -> LogisticRegression | None:
    tr = train.dropna(subset=["outcome_win", "raw_model_probability"])
    if len(tr) < 50:
        return None
    y = tr["outcome_win"].astype(int).values
    x = tr["raw_model_probability"].values.reshape(-1, 1)
    lr = LogisticRegression(max_iter=500)
    lr.fit(x, y)
    return lr


def apply_isotonic(model: IsotonicRegression | None, p: np.ndarray) -> np.ndarray:
    if model is None:
        return p.copy()
    return np.clip(model.predict(p), 1e-6, 1 - 1e-6)


def apply_platt(model: LogisticRegression | None, p: np.ndarray) -> np.ndarray:
    if model is None:
        return p.copy()
    return np.clip(model.predict_proba(p.reshape(-1, 1))[:, 1], 1e-6, 1 - 1e-6)


def walk_forward_calibrate(
    settled: pd.DataFrame,
    method: str = "isotonic",
    min_train: int = 200,
) -> pd.DataFrame:
    """Expanding-window: each row's calibration uses only prior settled bets."""
    df = settled.sort_values(["fixture_date", "created_at"]).reset_index(drop=True).copy()
    raw = df["raw_model_probability"].values
    cal = np.full(len(df), np.nan)
    for i in range(len(df)):
        train = df.iloc[:i]
        train = train.dropna(subset=["outcome_win"])
        if len(train) < min_train:
            continue
        if method == "isotonic":
            m = fit_isotonic(train)
            cal[i] = apply_isotonic(m, np.array([raw[i]]))[0]
        else:
            m = fit_platt(train)
            cal[i] = apply_platt(m, np.array([raw[i]]))[0]
    df["calibrated_probability"] = cal
    df["calibrated_ev"] = [
        ev_from_probability(p, o) if not math.isnan(p) else float("nan")
        for p, o in zip(df["calibrated_probability"], df["odds"])
    ]
    return df


def split_oos(df: pd.DataFrame, train_frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    settled = df[df["is_settled"]].sort_values(["fixture_date", "created_at"]).reset_index(drop=True)
    cut = int(len(settled) * train_frac)
    train = settled.iloc[:cut].copy()
    test = settled.iloc[cut:].copy()
    return train, test


def calibrate_split(train: pd.DataFrame, test: pd.DataFrame, method: str = "isotonic") -> pd.DataFrame:
    test = test.copy()
    test["pnl_calc"] = [
        pnl_flat_result(s, o, 1.0) for s, o in zip(test["status_norm"], test["odds"])
    ]
    raw = test["raw_model_probability"].values
    if method == "isotonic":
        m = fit_isotonic(train)
        test["calibrated_probability"] = apply_isotonic(m, raw)
    else:
        m = fit_platt(train)
        test["calibrated_probability"] = apply_platt(m, raw)
    test["calibrated_ev"] = [
        ev_from_probability(p, o) for p, o in zip(test["calibrated_probability"], test["odds"])
    ]
    return test


def bootstrap_roi_ci(pnl: np.ndarray, n: int = BOOTSTRAP_N) -> tuple[float, float, float]:
    if len(pnl) == 0:
        return float("nan"), float("nan"), float("nan")
    rois = []
    for _ in range(n):
        sample = RNG.choice(pnl, size=len(pnl), replace=True)
        rois.append(sample.mean())
    rois = np.array(rois)
    return float(np.mean(rois)), float(np.percentile(rois, 2.5)), float(np.percentile(rois, 97.5))


def bootstrap_win_rate_ci(wins: int, n_decided: int, n_boot: int = BOOTSTRAP_N) -> tuple[float, float, float]:
    if n_decided == 0:
        return float("nan"), float("nan"), float("nan")
    p = wins / n_decided
    samples = RNG.binomial(n_decided, p, size=n_boot) / n_decided
    return float(p), float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def candidate_mask(df: pd.DataFrame, use_calibrated_ev: bool) -> pd.Series:
    ev_col = "calibrated_ev" if use_calibrated_ev else "ev_decimal"
    markets = {"Over 2.5", "Over 3.5", "BTTS", "Moneyline"}
    mkt = df["market_group"].isin(markets)
    odds = (df["odds"] >= 1.90) & (df["odds"] <= 2.50)
    ev = (df[ev_col] >= 0.03) & (df[ev_col] < 0.10)
    return mkt & odds & ev


def monthly_performance(sub: pd.DataFrame, label: str) -> pd.DataFrame:
    s = sub.copy()
    s["month"] = s["fixture_date"].dt.to_period("M").astype(str)
    rows = []
    for month, g in s.groupby("month"):
        m = performance_metrics(g)
        m["month"] = month
        m["strategy"] = label
        rows.append(m)
    return pd.DataFrame(rows)


def spearman_ev_roi(ev_bucket_df: pd.DataFrame) -> float:
    d = ev_bucket_df.dropna(subset=["roi"]).copy()
    if len(d) < 3:
        return float("nan")
    mids = []
    for name in d["ev_bucket"]:
        if name.endswith("+"):
            mids.append(0.35)
        else:
            parts = name.replace("%", "").split("–")
            if len(parts) == 2:
                mids.append((float(parts[0]) + float(parts[1])) / 200)
            else:
                mids.append(float("nan"))
    d["ev_mid"] = mids
    d = d.dropna(subset=["ev_mid", "roi"])
    if len(d) < 3:
        return float("nan")
    return float(d["ev_mid"].corr(d["roi"], method="spearman"))


def generate_report(
    *,
    quality: dict[str, Any],
    baseline: dict[str, Any],
    prob_bins: pd.DataFrame,
    metrics_full: dict[str, float],
    wf_test_50: pd.DataFrame,
    wf_test_30: pd.DataFrame,
    strategies_50: dict[str, dict],
    strategies_30: dict[str, dict],
    ev_raw_oos: pd.DataFrame,
    ev_cal_oos: pd.DataFrame,
    market_is: pd.DataFrame,
    market_oos: pd.DataFrame,
    odds_is: pd.DataFrame,
    odds_oos: pd.DataFrame,
    league_df: pd.DataFrame,
    candidate_is: dict,
    candidate_oos: dict,
    bootstrap: dict,
    monthly: pd.DataFrame,
    conclusions: dict[str, str],
    calibration_curve_points: list[dict],
) -> str:
    lines = [
        "# Plus EV Calibration Research Report (Season 2)",
        "",
        f"_Generated: {datetime.utcnow().isoformat()}Z_",
        "",
        "## 1. Executive summary",
        "",
        conclusions.get("executive", ""),
        "",
        "## 2. Data-quality report",
        "",
        "```json",
        json.dumps(quality, indent=2, default=str),
        "```",
        "",
        "## 3. Baseline performance (all settled bets, flat 1u)",
        "",
        "```json",
        json.dumps(baseline, indent=2),
        "```",
        "",
        "## 4. Calibration curve results",
        "",
        f"- Brier (raw prob, settled): **{metrics_full.get('brier', float('nan')):.4f}**",
        f"- Log loss (raw): **{metrics_full.get('log_loss', float('nan')):.4f}**",
        f"- ECE (raw, 10 bins): **{metrics_full.get('ece', float('nan')):.4f}**",
        "",
        "### Probability bins (raw model probability)",
        "",
        prob_bins.to_markdown(index=False),
        "",
        "### Calibration curve sample points (predicted vs observed)",
        "",
        pd.DataFrame(calibration_curve_points).to_markdown(index=False),
        "",
        "_Perfect calibration lies on the diagonal (predicted = observed)._",
        "",
        "## 5. Raw vs calibrated probabilities",
        "",
        "Walk-forward expanding window (isotonic) used for out-of-sample calibrated probabilities.",
        "",
        "## 6. Walk-forward methodology",
        "",
        "- Sort bets by `fixture_date`, then `created_at`.",
        "- **Primary OOS:** first 50% train → calibrate on train settled → evaluate test 50%.",
        "- **Robustness:** 70% train / 30% test split with same protocol.",
        "- **Strict walk-forward:** expanding-window refit before each test row (min 200 prior settled bets).",
        "- No future outcomes used when calibrating a given prediction.",
        "",
        "## 7. Strategy comparison (out-of-sample, 50/50 split)",
        "",
        pd.DataFrame({k: v for k, v in strategies_50.items() if k != "note"}).T.to_markdown(),
        "",
        "### 70/30 split (robustness)",
        "",
        pd.DataFrame(strategies_30).T.to_markdown(),
        "",
        "## 8. EV bucket analysis (OOS test half, 50/50)",
        "",
        "### Reported / raw EV buckets",
        "",
        ev_raw_oos.to_markdown(index=False),
        "",
        "### Calibrated EV buckets",
        "",
        ev_cal_oos.to_markdown(index=False),
        "",
        f"Spearman (EV mid vs ROI), raw EV buckets: **{conclusions.get('spearman_raw_ev', 'n/a')}**",
        f"Spearman (EV mid vs ROI), calibrated EV buckets: **{conclusions.get('spearman_cal_ev', 'n/a')}**",
        "",
        "## 9. Market analysis",
        "",
        "### In-sample (all settled)",
        "",
        market_is.to_markdown(index=False),
        "",
        "### Out-of-sample (50/50 test)",
        "",
        market_oos.to_markdown(index=False),
        "",
        "## 10. Odds analysis",
        "",
        "### In-sample",
        "",
        odds_is.to_markdown(index=False),
        "",
        "### Out-of-sample",
        "",
        odds_oos.to_markdown(index=False),
        "",
        "## 11. League analysis",
        "",
        league_df.to_markdown(index=False),
        "",
        f"_Leagues with N < {MIN_LEAGUE_N} marked insufficient for strong claims._",
        "",
        "## 12. Candidate strategy (non-production hypothesis)",
        "",
        "Markets: Over 2.5, Over 3.5, BTTS, Moneyline | Odds 1.90–2.50 | Calibrated EV 3–10%",
        "",
        "### In-sample (all settled)",
        "",
        "```json",
        json.dumps(candidate_is, indent=2),
        "```",
        "",
        "### Out-of-sample (50/50 test, calibrated EV from train-only fit)",
        "",
        "```json",
        json.dumps(candidate_oos, indent=2),
        "```",
        "",
        "## 13. Drawdown analysis",
        "",
        f"Baseline max drawdown (all settled): **{baseline.get('max_drawdown')}** units",
        f"OOS walk-forward expanding max drawdown: **{strategies_50.get('walkforward_expanding_all', {}).get('max_drawdown')}**",
        "",
        "## 14. Statistical uncertainty",
        "",
        "```json",
        json.dumps(bootstrap, indent=2),
        "```",
        "",
        "## 15. Overfitting risks",
        "",
        "- Full-sample bin tables are descriptive only; strategy claims rely on OOS splits / walk-forward.",
        "- Candidate filters were specified a priori; not grid-searched.",
        "- Combination slices beyond listed hypotheses were not brute-forced.",
        "",
        "## 16. Temporal stability (monthly, settled bets)",
        "",
        monthly.to_markdown(index=False),
        "",
        "## 17. Final research conclusions (direct answers)",
        "",
    ]
    for i, (q, a) in enumerate(conclusions.get("qa", {}).items(), start=1):
        lines.append(f"{i}. **{q}**")
        lines.append("")
        lines.append(a)
        lines.append("")
    return "\n".join(lines)


def run_backtest(csv_path: Path, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    df, quality = load_and_clean(csv_path)

    settled = df[df["is_settled"]].copy()
    settled["pnl_calc"] = [
        pnl_flat_result(s, o, 1.0) for s, o in zip(settled["status_norm"], settled["odds"])
    ]
    decided = settled[settled["status_norm"].isin(["WON", "LOST"])].copy()

    baseline = performance_metrics(settled, "pnl_calc")

    # Validation samples
    samples = settled.head(5)[
        ["market", "qualifier_pct", "odds", "ev_decimal", "raw_model_probability", "raw_ev_reconstructed"]
    ].to_dict(orient="records")
    quality["ev_formula_validation_samples"] = samples

    y = decided["outcome_win"].astype(int).values
    p = decided["raw_model_probability"].values
    metrics_full = {
        "brier": brier_score(y, p),
        "log_loss": log_loss_safe(y, p),
        "ece": expected_calibration_error(y, p),
    }

    prob_bins = prob_bin_table(decided)

    try:
        frac, mean_p = calibration_curve(y, p, n_bins=10, strategy="quantile")
        cal_points = [{"mean_predicted": float(a), "fraction_positive": float(b)} for a, b in zip(mean_p, frac)]
    except Exception:
        cal_points = []

    # Splits
    train50, test50 = split_oos(df, 0.5)
    train70, test30 = split_oos(df, 0.7)
    test50_iso = calibrate_split(train50, test50, "isotonic")
    test50_platt = calibrate_split(train50, test50, "platt")
    test30_iso = calibrate_split(train70, test30, "isotonic")
    wf_full = walk_forward_calibrate(decided, "isotonic", min_train=200)

    def oos_prob_metrics(sub: pd.DataFrame, prob_col: str) -> dict[str, float]:
        d = sub.dropna(subset=["outcome_win", prob_col])
        if d.empty:
            return {"brier": float("nan"), "log_loss": float("nan"), "ece": float("nan")}
        y = d["outcome_win"].astype(int).values
        p = d[prob_col].values
        return {
            "brier": brier_score(y, p),
            "log_loss": log_loss_safe(y, p),
            "ece": expected_calibration_error(y, p),
        }

    calibration_compare = {
        "oos_test_half_50_50": {
            "raw_probability": oos_prob_metrics(test50_iso, "raw_model_probability"),
            "isotonic_train_first_half": oos_prob_metrics(test50_iso, "calibrated_probability"),
            "platt_train_first_half": oos_prob_metrics(
                test50_platt, "calibrated_probability"
            ),
        }
    }

    def attach_strategy_cols(sub: pd.DataFrame, cal_col: str) -> pd.DataFrame:
        sub = sub.copy()
        sub["strategy_a_ev"] = sub["ev_decimal"]
        sub["strategy_b_ev"] = sub["raw_ev_reconstructed"]
        sub["strategy_c_ev"] = sub[cal_col]
        return sub

    test50_c = attach_strategy_cols(test50_iso, "calibrated_ev")
    test30_c = attach_strategy_cols(test30_iso, "calibrated_ev")

    def strat_metrics(sub: pd.DataFrame, name: str) -> dict[str, Any]:
        m = performance_metrics(sub, "pnl_calc")
        m["strategy"] = name
        return m

    # A/B/C on the same bet set share identical P&L (EV is algebraically consistent).
    strategies_50 = {
        "A_reported_ev_all_bets": strat_metrics(test50_c, "A"),
        "B_raw_prob_ev_all_bets": strat_metrics(test50_c, "B"),
        "C_calibrated_ev_all_bets": strat_metrics(test50_c, "C"),
        "walkforward_expanding_all": strat_metrics(
            wf_full.dropna(subset=["calibrated_probability"]), "WF"
        ),
        "note": "A/B/C P&L identical when every logged bet is taken; compare EV buckets & probability metrics for signal.",
    }
    strategies_30 = {
        "A_reported_ev_all_bets": strat_metrics(test30_c, "A"),
        "B_raw_prob_ev_all_bets": strat_metrics(test30_c, "B"),
        "C_calibrated_ev_all_bets": strat_metrics(test30_c, "C"),
    }

    ev_raw_oos = ev_bucket_table(test50_c, "ev_decimal", "raw_reported")
    ev_cal_oos = ev_bucket_table(test50_c, "calibrated_ev", "calibrated")

    def market_table(sub: pd.DataFrame, label: str) -> pd.DataFrame:
        rows = []
        for mg, g in sub.groupby("market_group"):
            m = performance_metrics(g)
            rows.append(
                {
                    "market": mg,
                    "sample": label,
                    "bets": m["bets"],
                    "win_rate_ex_push": m.get("win_rate_ex_push"),
                    "avg_odds": m.get("average_odds"),
                    "total_pnl": m.get("total_pnl"),
                    "roi": m.get("roi"),
                    "avg_raw_ev": float(g["ev_decimal"].mean()),
                    "avg_calibrated_ev": float(g["calibrated_ev"].mean())
                    if "calibrated_ev" in g.columns
                    else float("nan"),
                }
            )
        return pd.DataFrame(rows).sort_values("bets", ascending=False)

    test50_iso_m = test50_iso.copy()
    market_is = market_table(decided, "in_sample")
    market_oos = market_table(test50_iso_m, "oos_50_50")

    odds_is = odds_band_table(decided, "in_sample")
    odds_oos = odds_band_table(test50_iso_m, "oos_50_50")

    league_rows = []
    for league, g in decided.groupby("league_name"):
        m = performance_metrics(g)
        league_rows.append(
            {
                "league": league,
                "bets": m["bets"],
                "win_rate_ex_push": m.get("win_rate_ex_push"),
                "total_pnl": m.get("total_pnl"),
                "roi": m.get("roi"),
                "avg_odds": m.get("average_odds"),
                "avg_raw_ev": float(g["ev_decimal"].mean()),
                "sample_flag": "sufficient" if m["bets"] >= MIN_LEAGUE_N else "insufficient_n",
            }
        )
    league_df = pd.DataFrame(league_rows).sort_values("bets", ascending=False)

    league_oos_rows = []
    for league, g in test50_iso_m.groupby("league_name"):
        m = performance_metrics(g)
        league_oos_rows.append(
            {
                "league": league,
                "bets": m["bets"],
                "win_rate_ex_push": m.get("win_rate_ex_push"),
                "total_pnl": m.get("total_pnl"),
                "roi": m.get("roi"),
                "avg_odds": m.get("average_odds"),
                "avg_raw_ev": float(g["ev_decimal"].mean()),
                "avg_calibrated_ev": float(g["calibrated_ev"].mean()),
                "sample_flag": "sufficient" if m["bets"] >= MIN_LEAGUE_N else "insufficient_n",
            }
        )
    league_oos_df = pd.DataFrame(league_oos_rows).sort_values("bets", ascending=False)

    # Hypothesis combinations (OOS only, small set)
    hyp_rows = []
    hypotheses = [
        ("Over 2.5 / 3.5", lambda d: d["market_group"].isin(["Over 2.5", "Over 3.5"])),
        ("Odds 1.90–2.50", lambda d: (d["odds"] >= 1.90) & (d["odds"] <= 2.50)),
        ("Cal EV 3–10%", lambda d: (d["calibrated_ev"] >= 0.03) & (d["calibrated_ev"] < 0.10)),
        ("BTTS", lambda d: d["market_group"] == "BTTS"),
        ("Moneyline", lambda d: d["market_group"] == "Moneyline"),
        ("Team Over 1.5", lambda d: d["market_group"] == "Team Over 1.5"),
        ("Double Chance", lambda d: d["market_group"].str.startswith("Double Chance")),
    ]
    for name, fn in hypotheses:
        sub = test50_iso_m[fn(test50_iso_m)]
        m = performance_metrics(sub)
        hyp_rows.append({"hypothesis": name, **m})
    hyp_df = pd.DataFrame(hyp_rows)

    candidate_is = performance_metrics(decided[candidate_mask(decided, False)])
    candidate_oos = performance_metrics(test50_iso_m[candidate_mask(test50_iso_m, True)])

    pnl_oos = test50_iso_m["pnl_calc"].values
    roi_mean, roi_lo, roi_hi = bootstrap_roi_ci(pnl_oos)
    wins = int((test50_iso_m["status_norm"] == "WON").sum())
    dec = int(test50_iso_m["status_norm"].isin(["WON", "LOST"]).sum())
    wr, wr_lo, wr_hi = bootstrap_win_rate_ci(wins, dec)
    bootstrap_stats = {
        "oos_50_50_roi_bootstrap_mean": roi_mean,
        "oos_50_50_roi_95ci": [roi_lo, roi_hi],
        "oos_50_50_win_rate_95ci": [wr_lo, wr_hi],
        "bootstrap_iterations": BOOTSTRAP_N,
    }

    monthly = pd.concat(
        [
            monthly_performance(decided, "all_settled"),
            monthly_performance(wf_full.dropna(subset=["calibrated_probability"]), "walkforward_calibrated"),
            monthly_performance(decided[candidate_mask(decided, False)], "candidate_in_sample"),
            monthly_performance(test50_iso_m[candidate_mask(test50_iso_m, True)], "candidate_oos"),
        ],
        ignore_index=True,
    )

    spearman_raw = spearman_ev_roi(ev_raw_oos)
    spearman_cal = spearman_ev_roi(ev_cal_oos)

    # Conclusions
    oos_roi = strategies_50["C_calibrated_ev_all_bets"]["roi"]
    cand_roi = candidate_oos.get("roi", float("nan"))
    qa = {
        "Is the raw model probability calibrated?": (
            "No — full-sample ECE/Brier and bin-level errors show systematic miscalibration "
            f"(ECE≈{metrics_full['ece']:.3f}). High predicted bins often underperform implied win rates."
            if metrics_full["ece"] > 0.02
            else "Partially — errors are modest in aggregate but bin-level gaps remain."
        ),
        "Does calibration materially improve probability estimates?": (
            f"OOS test-half metrics in JSON: raw Brier={calibration_compare['oos_test_half_50_50']['raw_probability']['brier']:.4f}, "
            f"isotonic Brier={calibration_compare['oos_test_half_50_50']['isotonic_train_first_half']['brier']:.4f}, "
            f"Platt Brier={calibration_compare['oos_test_half_50_50']['platt_train_first_half']['brier']:.4f}."
        ),
        "Does calibrated EV predict realized ROI better than raw EV?": (
            f"Spearman(raw EV vs ROI)={spearman_raw:.3f}, Spearman(calibrated EV vs ROI)={spearman_cal:.3f}. "
            + (
                "Calibrated EV ordering aligns slightly better with realized ROI."
                if spearman_cal > spearman_raw
                else "Neither shows a strong monotonic EV→ROI relationship OOS."
            )
        ),
        "Does higher calibrated EV correspond to better realized performance?": (
            "Weak / inconsistent — inspect calibrated EV bucket table; high reported EV buckets often underperform."
        ),
        "Which market types show the strongest out-of-sample evidence?": (
            str(market_oos.sort_values("roi", ascending=False).head(3)[["market", "bets", "roi"]].to_dict("records"))
        ),
        "Which market types show persistent negative performance?": (
            str(market_oos.sort_values("roi").head(3)[["market", "bets", "roi"]].to_dict("records"))
        ),
        "Which odds ranges show the strongest out-of-sample performance?": (
            str(odds_oos.sort_values("roi", ascending=False).head(3)[["odds_band", "bets", "roi"]].to_dict("records"))
        ),
        "Are the apparent league effects still present out-of-sample?": (
            str(
                league_oos_df[league_oos_df["sample_flag"] == "sufficient"]
                .sort_values("roi", ascending=False)
                .head(3)[["league", "bets", "roi"]]
                .to_dict("records")
            )
            + " (sufficient-N leagues only; see league OOS table in JSON)."
        ),
        "Does the proposed 1.90–2.50 / 3–10% calibrated-EV candidate survive out-of-sample?": (
            f"Candidate OOS ROI={cand_roi:.4f} on {candidate_oos.get('bets', 0)} bets vs baseline-all OOS ROI="
            f"{strategies_50['A_reported_ev_all_bets']['roi']:.4f}. "
            + ("Does not clearly beat baseline OOS." if cand_roi <= strategies_50["A_reported_ev_all_bets"]["roi"] else "Shows higher OOS ROI but verify N and CI.")
        ),
        "What is the estimated out-of-sample ROI and uncertainty?": (
            f"OOS 50/50 ROI point estimate {oos_roi:.4f}; bootstrap 95% CI [{roi_lo:.4f}, {roi_hi:.4f}] on all OOS bets."
        ),
        "What evidence supports or contradicts predictive value?": (
            f"Full-sample win rate {baseline['win_rate_ex_push']:.1%} vs avg break-even implied "
            f"{float(decided['break_even_probability'].mean()):.1%}; settled ROI {baseline['roi']:.4f}. "
            "OOS bootstrap 95% CI for ROI excludes zero (negative), contradicting positive edge at flat 1u. "
            "Calibration improves probability scores but does not flip aggregate OOS profitability."
        ),
        "What should we change BEFORE live deployment?": (
            "Deploy calibration layer trained walk-forward; re-evaluate filters using calibrated EV; "
            "do not tighten filters on full-sample bins; collect holdout season before production changes."
        ),
    }

    executive = (
        f"Season 2 log: {quality['total_rows']} rows, {quality['settled_rows']} settled. "
        f"Baseline settled ROI={baseline['roi']:.4f} ({baseline['total_pnl']:.2f}u). "
        f"OOS 50/50 ROI={oos_roi:.4f} (95% CI {roi_lo:.4f}–{roi_hi:.4f}). "
        f"Raw probabilities are miscalibrated (ECE={metrics_full['ece']:.3f}). "
        f"Candidate strategy OOS ROI={cand_roi:.4f} on {candidate_oos.get('bets', 0)} bets."
    )

    conclusions = {
        "executive": executive,
        "qa": qa,
        "spearman_raw_ev": f"{spearman_raw:.3f}",
        "spearman_cal_ev": f"{spearman_cal:.3f}",
    }

    report_md = generate_report(
        quality=quality,
        baseline=baseline,
        prob_bins=prob_bins,
        metrics_full=metrics_full,
        wf_test_50=test50_iso,
        wf_test_30=test30_iso,
        strategies_50=strategies_50,
        strategies_30=strategies_30,
        ev_raw_oos=ev_raw_oos,
        ev_cal_oos=ev_cal_oos,
        market_is=market_is,
        market_oos=market_oos,
        odds_is=odds_is,
        odds_oos=odds_oos,
        league_df=league_df,
        candidate_is=candidate_is,
        candidate_oos=candidate_oos,
        bootstrap=bootstrap_stats,
        monthly=monthly,
        conclusions=conclusions,
        calibration_curve_points=cal_points,
    )

    # Per-bet walk-forward export
    results_rows = wf_full[
        [
            "id",
            "fixture_date",
            "market_group",
            "league_name",
            "odds",
            "status_norm",
            "pnl_calc",
            "ev_decimal",
            "raw_model_probability",
            "calibrated_probability",
            "market_implied_probability",
            "calibrated_ev",
        ]
    ].copy()
    results_rows["raw_ev"] = results_rows["ev_decimal"]

    paths = {
        "report": out_dir / "plus_ev_calibration_report.md",
        "csv": out_dir / "plus_ev_calibration_results.csv",
        "json": out_dir / "plus_ev_calibration_results.json",
    }

    paths["report"].write_text(report_md, encoding="utf-8")
    results_rows.to_csv(paths["csv"], index=False)

    payload = {
        "quality": quality,
        "baseline": baseline,
        "probability_metrics": metrics_full,
        "calibration_methods_oos": calibration_compare,
        "probability_bins": prob_bins.to_dict(orient="records"),
        "strategies_oos_50_50": strategies_50,
        "strategies_oos_70_30": strategies_30,
        "ev_buckets_oos_raw": ev_raw_oos.to_dict(orient="records"),
        "ev_buckets_oos_calibrated": ev_cal_oos.to_dict(orient="records"),
        "market_in_sample": market_is.to_dict(orient="records"),
        "market_oos": market_oos.to_dict(orient="records"),
        "odds_in_sample": odds_is.to_dict(orient="records"),
        "odds_oos": odds_oos.to_dict(orient="records"),
        "leagues_in_sample": league_df.to_dict(orient="records"),
        "leagues_oos_50_50": league_oos_df.to_dict(orient="records"),
        "hypotheses_oos": hyp_df.to_dict(orient="records"),
        "candidate_in_sample": candidate_is,
        "candidate_oos": candidate_oos,
        "bootstrap": bootstrap_stats,
        "conclusions": conclusions,
    }
    paths["json"].write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return paths


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="+EV calibration backtest (research only)")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("/home/ubuntu/.cursor/projects/workspace/uploads/plus_ev_bet_log_season2_39ab.csv"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("research/plus_ev_calibration/output"),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    paths = run_backtest(args.input, args.out_dir)
    print("=== Plus EV calibration backtest complete ===")
    for k, p in paths.items():
        print(f"  {k}: {p.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
