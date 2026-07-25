"""Arahus Engine — stacked DataGaffer intel → fixture projections → bet picks.

Isolated from the main / LM / NO / +EV / CS / H2H bet logs (``log_type = "arahus"``).

Workflow (mirrors DataGaffer's research guide):
1. Ingest sims, ratings, pace/indexes, xG regression, highlights, form, book odds
2. Blend them into match-environment projections
3. Score candidate markets only when multiple signal families agree
4. Prefer markets with model-vs-book value when odds exist
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import os
import uuid
from typing import Any

from app.bet_log import compute_bet_stats
from app.db import insert_bets, list_bets, resolve_bet_entry
from app.dg_feeds import lookup_extra_for_fixture
from app.fixture_detail import find_raw_fixture
from app.fixture_math import edge as calc_edge
from app.fixture_math import expected_value_pct, implied_prob, num

LOG_TYPE = "arahus"

# Tunables (env overrides)
MIN_CONFIDENCE = float(os.getenv("ARAHUS_MIN_CONFIDENCE", "62"))
MIN_EDGE_WHEN_ODDS = float(os.getenv("ARAHUS_MIN_EDGE", "2.0"))
MAX_PICKS_PER_FIXTURE = int(os.getenv("ARAHUS_MAX_PICKS", "3"))
ALLOW_NO_ODDS = (os.getenv("ARAHUS_ALLOW_NO_ODDS", "true").strip().lower()
                 in {"1", "true", "yes"})

# Bet types → auto-resolve kind (also registered in bet_scenarios.ARAHUS_BET_TYPE_MAP)
BET_LABELS: dict[str, str] = {
    "arahus_o15": "Over 1.5",
    "arahus_o25": "Over 2.5",
    "arahus_o35": "Over 3.5",
    "arahus_u25": "Under 2.5",
    "arahus_btts": "BTTS Yes",
    "arahus_ml": "Moneyline",
    "arahus_team_o05": "Team O0.5",
    "arahus_team_o15": "Team O1.5",
    "arahus_dc_1x": "Double Chance 1X",
    "arahus_dc_x2": "Double Chance X2",
    "arahus_corners_o85": "Corners O8.5",
    "arahus_corners_o95": "Corners O9.5",
    "arahus_corners_o105": "Corners O10.5",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _avg(*values: float | None) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _rating_gap(home: dict[str, Any], away: dict[str, Any], key: str = "DGRtg") -> float | None:
    h, a = num(home.get(key)), num(away.get(key))
    if h is None or a is None:
        return None
    return round(h - a, 2)


def _luck_bias(xgr: dict[str, Any] | None) -> float:
    """Positive = results inflated vs chance (favor fade); negative = due better results."""
    if not isinstance(xgr, dict):
        return 0.0
    for key in ("luck", "luck_factor", "xg_diff", "goals_minus_xg"):
        v = num(xgr.get(key))
        if v is not None:
            # Normalize common scales: if |v| <= 1 treat as factor, else goals diff.
            return _clamp(v if abs(v) <= 2 else v / 3.0, -1.0, 1.0)
    gf = num(xgr.get("goals_for") or xgr.get("gf"))
    xgf = num(xgr.get("xg_for") or xgr.get("xG_for") or xgr.get("xg"))
    if gf is not None and xgf is not None:
        return _clamp((gf - xgf) / 2.0, -1.0, 1.0)
    return 0.0


def _poisson_cdf_ge(k: int, lam: float) -> float:
    """P(X >= k) for Poisson(lam)."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    # Sum P(X=0..k-1), return 1 - that.
    cdf = 0.0
    term = math.exp(-lam)
    cdf += term
    for i in range(1, k):
        term *= lam / i
        cdf += term
    return _clamp(1.0 - cdf, 0.0, 1.0)


def build_fixture_profile(
    raw: dict[str, Any],
    match: dict[str, Any] | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Flatten all available DG intel into one fixture profile."""
    match = match or {}
    sim = raw.get("sim_stats") or {}
    perc = sim.get("percents") if isinstance(sim.get("percents"), dict) else {}
    xg = sim.get("xg") if isinstance(sim.get("xg"), dict) else {}
    fh = sim.get("first_half") if isinstance(sim.get("first_half"), dict) else {}
    corners = sim.get("corners") if isinstance(sim.get("corners"), dict) else {}
    shots = sim.get("shots") if isinstance(sim.get("shots"), dict) else {}
    sot = sim.get("shots_on_target") if isinstance(sim.get("shots_on_target"), dict) else {}

    home_name = match.get("home_team") or (raw.get("home") or {}).get("name") or "Home"
    away_name = match.get("away_team") or (raw.get("away") or {}).get("name") or "Away"
    home_r = extra.get("home_rating") if isinstance(extra.get("home_rating"), dict) else {}
    away_r = extra.get("away_rating") if isinstance(extra.get("away_rating"), dict) else {}
    pace = extra.get("matchup_pace") if isinstance(extra.get("matchup_pace"), dict) else {}
    pace_ctx = extra.get("pace_context") if isinstance(extra.get("pace_context"), dict) else {}
    home_xgr = extra.get("home_xg_regression") if isinstance(extra.get("home_xg_regression"), dict) else {}
    away_xgr = extra.get("away_xg_regression") if isinstance(extra.get("away_xg_regression"), dict) else {}

    hx = num(xg.get("home")) or num(match.get("home_projected_goals"))
    ax = num(xg.get("away")) or num(match.get("away_projected_goals"))
    tx = num(xg.get("total"))
    if tx is None and hx is not None and ax is not None:
        tx = hx + ax

    return {
        "fixture_id": match.get("fixture_id") or raw.get("fixture_id"),
        "fixture": match.get("fixture") or f"{home_name} vs {away_name}",
        "fixture_date": match.get("fixture_date") or raw.get("date"),
        "league_name": match.get("league_name") or (raw.get("league") or {}).get("name") or "",
        "home_team": home_name,
        "away_team": away_name,
        "sim": {
            "home_win_pct": num(perc.get("home_win_pct")) or num(match.get("win_pct")),
            "draw_pct": num(perc.get("draw_pct")) or num(match.get("draw_pct")),
            "away_win_pct": num(perc.get("away_win_pct")) or num(match.get("away_win_pct")),
            "over_1_5_pct": num(perc.get("over_1_5_pct")) or num(match.get("over_1_5_pct")),
            "over_2_5_pct": num(perc.get("over_2_5_pct")) or num(match.get("over_25_pct")),
            "over_3_5_pct": num(perc.get("over_3_5_pct")) or num(match.get("over_3_5_pct")),
            "under_2_5_pct": num(perc.get("under_2_5_pct")) or num(match.get("under_2_5_pct")),
            "btts_pct": num(perc.get("btts_pct")) or num(match.get("btts_pct")),
            "home_o1_5_pct": num(perc.get("home_o1_5_pct")),
            "away_o1_5_pct": num(perc.get("away_o1_5_pct")),
        },
        "xg": {"home": hx, "away": ax, "total": tx},
        "volume": {
            "corners": num(corners.get("total")),
            "shots": num(shots.get("total")),
            "sot": num(sot.get("total")),
            "fh_goals": num((fh.get("xg") or {}).get("total")) if isinstance(fh.get("xg"), dict)
            else num(fh.get("total")),
        },
        "ratings": {
            "home": home_r,
            "away": away_r,
            "dgrtg_gap": _rating_gap(home_r, away_r, "DGRtg"),
            "ortg_gap": _rating_gap(home_r, away_r, "ORtg"),
            "drtg_gap": _rating_gap(home_r, away_r, "DRtg"),
        },
        "indexes": {
            "pace": num(pace.get("score")) or num(pace.get("pace_index"))
            or _avg(num(home_r.get("pace_index")), num(away_r.get("pace_index"))),
            "nec": num(pace.get("nec_index"))
            or _avg(num(home_r.get("nec_index")), num(away_r.get("nec_index"))),
            "agix": num(pace.get("agix_index"))
            or _avg(num(home_r.get("agix_index")), num(away_r.get("agix_index"))),
            "control": _avg(num(home_r.get("control_index")), num(away_r.get("control_index"))),
            "ppda": _avg(num(home_r.get("ppda")), num(away_r.get("ppda"))),
            "consistency": _avg(
                num(home_r.get("consistency_index")), num(away_r.get("consistency_index"))
            ),
            "pace_bucket_o25": num(pace_ctx.get("over_2_5_pct")),
            "pace_bucket_btts": num(pace_ctx.get("btts_pct")),
            "pace_bucket": pace_ctx.get("bucket"),
        },
        "regression": {
            "home_luck": _luck_bias(home_xgr),
            "away_luck": _luck_bias(away_xgr),
        },
        "highlights": list(extra.get("highlight_roles") or []),
        "odds": {
            "home_ml": num(match.get("home_ml_odds")),
            "away_ml": num(match.get("away_ml_odds")),
            "over_1_5": num(match.get("over_1_5_odds")),
            "over_2_5": num(match.get("over_2_5_odds")),
            "over_3_5": num(match.get("over_3_5_odds")),
            "under_2_5": num(match.get("under_2_5_odds")),
            "btts_yes": num(match.get("btts_yes_odds")),
            "home_o0_5": num(match.get("home_o0_5_odds")),
            "away_o0_5": num(match.get("away_o0_5_odds")),
            "home_o1_5": num(match.get("home_o1_5_odds")),
            "away_o1_5": num(match.get("away_o1_5_odds")),
            "dc_1x": num(match.get("dc_home_draw_odds")),
            "dc_x2": num(match.get("dc_draw_away_odds")),
        },
    }


def project_match(profile: dict[str, Any]) -> dict[str, Any]:
    """Blend sims + ratings/indexes/regression into Arahus projections."""
    xg = profile["xg"]
    sim = profile["sim"]
    idx = profile["indexes"]
    reg = profile["regression"]
    vol = profile["volume"]
    ratings = profile["ratings"]

    hx, ax, tx = xg.get("home"), xg.get("away"), xg.get("total")
    pace = idx.get("pace")
    nec = idx.get("nec")
    agix = idx.get("agix")
    luck = ((reg.get("home_luck") or 0.0) + (reg.get("away_luck") or 0.0)) / 2.0

    # --- Totals ---
    total_base = tx if tx is not None else None
    total_adj = 0.0
    if pace is not None:
        # Pace ~50–70 typical; treat 60 as neutral-ish
        total_adj += _clamp((pace - 58) / 40.0, -0.25, 0.30)
    if nec is not None:
        total_adj += _clamp((nec - 55) / 50.0, -0.15, 0.20)
    # Inflated finishing → slight unders lean
    total_adj -= luck * 0.15
    projected_total = round(total_base + total_adj, 2) if total_base is not None else None

    # Re-weight home/away xG by rating gap while keeping total
    home_xg = hx
    away_xg = ax
    gap = ratings.get("dgrtg_gap")
    if home_xg is not None and away_xg is not None and gap is not None and projected_total:
        share = home_xg / (home_xg + away_xg) if (home_xg + away_xg) else 0.5
        share = _clamp(share + gap / 200.0, 0.25, 0.75)
        home_xg = round(projected_total * share, 2)
        away_xg = round(projected_total - home_xg, 2)
    elif projected_total is not None and home_xg is not None and away_xg is not None:
        scale = projected_total / (home_xg + away_xg) if (home_xg + away_xg) else 1.0
        home_xg = round(home_xg * scale, 2)
        away_xg = round(away_xg * scale, 2)

    # Poisson-ish market probs from projected xG (fallback to sim %)
    def _line_pct(line: float, lam: float | None, sim_key: str) -> float | None:
        if lam is not None and lam > 0:
            # Over L → P(X >= floor(L)+1)
            need = int(math.floor(line)) + 1
            return round(_poisson_cdf_ge(need, lam) * 100, 1)
        return sim.get(sim_key)

    o15 = _line_pct(1.5, projected_total, "over_1_5_pct")
    o25 = _line_pct(2.5, projected_total, "over_2_5_pct")
    o35 = _line_pct(3.5, projected_total, "over_3_5_pct")
    u25 = round(100 - o25, 1) if o25 is not None else sim.get("under_2_5_pct")

    # BTTS: sim base + both-side xG + pace
    btts = sim.get("btts_pct")
    if home_xg is not None and away_xg is not None:
        p_home = 1.0 - math.exp(-home_xg)
        p_away = 1.0 - math.exp(-away_xg)
        btts_model = p_home * p_away * 100
        if btts is None:
            btts = round(btts_model, 1)
        else:
            btts = round(0.55 * btts + 0.45 * btts_model, 1)
        if pace is not None and pace >= 62:
            btts = round(min(95.0, btts + 2.5), 1)
        if luck > 0.4:
            btts = round(max(5.0, btts - 2.0), 1)

    # Corners / shots: volume sim + pace/ppda
    corners = vol.get("corners")
    if corners is not None and pace is not None:
        corners = round(corners + _clamp((pace - 58) / 25.0, -0.8, 1.2), 1)
    shots = vol.get("shots")
    if shots is not None and nec is not None:
        shots = round(shots + _clamp((nec - 55) / 30.0, -1.0, 1.5), 1)

    # Win probs: sim + rating nudge
    home_win = sim.get("home_win_pct")
    away_win = sim.get("away_win_pct")
    draw = sim.get("draw_pct")
    if gap is not None and home_win is not None and away_win is not None:
        nudge = _clamp(gap * 0.35, -6.0, 6.0)
        home_win = round(_clamp(home_win + nudge, 5.0, 90.0), 1)
        away_win = round(_clamp(away_win - nudge * 0.7, 5.0, 90.0), 1)
        if draw is not None:
            # renormalize softly
            s = home_win + away_win + draw
            if s > 0:
                home_win = round(home_win * 100 / s, 1)
                away_win = round(away_win * 100 / s, 1)
                draw = round(100 - home_win - away_win, 1)

    fh_share = None
    if agix is not None:
        fh_share = round(_clamp(42 + (agix - 55) * 0.35, 35.0, 55.0), 1)

    return {
        "home_xg": home_xg,
        "away_xg": away_xg,
        "total_xg": projected_total,
        "home_win_pct": home_win,
        "draw_pct": draw,
        "away_win_pct": away_win,
        "over_1_5_pct": o15,
        "over_2_5_pct": o25,
        "over_3_5_pct": o35,
        "under_2_5_pct": u25,
        "btts_pct": btts,
        "corners": corners,
        "shots": shots,
        "fh_goal_share_pct": fh_share,
        "pace": pace,
        "nec": nec,
        "agix": agix,
        "dgrtg_gap": gap,
        "luck": round(luck, 2),
        "archetype": _archetype(pace, projected_total, gap, btts),
    }


def _archetype(
    pace: float | None,
    total: float | None,
    gap: float | None,
    btts: float | None,
) -> str:
    if total is not None and total >= 3.2 and (pace or 0) >= 60:
        return "High-event"
    if total is not None and total <= 2.2 and (pace or 99) <= 55:
        return "Low-event"
    if gap is not None and abs(gap) >= 8:
        return "Mismatch"
    if btts is not None and btts >= 60:
        return "BTTS lean"
    return "Balanced"


def _signal(name: str, weight: float, detail: str) -> dict[str, Any]:
    return {"name": name, "weight": round(weight, 1), "detail": detail}


def _score_market(
    *,
    bet_type: str,
    label: str,
    team_name: str,
    model_pct: float | None,
    odds: float | None,
    signals: list[dict[str, Any]],
    line_token: str = "",
) -> dict[str, Any] | None:
    if model_pct is None:
        return None
    confidence = round(sum(s["weight"] for s in signals), 1)
    confidence = _clamp(confidence, 0.0, 100.0)
    edge_val = calc_edge(model_pct, odds)
    ev_val = expected_value_pct(model_pct, odds)
    imp = implied_prob(odds)

    if confidence < MIN_CONFIDENCE:
        return None
    if odds is not None and odds > 1:
        if edge_val is None or edge_val < MIN_EDGE_WHEN_ODDS:
            return None
        if ev_val is not None and ev_val <= 0:
            return None
    elif not ALLOW_NO_ODDS:
        return None

    units = 1.0
    if confidence >= 78 and (edge_val or 0) >= 5:
        units = 1.5
    elif confidence < 68:
        units = 0.75

    return {
        "bet_type": bet_type,
        "market_label": label,
        "team_name": team_name or line_token,
        "model_pct": round(model_pct, 1),
        "odds": odds,
        "implied_pct": imp,
        "edge": edge_val,
        "ev": ev_val,
        "confidence": confidence,
        "units": units,
        "signals": signals,
        "signal_summary": " · ".join(s["detail"] for s in signals[:4]),
    }


def pick_markets(profile: dict[str, Any], proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Score candidate markets; keep the strongest stacked-signal picks."""
    home = profile["home_team"]
    away = profile["away_team"]
    odds = profile["odds"]
    idx = profile["indexes"]
    highlights = {str(h).lower() for h in (profile.get("highlights") or [])}
    picks: list[dict[str, Any]] = []

    def pace_sig(for_overs: bool) -> dict[str, Any] | None:
        pace = proj.get("pace")
        if pace is None:
            return None
        if for_overs and pace >= 60:
            return _signal("pace", 12, f"Pace {pace:.0f} supports volume")
        if not for_overs and pace <= 52:
            return _signal("pace", 12, f"Pace {pace:.0f} suppresses volume")
        bucket_o25 = idx.get("pace_bucket_o25")
        if for_overs and bucket_o25 is not None and bucket_o25 >= 58:
            return _signal("pace_hist", 10, f"Pace bucket O2.5 hist {bucket_o25:.0f}%")
        return None

    def nec_sig() -> dict[str, Any] | None:
        nec = proj.get("nec")
        if nec is not None and nec >= 58:
            return _signal("nec", 10, f"NEC {nec:.0f} attacking identity")
        return None

    def highlight_sig(*keys: str) -> dict[str, Any] | None:
        for k in keys:
            for h in highlights:
                if k in h:
                    return _signal("highlight", 8, f"Slate highlight: {h}")
        return None

    def sim_sig(pct: float | None, floor: float, label: str) -> dict[str, Any] | None:
        if pct is not None and pct >= floor:
            return _signal("sim", min(28, 10 + (pct - floor) * 0.6), f"Sim {label} {pct:.0f}%")
        return None

    def xg_sig(ok: bool, detail: str, weight: float = 14) -> dict[str, Any] | None:
        return _signal("xg", weight, detail) if ok else None

    def luck_ok_for_overs() -> dict[str, Any] | None:
        luck = proj.get("luck") or 0
        if luck <= 0.35:
            return _signal("regression", 8, "Finishing not heavily inflated")
        return None

    def luck_ok_for_unders() -> dict[str, Any] | None:
        luck = proj.get("luck") or 0
        if luck >= 0.25:
            return _signal("regression", 10, "Results inflated vs xG — unders lean")
        return None

    # --- Over 2.5 ---
    sigs = [
        s
        for s in (
            sim_sig(proj.get("over_2_5_pct"), 58, "O2.5"),
            xg_sig(
                (proj.get("total_xg") or 0) >= 2.7,
                f"Projected total xG {proj.get('total_xg')}",
            ),
            pace_sig(True),
            nec_sig(),
            luck_ok_for_overs(),
            highlight_sig("over", "btts", "pace", "score", "goal"),
        )
        if s
    ]
    pick = _score_market(
        bet_type="arahus_o25",
        label="Over 2.5",
        team_name="",
        model_pct=proj.get("over_2_5_pct"),
        odds=odds.get("over_2_5"),
        signals=sigs,
    )
    if pick:
        picks.append(pick)

    # --- Over 1.5 ---
    sigs = [
        s
        for s in (
            sim_sig(proj.get("over_1_5_pct"), 70, "O1.5"),
            xg_sig((proj.get("total_xg") or 0) >= 2.3, f"Total xG {proj.get('total_xg')}", 12),
            pace_sig(True),
            luck_ok_for_overs(),
        )
        if s
    ]
    pick = _score_market(
        bet_type="arahus_o15",
        label="Over 1.5",
        team_name="",
        model_pct=proj.get("over_1_5_pct"),
        odds=odds.get("over_1_5"),
        signals=sigs,
    )
    if pick:
        picks.append(pick)

    # --- Over 3.5 ---
    sigs = [
        s
        for s in (
            sim_sig(proj.get("over_3_5_pct"), 48, "O3.5"),
            xg_sig((proj.get("total_xg") or 0) >= 3.4, f"Total xG {proj.get('total_xg')}", 16),
            pace_sig(True),
            nec_sig(),
            luck_ok_for_overs(),
            highlight_sig("pace", "score", "goal"),
        )
        if s
    ]
    pick = _score_market(
        bet_type="arahus_o35",
        label="Over 3.5",
        team_name="",
        model_pct=proj.get("over_3_5_pct"),
        odds=odds.get("over_3_5"),
        signals=sigs,
    )
    if pick:
        picks.append(pick)

    # --- Under 2.5 ---
    sigs = [
        s
        for s in (
            sim_sig(proj.get("under_2_5_pct"), 55, "U2.5"),
            xg_sig(
                proj.get("total_xg") is not None and (proj.get("total_xg") or 99) <= 2.35,
                f"Low total xG {proj.get('total_xg')}",
                16,
            ),
            pace_sig(False),
            luck_ok_for_unders(),
        )
        if s
    ]
    pick = _score_market(
        bet_type="arahus_u25",
        label="Under 2.5",
        team_name="",
        model_pct=proj.get("under_2_5_pct"),
        odds=odds.get("under_2_5"),
        signals=sigs,
    )
    if pick:
        picks.append(pick)

    # --- BTTS ---
    sigs = [
        s
        for s in (
            sim_sig(proj.get("btts_pct"), 55, "BTTS"),
            xg_sig(
                (proj.get("home_xg") or 0) >= 0.95 and (proj.get("away_xg") or 0) >= 0.95,
                f"Both sides xG {proj.get('home_xg')}/{proj.get('away_xg')}",
                14,
            ),
            pace_sig(True),
            highlight_sig("btts"),
            luck_ok_for_overs(),
        )
        if s
    ]
    pick = _score_market(
        bet_type="arahus_btts",
        label="BTTS Yes",
        team_name="",
        model_pct=proj.get("btts_pct"),
        odds=odds.get("btts_yes"),
        signals=sigs,
    )
    if pick:
        picks.append(pick)

    # --- Team totals / ML ---
    for side, xg_key, win_key, o15_odds_key, o05_odds_key, ml_key in (
        ("home", "home_xg", "home_win_pct", "home_o1_5", "home_o0_5", "home_ml"),
        ("away", "away_xg", "away_win_pct", "away_o1_5", "away_o0_5", "away_ml"),
    ):
        team = home if side == "home" else away
        txg = proj.get(xg_key)
        win_pct = proj.get(win_key)
        gap = proj.get("dgrtg_gap") or 0
        gap_ok = (gap >= 4 and side == "home") or (gap <= -4 and side == "away")

        # Team O1.5
        team_o15_pct = None
        if txg is not None:
            team_o15_pct = round(_poisson_cdf_ge(2, txg) * 100, 1)
        sigs = [
            s
            for s in (
                xg_sig(txg is not None and txg >= 1.75, f"{team} xG {txg}", 18),
                sim_sig(team_o15_pct, 55, f"{team} O1.5"),
                _signal("rating", 10, f"DGRtg gap {gap:+.1f}") if gap_ok else None,
                nec_sig(),
            )
            if s
        ]
        pick = _score_market(
            bet_type="arahus_team_o15",
            label=f"{team} O1.5",
            team_name=team,
            model_pct=team_o15_pct,
            odds=odds.get(o15_odds_key),
            signals=sigs,
        )
        if pick:
            picks.append(pick)

        # Team O0.5
        team_o05_pct = round((1 - math.exp(-(txg or 0))) * 100, 1) if txg else None
        sigs = [
            s
            for s in (
                xg_sig(txg is not None and txg >= 1.05, f"{team} xG {txg}", 16),
                sim_sig(team_o05_pct, 68, f"{team} O0.5"),
            )
            if s
        ]
        pick = _score_market(
            bet_type="arahus_team_o05",
            label=f"{team} O0.5",
            team_name=team,
            model_pct=team_o05_pct,
            odds=odds.get(o05_odds_key),
            signals=sigs,
        )
        if pick:
            picks.append(pick)

        # Moneyline
        sigs = [
            s
            for s in (
                sim_sig(win_pct, 55, f"{team} win"),
                _signal("rating", 14, f"DGRtg gap {gap:+.1f}") if gap_ok else None,
                xg_sig(
                    txg is not None
                    and (
                        (side == "home" and txg >= (proj.get("away_xg") or 0) + 0.35)
                        or (side == "away" and txg >= (proj.get("home_xg") or 0) + 0.35)
                    ),
                    f"Attacking edge xG {txg}",
                    12,
                ),
                highlight_sig("win"),
            )
            if s
        ]
        pick = _score_market(
            bet_type="arahus_ml",
            label=f"{team} Win",
            team_name=team,
            model_pct=win_pct,
            odds=odds.get(ml_key),
            signals=sigs,
        )
        if pick:
            picks.append(pick)

    # Double chance for milder favorites
    for side, win_key, dc_key, bt, label in (
        ("home", "home_win_pct", "dc_1x", "arahus_dc_1x", "Double Chance 1X"),
        ("away", "away_win_pct", "dc_x2", "arahus_dc_x2", "Double Chance X2"),
    ):
        team = home if side == "home" else away
        win_pct = proj.get(win_key)
        draw = proj.get("draw_pct") or 0
        dc_pct = round((win_pct or 0) + draw, 1) if win_pct is not None else None
        gap = proj.get("dgrtg_gap") or 0
        mild = (2 <= gap <= 9 and side == "home") or (-9 <= gap <= -2 and side == "away")
        sigs = [
            s
            for s in (
                sim_sig(dc_pct, 65, "DC"),
                _signal("rating", 12, f"Mild DGRtg edge {gap:+.1f}") if mild else None,
                xg_sig(win_pct is not None and win_pct >= 45, f"Win base {win_pct}%", 10),
            )
            if s
        ]
        pick = _score_market(
            bet_type=bt,
            label=f"{label} ({team})",
            team_name=team,
            model_pct=dc_pct,
            odds=odds.get(dc_key),
            signals=sigs,
        )
        if pick:
            picks.append(pick)

    # --- Corners ---
    corners = proj.get("corners")
    if corners is not None:
        for line, bt, label in (
            (8.5, "arahus_corners_o85", "Corners O8.5"),
            (9.5, "arahus_corners_o95", "Corners O9.5"),
            (10.5, "arahus_corners_o105", "Corners O10.5"),
        ):
            # Soft logistic around the line
            model = round(_clamp(50 + (corners - line) * 18, 5, 92), 1)
            sigs = [
                s
                for s in (
                    xg_sig(corners >= line + 0.3, f"Projected corners {corners}", 18),
                    pace_sig(True),
                    highlight_sig("corner"),
                    _signal("agix", 8, f"AGIX {proj.get('agix'):.0f}")
                    if (proj.get("agix") or 0) >= 58
                    else None,
                )
                if s
            ]
            pick = _score_market(
                bet_type=bt,
                label=label,
                team_name=str(line),
                model_pct=model,
                odds=None,  # book corners rarely on match row; allow no-odds if enabled
                signals=sigs,
                line_token=str(line),
            )
            if pick:
                picks.append(pick)

    picks.sort(
        key=lambda p: (
            p.get("confidence") or 0,
            p.get("edge") or -99,
            p.get("ev") or -99,
        ),
        reverse=True,
    )
    # Deduplicate conflicting totals (don't take O2.5 and U2.5 together)
    selected: list[dict[str, Any]] = []
    seen_families: set[str] = set()
    for p in picks:
        family = "totals" if p["bet_type"] in {"arahus_o15", "arahus_o25", "arahus_o35", "arahus_u25"} else p["bet_type"]
        if p["bet_type"] in {"arahus_o15", "arahus_o25", "arahus_o35"}:
            family = "overs"
        if p["bet_type"] == "arahus_u25":
            family = "unders"
        if family == "overs" and "unders" in seen_families:
            continue
        if family == "unders" and "overs" in seen_families:
            continue
        if family in seen_families and family in {"overs", "unders"}:
            # keep only best over/under
            continue
        # one ML max
        if p["bet_type"] == "arahus_ml" and "ml" in seen_families:
            continue
        if p["bet_type"] == "arahus_ml":
            seen_families.add("ml")
        elif family in {"overs", "unders"}:
            seen_families.add(family)
        selected.append(p)
        if len(selected) >= MAX_PICKS_PER_FIXTURE:
            break
    return selected


def evaluate_fixture(
    raw: dict[str, Any],
    match: dict[str, Any] | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    profile = build_fixture_profile(raw, match, extra)
    projections = project_match(profile)
    picks = pick_markets(profile, projections)
    return {
        "fixture_id": profile["fixture_id"],
        "fixture": profile["fixture"],
        "fixture_date": profile["fixture_date"],
        "league_name": profile["league_name"],
        "home_team": profile["home_team"],
        "away_team": profile["away_team"],
        "projections": projections,
        "profile": {
            "ratings": profile["ratings"],
            "indexes": profile["indexes"],
            "regression": profile["regression"],
            "highlights": profile["highlights"],
            "sim": profile["sim"],
            "xg": profile["xg"],
            "volume": profile["volume"],
        },
        "picks": picks,
        "pick_count": len(picks),
        "has_picks": bool(picks),
        "top_confidence": picks[0]["confidence"] if picks else 0,
    }


def build_arahus_slate(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate every fixture in the latest slate (fixture-wise cards)."""
    fixtures_by_id = state.get("fixtures_by_id") or {}
    indexes = state.get("dg_extra_indexes") or {}
    matches_by_id = {
        str(m.get("fixture_id")): m for m in (state.get("matches") or []) if m.get("fixture_id")
    }

    cards: list[dict[str, Any]] = []
    # Prefer iterating matches (scored slate); fall back to raw fixtures.
    ids = [str(m.get("fixture_id")) for m in (state.get("matches") or []) if m.get("fixture_id")]
    if not ids:
        ids = list(fixtures_by_id.keys())

    for fid in ids:
        raw = find_raw_fixture(fixtures_by_id, fid)
        if not raw:
            continue
        match = matches_by_id.get(str(fid))
        extra = lookup_extra_for_fixture(raw, indexes, include_player_sims=False) if indexes else {}
        try:
            card = evaluate_fixture(raw, match, extra)
        except Exception:
            continue
        cards.append(card)

    cards.sort(
        key=lambda c: (
            c.get("has_picks"),
            c.get("top_confidence") or 0,
            (c.get("projections") or {}).get("total_xg") or 0,
        ),
        reverse=True,
    )
    return cards


def flatten_picks(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for card in cards:
        for pick in card.get("picks") or []:
            out.append(
                {
                    "fixture_id": card.get("fixture_id"),
                    "fixture": card.get("fixture"),
                    "fixture_date": card.get("fixture_date"),
                    "league_name": card.get("league_name"),
                    "home_team": card.get("home_team"),
                    "away_team": card.get("away_team"),
                    "archetype": (card.get("projections") or {}).get("archetype"),
                    **pick,
                }
            )
    out.sort(key=lambda p: (p.get("confidence") or 0, p.get("edge") or -99), reverse=True)
    return out


# --- Bet log (isolated) ------------------------------------------------------

def load_arahus_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def sync_arahus_bets(picks: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for p in picks:
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": p.get("bet_type") or "unknown",
                "team_name": p.get("team_name") or "",
                "qualifier_pct": p.get("confidence"),
                "odds": p.get("odds"),
                "units": float(p.get("units") or 1.0),
                "status": "open",
                "pnl_units": None,
            }
        )
    inserted = insert_bets(LOG_TYPE, candidates)
    return {"inserted": inserted, "total": len(load_arahus_bet_log())}


def resolve_arahus_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")
    entry = next((e for e in load_arahus_bet_log() if e.get("id") == bet_id), None)
    if not entry:
        raise ValueError("Bet not found.")
    odds = float(entry.get("odds") or 0)
    units = float(entry.get("units") or 1)
    if result == "won":
        pnl = round((odds - 1) * units, 3) if odds > 0 else round(1.0 * units, 3)
    elif result == "lost":
        pnl = round(-1.0 * units, 3)
    else:
        pnl = 0.0
    updated = resolve_bet_entry(LOG_TYPE, bet_id, result, pnl, _now_iso())
    if not updated:
        raise ValueError("Bet not found.")
    return updated


def arahus_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    stats = compute_bet_stats(entries)
    by_type: dict[str, dict[str, Any]] = {}
    for bt in sorted({str(e.get("bet_type") or "") for e in entries} - {""}):
        subset = [e for e in entries if e.get("bet_type") == bt]
        row = compute_bet_stats(subset)
        row["bet_type"] = bt
        row["label"] = BET_LABELS.get(bt, bt)
        by_type[bt] = row
    return {**stats, "by_type": by_type}


def enrich_arahus_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in entries:
        row = dict(e)
        bt = str(row.get("bet_type") or "")
        label = BET_LABELS.get(bt, bt)
        team = str(row.get("team_name") or "").strip()
        if bt in {"arahus_ml", "arahus_team_o05", "arahus_team_o15", "arahus_dc_1x", "arahus_dc_x2"} and team:
            row["market_label"] = label if team in label else f"{team} · {label}"
        elif bt.startswith("arahus_corners_") and team:
            row["market_label"] = f"Corners O{team}"
        else:
            row["market_label"] = label
        conf = num(row.get("qualifier_pct"))
        row["confidence_fmt"] = f"{conf:.0f}" if conf is not None else "—"
        out.append(row)
    return out
