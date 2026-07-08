"""Pre-match feed for external trading bots (e.g. Polymarket). In-play data is out of scope."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.ev_bet_filters import is_actionable_plus_ev_market, resolve_kind_for_market
from app.fixture_detail import find_raw_fixture
from app.fixture_math import num
from app.plus_ev_strat import build_plus_ev_picks
from app.slate import _is_in_todays_slate_ist, _parse_dt

SCHEMA_VERSION = 1


def _team_name(team_val: Any) -> str:
    if isinstance(team_val, dict):
        return str(team_val.get("name") or "").strip()
    return str(team_val or "").strip()


def _volume_block(block: dict[str, Any] | None) -> dict[str, float | None] | None:
    if not block or not isinstance(block, dict):
        return None
    home = num(block.get("home"))
    away = num(block.get("away"))
    total = num(block.get("total"))
    if total is None and home is not None and away is not None:
        total = round(home + away, 2)
    if home is None and away is None and total is None:
        return None
    return {"home": home, "away": away, "total": total}


def _pct_block(perc: dict[str, Any], match: dict[str, Any] | None) -> dict[str, float | None]:
    m = match or {}
    return {
        "home_win": num(perc.get("home_win_pct")) if perc.get("home_win_pct") is not None else num(m.get("win_pct")),
        "draw": num(perc.get("draw_pct")) if perc.get("draw_pct") is not None else num(m.get("draw_pct")),
        "away_win": num(perc.get("away_win_pct")) if perc.get("away_win_pct") is not None else num(m.get("away_win_pct")),
        "over_1_5": num(perc.get("over_1_5_pct")) if perc.get("over_1_5_pct") is not None else num(m.get("over_1_5_pct")),
        "over_2_5": num(perc.get("over_2_5_pct")) if perc.get("over_2_5_pct") is not None else num(m.get("over_25_pct")),
        "over_3_5": num(perc.get("over_3_5_pct")) if perc.get("over_3_5_pct") is not None else num(m.get("over_3_5_pct")),
        "under_2_5": num(perc.get("under_2_5_pct")) if perc.get("under_2_5_pct") is not None else num(m.get("under_2_5_pct")),
        "under_3_5": num(perc.get("under_3_5_pct")) if perc.get("under_3_5_pct") is not None else num(m.get("under_3_5_pct")),
        "btts": num(perc.get("btts_pct")) if perc.get("btts_pct") is not None else num(m.get("btts_pct")),
        "home_o1_5": num(perc.get("home_o1_5_pct")),
        "away_o1_5": num(perc.get("away_o1_5_pct")),
        "dc_1x": num(perc.get("dc_1x_pct")),
        "dc_x2": num(perc.get("dc_x2_pct")),
    }


def _xg_block(xg: dict[str, Any], match: dict[str, Any] | None) -> dict[str, float | None]:
    m = match or {}
    home = num(xg.get("home")) if xg.get("home") is not None else num(m.get("home_projected_goals"))
    away = num(xg.get("away")) if xg.get("away") is not None else num(m.get("away_projected_goals"))
    total = num(xg.get("total")) if xg.get("total") is not None else num(m.get("projected_total_goals"))
    if total is None and home is not None and away is not None:
        total = round(home + away, 2)
    return {"home": home, "away": away, "total": total}


def _book_odds_block(book: dict[str, Any] | None) -> dict[str, float | None]:
    if not book:
        return {}
    keys = (
        "home_win",
        "draw",
        "away_win",
        "over_1_5",
        "over_2_5",
        "over_3_5",
        "under_2_5",
        "under_3_5",
        "btts_yes",
        "home_o0_5",
        "away_o0_5",
        "home_o1_5",
        "away_o1_5",
        "dc_home_draw",
        "dc_draw_away",
    )
    return {k: num(book.get(k)) for k in keys if book.get(k) is not None}


def _plus_ev_from_markets(
    markets: list[dict[str, Any]],
    *,
    home_name: str,
    away_name: str,
    xg: dict[str, Any],
    perc: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in markets:
        if not is_actionable_plus_ev_market(m, home_name=home_name, away_name=away_name, xg=xg, perc=perc):
            continue
        market = str(m.get("market") or "")
        bet_type, team_name = resolve_kind_for_market(market, home_name, away_name)
        out.append(
            {
                "market": market,
                "bet_type": bet_type,
                "team": team_name or None,
                "model_pct": num(m.get("model_pct")),
                "book_odds": num(m.get("book_odds")),
                "edge": num(m.get("edge")),
                "ev": num(m.get("ev")),
                "verdict": m.get("verdict"),
                "certainty": m.get("certainty_label"),
            }
        )
    return out


def _build_fixture_row(
    raw: dict[str, Any],
    match: dict[str, Any] | None,
    *,
    plus_ev_by_fixture: dict[str, list[dict[str, Any]]] | None = None,
    include_plus_ev: bool = True,
) -> dict[str, Any]:
    sim = raw.get("sim_stats") or {}
    perc = sim.get("percents") or {}
    xg_raw = sim.get("xg") or {}
    fh = sim.get("first_half") or {}
    book = raw.get("book_odds") or {}
    league = raw.get("league") or {}

    home_name = _team_name(raw.get("home"))
    away_name = _team_name(raw.get("away"))
    fid = raw.get("fixture_id")
    kickoff_raw = raw.get("date")

    xg = _xg_block(xg_raw, match)

    row: dict[str, Any] = {
        "fixture_id": fid,
        "fixture": f"{home_name} vs {away_name}",
        "home_team": home_name,
        "away_team": away_name,
        "home_team_id": raw.get("home_id"),
        "away_team_id": raw.get("away_id"),
        "league": league.get("name") or (match or {}).get("league_name") or "",
        "kickoff": kickoff_raw,
        "is_neutral": bool(raw.get("is_neutral")),
        "signal": (match or {}).get("signal"),
        "signal_score": num((match or {}).get("score")),
        "model": {
            "probabilities": _pct_block(perc, match),
            "xg": xg,
            "first_half_xg": _volume_block((fh.get("xg") or {})),
            "corners": _volume_block(sim.get("corners")),
            "shots": _volume_block(sim.get("shots")),
            "shots_on_target": _volume_block(sim.get("shots_on_target")),
            "cards": _volume_block(sim.get("cards")),
        },
        "book_odds": _book_odds_block(book),
    }

    if include_plus_ev and plus_ev_by_fixture is not None:
        row["plus_ev"] = plus_ev_by_fixture.get(str(fid), [])
    elif include_plus_ev:
        row["plus_ev"] = []

    return row


def build_prematch_feed(
    state: dict[str, Any],
    *,
    slate_only: bool = False,
    include_plus_ev: bool = True,
    fixture_id: int | str | None = None,
) -> dict[str, Any]:
    """
    Build a stable pre-match JSON payload for external bots.
    Does not include in-play data — bots should switch feeds after kickoff.
    """
    fixtures_by_id = state.get("fixtures_by_id") or {}
    matches_by_id = {
        str(m.get("fixture_id")): m for m in (state.get("matches") or []) if m.get("fixture_id")
    }

    plus_ev_by_fixture: dict[str, list[dict[str, Any]]] = {}
    if include_plus_ev:
        for pick in build_plus_ev_picks(state):
            fid = str(pick.get("fixture_id") or "")
            if not fid:
                continue
            plus_ev_by_fixture.setdefault(fid, []).append(
                {
                    "market": pick.get("market"),
                    "bet_type": pick.get("bet_type"),
                    "team": pick.get("team_name") or None,
                    "model_pct": None,
                    "book_odds": num(pick.get("odds")),
                    "edge": num(pick.get("edge")),
                    "ev": num(pick.get("ev")),
                    "verdict": pick.get("verdict"),
                    "certainty": pick.get("certainty_label"),
                }
            )

    fixtures: list[dict[str, Any]] = []
    target = str(fixture_id) if fixture_id is not None else None

    for fid_key, raw in fixtures_by_id.items():
        if target and str(raw.get("fixture_id")) != target and fid_key != target:
            continue

        kickoff_dt = _parse_dt(raw.get("date"))
        if slate_only and not _is_in_todays_slate_ist(kickoff_dt):
            continue

        match = matches_by_id.get(str(raw.get("fixture_id")))
        fixtures.append(
            _build_fixture_row(
                raw,
                match,
                plus_ev_by_fixture=plus_ev_by_fixture if include_plus_ev else None,
                include_plus_ev=include_plus_ev,
            )
        )

    fixtures.sort(key=lambda f: (f.get("kickoff") or "", f.get("fixture_id") or 0))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "prematch",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scraped_at": state.get("scraped_at"),
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "notes": {
            "prematch_only": True,
            "in_play": "Not provided — fetch live data from your bot's in-play source after kickoff.",
            "slate_filter": slate_only,
            "plus_ev_included": include_plus_ev,
        },
    }


def get_prematch_fixture(state: dict[str, Any], fixture_id: int | str) -> dict[str, Any] | None:
    """Single-fixture pre-match payload."""
    feed = build_prematch_feed(state, fixture_id=fixture_id, include_plus_ev=True)
    items = feed.get("fixtures") or []
    return items[0] if items else None
