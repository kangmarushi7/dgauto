"""Quant terminal enrichments: archetypes, opportunities, movement placeholders, risk v2, etc."""
from __future__ import annotations

import math
import random
from typing import Any

from app.fixture_math import (
    certainty_score,
    expected_value_pct,
    fmt as qfmt,
    grade_label,
    implied_prob,
    kelly_fraction,
    num,
    verdict_from_edge_strict,
)


def _poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0:
        return 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def _goal_histogram(home_xg: float, away_xg: float, max_g: int = 6) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in range(max_g + 1):
        p = 0.0
        for h in range(g + 1):
            a = g - h
            if a < 0:
                continue
            p += _poisson_pmf(home_xg, h) * _poisson_pmf(away_xg, a)
        out.append({"label": str(g), "pct": round(p * 100, 2)})
    mx = max((x["pct"] for x in out), default=1) or 1
    for x in out:
        x["bar_width"] = round(100 * x["pct"] / mx, 1)
    return out


def _volume_histogram(total: float | None, *, scale: float = 1.15) -> list[dict[str, Any]]:
    if total is None or total <= 0:
        return []
    lam = total * scale
    out = []
    for k in range(0, 28, 2):
        p = _poisson_pmf(lam, k) * 100
        if p < 0.02 and k > int(lam) + 8:
            break
        out.append({"label": str(k), "pct": round(p, 2)})
    mx = max((x["pct"] for x in out), default=1) or 1
    for x in out:
        x["bar_width"] = round(100 * x["pct"] / mx, 1)
    return out


def build_fixture_archetype(
    perc: dict[str, Any],
    xg: dict[str, Any],
    markets: list[dict[str, Any]],
    match: dict[str, Any],
) -> dict[str, Any]:
    tx = num(xg.get("total")) or 0
    draw = num(perc.get("draw_pct")) or 0
    hw = num(perc.get("home_win_pct")) or 0
    aw = num(perc.get("away_win_pct")) or 0
    edges = [num(m.get("edge")) for m in markets if num(m.get("edge")) is not None]
    edge_spread = (max(edges) - min(edges)) if len(edges) >= 2 else 0
    best_e = max((e for e in edges if e is not None), default=None)

    tags: list[str] = []
    primary = "BALANCED"
    if tx >= 3.2:
        tags.append("HIGH_TEMPO")
        primary = "OPEN_GAME"
    elif tx < 2.15:
        tags.append("LOW_TEMPO")
        primary = "DEFENSIVE_BATTLE"
    if num(perc.get("over_2_5_pct")) or 0 >= 68:
        tags.append("GOAL_FEST")
        if primary == "BALANCED":
            primary = "OPEN_GAME"
    if draw >= 30:
        tags.append("TRAP_GAME")
        primary = "TRAP_GAME"
    if abs(hw - aw) < 8 and draw >= 26:
        tags.append("COIN_FLIP")
    if best_e is not None and best_e >= 6 and edge_spread >= 12:
        tags.append("MARKET_DISAGREEMENT")
    if (num(match.get("score")) or 0) < 48 and tx >= 2.8:
        tags.append("CHAOTIC_MATCHUP")

    return {
        "primary": primary,
        "tags": tags[:4],
        "subtitle": " · ".join(tags) if tags else "Standard profile",
    }


def build_certainty_for_market(
    m: dict[str, Any],
    perc: dict[str, Any],
    xg: dict[str, Any],
    match: dict[str, Any],
) -> tuple[int, str]:
    return certainty_score(
        edge_val=m.get("edge"),
        model_pct=m.get("model_pct"),
        draw_pct=perc.get("draw_pct"),
        total_xg=num(xg.get("total")),
        signal_score=match.get("score"),
    )


def _kelly_units(k_full: float | None, certainty_label: str) -> dict[str, Any]:
    if k_full is None or k_full <= 0:
        return {
            "full": 0.0,
            "half": 0.0,
            "quarter": 0.0,
            "recommended": 0.0,
            "profile": "—",
            "label": "No edge",
        }
    mult = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.25}.get(certainty_label, 0.25)
    rec = round(k_full * mult * 100, 2)
    profile = "Aggressive" if mult >= 1.0 else ("Balanced" if mult >= 0.5 else "Conservative")
    return {
        "full": round(k_full * 100, 2),
        "half": round(k_full * 50, 2),
        "quarter": round(k_full * 25, 2),
        "recommended": rec,
        "profile": profile,
        "label": f"{rec}% bankroll ({profile})",
    }


def enrich_market_row(
    m: dict[str, Any],
    perc: dict[str, Any],
    xg: dict[str, Any],
    match: dict[str, Any],
    *,
    home_name: str,
    away_name: str,
    profiles: list[dict[str, Any]],
    insight: dict[str, Any] | None,
) -> dict[str, Any]:
    model = m.get("model_pct")
    odds = m.get("book_odds")
    ev = expected_value_pct(model, odds)
    k_full = kelly_fraction(model, odds)
    cert_score, cert_label = build_certainty_for_market(m, perc, xg, match)
    kelly = _kelly_units(k_full, cert_label)
    grade = m.get("grade")
    verdict = verdict_from_edge_strict(m.get("edge"))

    why: list[str] = []
    e = num(m.get("edge"))
    if e is not None and e >= 2:
        why.append(f"Model edge vs implied: {m.get('edge_fmt')}")
    if ev is not None and ev > 0:
        why.append(f"Positive expected value: {ev:+.1f}%")
    hx, ax = num(xg.get("home")), num(xg.get("away"))
    mk = str(m.get("market") or "")
    if hx is not None and ax is not None:
        if home_name and home_name in mk and "Win" in mk and hx > ax + 0.35:
            why.append(f"xG edge for {home_name}: +{round(hx - ax, 2)} vs opponent projection")
        elif away_name and away_name in mk and "Win" in mk and ax > hx + 0.35:
            why.append(f"xG edge for {away_name}: +{round(ax - hx, 2)} vs opponent projection")
        elif "Over" in mk or "Under" in mk or "BTTS" in mk:
            why.append(f"Match xG environment {round((hx or 0) + (ax or 0), 2)} combined")
    if any(p.get("qualifies") for p in profiles):
        why.append("Fixture matches at least one historically profitable model profile")
    if insight:
        txt = str(insight.get("summary") or insight.get("insight") or insight.get("text") or "").strip()
        if txt and len(txt) < 220:
            why.append(txt[:220])

    glow = verdict == "STRONG VALUE"
    units = 0.0
    if verdict in ("STRONG VALUE", "VALUE", "LEAN") and (e or 0) >= 2 and ev is not None and ev > 0:
        units = round(min(3.0, max(0.25, kelly["recommended"] / 25)), 2)

    return {
        **m,
        "verdict": verdict,
        "grade_label": grade_label(str(grade) if grade else None),
        "ev": ev,
        "ev_fmt": f"{ev:+.1f}%" if ev is not None else "—",
        "kelly_full_pct": kelly["full"],
        "kelly_half_pct": kelly["half"],
        "kelly_quarter_pct": kelly["quarter"],
        "kelly_recommended_pct": kelly["recommended"],
        "kelly_profile": kelly["profile"],
        "kelly_label": kelly["label"],
        "certainty_score": cert_score,
        "certainty_label": cert_label,
        "why_bet": why[:6],
        "glow": glow,
        "units": units,
        "risk": "LOW" if (e or 0) >= 6 else ("MED" if (e or 0) >= 2 else "HIGH"),
    }


def build_ranked_opportunities(markets: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    ranked = []
    pool = [x for x in markets if num(x.get("edge")) is not None and x.get("model_ok", True)]
    for i, m in enumerate(
        sorted(
            pool,
            key=lambda x: (num(x.get("edge")) or 0),
            reverse=True,
        )[:limit],
        start=1,
    ):
        e = num(m.get("edge")) or 0
        ev = num(m.get("ev"))
        ranked.append(
            {
                "rank": i,
                "market": m.get("market"),
                "verdict": m.get("verdict"),
                "model_pct_fmt": m.get("model_pct_fmt"),
                "book_pct_fmt": m.get("book_pct_fmt"),
                "book_odds_fmt": m.get("book_odds_fmt"),
                "fair_odds_fmt": m.get("fair_odds_fmt"),
                "edge": e,
                "edge_fmt": m.get("edge_fmt"),
                "edge_bar": min(100, max(0, round((e + 5) * 8, 1))),
                "ev_fmt": m.get("ev_fmt"),
                "ev": ev,
                "grade": m.get("grade"),
                "grade_label": m.get("grade_label"),
                "certainty_label": m.get("certainty_label"),
                "certainty_score": m.get("certainty_score"),
                "risk": m.get("risk"),
                "tone": "positive" if e >= 2 else ("trap" if e <= -3 else "neutral"),
            }
        )
    return ranked


def build_market_movement(markets: list[dict[str, Any]], book: dict[str, Any]) -> dict[str, Any]:
    """Placeholder movement intel until a real odds-history feed exists."""
    rows = []
    for m in markets[:6]:
        odds = m.get("book_odds")
        fair = m.get("fair_odds")
        if odds is None:
            continue
        o = num(odds) or 1.01
        f = num(fair) or o
        rng = random.Random(str(m.get("market")) + str(round(o, 2)))
        drift = round((rng.random() - 0.45) * 0.12, 3)
        open_est = round(max(1.01, f * (1 + drift)), 2)
        move = round(((o - open_est) / open_est) * 100, 1) if open_est else 0
        model = num(m.get("model_pct")) or 0
        imp_o = num(implied_prob(open_est)) or 0
        imp_c = num(implied_prob(o)) or 0
        toward = "toward_favorite" if move < -0.5 else ("toward_underdog" if move > 0.5 else "flat")
        disagree = (model > imp_c + 3) and move < -1
        rows.append(
            {
                "market": m.get("market"),
                "opening_odds_est": open_est,
                "opening_fmt": qfmt(open_est, digits=2),
                "current_odds": o,
                "current_fmt": qfmt(o, digits=2),
                "move_pct": move,
                "steam_note": "Model-estimated open vs current book (no exchange feed).",
                "sharp_signal": "Model disagrees with line compression" if disagree else "Aligned with model",
                "public_signal": "Likely public on favorite" if move < -1.5 else "Balanced flow assumption",
            }
        )
    return {
        "disclaimer": "Line movement is model-estimated from fair vs current odds. No live steam or opening line feed.",
        "rows": rows,
    }


def build_correlation_intel(perc: dict[str, Any], markets: list[dict[str, Any]]) -> dict[str, Any]:
    hw = num(perc.get("home_win_pct")) or 0
    o25 = num(perc.get("over_2_5_pct")) or 0
    btts = num(perc.get("btts_pct")) or 0
    pairs = [
        {
            "a": "Home win",
            "b": "Over 2.5",
            "strength": min(100, round(abs(hw - 50) * 0.6 + abs(o25 - 50) * 0.5, 0)),
            "note": "Home control often coincides with higher goal volume.",
        },
        {
            "a": "BTTS Yes",
            "b": "Over 2.5",
            "strength": min(100, round(abs(btts - 50) * 0.7 + abs(o25 - 50) * 0.45, 0)),
            "note": "Both teams scoring aligns with elevated total goals.",
        },
    ]
    best_combo = None
    pos = [m for m in markets if num(m.get("ev")) is not None and (num(m.get("ev")) or 0) > 0]
    if len(pos) >= 2:
        pos.sort(key=lambda x: num(x.get("ev")) or 0, reverse=True)
        best_combo = {
            "legs": [pos[0].get("market"), pos[1].get("market")],
            "note": "Heuristic combo from top two positive-EV priced markets (correlation assumed moderate).",
        }
    return {"pairs": pairs, "best_combo": best_combo}


def build_live_triggers(perc: dict[str, Any], xg: dict[str, Any], fh: dict[str, Any]) -> list[dict[str, Any]]:
    tx = num(xg.get("total")) or 0
    o15 = num(perc.get("over_1_5_pct")) or 0
    fh_xg = num((fh.get("xg") or {}).get("total")) or 0
    triggers = []
    if tx >= 2.6 and o15 >= 78:
        triggers.append(
            {
                "title": "Live Over 1.5 watch",
                "condition": "IF 0-0 after 25' AND xThreat proxy remains high",
                "action": "Live Over 1.5 may offer value if price drifts above model fair.",
                "confidence": "MEDIUM",
            }
        )
    if fh_xg and fh_xg / max(tx, 0.1) >= 0.48:
        triggers.append(
            {
                "title": "First-half goal pressure",
                "condition": "Early volume suggests first-half goal markets merit monitoring.",
                "action": "Consider FH O0.5 / FH goal line only if live odds exceed model fair.",
                "confidence": "LOW",
            }
        )
    return triggers


def build_trend_intel(
    home_name: str,
    away_name: str,
    home_trends: dict[str, Any] | None,
    away_trends: dict[str, Any] | None,
    h2h: dict[str, Any],
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    def add_trend(label: str, text: str, tone: str = "neutral") -> None:
        cards.append({"label": label, "text": text, "tone": tone})

    if home_trends:
        l6 = home_trends.get("last6") or {}
        gf = l6.get("avg_goals_for")
        if gf is not None:
            add_trend(home_name, f"L6 avg goals for: {gf}", "up" if float(gf) >= 1.2 else "neutral")
        oc = (l6.get("over_10_corners") or {}).get("percent")
        if oc is not None:
            add_trend(home_name, f"L6 over 10 corners: {oc}%", "up" if float(oc) >= 55 else "neutral")
    if away_trends:
        l6 = away_trends.get("last6") or {}
        gf = l6.get("avg_goals_for")
        if gf is not None:
            add_trend(away_name, f"L6 avg goals for: {gf}", "up" if float(gf) >= 1.2 else "neutral")

    raw = (h2h.get("h2h") or {}).get("raw_matches") or []
    if isinstance(raw, list) and len(raw) >= 3:
        add_trend("H2H sample", f"{len(raw)} recent meetings in database", "neutral")

    return cards[:10]


def build_distribution_blocks(sim: dict[str, Any], xg: dict[str, Any]) -> dict[str, Any]:
    hx = num(xg.get("home")) or 0
    ax = num(xg.get("away")) or 0
    goals = _goal_histogram(hx, ax)
    corners = _volume_histogram(num((sim.get("corners") or {}).get("total")))
    shots = _volume_histogram(num((sim.get("shots") or {}).get("total")), scale=1.08)
    cards = _volume_histogram(num((sim.get("cards") or {}).get("total")), scale=1.05)
    return {
        "goals": goals,
        "corners": corners,
        "shots": shots,
        "cards": cards,
    }


def build_match_flow_timeline(perc: dict[str, Any], fh: dict[str, Any], xg: dict[str, Any]) -> list[dict[str, Any]]:
    fh_xg = num((fh.get("xg") or {}).get("total")) or 0
    ft = num(xg.get("total")) or 0
    o25 = num(perc.get("over_2_5_pct")) or 50
    segs = [
        {"id": "0-15", "label": "0'–15'", "pressure": min(100, round(fh_xg * 28 + 15, 0))},
        {"id": "15-45", "label": "15'–HT", "pressure": min(100, round(fh_xg * 32 + o25 * 0.25, 0))},
        {"id": "45-75", "label": "2H open", "pressure": min(100, round((ft - fh_xg) * 26 + o25 * 0.3, 0))},
        {"id": "75-90", "label": "75'–90'", "pressure": min(100, round((ft - fh_xg) * 22 + 20, 0))},
    ]
    return segs


def build_risk_v2(
    match: dict[str, Any],
    perc: dict[str, Any],
    xg: dict[str, Any],
    markets: list[dict[str, Any]],
) -> dict[str, Any]:
    draw = num(perc.get("draw_pct")) or 0
    tx = num(xg.get("total")) or 0
    edges = [num(m.get("edge")) for m in markets if num(m.get("edge")) is not None]
    spread = (max(edges) - min(edges)) if len(edges) >= 2 else 0
    neg = sum(1 for e in edges if e is not None and e < -2)

    variance = min(100, round(draw * 1.1 + spread * 1.5 + abs(tx - 2.7) * 12, 0))
    stability = max(0, min(100, round(100 - variance * 0.55 + (num(match.get("score")) or 50) * 0.25, 0)))
    team_vol = min(100, round(abs(num(perc.get("home_win_pct")) or 50 - num(perc.get("away_win_pct")) or 50) * 0.8 + tx * 8, 0))
    mkt_eff = min(100, round(72 - (max(edges) or 0) * 2 + neg * 6, 0))
    sim_agree = max(0, min(100, round(num(match.get("score")) or 50, 0)))
    corr_risk = min(100, round(spread * 1.2 + (10 if neg else 0), 0))

    overall = "MEDIUM"
    score_risk = round((variance + (100 - stability) + team_vol + (100 - mkt_eff) + corr_risk) / 5)
    if score_risk >= 62 or draw >= 30:
        overall = "HIGH"
    elif score_risk <= 42 and draw < 22:
        overall = "LOW"

    return {
        "overall": overall,
        "overall_score": score_risk,
        "dimensions": [
            {"key": "variance", "label": "Variance", "value": variance},
            {"key": "stability", "label": "Model stability", "value": stability},
            {"key": "team_vol", "label": "Team volatility", "value": team_vol},
            {"key": "mkt_eff", "label": "Market efficiency", "value": mkt_eff},
            {"key": "sim_agree", "label": "Simulation agreement", "value": sim_agree},
            {"key": "corr", "label": "Correlation risk", "value": corr_risk},
        ],
    }


def build_hero_v2(
    *,
    home_name: str,
    away_name: str,
    league_name: str,
    round_name: str,
    kickoff: str,
    is_neutral: bool,
    match: dict[str, Any],
    archetype: dict[str, Any],
    confidence_grade: str,
    risk: str,
    top_edge: dict[str, Any] | None,
    recommended: list[dict[str, Any]],
    scorelines: list[dict[str, Any]],
    hx: float | None,
    ax: float | None,
    tx: float | None,
    tempo: str,
    volatility: int,
    hist_qualified: int,
    certainty_label: str,
    certainty_score: int,
) -> dict[str, Any]:
    best_market = top_edge.get("market") if top_edge else None
    combo = None
    if len(recommended) >= 2:
        combo = f"{recommended[0].get('market')} + {recommended[1].get('market')}"
    return {
        "left": {
            "fixture": f"{home_name} vs {away_name}",
            "league": league_name,
            "round": round_name,
            "kickoff": kickoff,
            "neutral": is_neutral,
            "signal": match.get("signal"),
            "signal_score": match.get("score"),
            "confidence_grade": confidence_grade,
            "confidence_label": grade_label(confidence_grade),
            "risk_level": risk,
            "archetype": archetype.get("primary"),
            "archetype_tags": archetype.get("tags") or [],
        },
        "center": {
            "top_bets": [b.get("market") for b in recommended[:3]],
            "strongest_edge": top_edge.get("edge_fmt") if top_edge else "—",
            "strongest_market": best_market,
            "suggested_combo": combo,
            "certainty_score": certainty_score,
            "certainty_label": certainty_label,
            "best_market": best_market,
        },
        "right": {
            "scoreline": scorelines[0]["score"] if scorelines else "—",
            "scoreline_pct": scorelines[0].get("pct") if scorelines else None,
            "xg_home": hx,
            "xg_away": ax,
            "xg_total": tx,
            "tempo": tempo,
            "volatility": volatility,
            "hist_qualified": hist_qualified,
        },
    }
