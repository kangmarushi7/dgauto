"""Global DG scenario-validation calibration (log-only for Arahus).

Source: ``daily_accuracy.json`` → ``scenario_validation`` (GLOBAL aggregate —
not per-league). Used as debug metadata on picks; does not change confidence,
stake, or EV gates.

ASSUMPTION map (scenarioKey / subKey / simPct) — easy to correct later:
  simWinPct >= 70          -> win_70 / win   / that side's win %
  simWinPct >= 60          -> win_60 / win   / that side's win %
  simTotalGoals >= 4.0     -> tot_40 / o25   / sim O2.5 %
  simTotalGoals >= 3.5     -> tot_35 / o25   / sim O2.5 %
  simTeamGoals  >= 2.5     -> team_25 / o15  / that side's O1.5 %
  simTeamGoals  >= 2.0     -> team_20 / o15  / that side's O1.5 %
  both sides xG >= 1.5     -> btts_15 / btts / sim BTTS %
  simTotalGoals <= 2.0     -> under_20 / u25 / sim U2.5 %

Highest-threshold only within each family (win_70 beats win_60, etc.).
"""
from __future__ import annotations

import math
from typing import Any

MIN_SAMPLE = 50  # hard floor — buckets below this are "uncalibrated"

# Which Arahus bet_types a scenario row is most relevant to (review / future live use).
SCENARIO_RELEVANT_BETS: dict[str, set[str]] = {
    "win_60": {"arahus_ml", "arahus_dc_1x", "arahus_dc_x2"},
    "win_70": {"arahus_ml", "arahus_dc_1x", "arahus_dc_x2"},
    "tot_35": {"arahus_o25", "arahus_o15", "arahus_o35"},
    "tot_40": {"arahus_o25", "arahus_o15", "arahus_o35"},
    "team_20": {"arahus_team_o15", "arahus_team_o05"},
    "team_25": {"arahus_team_o15", "arahus_team_o05"},
    "btts_15": {"arahus_btts"},
    "under_20": {"arahus_u25"},
}


def _num(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _poisson_cdf_ge(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k <= 0 else 0.0
    # P(X >= k) = 1 - P(X <= k-1)
    cdf = 0.0
    for i in range(0, k):
        cdf += math.exp(-lam) * (lam**i) / math.factorial(i)
    return max(0.0, min(1.0, 1.0 - cdf))


def _team_o15_pct(sim_pct: float | None, team_xg: float | None) -> float | None:
    if sim_pct is not None:
        return sim_pct
    if team_xg is None:
        return None
    return round(_poisson_cdf_ge(2, team_xg) * 100, 1)


def pick_scenario_bucket(sim_outputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Map fixture sim outputs → scenario_validation key + subKey matches.

    Returns all families that apply (win AND totals AND BTTS can coexist).
    Within a family, only the highest qualifying threshold is kept.
    """
    home_win = _num(sim_outputs.get("sim_home_win_pct"))
    away_win = _num(sim_outputs.get("sim_away_win_pct"))
    total_xg = _num(sim_outputs.get("sim_total_goals"))
    home_xg = _num(sim_outputs.get("sim_home_goals"))
    away_xg = _num(sim_outputs.get("sim_away_goals"))
    o25 = _num(sim_outputs.get("sim_over_2_5_pct"))
    u25 = _num(sim_outputs.get("sim_under_2_5_pct"))
    btts = _num(sim_outputs.get("sim_btts_pct"))
    home_o15 = _team_o15_pct(_num(sim_outputs.get("sim_home_o1_5_pct")), home_xg)
    away_o15 = _team_o15_pct(_num(sim_outputs.get("sim_away_o1_5_pct")), away_xg)

    matches: list[dict[str, Any]] = []

    # Win — highest of home/away win %; win_70 beats win_60.
    best_win = None
    best_side = None
    if home_win is not None or away_win is not None:
        if (home_win or 0) >= (away_win or 0):
            best_win, best_side = home_win, "home"
        else:
            best_win, best_side = away_win, "away"
    if best_win is not None:
        if best_win >= 70:
            matches.append(
                {
                    "scenarioKey": "win_70",
                    "subKey": "win",
                    "simPct": best_win,
                    "side": best_side,
                }
            )
        elif best_win >= 60:
            matches.append(
                {
                    "scenarioKey": "win_60",
                    "subKey": "win",
                    "simPct": best_win,
                    "side": best_side,
                }
            )

    # Totals overs — tot_40 beats tot_35; simPct is market O2.5%.
    if total_xg is not None and o25 is not None:
        if total_xg >= 4.0:
            matches.append(
                {"scenarioKey": "tot_40", "subKey": "o25", "simPct": o25, "side": None}
            )
        elif total_xg >= 3.5:
            matches.append(
                {"scenarioKey": "tot_35", "subKey": "o25", "simPct": o25, "side": None}
            )

    # Team goals — evaluate each side; highest threshold per side.
    for side, txg, o15 in (
        ("home", home_xg, home_o15),
        ("away", away_xg, away_o15),
    ):
        if txg is None or o15 is None:
            continue
        if txg >= 2.5:
            matches.append(
                {"scenarioKey": "team_25", "subKey": "o15", "simPct": o15, "side": side}
            )
        elif txg >= 2.0:
            matches.append(
                {"scenarioKey": "team_20", "subKey": "o15", "simPct": o15, "side": side}
            )

    # BTTS — DG wording: both teams projected 1.5+ goals.
    if (
        home_xg is not None
        and away_xg is not None
        and home_xg >= 1.5
        and away_xg >= 1.5
        and btts is not None
    ):
        matches.append(
            {"scenarioKey": "btts_15", "subKey": "btts", "simPct": btts, "side": None}
        )

    # Unders — projected total <= 2.0; simPct is U2.5%.
    if total_xg is not None and total_xg <= 2.0 and u25 is not None:
        matches.append(
            {"scenarioKey": "under_20", "subKey": "u25", "simPct": u25, "side": None}
        )

    return matches


def calibration_ratio(
    scenario_validation: dict[str, Any] | None,
    scenario_key: str,
    sub_key: str,
    sim_pct: float | None,
) -> dict[str, Any]:
    """Compute historicalHitPct / simPct for one bucket match."""
    bucket = None
    if isinstance(scenario_validation, dict):
        bucket = scenario_validation.get(scenario_key)
    games = int(bucket.get("games") or 0) if isinstance(bucket, dict) else 0

    if not isinstance(bucket, dict) or games < MIN_SAMPLE:
        return {
            "ratio": 1.0,
            "status": "uncalibrated",
            "historicalHitPct": None,
            "n": games,
        }

    if sim_pct is None or sim_pct <= 0:
        return {
            "ratio": 1.0,
            "status": "uncalibrated",
            "historicalHitPct": None,
            "n": games,
        }

    hits = bucket.get(sub_key)
    try:
        hits_f = float(hits)
    except (TypeError, ValueError):
        return {
            "ratio": 1.0,
            "status": "uncalibrated",
            "historicalHitPct": None,
            "n": games,
        }

    historical_hit_pct = (hits_f / games) * 100.0
    ratio = round(historical_hit_pct / float(sim_pct), 3)
    return {
        "ratio": ratio,
        "status": "calibrated",
        "historicalHitPct": round(historical_hit_pct, 1),
        "n": games,
    }


def calibrate_fixture(
    sim_outputs: dict[str, Any],
    scenario_validation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return calibration rows for every matched scenario on a fixture."""
    matches = pick_scenario_bucket(sim_outputs)
    out: list[dict[str, Any]] = []
    for m in matches:
        row = {
            "scenarioKey": m["scenarioKey"],
            "subKey": m["subKey"],
            "rawSimPct": m["simPct"],
            "side": m.get("side"),
            **calibration_ratio(
                scenario_validation, m["scenarioKey"], m["subKey"], m["simPct"]
            ),
        }
        row["relevantBets"] = sorted(SCENARIO_RELEVANT_BETS.get(m["scenarioKey"], set()))
        out.append(row)
    return out


def sim_outputs_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Build calibrate_fixture inputs from an Arahus fixture profile (raw sim)."""
    sim = profile.get("sim") if isinstance(profile.get("sim"), dict) else {}
    xg = profile.get("xg") if isinstance(profile.get("xg"), dict) else {}
    return {
        "sim_home_win_pct": sim.get("home_win_pct"),
        "sim_away_win_pct": sim.get("away_win_pct"),
        "sim_total_goals": xg.get("total"),
        "sim_home_goals": xg.get("home"),
        "sim_away_goals": xg.get("away"),
        "sim_over_2_5_pct": sim.get("over_2_5_pct"),
        "sim_under_2_5_pct": sim.get("under_2_5_pct"),
        "sim_btts_pct": sim.get("btts_pct"),
        "sim_home_o1_5_pct": sim.get("home_o1_5_pct"),
        "sim_away_o1_5_pct": sim.get("away_o1_5_pct"),
    }


def filter_calibration_for_bet(
    rows: list[dict[str, Any]], bet_type: str
) -> list[dict[str, Any]]:
    """Mark/filter rows relevant to a specific Arahus bet_type (log helper)."""
    tagged: list[dict[str, Any]] = []
    for row in rows:
        relevant = bet_type in (row.get("relevantBets") or [])
        # Team scenarios: also require side match when team_name context exists later.
        tagged.append({**row, "relevantToPick": relevant})
    return tagged
