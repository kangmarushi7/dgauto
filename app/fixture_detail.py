from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.dg_feeds import lookup_extra_for_fixture
from app.signals import score_match
from app.slate import _build_picks, _fmt_kickoff, _parse_dt

IST = ZoneInfo("Asia/Kolkata")

# Tools with no public feed (parlay is built interactively on DataGaffer).
UNAVAILABLE_FEATURES = [
    "Parlay Builder (interactive - use Top Edges / Value Finder here)",
]


def _num(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fmt(val: Any, suffix: str = "", digits: int = 1) -> str:
    n = _num(val)
    if n is None:
        return "—"
    if suffix == "%":
        return f"{n:.{digits}f}%"
    return f"{n:.{digits}f}{suffix}"


def _implied_prob(odds: Any) -> float | None:
    o = _num(odds)
    if o is None or o <= 1:
        return None
    return round(100.0 / o, 1)


def _edge(sim_pct: Any, odds: Any) -> float | None:
    s = _num(sim_pct)
    imp = _implied_prob(odds)
    if s is None or imp is None:
        return None
    return round(s - imp, 1)


def _split_block(title: str, data: dict | None) -> dict[str, Any]:
    data = data or {}
    return {
        "type": "split",
        "title": title,
        "rows": [
            {"label": "Home", "value": _fmt(data.get("home"), digits=2)},
            {"label": "Away", "value": _fmt(data.get("away"), digits=2)},
            {"label": "Total", "value": _fmt(data.get("total"), digits=2)},
        ],
    }


def _kv_table(title: str, items: list[tuple[str, Any]], *, suffix: str = "%") -> dict[str, Any]:
    return {
        "type": "kv",
        "title": title,
        "rows": [{"label": label, "value": _fmt(val, suffix=suffix)} for label, val in items],
    }


def _odds_table(title: str, items: list[tuple[str, Any]]) -> dict[str, Any]:
    return {
        "type": "odds",
        "title": title,
        "rows": [
            {
                "market": label,
                "odds": _fmt(o, digits=2) if _num(o) is not None else "—",
                "implied": _fmt(_implied_prob(o), suffix="%", digits=1),
            }
            for label, o in items
        ],
    }


def _edge_table(title: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "edges", "title": title, "rows": rows}


def _comparison_block(title: str, metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "compare", "title": title, "metrics": metrics}


def _synthesize_sim_card(raw: dict[str, Any]) -> dict[str, Any]:
    """Build sim-card style rows from fixtures.json when sim_cards.json has no row."""
    perc = (raw.get("sim_stats") or {}).get("percents") or {}
    book = raw.get("book_odds") or {}
    home = raw.get("home") or {}
    away = raw.get("away") or {}
    xg = (raw.get("sim_stats") or {}).get("xg") or {}

    def _cell(sim_pct: Any, odds_key: str) -> dict[str, Any]:
        sp = _num(sim_pct)
        sim_str = f"{sp:.1f}%" if sp is not None else "—"
        if sp is not None and sp > 0:
            sim_str += f" ({100 / sp:.2f})"
        return {"sim": sim_str, "book": book.get(odds_key)}

    return {
        "projected_score": f"{_fmt(xg.get('home'), digits=2)} vs {_fmt(xg.get('away'), digits=2)} xG",
        "win": _cell(perc.get("home_win_pct"), "home_win"),
        "draw": _cell(perc.get("draw_pct"), "draw"),
        "away_win": _cell(perc.get("away_win_pct"), "away_win"),
        "home_o1_5": _cell(perc.get("home_o1_5_pct"), "home_o1_5"),
        "away_o1_5": _cell(perc.get("away_o1_5_pct"), "away_o1_5"),
        "over_2_5": _cell(perc.get("over_2_5_pct"), "over_2_5"),
        "btts": _cell(perc.get("btts_pct"), "btts_yes"),
        "_synthetic": True,
    }


def _sim_market_rows(card: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, label in [
        ("win", "Home win"),
        ("draw", "Draw"),
        ("away_win", "Away win"),
        ("home_o1_5", "Home O1.5"),
        ("away_o1_5", "Away O1.5"),
        ("over_2_5", "Over 2.5"),
        ("btts", "BTTS"),
    ]:
        m = card.get(key) or {}
        sim = m.get("sim") if isinstance(m, dict) else m
        book = m.get("book") if isinstance(m, dict) else None
        rows.append(
            {
                "market": label,
                "sim": str(sim) if sim is not None else "—",
                "book": _fmt(book, digits=2) if _num(book) is not None else "—",
            }
        )
    return rows


def _h2h_summary(h2h: dict[str, Any]) -> list[tuple[str, Any]]:
    core = h2h.get("h2h") or {}
    agg = core.get("aggregate") or core.get("summary") or {}
    if agg:
        return [
            ("Meetings", agg.get("played") or agg.get("matches")),
            ("Home wins", agg.get("home_wins") or agg.get("team_wins")),
            ("Draws", agg.get("draws")),
            ("Away wins", agg.get("away_wins") or agg.get("opp_wins")),
            ("Avg goals", agg.get("avg_goals") or agg.get("avg_total_goals")),
        ]
    raw_matches = core.get("raw_matches") or []
    return [("Recent meetings", len(raw_matches))]


def _heat_stat_rows(side: dict[str, Any]) -> list[tuple[str, Any]]:
    labels = [
        ("possession", "Possession %"),
        ("expected_goals", "xG"),
        ("shots", "Shots"),
        ("shots_on_target", "Shots on target"),
        ("dangerous_attacks", "Dangerous attacks"),
        ("passes", "Passes"),
        ("big_chances_created", "Big chances"),
    ]
    return [(label, side.get(key)) for key, label in labels if side.get(key) is not None]


def _top_players(players: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    ranked = sorted(
        players,
        key=lambda p: (
            _num(p.get("goals_per90_simulated")) or 0,
            _num(p.get("shots_per90")) or 0,
        ),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for p in ranked[:limit]:
        out.append(
            {
                "name": p.get("name"),
                "position": p.get("position"),
                "goals90": _fmt(p.get("goals_per90_simulated"), digits=2),
                "shots90": _fmt(p.get("shots_per90"), digits=2),
                "sot90": _fmt(p.get("sot_per90"), digits=2),
            }
        )
    return out


def _trends_rows(trends: dict[str, Any] | None) -> list[tuple[str, Any]]:
    if not trends:
        return []
    last6 = trends.get("last6") or {}
    return [
        ("Form (L6)", last6.get("form")),
        ("Record L6", f"{last6.get('wins', 0)}-{last6.get('draws', 0)}-{last6.get('losses', 0)}"),
        ("GF / GA L6", f"{last6.get('avg_goals_for')} / {last6.get('avg_goals_against')}"),
        ("BTTS L6", (last6.get("btts_yes") or {}).get("percent")),
        ("Over 2.5 L6", (last6.get("over_2_5") or {}).get("percent")),
    ]


def _sections_from_extra(
    extra: dict[str, Any],
    *,
    home_name: str,
    away_name: str,
    raw: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []

    card = extra.get("sim_card") or (_synthesize_sim_card(raw) if raw else None)
    if card:
        title = "Sim Cards"
        if card.get("_synthetic"):
            title = "Sim Cards (from fixture feed)"
        sections.append(
            {
                "key": "sim_cards",
                "category": "Match Simulations",
                "title": title,
                "blocks": [
                    {
                        "type": "sim_card",
                        "title": card.get("projected_score") or "Projected score",
                        "rows": _sim_market_rows(card),
                    }
                ],
            }
        )

    h2h = extra.get("head2head")
    if h2h:
        grades = (h2h.get("versus_grades") or {}).get("team_vs_team") or {}
        grade_rows: list[tuple[str, Any]] = []
        for side, label in (("home_team", home_name), ("away_team", away_name)):
            g = grades.get(side) or {}
            if g:
                grade_rows.append((label, f"{g.get('grade')} ({g.get('score')})"))
        blocks: list[dict[str, Any]] = [
            _kv_table("Head-to-head summary", _h2h_summary(h2h), suffix=""),
        ]
        if grade_rows:
            blocks.append(_kv_table("Versus grades", grade_rows, suffix=""))
        sections.append(
            {
                "key": "head2head",
                "category": "Research Tools",
                "title": "Head2Head",
                "blocks": blocks,
            }
        )

    heat = extra.get("heat")
    if heat:
        proj = heat.get("projected_stats") or {}
        sections.append(
            {
                "key": "heat_maps",
                "category": "Research Tools",
                "title": "Heat Maps (projected stats)",
                "blocks": [
                    _kv_table(f"{home_name} projection", _heat_stat_rows(proj.get("home") or {}), suffix=""),
                    _kv_table(f"{away_name} projection", _heat_stat_rows(proj.get("away") or {}), suffix=""),
                ],
            }
        )

    cs = extra.get("correct_score")
    if cs:
        sections.append(
            {
                "key": "correct_score",
                "category": "Simulation Tools",
                "title": "Correct Score matrix",
                "blocks": [{"type": "score_matrix", "title": "Poisson score grid (from sim xG)", **cs}],
            }
        )

    home_players = extra.get("home_player_sims") or []
    away_players = extra.get("away_player_sims") or []
    if home_players or away_players:
        sections.append(
            {
                "key": "player_sims",
                "category": "Match Simulations",
                "title": "Player Sims",
                "blocks": [
                    {"type": "players", "title": home_name, "players": _top_players(home_players)},
                    {"type": "players", "title": away_name, "players": _top_players(away_players)},
                ],
            }
        )

    insight_blocks: list[dict[str, Any]] = []
    top_pick = extra.get("top_pick")
    if top_pick:
        insight_blocks.append(
            {
                "type": "insight",
                "title": "DataGaffer Top Edge",
                "lines": [
                    f"{top_pick.get('pick')} · Sim {top_pick.get('sim_pct')}% · Book {_fmt(top_pick.get('book_odds'), digits=2)} · Edge +{top_pick.get('edge')}%",
                    str(top_pick.get("explanation") or ""),
                ],
            }
        )
    matchup = extra.get("matchup_insight")
    if matchup:
        for tag, label in [
            ("home_analysis", home_name),
            ("away_analysis", away_name),
        ]:
            analysis = matchup.get(tag) or {}
            if not analysis:
                continue
            rows = []
            for bucket, stats in analysis.items():
                if isinstance(stats, dict):
                    rows.append(
                        (
                            bucket.replace("_", " ").title(),
                            f"O2.5 {stats.get('over_2_5_pct')}% · BTTS {stats.get('btts_pct')}% · GF {stats.get('goals_for')}",
                        )
                    )
            if rows:
                insight_blocks.append(_kv_table(f"{label} situational splits", rows, suffix=""))
    home_tr = extra.get("home_trends")
    away_tr = extra.get("away_trends")
    if home_tr:
        insight_blocks.append(_kv_table(f"{home_name} last-6", _trends_rows(home_tr), suffix=""))
    if away_tr:
        insight_blocks.append(_kv_table(f"{away_name} last-6", _trends_rows(away_tr), suffix=""))
    if insight_blocks:
        sections.append(
            {
                "key": "dg_insights",
                "category": "Betting Tools",
                "title": "DataGaffer Insights",
                "blocks": insight_blocks,
            }
        )

    return sections


def build_fixture_detail(
    raw: dict[str, Any],
    match: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full fixture analysis from DataGaffer fixtures.json (all public fields)."""
    home = raw.get("home") or {}
    away = raw.get("away") or {}
    league = raw.get("league") or {}
    sim = raw.get("sim_stats") or {}
    perc = sim.get("percents") or {}
    fh = sim.get("first_half") or {}
    book = raw.get("book_odds") or {}

    home_name = home.get("name") or raw.get("home_id") or "Home"
    away_name = away.get("name") or raw.get("away_id") or "Away"
    fixture_label = f"{home_name} vs {away_name}"
    dt = _parse_dt(raw.get("date"))

    if match is None:
        goal_row = {
            "fixture_id": raw.get("fixture_id"),
            "home": home_name,
            "away": away_name,
            "fixture_date": raw.get("date"),
            "league_name": league.get("name"),
            "over_1_5_pct": perc.get("over_1_5_pct"),
            "over_25_pct": perc.get("over_2_5_pct"),
            "over_3_5_pct": perc.get("over_3_5_pct"),
            "btts_pct": perc.get("btts_pct"),
            "home_projected_goals": (sim.get("xg") or {}).get("home"),
            "away_projected_goals": (sim.get("xg") or {}).get("away"),
            "projected_total_goals": (sim.get("xg") or {}).get("total"),
            **{k: v for k, v in book.items()},
        }
        win_row = {
            "home": home_name,
            "away": away_name,
            "fixture_id": raw.get("fixture_id"),
            "home_win_pct": perc.get("home_win_pct"),
            "draw_pct": perc.get("draw_pct"),
            "away_win_pct": perc.get("away_win_pct"),
            "home_logo": raw.get("home_logo") or home.get("logo"),
            "away_logo": raw.get("away_logo") or away.get("logo"),
        }
        match = score_match(win_row, goal_row)

    picks = _build_picks(match)

    edges: list[dict[str, Any]] = []
    edge_specs = [
        ("Home win", perc.get("home_win_pct"), book.get("home_win")),
        ("Draw", perc.get("draw_pct"), book.get("draw")),
        ("Away win", perc.get("away_win_pct"), book.get("away_win")),
        ("Over 2.5", perc.get("over_2_5_pct"), book.get("over_2_5")),
        ("BTTS Yes", perc.get("btts_pct"), book.get("btts_yes")),
        ("Home O1.5", perc.get("home_o1_5_pct"), book.get("home_o1_5")),
        ("Away O1.5", perc.get("away_o1_5_pct"), book.get("away_o1_5")),
        ("DC 1X", perc.get("dc_1x_pct"), book.get("dc_home_draw")),
        ("DC X2", perc.get("dc_x2_pct"), book.get("dc_draw_away")),
    ]
    for label, sim_p, odds in edge_specs:
        e = _edge(sim_p, odds)
        if e is not None and abs(e) >= 3:
            edges.append(
                {
                    "market": label,
                    "sim": _fmt(sim_p, suffix="%"),
                    "odds": _fmt(odds, digits=2),
                    "implied": _fmt(_implied_prob(odds), suffix="%"),
                    "edge": f"{e:+.1f}%",
                    "edge_val": e,
                }
            )
    edges.sort(key=lambda x: abs(x.get("edge_val") or 0), reverse=True)

    compare_metrics = []
    for label, key in [
        ("xG", "xg"),
        ("Corners", "corners"),
        ("Shots", "shots"),
        ("Shots on target", "shots_on_target"),
    ]:
        block = sim.get(key) or {}
        h, a = _num(block.get("home")), _num(block.get("away"))
        if h is not None and a is not None and (h + a) > 0:
            compare_metrics.append(
                {
                    "label": label,
                    "home": h,
                    "away": a,
                    "home_pct": round(100 * h / (h + a), 1),
                    "away_pct": round(100 * a / (h + a), 1),
                }
            )

    extra_sections = _sections_from_extra(
        extra or {}, home_name=home_name, away_name=away_name, raw=raw
    )

    sections: list[dict[str, Any]] = [
        {
            "key": "outlooks",
            "category": "Match Simulations",
            "title": "Outlooks (Win probability)",
            "blocks": [
                _kv_table(
                    "Full-time result",
                    [
                        (home_name, perc.get("home_win_pct")),
                        ("Draw", perc.get("draw_pct")),
                        (away_name, perc.get("away_win_pct")),
                    ],
                ),
                _kv_table(
                    "Double chance",
                    [
                        ("1X (Home or Draw)", perc.get("dc_1x_pct")),
                        ("12 (Home or Away)", perc.get("dc_12_pct")),
                        ("X2 (Draw or Away)", perc.get("dc_x2_pct")),
                    ],
                ),
            ],
        },
        {
            "key": "full_time",
            "category": "Match Simulations",
            "title": "Full Time",
            "blocks": [
                _split_block("Expected goals (xG)", sim.get("xg")),
                _split_block("Corners", sim.get("corners")),
                _split_block("Shots", sim.get("shots")),
                _split_block("Shots on target", sim.get("shots_on_target")),
                _split_block("Cards", sim.get("cards")),
                _kv_table(
                    "Possession",
                    [
                        (home_name, (sim.get("possession") or {}).get("home")),
                        (away_name, (sim.get("possession") or {}).get("away")),
                    ],
                    suffix="%",
                ),
            ],
        },
        {
            "key": "first_half",
            "category": "Match Simulations",
            "title": "First Half",
            "blocks": [
                _split_block("First-half xG", fh.get("xg")),
                _split_block("First-half corners", fh.get("corners")),
                _split_block("First-half shots", fh.get("shots")),
                _split_block("First-half shots on target", fh.get("shots_on_target")),
                _odds_table(
                    "First-half book odds",
                    [
                        ("FH Home win", book.get("fh_home_win")),
                        ("FH Draw", book.get("fh_draw")),
                        ("FH Away win", book.get("fh_away_win")),
                        ("FH Over 0.5", book.get("fh_over_0_5")),
                        ("FH Under 0.5", book.get("fh_under_0_5")),
                        ("FH Over 1.5", book.get("fh_over_1_5")),
                        ("FH Under 1.5", book.get("fh_under_1_5")),
                    ],
                ),
            ],
        },
        {
            "key": "goal_zone",
            "category": "Match Simulations",
            "title": "Goal Zone",
            "blocks": [
                _split_block("Projected goals (xG)", sim.get("xg")),
                _kv_table(
                    "Goal markets (sim %)",
                    [
                        ("Over 1.5", perc.get("over_1_5_pct")),
                        ("Under 1.5", perc.get("under_1_5_pct")),
                        ("Over 2.5", perc.get("over_2_5_pct")),
                        ("Under 2.5", perc.get("under_2_5_pct")),
                        ("Over 3.5", perc.get("over_3_5_pct")),
                        ("Under 3.5", perc.get("under_3_5_pct")),
                        ("BTTS Yes", perc.get("btts_pct")),
                        ("BTTS No", perc.get("btts_no_pct")),
                        ("O2.5 + BTTS", perc.get("over_2_5_and_btts_yes_pct")),
                    ],
                ),
                _kv_table(
                    "Team goals (sim %)",
                    [
                        (f"{home_name} O0.5", perc.get("home_o0_5_pct")),
                        (f"{home_name} O1.5", perc.get("home_o1_5_pct")),
                        (f"{home_name} O2.5", perc.get("home_o2_5_pct")),
                        (f"{away_name} O0.5", perc.get("away_o0_5_pct")),
                        (f"{away_name} O1.5", perc.get("away_o1_5_pct")),
                        (f"{away_name} O2.5", perc.get("away_o2_5_pct")),
                    ],
                ),
            ],
        },
        {
            "key": "corners",
            "category": "Match Simulations",
            "title": "Corners",
            "blocks": [
                _split_block("Full match", sim.get("corners")),
                _split_block("First half", fh.get("corners")),
            ],
        },
        {
            "key": "shots",
            "category": "Match Simulations",
            "title": "Shots",
            "blocks": [
                _split_block("Shots", sim.get("shots")),
                _split_block("Shots on target", sim.get("shots_on_target")),
                _split_block("First-half shots", fh.get("shots")),
            ],
        },
        {
            "key": "dg_rating",
            "category": "Match Simulations",
            "title": "DG Rating & Index",
            "blocks": [
                _kv_table(
                    "Composite",
                    [
                        ("Matchup score", match.get("score")),
                        ("Signal tier", match.get("signal")),
                    ],
                    suffix="",
                ),
                _comparison_block("Team matchup balance", compare_metrics),
            ],
        },
        {
            "key": "probability",
            "category": "Simulation Tools",
            "title": "Probability",
            "blocks": [
                _kv_table(
                    "All simulated probabilities",
                    sorted(
                        [(k.replace("_pct", "").replace("_", " ").title(), v) for k, v in perc.items()],
                        key=lambda x: _num(x[1]) or 0,
                        reverse=True,
                    ),
                ),
            ],
        },
        {
            "key": "xg_performance",
            "category": "Simulation Tools",
            "title": "xG Performance",
            "blocks": [
                _split_block("Full match xG", sim.get("xg")),
                _split_block("First half xG", fh.get("xg")),
            ],
        },
        {
            "key": "matchup_score",
            "category": "Simulation Tools",
            "title": "Matchup Score",
            "blocks": [
                _comparison_block("Statistical duel", compare_metrics),
                _kv_table(
                    "Win outlook",
                    [
                        (home_name, perc.get("home_win_pct")),
                        (away_name, perc.get("away_win_pct")),
                    ],
                ),
            ],
        },
        {
            "key": "book_odds",
            "category": "Betting Tools",
            "title": "Book odds (full market)",
            "blocks": [
                _odds_table(
                    "Match result",
                    [
                        ("Home win", book.get("home_win")),
                        ("Draw", book.get("draw")),
                        ("Away win", book.get("away_win")),
                        ("DC Home/Draw", book.get("dc_home_draw")),
                        ("DC Home/Away", book.get("dc_home_away")),
                        ("DC Draw/Away", book.get("dc_draw_away")),
                    ],
                ),
                _odds_table(
                    "Goals",
                    [
                        ("Over 1.5", book.get("over_1_5")),
                        ("Under 1.5", book.get("under_1_5")),
                        ("Over 2.5", book.get("over_2_5")),
                        ("Under 2.5", book.get("under_2_5")),
                        ("Over 3.5", book.get("over_3_5")),
                        ("Under 3.5", book.get("under_3_5")),
                        ("BTTS Yes", book.get("btts_yes")),
                        ("BTTS No", book.get("btts_no")),
                    ],
                ),
                _odds_table(
                    "Team totals",
                    [
                        ("Home O0.5", book.get("home_o0_5")),
                        ("Home O1.5", book.get("home_o1_5")),
                        ("Home O2.5", book.get("home_o2_5")),
                        ("Away O0.5", book.get("away_o0_5")),
                        ("Away O1.5", book.get("away_o1_5")),
                        ("Away O2.5", book.get("away_o2_5")),
                    ],
                ),
            ],
        },
        {
            "key": "value_finder",
            "category": "Betting Tools",
            "title": "Value Finder / Top Edges",
            "blocks": [
                _edge_table(
                    "Sim vs book implied probability (edge ≥ 3%)",
                    edges if edges else [{"market": "—", "sim": "", "odds": "", "implied": "", "edge": "No strong edges"}],
                ),
            ],
        },
        {
            "key": "insights",
            "category": "Betting Tools",
            "title": "Insights",
            "blocks": [
                {
                    "type": "picks",
                    "title": "Recommended angles (app rules)",
                    "picks": picks,
                },
            ],
        },
    ]

    # Insert DataGaffer supplemental sections after core simulation blocks.
    insert_at = next((i for i, s in enumerate(sections) if s["key"] == "book_odds"), len(sections))
    sections[insert_at:insert_at] = extra_sections

    unavailable = list(UNAVAILABLE_FEATURES)
    if not extra_sections:
        unavailable = [
            "Sim Cards",
            "Player Sims",
            "Head2Head",
            "Heat Maps",
            "Correct Score matrix",
            *UNAVAILABLE_FEATURES,
        ]

    return {
        "fixture_id": raw.get("fixture_id"),
        "fixture": fixture_label,
        "home_team": home_name,
        "away_team": away_name,
        "home_logo": raw.get("home_logo") or home.get("logo") or "",
        "away_logo": raw.get("away_logo") or away.get("logo") or "",
        "league_name": league.get("name") or "",
        "round": raw.get("round") or "",
        "fixture_date": raw.get("date"),
        "kickoff": _fmt_kickoff(dt),
        "is_neutral": bool(raw.get("is_neutral")),
        "match": match,
        "picks": picks,
        "sections": sections,
        "unavailable": unavailable,
        "extra_sources": {
            k: bool(extra.get(k))
            for k in (
                "sim_card",
                "head2head",
                "heat",
                "correct_score",
                "home_player_sims",
                "away_player_sims",
                "top_pick",
                "matchup_insight",
            )
        }
        if extra
        else {},
        "two_leg_ctx": raw.get("two_leg_ctx"),
    }


def find_raw_fixture(fixtures_by_id: dict[str, Any], fixture_id: str | int) -> dict[str, Any] | None:
    key = str(fixture_id)
    if key in fixtures_by_id:
        return fixtures_by_id[key]
    try:
        return fixtures_by_id.get(str(int(fixture_id)))
    except (TypeError, ValueError):
        return None


def get_fixture_detail_from_state(state: dict[str, Any], fixture_id: str | int) -> dict[str, Any] | None:
    fixtures_by_id = state.get("fixtures_by_id") or {}
    raw = find_raw_fixture(fixtures_by_id, fixture_id)
    if not raw:
        return None
    match = None
    for m in state.get("matches") or []:
        if str(m.get("fixture_id")) == str(fixture_id):
            match = m
            break
    indexes = state.get("dg_extra_indexes") or {}
    extra = lookup_extra_for_fixture(raw, indexes) if indexes else {}
    return build_fixture_detail(raw, match, extra=extra)
