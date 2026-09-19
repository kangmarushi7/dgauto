"""Portfolio evidence status labels — no 'proven profitable' language."""
from __future__ import annotations

from typing import Any


def classify_portfolio(metrics: dict[str, Any]) -> str:
    """
    Classify using sample size + ROI/CLV signs.

    Labels allowed:
      INSUFFICIENT SAMPLE
      PROMISING — NEEDS MORE DATA
      MIXED
      NEGATIVE
      STRONGER EVIDENCE — CONTINUE VALIDATION
    """
    n = int(metrics.get("n") or metrics.get("bets") or 0)
    roi = metrics.get("roi")
    mean_clv = metrics.get("mean_clv")
    clv_n = int(metrics.get("clv_n") or 0)

    if n < 50:
        return "INSUFFICIENT SAMPLE"

    roi_pos = roi is not None and roi > 0
    roi_neg = roi is not None and roi < 0
    clv_pos = mean_clv is not None and clv_n >= 20 and mean_clv > 0
    clv_neg = mean_clv is not None and clv_n >= 20 and mean_clv < 0

    if n >= 250 and roi_pos and clv_pos:
        return "STRONGER EVIDENCE — CONTINUE VALIDATION"
    if n >= 100 and roi_pos and (clv_pos or clv_n < 20):
        return "PROMISING — NEEDS MORE DATA"
    if n >= 100 and roi_neg and clv_neg:
        return "NEGATIVE"
    if n >= 100 and ((roi_pos and clv_neg) or (roi_neg and clv_pos)):
        return "MIXED"
    if n >= 50 and roi_neg and (clv_neg or clv_n < 20):
        return "NEGATIVE"
    if n >= 50 and roi_pos:
        return "PROMISING — NEEDS MORE DATA"
    return "MIXED"


def sample_milestone(n: int) -> str:
    if n < 25:
        return "preliminary only (<25)"
    if n < 50:
        return "very weak evidence (25–49)"
    if n < 100:
        return "interesting (50–99)"
    if n < 250:
        return "meaningful (100–249)"
    if n < 500:
        return "strong forward-test sample building (250–499)"
    return "strong forward-test sample (≥500)"
