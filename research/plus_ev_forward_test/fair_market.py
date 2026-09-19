"""Fair market probability — only when mutually exclusive outcomes exist."""
from __future__ import annotations

from typing import Any


def fair_from_outcome_odds(outcome_odds: dict[str, float] | None) -> dict[str, Any]:
    """
    outcome_odds: mapping selection -> decimal odds for all outcomes in the market.
    Returns fair probs or unavailable.
    """
    if not outcome_odds:
        return {
            "fair_available": False,
            "fair_probabilities": None,
            "overround": None,
            "reason": "no_outcome_odds",
        }
    cleaned: dict[str, float] = {}
    for k, v in outcome_odds.items():
        try:
            o = float(v)
        except (TypeError, ValueError):
            continue
        if o > 1.0:
            cleaned[str(k)] = o
    if len(cleaned) < 2:
        return {
            "fair_available": False,
            "fair_probabilities": None,
            "overround": None,
            "reason": "need_at_least_two_outcomes",
        }
    raw = {k: 1.0 / o for k, o in cleaned.items()}
    overround = sum(raw.values())
    if overround <= 0:
        return {
            "fair_available": False,
            "fair_probabilities": None,
            "overround": None,
            "reason": "invalid_overround",
        }
    fair = {k: raw[k] / overround for k in raw}
    return {
        "fair_available": True,
        "fair_probabilities": fair,
        "overround": overround,
        "reason": "de_vig",
    }


def fair_probability_for_selection(
    selection_key: str,
    outcome_odds: dict[str, float] | None,
) -> float | None:
    info = fair_from_outcome_odds(outcome_odds)
    if not info["fair_available"]:
        return None
    probs = info["fair_probabilities"] or {}
    # try exact then fuzzy
    if selection_key in probs:
        return float(probs[selection_key])
    for k, v in probs.items():
        if k.lower() == str(selection_key).lower():
            return float(v)
    return None
