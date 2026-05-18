"""Fetch and index extra DataGaffer public JSON feeds (beyond fixtures.json)."""
from __future__ import annotations

import json
import math
from typing import Any
from urllib.request import urlopen

DG_BASE = "https://www.datagaffer.com"

FEED_PATHS = {
    "sim_cards": f"{DG_BASE}/sim_cards.json",
    "head2head": f"{DG_BASE}/head2head.json",
    "heat": f"{DG_BASE}/projected_heat_stats.json",
    "top_picks": f"{DG_BASE}/top_picks.json",
    "matchup_insights": f"{DG_BASE}/matchup_insights.json",
    "trends_last6": f"{DG_BASE}/trends_last6.json",
    "player_form": f"{DG_BASE}/player_form.json",
}


def _load_json(url: str) -> Any:
    with urlopen(url, timeout=30) as resp:
        return json.load(resp)


def _norm_team(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def _match_key(home: str, away: str) -> str:
    return f"{_norm_team(home)}|{_norm_team(away)}"


def _team_name(val: Any) -> str:
    if isinstance(val, dict):
        return str(val.get("name") or "").strip()
    return str(val or "").strip()


def fetch_player_sims_for_team(team_id: int | str) -> list[dict[str, Any]]:
    url = f"{DG_BASE}/player_simulations/{int(team_id)}.json"
    try:
        data = _load_json(url)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def build_correct_score_matrix(home_xg: float, away_xg: float, max_goals: int = 5) -> dict[str, Any]:
    """Independent Poisson score grid (same model as DataGaffer goal_zone helpers)."""
    rows: list[list[dict[str, Any]]] = []
    top: list[tuple[str, float]] = []
    for h in range(max_goals + 1):
        row: list[dict[str, Any]] = []
        ph = math.exp(-home_xg) * (home_xg**h) / math.factorial(h)
        for a in range(max_goals + 1):
            pa = math.exp(-away_xg) * (away_xg**a) / math.factorial(a)
            pct = round(ph * pa * 100, 2)
            row.append({"home": h, "away": a, "pct": pct})
            top.append((f"{h}-{a}", pct))
        rows.append(row)
    top.sort(key=lambda x: x[1], reverse=True)
    return {
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "max_goals": max_goals,
        "matrix": rows,
        "top_scores": [{"score": s, "pct": p} for s, p in top[:8]],
    }


def fetch_extra_feeds() -> dict[str, Any]:
    """Pull all supplemental feeds and build lookup indexes."""
    raw: dict[str, Any] = {}
    for key, url in FEED_PATHS.items():
        try:
            raw[key] = _load_json(url)
        except Exception:
            raw[key] = None

    sim_cards_by_match: dict[str, dict] = {}
    for card in raw.get("sim_cards") or []:
        if not isinstance(card, dict):
            continue
        mk = _match_key(card.get("home", ""), card.get("away", ""))
        sim_cards_by_match[mk] = card

    head2head_by_id: dict[str, dict] = {}
    for row in raw.get("head2head") or []:
        if isinstance(row, dict) and row.get("fixture_id") is not None:
            head2head_by_id[str(row["fixture_id"])] = row

    heat_by_id: dict[str, dict] = {}
    heat_payload = raw.get("heat") or {}
    for row in (heat_payload.get("matches") if isinstance(heat_payload, dict) else []) or []:
        if isinstance(row, dict) and row.get("fixture_id") is not None:
            heat_by_id[str(row["fixture_id"])] = row

    top_picks_by_id: dict[str, dict] = {}
    picks_payload = raw.get("top_picks") or {}
    if isinstance(picks_payload, dict):
        for bucket in ("today", "yesterday", "tomorrow", "day_after_tomorrow"):
            for pick in picks_payload.get(bucket) or []:
                if isinstance(pick, dict) and pick.get("fixture_id") is not None:
                    top_picks_by_id[str(pick["fixture_id"])] = pick

    insights_by_id: dict[str, dict] = {}
    insights_by_match: dict[str, dict] = {}
    for row in raw.get("matchup_insights") or []:
        if not isinstance(row, dict):
            continue
        match_label = str(row.get("match") or "")
        if " vs " in match_label:
            parts = match_label.split(" vs ", 1)
            insights_by_match[_match_key(parts[0], parts[1])] = row
        hid, aid = row.get("home_id"), row.get("away_id")
        if hid and aid:
            insights_by_id[f"{hid}:{aid}"] = row

    trends_by_team_id: dict[str, dict] = {}
    for row in raw.get("trends_last6") or []:
        if isinstance(row, dict) and row.get("team_id") is not None:
            trends_by_team_id[str(row["team_id"])] = row

    player_form = raw.get("player_form") if isinstance(raw.get("player_form"), dict) else {}

    return {
        "raw": raw,
        "sim_cards_by_match": sim_cards_by_match,
        "head2head_by_id": head2head_by_id,
        "heat_by_id": heat_by_id,
        "top_picks_by_id": top_picks_by_id,
        "insights_by_id": insights_by_id,
        "insights_by_match": insights_by_match,
        "trends_by_team_id": trends_by_team_id,
        "player_form": player_form,
        "heat_averages": (heat_payload.get("averages") if isinstance(heat_payload, dict) else None),
    }


def lookup_extra_for_fixture(
    raw_fixture: dict[str, Any],
    indexes: dict[str, Any],
    *,
    include_player_sims: bool = True,
) -> dict[str, Any]:
    """Resolve supplemental data for one fixture from pre-built indexes."""
    fid = str(raw_fixture.get("fixture_id") or "")
    home = _team_name(raw_fixture.get("home"))
    away = _team_name(raw_fixture.get("away"))
    mk = _match_key(home, away)
    home_id = raw_fixture.get("home_id")
    away_id = raw_fixture.get("away_id")

    sim = raw_fixture.get("sim_stats") or {}
    xg = sim.get("xg") or {}
    home_xg = float(xg.get("home") or 0)
    away_xg = float(xg.get("away") or 0)

    extra: dict[str, Any] = {
        "sim_card": indexes.get("sim_cards_by_match", {}).get(mk),
        "head2head": indexes.get("head2head_by_id", {}).get(fid),
        "heat": indexes.get("heat_by_id", {}).get(fid),
        "top_pick": indexes.get("top_picks_by_id", {}).get(fid),
        "matchup_insight": indexes.get("insights_by_match", {}).get(mk)
        or indexes.get("insights_by_id", {}).get(f"{home_id}:{away_id}"),
        "home_trends": indexes.get("trends_by_team_id", {}).get(str(home_id or "")),
        "away_trends": indexes.get("trends_by_team_id", {}).get(str(away_id or "")),
    }

    if home_xg > 0 and away_xg > 0:
        extra["correct_score"] = build_correct_score_matrix(home_xg, away_xg)

    if include_player_sims:
        if home_id:
            extra["home_player_sims"] = fetch_player_sims_for_team(home_id)
        if away_id:
            extra["away_player_sims"] = fetch_player_sims_for_team(away_id)

    return extra
