"""Institutional-grade fixture intelligence dashboard (consolidated, no duplicate sections)."""
from __future__ import annotations

import math
from typing import Any

from app.dg_feeds import build_correct_score_matrix
from app.fixture_math import edge as _edge
from app.fixture_math import fmt as _fmt
from app.fixture_math import implied_prob as _implied_prob
from app.fixture_math import num as _num
from app.slate import _build_picks, _fmt_kickoff, _parse_dt
from app.signals import score_match


def grade_from_pct(pct: float | None) -> str:
    p = _num(pct)
    if p is None:
        return "—"
    if p >= 85:
        return "A+"
    if p >= 75:
        return "A"
    if p >= 65:
        return "B"
    if p >= 55:
        return "C"
    return "D"


def units_from_grade(grade: str) -> float:
    return {"A+": 3.0, "A": 2.0, "B": 1.0, "C": 0.5}.get(grade, 0.0)


def verdict_from_edge(edge: float | None, model_pct: float | None) -> str:
    e = _num(edge)
    p = _num(model_pct)
    if e is not None:
        if e >= 8:
            return "STRONG VALUE"
        if e >= 4:
            return "VALUE"
        if e >= 1:
            return "LEAN"
        if e <= -4:
            return "AVOID"
    if p is not None and p >= 70:
        return "LEAN"
    return "NEUTRAL"


def fair_odds_from_pct(pct: float | None) -> float | None:
    p = _num(pct)
    if p is None or p <= 0:
        return None
    return round(100.0 / p, 2)


def risk_level(match: dict[str, Any], perc: dict[str, Any], xg: dict[str, Any]) -> str:
    score = _num(match.get("score")) or 0
    draw = _num(perc.get("draw_pct")) or 0
    total_xg = _num(xg.get("total")) or 0
    if draw >= 30 or score < 45:
        return "HIGH"
    if total_xg >= 3.2 and score >= 65:
        return "LOW"
    return "MEDIUM"


def _market_row(
    market: str,
    sim_pct: Any,
    book_odds: Any,
    *,
    kind: str = "main",
) -> dict[str, Any]:
    model = _num(sim_pct)
    imp = _implied_prob(book_odds)
    edge = _edge(sim_pct, book_odds)
    grade = grade_from_pct(model)
    verdict = verdict_from_edge(edge, model)
    return {
        "market": market,
        "kind": kind,
        "model_pct": model,
        "model_pct_fmt": _fmt(model, suffix="%"),
        "book_pct": imp,
        "book_pct_fmt": _fmt(imp, suffix="%"),
        "book_odds": _num(book_odds),
        "book_odds_fmt": _fmt(book_odds, digits=2),
        "fair_odds": fair_odds_from_pct(model),
        "fair_odds_fmt": _fmt(fair_odds_from_pct(model), digits=2),
        "edge": edge,
        "edge_fmt": f"{edge:+.1f}%" if edge is not None else "—",
        "grade": grade,
        "units": units_from_grade(grade) if verdict in ("STRONG VALUE", "VALUE", "LEAN") else 0,
        "verdict": verdict,
        "risk": "LOW" if (edge or 0) >= 6 else ("MED" if (edge or 0) >= 2 else "HIGH"),
        "glow": verdict == "STRONG VALUE",
    }


def _poisson_over_prob(lam: float, line: float) -> float | None:
    if lam <= 0:
        return None
    k_max = int(math.floor(line))
    cdf = 0.0
    for k in range(k_max + 1):
        cdf += math.exp(-lam) * (lam**k) / math.factorial(k)
    return round(100 * (1 - cdf), 1)


def _volume_bar(home: float | None, away: float | None, total: float | None) -> dict[str, Any]:
    h, a = _num(home), _num(away)
    t = _num(total)
    if t is None and h is not None and a is not None:
        t = h + a
    if h is None or a is None or not t:
        return {}
    return {
        "home": h,
        "away": a,
        "total": round(t, 1),
        "home_pct": round(100 * h / t, 1),
        "away_pct": round(100 * a / t, 1),
    }


def _prop_lines(total: float | None, thresholds: list[float]) -> list[dict[str, Any]]:
    lam = _num(total)
    if lam is None:
        return []
    out: list[dict[str, Any]] = []
    for line in thresholds:
        pct = _poisson_over_prob(lam, line)
        if pct is None:
            continue
        out.append(
            {
                "line": line,
                "label": f"Over {line}",
                "model_pct": pct,
                "model_pct_fmt": f"{pct:.1f}%",
                "grade": grade_from_pct(pct),
            }
        )
    return out


def _h2h_prop_averages(h2h: dict[str, Any] | None) -> dict[str, Any]:
    if not h2h:
        return {}
    raw = (h2h.get("h2h") or {}).get("raw_matches") or []
    if not raw:
        return {}
    corners, shots, sot = [], [], []
    for m in raw:
        c = m.get("corners") or {}
        s = m.get("shots") or {}
        st = m.get("shots_on_target") or {}
        if isinstance(c, dict):
            corners.append((_num(c.get("team")) or 0) + (_num(c.get("opp")) or 0))
        if isinstance(s, dict):
            shots.append((_num(s.get("team")) or 0) + (_num(s.get("opp")) or 0))
        if isinstance(st, dict):
            sot.append((_num(st.get("team")) or 0) + (_num(st.get("opp")) or 0))
    def avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "meetings": len(raw),
        "avg_corners": avg(corners),
        "avg_shots": avg(shots),
        "avg_sot": avg(sot),
    }


def _build_prop_analysis(
    home_name: str,
    away_name: str,
    sim: dict[str, Any],
    fh: dict[str, Any],
    extra: dict[str, Any],
    home_trends: dict[str, Any] | None,
    away_trends: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    h2h = extra.get("head2head") or {}
    h2h_avg = _h2h_prop_averages(h2h)
    heat = extra.get("heat") or {}
    heat_proj = heat.get("projected_stats") or {}

    def pack(
        key: str,
        title: str,
        lines: list[float],
        *,
        has_fh: bool = True,
    ) -> dict[str, Any]:
        ft = sim.get(key) or {}
        fh_b = (fh or {}).get(key) or {} if has_fh else {}
        full = _volume_bar(ft.get("home"), ft.get("away"), ft.get("total"))
        first_half = _volume_bar(fh_b.get("home"), fh_b.get("away"), fh_b.get("total")) if fh_b else {}
        total = _num(full.get("total"))
        insights: list[str] = []
        if total is not None:
            if key == "corners" and total >= 10.5:
                insights.append("High corner volume environment — wide play / pressure expected")
            elif key == "corners" and total < 8.5:
                insights.append("Below-average corner projection — tighter central game")
            if key == "shots" and total >= 26:
                insights.append("Heavy shot volume — live overs on attempts may have merit")
            if key == "cards" and total >= 4.5:
                insights.append("Elevated card projection — discipline / foul market angle")
            elif key == "cards" and total <= 3.0:
                insights.append("Low card expectation — cleaner fixture profile")

        hist_notes: list[str] = []
        for label, tr in [(home_name, home_trends), (away_name, away_trends)]:
            if not tr:
                continue
            l6 = tr.get("last6") or {}
            oc = (l6.get("over_10_corners") or {}).get("percent")
            if key == "corners" and oc is not None:
                hist_notes.append(f"{label} L6 over 10 corners: {oc}%")
            if key == "shots" and l6.get("avg_goals_for") is not None:
                hist_notes.append(f"{label} L6 GF: {l6.get('avg_goals_for')}")

        heat_side = None
        if heat_proj and key == "shots":
            hs = (heat_proj.get("home") or {}).get("shots")
            aws = (heat_proj.get("away") or {}).get("shots")
            if hs is not None and aws is not None:
                heat_side = f"Heat map shots: {hs:.0f} / {aws:.0f}"

        return {
            "key": key,
            "title": title,
            "full": full,
            "first_half": first_half,
            "lines": _prop_lines(total, lines),
            "insights": insights,
            "hist_notes": hist_notes,
            "heat_note": heat_side,
            "h2h": {
                "avg_corners": h2h_avg.get("avg_corners"),
                "avg_shots": h2h_avg.get("avg_shots"),
                "avg_sot": h2h_avg.get("avg_sot"),
                "meetings": h2h_avg.get("meetings"),
            }
            if h2h_avg
            else {},
        }

    props = [
        pack("corners", "Corners", [8.5, 9.5, 10.5, 11.5]),
        pack("shots", "Shots", [20.5, 22.5, 24.5, 26.5]),
        pack("shots_on_target", "Shots on Target", [7.5, 8.5, 9.5, 10.5]),
        pack("cards", "Cards", [3.5, 4.5, 5.5], has_fh=False),
    ]
    return [p for p in props if p.get("full")]


_BOOK_SIM_PCT: dict[str, str] = {
    "home_win": "home_win_pct",
    "draw": "draw_pct",
    "away_win": "away_win_pct",
    "dc_home_draw": "dc_1x_pct",
    "dc_home_away": "dc_12_pct",
    "dc_draw_away": "dc_x2_pct",
    "over_1_5": "over_1_5_pct",
    "under_1_5": "under_1_5_pct",
    "over_2_5": "over_2_5_pct",
    "under_2_5": "under_2_5_pct",
    "over_3_5": "over_3_5_pct",
    "under_3_5": "under_3_5_pct",
    "btts_yes": "btts_pct",
    "btts_no": "btts_no_pct",
    "home_o0_5": "home_o0_5_pct",
    "home_o1_5": "home_o1_5_pct",
    "home_o2_5": "home_o2_5_pct",
    "away_o0_5": "away_o0_5_pct",
    "away_o1_5": "away_o1_5_pct",
    "away_o2_5": "away_o2_5_pct",
}


def _build_book_odds_groups(book: dict[str, Any], perc: dict[str, Any]) -> list[dict[str, Any]]:
    groups = [
        (
            "Match result",
            [
                ("Home win", "home_win"),
                ("Draw", "draw"),
                ("Away win", "away_win"),
                ("DC Home/Draw", "dc_home_draw"),
                ("DC Home/Away", "dc_home_away"),
                ("DC Draw/Away", "dc_draw_away"),
            ],
        ),
        (
            "Goals",
            [
                ("Over 1.5", "over_1_5"),
                ("Under 1.5", "under_1_5"),
                ("Over 2.5", "over_2_5"),
                ("Under 2.5", "under_2_5"),
                ("Over 3.5", "over_3_5"),
                ("Under 3.5", "under_3_5"),
                ("BTTS Yes", "btts_yes"),
                ("BTTS No", "btts_no"),
            ],
        ),
        (
            "First half",
            [
                ("FH Home win", "fh_home_win"),
                ("FH Draw", "fh_draw"),
                ("FH Away win", "fh_away_win"),
                ("FH Over 0.5", "fh_over_0_5"),
                ("FH Under 0.5", "fh_under_0_5"),
                ("FH Over 1.5", "fh_over_1_5"),
                ("FH Under 1.5", "fh_under_1_5"),
            ],
        ),
        (
            "Team totals",
            [
                ("Home O0.5", "home_o0_5"),
                ("Home O1.5", "home_o1_5"),
                ("Home O2.5", "home_o2_5"),
                ("Away O0.5", "away_o0_5"),
                ("Away O1.5", "away_o1_5"),
                ("Away O2.5", "away_o2_5"),
            ],
        ),
    ]
    out: list[dict[str, Any]] = []
    for title, specs in groups:
        rows = []
        for label, key in specs:
            odds = book.get(key)
            if odds is None:
                continue
            imp = _implied_prob(odds)
            sim_key = _BOOK_SIM_PCT.get(key)
            sim = _num(perc.get(sim_key)) if sim_key else None
            sim_highlight = sim is not None and imp is not None and sim > imp
            rows.append(
                {
                    "market": label,
                    "odds": _fmt(odds, digits=2),
                    "implied": _fmt(imp, suffix="%"),
                    "simulated": _fmt(sim, suffix="%") if sim is not None else "—",
                    "sim_highlight": sim_highlight,
                }
            )
        if rows:
            out.append({"title": title, "rows": rows})
    return out


def _build_markets(
    home_name: str,
    away_name: str,
    perc: dict[str, Any],
    book: dict[str, Any],
) -> list[dict[str, Any]]:
    specs = [
        (f"{home_name} Win", perc.get("home_win_pct"), book.get("home_win")),
        ("Draw", perc.get("draw_pct"), book.get("draw")),
        (f"{away_name} Win", perc.get("away_win_pct"), book.get("away_win")),
        ("Over 1.5", perc.get("over_1_5_pct"), book.get("over_1_5")),
        ("Over 2.5", perc.get("over_2_5_pct"), book.get("over_2_5")),
        ("Over 3.5", perc.get("over_3_5_pct"), book.get("over_3_5")),
        ("Under 2.5", perc.get("under_2_5_pct"), book.get("under_2_5")),
        ("BTTS Yes", perc.get("btts_pct"), book.get("btts_yes")),
        (f"{home_name} O1.5", perc.get("home_o1_5_pct"), book.get("home_o1_5")),
        (f"{away_name} O1.5", perc.get("away_o1_5_pct"), book.get("away_o1_5")),
        ("DC 1X", perc.get("dc_1x_pct"), book.get("dc_home_draw")),
        ("DC X2", perc.get("dc_x2_pct"), book.get("dc_draw_away")),
    ]
    return [_market_row(label, sp, o) for label, sp, o in specs]


def _executive_summary(
    home_name: str,
    away_name: str,
    xg: dict[str, Any],
    perc: dict[str, Any],
    markets: list[dict[str, Any]],
    match: dict[str, Any],
    sim: dict[str, Any] | None = None,
) -> str:
    sim = sim or {}
    hx, ax, tx = _num(xg.get("home")), _num(xg.get("away")), _num(xg.get("total"))
    parts: list[str] = []
    if hx is not None and ax is not None:
        if hx > ax + 0.4:
            parts.append(
                f"{home_name} project significant attacking superiority with {hx:.2f} xG versus {away_name} {ax:.2f} xG."
            )
        elif ax > hx + 0.4:
            parts.append(
                f"{away_name} carry the offensive edge ({ax:.2f} xG vs {hx:.2f}) in model simulations."
            )
        else:
            parts.append(f"Balanced attacking projection ({hx:.2f}–{ax:.2f} xG) with {tx:.2f} combined xG.")

    value_rows = [m for m in markets if m.get("verdict") in ("STRONG VALUE", "VALUE")]
    if value_rows:
        names = ", ".join(m["market"] for m in value_rows[:3])
        parts.append(f"Simulations flag value on {names} with favorable book mispricing.")
    elif (_num(perc.get("over_2_5_pct")) or 0) >= 65:
        parts.append("Goal-heavy profile supports Over 2.5 and BTTS angles at elevated model confidence.")

    ct = _num((sim.get("corners") or {}).get("total"))
    st = _num((sim.get("shots") or {}).get("total"))
    cd = _num((sim.get("cards") or {}).get("total"))
    if ct is not None and st is not None:
        parts.append(
            f"Volume sims project {ct:.1f} corners, {st:.1f} shots"
            + (f", and {cd:.1f} cards" if cd is not None else "")
            + "."
        )

    sig = str(match.get("signal") or "medium").upper()
    parts.append(f"Composite signal tier: {sig} (score {match.get('score', '—')}).")
    return " ".join(parts)


def _historical_profiles(
    perc: dict[str, Any],
    xg: dict[str, Any],
    home_name: str,
    away_name: str,
    sim: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    sim = sim or {}
    profiles = [
        {
            "id": "o25_70",
            "label": "Over 2.5 model ≥70%",
            "hist_hit": 71.8,
            "qualifies": (_num(perc.get("over_2_5_pct")) or 0) >= 70,
        },
        {
            "id": "xg_35",
            "label": "Combined xG ≥3.5",
            "hist_hit": 64.8,
            "qualifies": (_num(xg.get("total")) or 0) >= 3.5,
        },
        {
            "id": "team_o15",
            "label": f"Team O1.5 ≥70% ({home_name} or {away_name})",
            "hist_hit": 63.4,
            "qualifies": (_num(perc.get("home_o1_5_pct")) or 0) >= 70
            or (_num(perc.get("away_o1_5_pct")) or 0) >= 70,
        },
        {
            "id": "o15_86",
            "label": "Over 1.5 model ≥80%",
            "hist_hit": 86.5,
            "qualifies": (_num(perc.get("over_1_5_pct")) or 0) >= 80,
        },
        {
            "id": "win_70",
            "label": "Side win model ≥70%",
            "hist_hit": 71.7,
            "qualifies": (_num(perc.get("home_win_pct")) or 0) >= 70
            or (_num(perc.get("away_win_pct")) or 0) >= 70,
        },
    ]
    corners_t = _num((sim.get("corners") or {}).get("total"))
    shots_t = _num((sim.get("shots") or {}).get("total"))
    if corners_t is not None:
        profiles.append(
            {
                "id": "corners_105",
                "label": "Projected corners ≥10.5",
                "hist_hit": 68.0,
                "qualifies": corners_t >= 10.5,
            }
        )
    if shots_t is not None:
        profiles.append(
            {
                "id": "shots_24",
                "label": "Projected shots ≥24.5",
                "hist_hit": 62.0,
                "qualifies": shots_t >= 24.5,
            }
        )
    return profiles


def _match_flow(perc: dict[str, Any], fh: dict[str, Any], xg: dict[str, Any]) -> list[dict[str, Any]]:
    fh_xg = fh.get("xg") or {}
    fh_total = _num(fh_xg.get("total"))
    ft_total = _num((xg or {}).get("total"))
    home_win = _num(perc.get("home_win_pct")) or 50
    btts = _num(perc.get("btts_pct")) or 50
    o25 = _num(perc.get("over_2_5_pct")) or 50

    fh_goal_est = min(95, max(5, (fh_total or 0.9) * 38)) if fh_total else None
    sh_goal_est = None
    if fh_goal_est is not None and ft_total:
        sh_goal_est = min(95, max(5, o25 * 0.55))

    return [
        {
            "label": "Home scores first (est.)",
            "value": round(home_win * 0.62 + 12, 1),
            "suffix": "%",
        },
        {
            "label": "Goal before halftime (est.)",
            "value": round(fh_goal_est, 1) if fh_goal_est else round(o25 * 0.72, 1),
            "suffix": "%",
        },
        {
            "label": "More goals 2nd half (est.)",
            "value": round(sh_goal_est, 1) if sh_goal_est else round(o25 * 0.58, 1),
            "suffix": "%",
        },
        {"label": "BTTS likelihood", "value": round(btts, 1), "suffix": "%"},
        {
            "label": "Match tempo",
            "value": "HIGH" if (ft_total or 0) >= 3.0 else ("LOW" if (ft_total or 0) < 2.2 else "MED"),
            "suffix": "",
        },
    ]


def _team_bars(sim: dict[str, Any], home_name: str, away_name: str) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for key, label in [
        ("xg", "Expected Goals"),
        ("shots", "Shots"),
        ("shots_on_target", "Shots on Target"),
        ("corners", "Corners"),
    ]:
        block = sim.get(key) or {}
        h, a = _num(block.get("home")), _num(block.get("away"))
        if h is None or a is None:
            continue
        total = h + a or 1
        bars.append(
            {
                "label": label,
                "home": h,
                "away": a,
                "home_pct": round(100 * h / total, 1),
                "away_pct": round(100 * a / total, 1),
                "home_name": home_name,
                "away_name": away_name,
            }
        )
    poss = sim.get("possession") or {}
    ph, pa = _num(poss.get("home")), _num(poss.get("away"))
    if ph is not None and pa is not None:
        bars.append(
            {
                "label": "Possession",
                "home": ph,
                "away": pa,
                "home_pct": ph,
                "away_pct": pa,
                "home_name": home_name,
                "away_name": away_name,
                "is_pct": True,
            }
        )
    return bars


def _radar_axes(sim: dict[str, Any], perc: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalized 0–100 radar spokes for SVG/JS."""
    axes: list[dict[str, Any]] = []

    def norm_pair(block: dict | None, scale: float = 1.0) -> tuple[float, float]:
        if not block:
            return 50.0, 50.0
        h, a = _num(block.get("home")), _num(block.get("away"))
        if h is None or a is None:
            return 50.0, 50.0
        t = (h + a) or 1
        return round(100 * h / t * scale, 1), round(100 * a / t * scale, 1)

    xg = sim.get("xg") or {}
    h_xg, a_xg = _num(xg.get("home")), _num(xg.get("away"))
    if h_xg is not None and a_xg is not None:
        mx = max(h_xg, a_xg, 0.1)
        axes.append({"axis": "Attack (xG)", "home": round(100 * h_xg / mx, 1), "away": round(100 * a_xg / mx, 1)})

    for key, title in [("shots", "Shots"), ("corners", "Corners")]:
        h, a = norm_pair(sim.get(key))
        axes.append({"axis": title, "home": h, "away": a})

    hw = _num(perc.get("home_win_pct")) or 50
    aw = _num(perc.get("away_win_pct")) or 50
    axes.append({"axis": "Win %", "home": hw, "away": aw})
    axes.append({"axis": "Over 2.5", "home": _num(perc.get("over_2_5_pct")) or 50, "away": _num(perc.get("over_2_5_pct")) or 50})
    return axes[:6]


def _risk_panel(
    match: dict[str, Any],
    perc: dict[str, Any],
    xg: dict[str, Any],
    markets: list[dict[str, Any]],
) -> dict[str, Any]:
    draw = _num(perc.get("draw_pct")) or 0
    total_xg = _num(xg.get("total")) or 0
    edges = [_num(m.get("edge")) for m in markets if _num(m.get("edge")) is not None]
    edge_spread = (max(edges) - min(edges)) if len(edges) >= 2 else 0

    volatility = min(100, round(draw * 1.2 + edge_spread * 2 + (8 if total_xg >= 3.5 else 0), 0))
    stability = max(0, min(100, round((_num(match.get("score")) or 50) - volatility * 0.35, 0)))

    warnings: list[str] = []
    if draw >= 28:
        warnings.append("Elevated draw probability — result market variance high")
    if total_xg >= 3.8 and not any(m.get("verdict") == "STRONG VALUE" for m in markets):
        warnings.append("High goal environment but limited priced edge — market may be adjusted")
    if (_num(match.get("score")) or 0) < 50:
        warnings.append("Low composite signal — reduce stake sizing")
    negative = [m for m in markets if (m.get("edge") or 0) <= -5]
    if negative:
        warnings.append(f"Trap risk on {negative[0]['market']} (negative model edge)")

    return {
        "volatility": volatility,
        "stability": stability,
        "consistency": round((stability + (100 - volatility)) / 2, 0),
        "warnings": warnings,
    }


def build_fixture_dashboard(
    raw: dict[str, Any],
    match: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extra = extra or {}
    home = raw.get("home") or {}
    away = raw.get("away") or {}
    league = raw.get("league") or {}
    sim = raw.get("sim_stats") or {}
    perc = sim.get("percents") or {}
    fh = sim.get("first_half") or {}
    xg = sim.get("xg") or {}
    book = raw.get("book_odds") or {}

    home_name = home.get("name") or "Home"
    away_name = away.get("name") or "Away"
    dt = _parse_dt(raw.get("date"))

    if match is None:
        goal_row = {
            "fixture_id": raw.get("fixture_id"),
            "home": home_name,
            "away": away_name,
            "fixture_date": raw.get("date"),
            "league_name": league.get("name"),
            "over_25_pct": perc.get("over_2_5_pct"),
            "btts_pct": perc.get("btts_pct"),
            "home_projected_goals": xg.get("home"),
            "away_projected_goals": xg.get("away"),
            "projected_total_goals": xg.get("total"),
            **book,
        }
        win_row = {
            "home": home_name,
            "away": away_name,
            "fixture_id": raw.get("fixture_id"),
            "home_win_pct": perc.get("home_win_pct"),
            "draw_pct": perc.get("draw_pct"),
            "away_win_pct": perc.get("away_win_pct"),
        }
        match = score_match(win_row, goal_row)

    picks = _build_picks(match)
    markets = _build_markets(home_name, away_name, perc, book)
    markets_sorted = sorted(
        markets,
        key=lambda m: (m.get("edge") is not None, abs(m.get("edge") or 0)),
        reverse=True,
    )

    top_edge = next((m for m in markets_sorted if (m.get("edge") or 0) > 0), markets_sorted[0] if markets_sorted else None)
    confidence_grade = grade_from_pct(_num(match.get("score")) or _num(perc.get("home_win_pct")))
    risk = risk_level(match, perc, xg)

    hx, ax, tx = _num(xg.get("home")), _num(xg.get("away")), _num(xg.get("total"))
    cs = extra.get("correct_score") or (
        build_correct_score_matrix(hx, ax) if hx and ax else None
    )
    scorelines = []
    for s in (cs or {}).get("top_scores") or []:
        pct = _num(s.get("pct")) or 0
        scorelines.append({**s, "bar_width": min(100, round(pct * 4, 1))})

    hero_kpis = [
        {
            "label": f"{home_name} Win",
            "value": _fmt(perc.get("home_win_pct"), suffix="%"),
            "grade": grade_from_pct(perc.get("home_win_pct")),
            "glow": (_num(perc.get("home_win_pct")) or 0) >= 65,
        },
        {
            "label": "Over 2.5",
            "value": _fmt(perc.get("over_2_5_pct"), suffix="%"),
            "grade": grade_from_pct(perc.get("over_2_5_pct")),
            "glow": (_num(perc.get("over_2_5_pct")) or 0) >= 70,
        },
        {
            "label": "BTTS",
            "value": _fmt(perc.get("btts_pct"), suffix="%"),
            "grade": grade_from_pct(perc.get("btts_pct")),
            "glow": (_num(perc.get("btts_pct")) or 0) >= 65,
        },
        {
            "label": "Total xG",
            "value": _fmt(tx, digits=2),
            "grade": grade_from_pct(min(99, (tx or 0) * 22)) if tx else "—",
            "glow": (tx or 0) >= 3.2,
        },
    ]

    recommended = [m for m in markets_sorted if m.get("verdict") in ("STRONG VALUE", "VALUE", "LEAN")][:6]
    if not recommended:
        recommended = sorted(markets, key=lambda m: _num(m.get("model_pct")) or 0, reverse=True)[:4]

    prop_analysis = _build_prop_analysis(
        home_name,
        away_name,
        sim,
        fh,
        extra,
        extra.get("home_trends"),
        extra.get("away_trends"),
    )
    book_odds_groups = _build_book_odds_groups(book, perc)
    profiles = _historical_profiles(perc, xg, home_name, away_name, sim)
    qualified = [p for p in profiles if p.get("qualifies")]

    top_players_home = []
    top_players_away = []
    if extra.get("home_player_sims"):
        top_players_home = sorted(
            extra["home_player_sims"],
            key=lambda p: _num(p.get("goals_per90_simulated")) or 0,
            reverse=True,
        )[:4]
    if extra.get("away_player_sims"):
        top_players_away = sorted(
            extra["away_player_sims"],
            key=lambda p: _num(p.get("goals_per90_simulated")) or 0,
            reverse=True,
        )[:4]

    h2h = extra.get("head2head") or {}
    versus = ((h2h.get("versus_grades") or {}).get("team_vs_team") or {}) if h2h else {}

    return {
        "fixture_id": raw.get("fixture_id"),
        "fixture": f"{home_name} vs {away_name}",
        "home_team": home_name,
        "away_team": away_name,
        "home_logo": raw.get("home_logo") or home.get("logo") or "",
        "away_logo": raw.get("away_logo") or away.get("logo") or "",
        "league_name": league.get("name") or "",
        "round": raw.get("round") or "",
        "kickoff": _fmt_kickoff(dt),
        "is_neutral": bool(raw.get("is_neutral")),
        "match": match,
        "picks": picks,
        "hero": {
            "signal": match.get("signal"),
            "signal_score": match.get("score"),
            "confidence_grade": confidence_grade,
            "risk_level": risk,
            "projected_scoreline": scorelines[0]["score"] if scorelines else "—",
            "projected_scoreline_pct": scorelines[0]["pct"] if scorelines else None,
            "main_edge_market": top_edge.get("market") if top_edge else None,
            "main_edge_fmt": top_edge.get("edge_fmt") if top_edge else None,
            "xg_home": hx,
            "xg_away": ax,
            "xg_total": tx,
            "kpis": hero_kpis,
            "recommended_labels": [p.get("label") for p in picks],
        },
        "executive_summary": _executive_summary(home_name, away_name, xg, perc, markets, match, sim),
        "prop_analysis": prop_analysis,
        "book_odds_groups": book_odds_groups,
        "recommended_bets": recommended,
        "all_markets": markets_sorted,
        "scorelines": scorelines,
        "score_matrix": cs,
        "match_flow": _match_flow(perc, fh, xg),
        "market_inefficiency": [m for m in markets_sorted if m.get("edge") is not None][:8],
        "risk": _risk_panel(match, perc, xg, markets),
        "historical_profiles": profiles,
        "historical_qualified_count": len(qualified),
        "team_comparison": {
            "bars": _team_bars(sim, home_name, away_name),
            "radar": _radar_axes(sim, perc),
        },
        "context": {
            "top_pick": extra.get("top_pick"),
            "h2h_meetings": len((h2h.get("h2h") or {}).get("raw_matches") or []) if h2h else 0,
            "versus_home": (versus.get("home_team") or {}).get("grade"),
            "versus_away": (versus.get("away_team") or {}).get("grade"),
            "top_players_home": [
                {"name": p.get("name"), "pos": p.get("position"), "g90": _fmt(p.get("goals_per90_simulated"), digits=2)}
                for p in top_players_home
            ],
            "top_players_away": [
                {"name": p.get("name"), "pos": p.get("position"), "g90": _fmt(p.get("goals_per90_simulated"), digits=2)}
                for p in top_players_away
            ],
        },
    }
