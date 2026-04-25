from __future__ import annotations

from typing import Any


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}%"


def _fmt_num(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def _moneyline_items(matches: list[dict[str, Any]], min_win_pct: float) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for m in matches:
        home_win = m.get("win_pct") or 0.0
        away_win = m.get("away_win_pct") or 0.0
        if home_win >= min_win_pct:
            items.append(
                {
                    "fixture": m.get("fixture", ""),
                    "selection": m.get("home_team", ""),
                    "metric": _fmt_pct(home_win),
                    "outcome": "Win Outright",
                }
            )
        if away_win >= min_win_pct:
            items.append(
                {
                    "fixture": m.get("fixture", ""),
                    "selection": m.get("away_team", ""),
                    "metric": _fmt_pct(away_win),
                    "outcome": "Win Outright",
                }
            )
    return items


def _win_or_draw_items(matches: list[dict[str, Any]], min_win_pct: float) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for m in matches:
        home_win = m.get("win_pct") or 0.0
        away_win = m.get("away_win_pct") or 0.0
        if home_win >= min_win_pct:
            items.append(
                {
                    "fixture": m.get("fixture", ""),
                    "selection": m.get("home_team", ""),
                    "metric": _fmt_pct(home_win),
                    "outcome": "Home or Draw (1X)",
                }
            )
        if away_win >= min_win_pct:
            items.append(
                {
                    "fixture": m.get("fixture", ""),
                    "selection": m.get("away_team", ""),
                    "metric": _fmt_pct(away_win),
                    "outcome": "Away or Draw (X2)",
                }
            )
    return items


def _total_goals_items(
    matches: list[dict[str, Any]], threshold: float, cmp: str, outcome: str
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for m in matches:
        total = m.get("projected_total_goals")
        if total is None:
            continue
        ok = total >= threshold if cmp == ">=" else total <= threshold
        if ok:
            items.append(
                {
                    "fixture": m.get("fixture", ""),
                    "selection": "Match Total",
                    "metric": _fmt_num(total),
                    "outcome": outcome,
                }
            )
    return items


def _team_goals_items(matches: list[dict[str, Any]], min_team_goals: float, outcome: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for m in matches:
        home_g = m.get("home_projected_goals")
        away_g = m.get("away_projected_goals")
        if home_g is not None and home_g >= min_team_goals:
            items.append(
                {
                    "fixture": m.get("fixture", ""),
                    "selection": m.get("home_team", ""),
                    "metric": _fmt_num(home_g),
                    "outcome": outcome,
                }
            )
        if away_g is not None and away_g >= min_team_goals:
            items.append(
                {
                    "fixture": m.get("fixture", ""),
                    "selection": m.get("away_team", ""),
                    "metric": _fmt_num(away_g),
                    "outcome": outcome,
                }
            )
    return items


def _btts_projected_items(matches: list[dict[str, Any]], min_team_goals: float) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for m in matches:
        home_g = m.get("home_projected_goals")
        away_g = m.get("away_projected_goals")
        if home_g is None or away_g is None:
            continue
        if home_g >= min_team_goals and away_g >= min_team_goals:
            items.append(
                {
                    "fixture": m.get("fixture", ""),
                    "selection": "Both Teams",
                    "metric": f"H {_fmt_num(home_g)} / A {_fmt_num(away_g)}",
                    "outcome": "Both Teams to Score",
                }
            )
    return items


def build_todays_bets_scenarios(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenarios = [
        {
            "name": "Win Probability 60% or Higher",
            "outcome": "Win Outright",
            "hit_rate": "66.9%",
            "items": _moneyline_items(matches, 60.0),
        },
        {
            "name": "Win Probability 60% or Higher",
            "outcome": "Win or Draw",
            "hit_rate": "85.7%",
            "items": _win_or_draw_items(matches, 60.0),
        },
        {
            "name": "Win Probability 70% or Higher",
            "outcome": "Win Outright",
            "hit_rate": "71.9%",
            "items": _moneyline_items(matches, 70.0),
        },
        {
            "name": "Win Probability 70% or Higher",
            "outcome": "Win or Draw",
            "hit_rate": "88.4%",
            "items": _win_or_draw_items(matches, 70.0),
        },
        {
            "name": "Projected Total Goals 3.5 or Higher",
            "outcome": "Over 1.5 Goals",
            "hit_rate": "86.1%",
            "items": _total_goals_items(matches, 3.5, ">=", "Over 1.5 Goals"),
        },
        {
            "name": "Projected Total Goals 3.5 or Higher",
            "outcome": "Over 2.5 Goals",
            "hit_rate": "64.9%",
            "items": _total_goals_items(matches, 3.5, ">=", "Over 2.5 Goals"),
        },
        {
            "name": "Projected Total Goals 4.0 or Higher",
            "outcome": "Over 1.5 Goals",
            "hit_rate": "91.1%",
            "items": _total_goals_items(matches, 4.0, ">=", "Over 1.5 Goals"),
        },
        {
            "name": "Projected Total Goals 4.0 or Higher",
            "outcome": "Over 2.5 Goals",
            "hit_rate": "75.4%",
            "items": _total_goals_items(matches, 4.0, ">=", "Over 2.5 Goals"),
        },
        {
            "name": "Projected Total Goals 4.0 or Higher",
            "outcome": "Over 3.5 Goals",
            "hit_rate": "53.2%",
            "items": _total_goals_items(matches, 4.0, ">=", "Over 3.5 Goals"),
        },
        {
            "name": "Projected Team Goals 2.0 or Higher",
            "outcome": "Team Over 0.5 Goals",
            "hit_rate": "89.3%",
            "items": _team_goals_items(matches, 2.0, "Team Over 0.5 Goals"),
        },
        {
            "name": "Projected Team Goals 2.0 or Higher",
            "outcome": "Team Over 1.5 Goals",
            "hit_rate": "63.3%",
            "items": _team_goals_items(matches, 2.0, "Team Over 1.5 Goals"),
        },
        {
            "name": "Projected Team Goals 2.5 or Higher",
            "outcome": "Team Over 0.5 Goals",
            "hit_rate": "92.9%",
            "items": _team_goals_items(matches, 2.5, "Team Over 0.5 Goals"),
        },
        {
            "name": "Projected Team Goals 2.5 or Higher",
            "outcome": "Team Over 1.5 Goals",
            "hit_rate": "70.4%",
            "items": _team_goals_items(matches, 2.5, "Team Over 1.5 Goals"),
        },
        {
            "name": "Both Teams Projected 1.5 Goals or Higher",
            "outcome": "Both Teams to Score",
            "hit_rate": "62.2%",
            "items": _btts_projected_items(matches, 1.5),
        },
        {
            "name": "Projected Total Goals 2.0 or Lower",
            "outcome": "Under 2.5 Goals",
            "hit_rate": "54.5%",
            "items": _total_goals_items(matches, 2.0, "<=", "Under 2.5 Goals"),
        },
        {
            "name": "Projected Total Goals 2.0 or Lower",
            "outcome": "Under 3.5 Goals",
            "hit_rate": "79.8%",
            "items": _total_goals_items(matches, 2.0, "<=", "Under 3.5 Goals"),
        },
    ]
    return scenarios
