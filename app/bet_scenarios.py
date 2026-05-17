"""Scenario thresholds and labels aligned with DataGaffer historical tables."""

from __future__ import annotations

# (bet_type, display label, historical hit rate % for UI reference)
BET_TYPE_META: list[tuple[str, str, float]] = [
    ("moneyline", "Moneyline", 0.0),
    ("over1.5", "Over 1.5", 86.5),
    ("over2.5", "Over 2.5", 64.2),
    ("over3.5", "Over 3.5", 52.5),
    ("btts", "BTTS", 63.0),
    ("team_o0.5", "Team O0.5", 89.5),
    ("team_o1.5", "Team O1.5", 63.6),
    ("under2.5", "Under 2.5", 53.7),
    ("under3.5", "Under 3.5", 77.8),
]

TOTAL_OVER_15_MIN = 3.5
TOTAL_OVER_25_MIN = 3.5
TOTAL_OVER_35_MIN = 4.0
TOTAL_UNDER_MAX = 2.0
TEAM_PROP_MIN = 2.0
BTTS_MIN_TEAM_PROJECTED = 1.5
