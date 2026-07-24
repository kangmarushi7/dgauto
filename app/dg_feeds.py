"""Fetch and index DataGaffer JSON feeds (beyond fixtures.json)."""
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
    "correct_score_charts": f"{DG_BASE}/correct_score_match_charts.json",
    "dg_ratings": f"{DG_BASE}/dg_ratings.json",
    "all_odds": f"{DG_BASE}/all_odds.json",
    "highlighted_matchups": f"{DG_BASE}/highlighted_matchups.json",
    "form_trends": f"{DG_BASE}/form_trends.json",
    "xg_stats": f"{DG_BASE}/xg_stats.json",
    "xg_regression": f"{DG_BASE}/xg_regression_last6.json",
    "pace_accuracy": f"{DG_BASE}/pace_accuracy_summary.json",
    "rankings": f"{DG_BASE}/rankings/rankings.json",
    "team_stats": f"{DG_BASE}/team_stats_2026/all_teams.json",
    "team_betting_lookup": f"{DG_BASE}/team_betting_lookup_2026.json",
    "manager_h2h": f"{DG_BASE}/todays_manager_vs_manager.json",
    "referee_stats": f"{DG_BASE}/referee_stats.json",
}


def _load_json(url: str) -> Any:
    with urlopen(url, timeout=45) as resp:
        return json.load(resp)


def _norm_team(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def _match_key(home: str, away: str) -> str:
    return f"{_norm_team(home)}|{_norm_team(away)}"


def _team_name(val: Any) -> str:
    if isinstance(val, dict):
        return str(val.get("name") or "").strip()
    return str(val or "").strip()


def _num(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def fetch_player_sims_for_team(team_id: int | str) -> list[dict[str, Any]]:
    url = f"{DG_BASE}/player_simulations/{int(team_id)}.json"
    try:
        data = _load_json(url)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def _dixon_coles_tau(h: int, a: int, home_xg: float, away_xg: float, rho: float = -0.10) -> float:
    """Dixon–Coles low-score adjustment (matches DataGaffer /scoreline)."""
    total = home_xg + away_xg
    adjusted_rho = rho * 0.4 if total > 3.2 else rho

    if h == 0 and a == 0:
        multiplier = 1 - (home_xg * away_xg * adjusted_rho)
        if 1.6 <= total <= 2.4:
            multiplier *= 0.97
        return multiplier
    if h == 0 and a == 1:
        return 1 + (home_xg * adjusted_rho)
    if h == 1 and a == 0:
        return 1 + (away_xg * adjusted_rho)
    if h == 1 and a == 1:
        return (1 - adjusted_rho) * 0.90 if total > 3.5 else (1 - adjusted_rho)
    return 1.0


def build_correct_score_matrix(
    home_xg: float,
    away_xg: float,
    max_goals: int = 5,
    *,
    dixon_coles: bool = True,
) -> dict[str, Any]:
    """Poisson score grid; Dixon–Coles on by default (DataGaffer scoreline parity)."""
    cells: list[tuple[int, int, float]] = []
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson_pmf(h, home_xg) * _poisson_pmf(a, away_xg)
            if dixon_coles:
                p *= _dixon_coles_tau(h, a, home_xg, away_xg)
            cells.append((h, a, p))

    total_p = sum(p for _, _, p in cells) or 1.0
    rows: list[list[dict[str, Any]]] = []
    top: list[tuple[str, float]] = []
    for h in range(max_goals + 1):
        row: list[dict[str, Any]] = []
        for a in range(max_goals + 1):
            raw_p = next(p for hh, aa, p in cells if hh == h and aa == a)
            pct = round((raw_p / total_p) * 100, 2)
            row.append({"home": h, "away": a, "pct": pct})
            top.append((f"{h}-{a}", pct))
        rows.append(row)
    top.sort(key=lambda x: x[1], reverse=True)
    return {
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "max_goals": max_goals,
        "model": "dixon_coles" if dixon_coles else "independent_poisson",
        "matrix": rows,
        "top_scores": [{"score": s, "pct": p} for s, p in top[:8]],
    }


def _slim_rating(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "team": row.get("team"),
        "team_id": row.get("team_id"),
        "league_id": row.get("league_id"),
        "DGRtg": _num(row.get("DGRtg")),
        "ORtg": _num(row.get("ORtg")),
        "DRtg": _num(row.get("DRtg")),
        "pace_index": _num(row.get("pace_index") or row.get("home_pace_index")),
        "agix_index": _num(row.get("agix_index") or row.get("home_agix_index")),
        "nec_index": _num(row.get("nec_index") or row.get("home_nec_index")),
        "control_index": _num(row.get("control_index")),
        "consistency_index": _num(row.get("consistency_index")),
        "chaos_index": _num(row.get("chaos_index")),
        "ppda": _num(row.get("ppda") or row.get("PPDA")),
        "change": _num(row.get("change")),
        "direction": row.get("direction"),
    }


def _slim_team_stats(row: dict[str, Any]) -> dict[str, Any]:
    betting = row.get("betting") if isinstance(row.get("betting"), dict) else {}
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "league": row.get("league"),
        "league_id": row.get("league_id"),
        "betting": {
            "matches": betting.get("matches"),
            "over_2_5": _num(betting.get("over_2_5")),
            "under_2_5": _num(betting.get("under_2_5")),
            "btts": _num(betting.get("btts")),
            "over_3_5": _num(betting.get("over_3_5")),
            "team_o1_5": _num(betting.get("team_o1_5")),
            "corners_o9_5": _num(betting.get("corners_o9_5")),
            "points_per_match": _num(betting.get("points_per_match")),
        },
    }


def _pace_bucket_for_score(profiles: dict[str, Any] | None, pace_score: float | None) -> dict[str, Any] | None:
    if not profiles or pace_score is None:
        return None
    pace_prof = profiles.get("pace_score") if isinstance(profiles, dict) else None
    if not isinstance(pace_prof, dict):
        return None
    buckets = pace_prof.get("buckets") or []
    for b in buckets:
        if not isinstance(b, dict):
            continue
        lo = _num(b.get("min_pace"))
        hi = _num(b.get("max_pace"))
        if lo is None or hi is None:
            continue
        if lo <= pace_score <= hi:
            lift = b.get("lift") if isinstance(b.get("lift"), dict) else {}
            return {
                "bucket": b.get("bucket"),
                "pace_score": round(pace_score, 1),
                "matches": b.get("matches"),
                "avg_goals": _num(b.get("avg_goals")),
                "avg_corners": _num(b.get("avg_corners")),
                "over_2_5_pct": _num(b.get("over_2_5_pct")),
                "btts_pct": _num(b.get("btts_pct")),
                "lift_over_2_5": _num(lift.get("over_2_5_pct")),
                "lift_btts": _num(lift.get("btts_pct")),
                "lift_goals": _num(lift.get("avg_goals")),
            }
    return None


def _ranking_for_team(rankings: dict[str, Any] | None, team_id: Any) -> dict[str, Any]:
    if not isinstance(rankings, dict) or team_id is None:
        return {}
    tid = int(team_id)
    out: dict[str, Any] = {}
    for market, rows in rankings.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and int(row.get("id") or 0) == tid:
                out[market] = {
                    "rank": row.get("rank"),
                    "value": _num(row.get("value")),
                    "matches": row.get("matches"),
                    "change": row.get("change"),
                    "direction": row.get("direction"),
                }
                break
    return out


def fetch_extra_feeds() -> dict[str, Any]:
    """Pull supplemental feeds and build lookup indexes."""
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
        sim_cards_by_match[_match_key(card.get("home", ""), card.get("away", ""))] = card

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

    cs_charts_by_id: dict[str, dict] = {}
    for row in raw.get("correct_score_charts") or []:
        if isinstance(row, dict) and row.get("fixture_id") is not None:
            cs_charts_by_id[str(row["fixture_id"])] = {
                "fixture_id": row.get("fixture_id"),
                "home_name": row.get("home_name"),
                "away_name": row.get("away_name"),
                "chart": row.get("chart"),
                "chart_url": (
                    f"{DG_BASE}/{row['chart']}"
                    if isinstance(row.get("chart"), str) and not str(row.get("chart")).startswith("http")
                    else row.get("chart")
                ),
                "home_scorelines": (row.get("home_scorelines") or [])[:8],
                "away_scorelines": (row.get("away_scorelines") or [])[:8],
            }

    ratings_by_team_id: dict[str, dict] = {}
    for row in raw.get("dg_ratings") or []:
        if isinstance(row, dict) and row.get("team_id") is not None:
            ratings_by_team_id[str(row["team_id"])] = _slim_rating(row)

    all_odds_by_match: dict[str, dict] = {}
    odds_payload = raw.get("all_odds") or {}
    if isinstance(odds_payload, dict):
        for label, payload in odds_payload.items():
            if not isinstance(payload, dict):
                continue
            home = payload.get("home_team") or ""
            away = payload.get("away_team") or ""
            if " vs " in label and (not home or not away):
                parts = label.split(" vs ", 1)
                home, away = parts[0], parts[1]
            mk = _match_key(str(home), str(away))
            markets = payload.get("markets") if isinstance(payload.get("markets"), dict) else {}
            all_odds_by_match[mk] = {
                "label": label,
                "home_team": home,
                "away_team": away,
                "markets": {
                    k: v
                    for k, v in markets.items()
                    if k
                    in (
                        "first_half_winner",
                        "first_half_goals",
                        "corners_over_under",
                        "home_corners",
                        "away_corners",
                        "goal_btts_combo",
                    )
                },
            }

    form_trends_by_id: dict[str, dict] = {}
    for row in raw.get("form_trends") or []:
        if isinstance(row, dict) and row.get("fixture_id") is not None:
            form_trends_by_id[str(row["fixture_id"])] = row

    xg_regression_by_team_id: dict[str, dict] = {}
    xg_reg = raw.get("xg_regression") or {}
    if isinstance(xg_reg, dict):
        for tid, row in xg_reg.items():
            if isinstance(row, dict):
                xg_regression_by_team_id[str(tid)] = {
                    "team": row.get("team"),
                    "avg_xg_for": _num(row.get("avg_xg_for")),
                    "avg_xg_against": _num(row.get("avg_xg_against")),
                    "avg_goals_for": _num(row.get("avg_goals_for")),
                    "avg_goals_against": _num(row.get("avg_goals_against")),
                    "attack_delta": _num(row.get("attack_delta")),
                    "defense_delta": _num(row.get("defense_delta")),
                }

    team_stats_by_id: dict[str, dict] = {}
    for row in raw.get("team_stats") or []:
        if isinstance(row, dict) and row.get("id") is not None:
            team_stats_by_id[str(row["id"])] = _slim_team_stats(row)

    manager_h2h_by_id: dict[str, dict] = {}
    for row in raw.get("manager_h2h") or []:
        if isinstance(row, dict) and row.get("fixture_id") is not None:
            manager_h2h_by_id[str(row["fixture_id"])] = row

    highlighted = raw.get("highlighted_matchups") if isinstance(raw.get("highlighted_matchups"), dict) else {}
    pace_profiles = None
    pace_payload = raw.get("pace_accuracy")
    if isinstance(pace_payload, dict):
        pace_profiles = pace_payload.get("profiles")

    rankings = raw.get("rankings") if isinstance(raw.get("rankings"), dict) else {}

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
        "cs_charts_by_id": cs_charts_by_id,
        "ratings_by_team_id": ratings_by_team_id,
        "all_odds_by_match": all_odds_by_match,
        "form_trends_by_id": form_trends_by_id,
        "xg_regression_by_team_id": xg_regression_by_team_id,
        "team_stats_by_id": team_stats_by_id,
        "manager_h2h_by_id": manager_h2h_by_id,
        "highlighted_matchups": highlighted,
        "pace_profiles": pace_profiles,
        "rankings": rankings,
    }


def _highlight_roles_for_fixture(
    highlighted: dict[str, Any],
    home: str,
    away: str,
    fixture_id: str,
) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    mk = _match_key(home, away)
    for key, payload in (highlighted or {}).items():
        if not isinstance(payload, dict):
            continue
        label = str(payload.get("match") or "")
        hid = payload.get("fixture_id")
        match_hit = _match_key(
            str(payload.get("home_team") or ""),
            str(payload.get("away_team") or ""),
        ) == mk or (" vs " in label and _match_key(*label.split(" vs ", 1)) == mk)
        id_hit = hid is not None and str(hid) == fixture_id
        if match_hit or id_hit:
            roles.append(
                {
                    "role": key.replace("highest_", "").replace("_", " "),
                    "home_value": _num(payload.get("home_value")),
                    "away_value": _num(payload.get("away_value")),
                    "total": _num(payload.get("total")),
                }
            )
    return roles


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
    pace = sim.get("matchup_pace") if isinstance(sim.get("matchup_pace"), dict) else {}
    pace_score = _num(pace.get("score"))

    extra: dict[str, Any] = {
        "sim_card": indexes.get("sim_cards_by_match", {}).get(mk),
        "head2head": indexes.get("head2head_by_id", {}).get(fid),
        "heat": indexes.get("heat_by_id", {}).get(fid),
        "top_pick": indexes.get("top_picks_by_id", {}).get(fid),
        "matchup_insight": indexes.get("insights_by_match", {}).get(mk)
        or indexes.get("insights_by_id", {}).get(f"{home_id}:{away_id}"),
        "home_trends": indexes.get("trends_by_team_id", {}).get(str(home_id or "")),
        "away_trends": indexes.get("trends_by_team_id", {}).get(str(away_id or "")),
        "correct_score_chart": indexes.get("cs_charts_by_id", {}).get(fid),
        "home_rating": indexes.get("ratings_by_team_id", {}).get(str(home_id or "")),
        "away_rating": indexes.get("ratings_by_team_id", {}).get(str(away_id or "")),
        "all_odds": indexes.get("all_odds_by_match", {}).get(mk),
        "form_trends": indexes.get("form_trends_by_id", {}).get(fid),
        "home_xg_regression": indexes.get("xg_regression_by_team_id", {}).get(str(home_id or "")),
        "away_xg_regression": indexes.get("xg_regression_by_team_id", {}).get(str(away_id or "")),
        "home_team_stats": indexes.get("team_stats_by_id", {}).get(str(home_id or "")),
        "away_team_stats": indexes.get("team_stats_by_id", {}).get(str(away_id or "")),
        "manager_h2h": indexes.get("manager_h2h_by_id", {}).get(fid),
        "pace_context": _pace_bucket_for_score(indexes.get("pace_profiles"), pace_score),
        "matchup_pace": {
            "score": pace_score,
            "pace_index": _num(pace.get("pace_index")),
            "agix_index": _num(pace.get("agix_index")),
            "nec_index": _num(pace.get("nec_index")),
        },
        "home_rankings": _ranking_for_team(indexes.get("rankings"), home_id),
        "away_rankings": _ranking_for_team(indexes.get("rankings"), away_id),
        "highlight_roles": _highlight_roles_for_fixture(
            indexes.get("highlighted_matchups") or {},
            home,
            away,
            fid,
        ),
    }

    if home_xg > 0 and away_xg > 0:
        extra["correct_score"] = build_correct_score_matrix(home_xg, away_xg, dixon_coles=True)

    if include_player_sims:
        if home_id:
            extra["home_player_sims"] = fetch_player_sims_for_team(home_id)
        if away_id:
            extra["away_player_sims"] = fetch_player_sims_for_team(away_id)

    return extra
