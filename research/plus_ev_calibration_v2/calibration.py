"""Walk-forward Platt / isotonic calibration (no future leakage)."""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

Method = Literal["platt", "isotonic"]


def _fit_platt(x: np.ndarray, y: np.ndarray) -> LogisticRegression | None:
    if len(x) < 50 or len(np.unique(y)) < 2:
        return None
    lr = LogisticRegression(max_iter=500)
    lr.fit(x.reshape(-1, 1), y.astype(int))
    return lr


def _fit_isotonic(x: np.ndarray, y: np.ndarray) -> IsotonicRegression | None:
    if len(x) < 30 or len(np.unique(y)) < 2:
        return None
    iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6)
    iso.fit(x, y.astype(int))
    return iso


def _predict(method: Method, model, x: np.ndarray) -> np.ndarray:
    if model is None:
        return x.copy()
    if method == "platt":
        return np.clip(model.predict_proba(x.reshape(-1, 1))[:, 1], 1e-6, 1 - 1e-6)
    return np.clip(model.predict(x), 1e-6, 1 - 1e-6)


def walk_forward_calibrate(
    decided: pd.DataFrame,
    *,
    min_train: int = 200,
    fold: str = "month",
) -> pd.DataFrame:
    """
    Expanding-window calibration by chronological fold.

    For each test fold, fit Platt + isotonic on all prior decided bets only.
    """
    df = decided.sort_values(["fixture_date", "created_at"]).reset_index(drop=True).copy()
    df["month"] = df["fixture_date"].dt.tz_convert("UTC").dt.to_period("M").astype(str)

    platt = np.full(len(df), np.nan)
    iso = np.full(len(df), np.nan)
    fold_id = np.array([""] * len(df), dtype=object)

    if fold == "month":
        periods = sorted(df["month"].dropna().unique())
        for i, period in enumerate(periods):
            test_idx = df.index[df["month"] == period].to_numpy()
            train_mask = df["month"].isin(periods[:i])
            train = df.loc[train_mask].dropna(subset=["outcome_win", "raw_model_probability"])
            if len(train) < min_train:
                continue
            x_tr = train["raw_model_probability"].values
            y_tr = train["outcome_win"].values
            m_p = _fit_platt(x_tr, y_tr)
            m_i = _fit_isotonic(x_tr, y_tr)
            x_te = df.loc[test_idx, "raw_model_probability"].values
            platt[test_idx] = _predict("platt", m_p, x_te)
            iso[test_idx] = _predict("isotonic", m_i, x_te)
            fold_id[test_idx] = f"month:{period}|train_n={len(train)}"
    else:
        # Sequential blocks of ~equal size after warm-up.
        n = len(df)
        block = max(min_train // 2, 100)
        start = min_train
        while start < n:
            end = min(n, start + block)
            train = df.iloc[:start].dropna(subset=["outcome_win", "raw_model_probability"])
            if len(train) < min_train:
                start = end
                continue
            x_tr = train["raw_model_probability"].values
            y_tr = train["outcome_win"].values
            m_p = _fit_platt(x_tr, y_tr)
            m_i = _fit_isotonic(x_tr, y_tr)
            idx = np.arange(start, end)
            x_te = df.iloc[start:end]["raw_model_probability"].values
            platt[idx] = _predict("platt", m_p, x_te)
            iso[idx] = _predict("isotonic", m_i, x_te)
            fold_id[idx] = f"block:{start}-{end}|train_n={len(train)}"
            start = end

    df["platt_probability"] = platt
    df["isotonic_probability"] = iso
    df["calibration_fold"] = fold_id
    return df
