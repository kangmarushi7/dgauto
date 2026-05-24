"""DataGaffer scenario definitions — one bet_type per scenario row in the screenshot."""

from __future__ import annotations

from typing import Any

# bet_type, category, card label, historical hit %, resolve kind
SCENARIO_DEFS: list[dict[str, Any]] = [
    # Win probability
    {
        "bet_type": "ml_win60",
        "category": "Win Probability 60%+",
        "label": "Win Outright",
        "hist_hit_pct": 66.8,
        "resolve": "moneyline",
    },
    {
        "bet_type": "dc_win60",
        "category": "Win Probability 60%+",
        "label": "Win or Draw",
        "hist_hit_pct": 85.7,
        "resolve": "win_or_draw",
    },
    {
        "bet_type": "ml_win70",
        "category": "Win Probability 70%+",
        "label": "Win Outright",
        "hist_hit_pct": 71.7,
        "resolve": "moneyline",
    },
    {
        "bet_type": "dc_win70",
        "category": "Win Probability 70%+",
        "label": "Win or Draw",
        "hist_hit_pct": 88.6,
        "resolve": "win_or_draw",
    },
    # Total goals 3.5+
    {
        "bet_type": "o15_t35",
        "category": "Projected Total Goals 3.5+",
        "label": "Over 1.5 Goals",
        "hist_hit_pct": 86.5,
        "resolve": "over1.5",
    },
    {
        "bet_type": "o25_t35",
        "category": "Projected Total Goals 3.5+",
        "label": "Over 2.5 Goals",
        "hist_hit_pct": 64.2,
        "resolve": "over2.5",
    },
    # Total goals 4.0+
    {
        "bet_type": "o15_t40",
        "category": "Projected Total Goals 4.0+",
        "label": "Over 1.5 Goals",
        "hist_hit_pct": 90.0,
        "resolve": "over1.5",
    },
    {
        "bet_type": "o25_t40",
        "category": "Projected Total Goals 4.0+",
        "label": "Over 2.5 Goals",
        "hist_hit_pct": 74.0,
        "resolve": "over2.5",
    },
    {
        "bet_type": "o35_t40",
        "category": "Projected Total Goals 4.0+",
        "label": "Over 3.5 Goals",
        "hist_hit_pct": 52.5,
        "resolve": "over3.5",
    },
    # Team goals 2.0+
    {
        "bet_type": "to05_t20",
        "category": "Projected Team Goals 2.0+",
        "label": "Team Over 0.5 Goals",
        "hist_hit_pct": 89.5,
        "resolve": "team_o0.5",
    },
    {
        "bet_type": "to15_t20",
        "category": "Projected Team Goals 2.0+",
        "label": "Team Over 1.5 Goals",
        "hist_hit_pct": 63.6,
        "resolve": "team_o1.5",
    },
    # Team goals 2.5+
    {
        "bet_type": "to05_t25",
        "category": "Projected Team Goals 2.5+",
        "label": "Team Over 0.5 Goals",
        "hist_hit_pct": 93.2,
        "resolve": "team_o0.5",
    },
    {
        "bet_type": "to15_t25",
        "category": "Projected Team Goals 2.5+",
        "label": "Team Over 1.5 Goals",
        "hist_hit_pct": 70.9,
        "resolve": "team_o1.5",
    },
    # BTTS
    {
        "bet_type": "btts_both15",
        "category": "Both Teams Projected 1.5+",
        "label": "Both Teams to Score",
        "hist_hit_pct": 63.0,
        "resolve": "btts",
    },
    # Total goals 2.0 or lower
    {
        "bet_type": "u25_t20",
        "category": "Projected Total Goals 2.0 or Lower",
        "label": "Under 2.5 Goals",
        "hist_hit_pct": 53.7,
        "resolve": "under2.5",
    },
    {
        "bet_type": "u35_t20",
        "category": "Projected Total Goals 2.0 or Lower",
        "label": "Under 3.5 Goals",
        "hist_hit_pct": 77.8,
        "resolve": "under3.5",
    },
]

SCENARIO_BY_BET_TYPE: dict[str, dict[str, Any]] = {s["bet_type"]: s for s in SCENARIO_DEFS}

# Legacy bet_type -> display (pre-split rows still in DB)
LEGACY_BET_TYPE_MAP: dict[str, dict[str, str]] = {
    "moneyline": {"category": "Legacy", "label": "Moneyline (unsplit)", "resolve": "moneyline"},
    "over1.5": {"category": "Legacy", "label": "Over 1.5 (unsplit)", "resolve": "over1.5"},
    "over2.5": {"category": "Legacy", "label": "Over 2.5 (unsplit)", "resolve": "over2.5"},
    "over3.5": {"category": "Legacy", "label": "Over 3.5 (unsplit)", "resolve": "over3.5"},
    "btts": {"category": "Legacy", "label": "BTTS (unsplit)", "resolve": "btts"},
    "team_o0.5": {"category": "Legacy", "label": "Team O0.5 (unsplit)", "resolve": "team_o0.5"},
    "team_o1.5": {"category": "Legacy", "label": "Team O1.5 (unsplit)", "resolve": "team_o1.5"},
    "under2.5": {"category": "Legacy", "label": "Under 2.5 (unsplit)", "resolve": "under2.5"},
    "under3.5": {"category": "Legacy", "label": "Under 3.5 (unsplit)", "resolve": "under3.5"},
    "draw": {"category": "+EV", "label": "Draw", "resolve": "draw"},
    "dc_1x": {"category": "+EV", "label": "Double Chance 1X", "resolve": "dc_1x"},
    "dc_x2": {"category": "+EV", "label": "Double Chance X2", "resolve": "dc_x2"},
    "not_win": {"category": "NO Strat", "label": "Team not to win", "resolve": "not_win"},
}

WIN_MIN_60 = 60.0
WIN_MIN_70 = 70.0
TOTAL_OVER_35_MIN = 3.5
TOTAL_OVER_40_MIN = 4.0
TOTAL_UNDER_20_MAX = 2.0
TEAM_GOALS_20_MIN = 2.0
TEAM_GOALS_25_MIN = 2.5
BTTS_MIN_TEAM_PROJECTED = 1.5

CATEGORY_ORDER: list[str] = [
    "Win Probability 60%+",
    "Win Probability 70%+",
    "Projected Total Goals 3.5+",
    "Projected Total Goals 4.0+",
    "Projected Team Goals 2.0+",
    "Projected Team Goals 2.5+",
    "Both Teams Projected 1.5+",
    "Projected Total Goals 2.0 or Lower",
    "Legacy",
]


def is_legacy_entry(entry: dict[str, Any]) -> bool:
    bt = str(entry.get("bet_type") or "")
    return bt in LEGACY_BET_TYPE_MAP


def scenario_meta_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    bt = str(entry.get("bet_type") or "")
    if bt in SCENARIO_BY_BET_TYPE:
        s = SCENARIO_BY_BET_TYPE[bt]
        return {
            "bet_type": bt,
            "category": s["category"],
            "label": s["label"],
            "hist_hit_pct": s["hist_hit_pct"],
            "resolve": s["resolve"],
        }
    legacy = LEGACY_BET_TYPE_MAP.get(bt, {})
    return {
        "bet_type": bt,
        "category": legacy.get("category", "Other"),
        "label": legacy.get("label", bt),
        "hist_hit_pct": 0.0,
        "resolve": legacy.get("resolve", bt),
    }


def resolve_kind_for_entry(entry: dict[str, Any]) -> str:
    return str(scenario_meta_for_entry(entry).get("resolve") or entry.get("bet_type") or "")
