from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz, process


FIXTURE_SPLIT_RE = re.compile(r"\s+(?:vs|v|-)\s+", re.IGNORECASE)


def normalize_fixture(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", " ", text).lower()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    parts = FIXTURE_SPLIT_RE.split(text)
    if len(parts) >= 2:
        parts = sorted(p.strip() for p in parts[:2])
        return " vs ".join(parts)
    return text


def to_pct(value: Any) -> float | None:
    if value is None:
        return None
    txt = str(value).strip().replace("%", "")
    try:
        return float(txt)
    except ValueError:
        return None


def to_odds(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return None
    return odds if odds > 1.0 else None


def _pick_odds(*values: Any) -> float | None:
    for value in values:
        odds = to_odds(value)
        if odds is not None:
            return odds
    return None


def score_match(win_row: dict[str, Any], goals_row: dict[str, Any] | None) -> dict[str, Any]:
    home = win_row.get("home") or ""
    away = win_row.get("away") or ""
    home_logo = win_row.get("home_logo") or (goal_row.get("home_logo") if goal_row else "") or ""
    away_logo = win_row.get("away_logo") or (goal_row.get("away_logo") if goal_row else "") or ""
    fixture = f"{home} vs {away}".strip(" vs ")
    fixture_id = win_row.get("fixture_id") or (goals_row.get("fixture_id") if goals_row else None)
    home_team_id = win_row.get("home_team_id") or (goals_row.get("home_team_id") if goals_row else None)
    away_team_id = win_row.get("away_team_id") or (goals_row.get("away_team_id") if goals_row else None)

    win_pct = to_pct(win_row.get("home_win_pct"))
    draw_pct = to_pct(win_row.get("draw_pct"))
    away_win_pct = to_pct(win_row.get("away_win_pct"))
    over_1_5_pct = to_pct(
        (goals_row or {}).get("over_1_5_pct") or win_row.get("over_1_5_pct")
    )
    under_1_5_pct = to_pct(
        (goals_row or {}).get("under_1_5_pct") or win_row.get("under_1_5_pct")
    )
    over_25_pct = to_pct((goals_row or {}).get("over_25_pct") or win_row.get("over_25_pct"))
    over_3_5_pct = to_pct((goals_row or {}).get("over_3_5_pct") or win_row.get("over_3_5_pct"))
    under_2_5_pct = to_pct((goals_row or {}).get("under_2_5_pct") or win_row.get("under_2_5_pct"))
    under_3_5_pct = to_pct((goals_row or {}).get("under_3_5_pct") or win_row.get("under_3_5_pct"))
    btts_pct = to_pct((goals_row or {}).get("btts_pct") or win_row.get("btts_pct"))
    home_projected_goals = to_pct(goals_row.get("home_projected_goals")) if goals_row else None
    away_projected_goals = to_pct(goals_row.get("away_projected_goals")) if goals_row else None
    projected_total_goals = to_pct(goals_row.get("projected_total_goals")) if goals_row else None
    fixture_date = win_row.get("fixture_date") or (goals_row.get("fixture_date") if goals_row else None)
    league_name = win_row.get("league_name") or (goals_row.get("league_name") if goals_row else "")
    gr = goals_row or {}
    home_ml_odds = _pick_odds(win_row.get("home_ml_odds"), gr.get("home_ml_odds"))
    away_ml_odds = _pick_odds(win_row.get("away_ml_odds"), gr.get("away_ml_odds"))
    over_1_5_odds = _pick_odds(gr.get("over_1_5_odds"), win_row.get("over_1_5_odds"))
    over_2_5_odds = _pick_odds(gr.get("over_2_5_odds"), win_row.get("over_2_5_odds"))
    over_3_5_odds = _pick_odds(gr.get("over_3_5_odds"), win_row.get("over_3_5_odds"))
    under_2_5_odds = _pick_odds(gr.get("under_2_5_odds"), win_row.get("under_2_5_odds"))
    under_3_5_odds = _pick_odds(gr.get("under_3_5_odds"), win_row.get("under_3_5_odds"))
    btts_yes_odds = _pick_odds(gr.get("btts_yes_odds"), win_row.get("btts_yes_odds"))
    home_o0_5_odds = _pick_odds(gr.get("home_o0_5_odds"), win_row.get("home_o0_5_odds"))
    away_o0_5_odds = _pick_odds(gr.get("away_o0_5_odds"), win_row.get("away_o0_5_odds"))
    home_o1_5_odds = _pick_odds(gr.get("home_o1_5_odds"), win_row.get("home_o1_5_odds"))
    away_o1_5_odds = _pick_odds(gr.get("away_o1_5_odds"), win_row.get("away_o1_5_odds"))
    dc_home_draw_odds = _pick_odds(gr.get("dc_home_draw_odds"), win_row.get("dc_home_draw_odds"))
    dc_draw_away_odds = _pick_odds(gr.get("dc_draw_away_odds"), win_row.get("dc_draw_away_odds"))

    score_inputs = [x for x in [win_pct, over_25_pct, btts_pct] if x is not None]
    score = round(sum(score_inputs) / len(score_inputs), 2) if score_inputs else 0.0

    signal = "watch"
    if (win_pct or 0) >= 60 and (over_25_pct or 0) >= 65:
        signal = "high"
    elif (win_pct or 0) >= 55 and (over_25_pct or 0) >= 55:
        signal = "medium"

    return {
        "fixture": fixture,
        "fixture_id": fixture_id,
        "home_team": home,
        "away_team": away,
        "home_logo": home_logo,
        "away_logo": away_logo,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "fixture_date": fixture_date,
        "league_name": league_name,
        "win_pct": win_pct,
        "draw_pct": draw_pct,
        "away_win_pct": away_win_pct,
        "home_ml_odds": home_ml_odds,
        "away_ml_odds": away_ml_odds,
        "over_1_5_odds": over_1_5_odds,
        "over_2_5_odds": over_2_5_odds,
        "over_3_5_odds": over_3_5_odds,
        "under_2_5_odds": under_2_5_odds,
        "under_3_5_odds": under_3_5_odds,
        "btts_yes_odds": btts_yes_odds,
        "home_o0_5_odds": home_o0_5_odds,
        "away_o0_5_odds": away_o0_5_odds,
        "home_o1_5_odds": home_o1_5_odds,
        "away_o1_5_odds": away_o1_5_odds,
        "dc_home_draw_odds": dc_home_draw_odds,
        "dc_draw_away_odds": dc_draw_away_odds,
        "over_1_5_pct": over_1_5_pct,
        "under_1_5_pct": under_1_5_pct,
        "over_25_pct": over_25_pct,
        "over_3_5_pct": over_3_5_pct,
        "under_2_5_pct": under_2_5_pct,
        "under_3_5_pct": under_3_5_pct,
        "btts_pct": btts_pct,
        "home_projected_goals": home_projected_goals,
        "away_projected_goals": away_projected_goals,
        "projected_total_goals": projected_total_goals,
        "score": score,
        "signal": signal,
    }


def _find_goal_row(
    win_row: dict[str, Any],
    goals_by_id: dict[int, dict[str, Any]],
    goals_keys: dict[str, dict[str, Any]],
    goal_key_list: list[str],
) -> dict[str, Any] | None:
    fixture_id = win_row.get("fixture_id")
    if fixture_id is not None:
        try:
            matched = goals_by_id.get(int(fixture_id))
        except (TypeError, ValueError):
            matched = None
        if matched:
            return matched

    key = normalize_fixture(f"{win_row.get('home', '')} vs {win_row.get('away', '')}")
    best = process.extractOne(key, goal_key_list, scorer=fuzz.token_set_ratio, score_cutoff=72)
    return goals_keys.get(best[0]) if best else None


def merge_outlooks(win_rows: list[dict[str, Any]], goals_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    goals_keys = {normalize_fixture(f"{r.get('home', '')} vs {r.get('away', '')}"): r for r in goals_rows}
    goals_by_id: dict[int, dict[str, Any]] = {}
    for row in goals_rows:
        fid = row.get("fixture_id")
        if fid is not None:
            try:
                goals_by_id[int(fid)] = row
            except (TypeError, ValueError):
                pass
    goal_key_list = list(goals_keys.keys())
    merged = []

    for row in win_rows:
        goal_row = _find_goal_row(row, goals_by_id, goals_keys, goal_key_list)
        merged.append(score_match(row, goal_row))

    merged.sort(key=lambda x: (x["signal"] == "high", x["signal"] == "medium", x["score"]), reverse=True)
    return merged
