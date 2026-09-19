"""Calibration / reliability plots for research outputs."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve


def save_calibration_plot(
    y: np.ndarray,
    probs: dict[str, np.ndarray],
    out_path: Path,
    title: str = "Calibration curves",
) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration", linewidth=1)
    for name, p in probs.items():
        mask = ~np.isnan(p)
        if mask.sum() < 20:
            continue
        try:
            frac, mean_p = calibration_curve(y[mask], p[mask], n_bins=10, strategy="quantile")
            ax.plot(mean_p, frac, marker="o", label=name)
        except Exception:
            continue
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Observed win rate")
    ax.set_title(title)
    ax.legend(loc="best")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def save_edge_roi_plot(edge_df: pd.DataFrame, out_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(edge_df))
    ax.bar(x, edge_df["roi"].fillna(0), color="#3d6b5a")
    ax.set_xticks(x)
    ax.set_xticklabels(edge_df["edge_bucket"], rotation=30, ha="right")
    ax.set_ylabel("ROI")
    ax.set_title(title)
    ax.axhline(0, color="black", linewidth=0.8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
