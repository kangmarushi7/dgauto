from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from app.bet_scenarios import (
    BET_TYPE_META,
    BTTS_MIN_TEAM_PROJECTED,
    TEAM_PROP_MIN,
    TOTAL_OVER_15_MIN,
    TOTAL_OVER_25_MIN,
    TOTAL_OVER_35_MIN,
    TOTAL_UNDER_MAX,
)
from app.db import insert_bets, list_bets, resolve_bet_entry

LOG_TYPE = "main"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bet_entry(m: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "created_at": _now_iso(),
        "fixture_date": m.get("fixture_date"),
        "fixture": m.get("fixture", ""),
        "league_name": m.get("league_name", ""),
        "units": 1.0,
        "status": "open",
        "pnl_units": None,
        **fields,
    }


def _make_moneyline_bets(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for m in matches:
        home_win = float(m.get("win_pct") or 0)
        away_win = float(m.get("away_win_pct") or 0)
        if home_win <= 61 and away_win <= 61:
            continue

        if home_win >= away_win:
            team = m.get("home_team") or ""
            win_pct = home_win
            odds = m.get("home_ml_odds")
        else:
            team = m.get("away_team") or ""
            win_pct = away_win
            odds = m.get("away_ml_odds")

        bets.append(
            _bet_entry(
                m,
                bet_type="moneyline",
                team_name=team,
                qualifier_pct=round(win_pct, 1),
                odds=odds,
            )
        )
    return bets


def _make_match_total_bets(
    matches: list[dict[str, Any]],
    *,
    bet_type: str,
    min_total: float | None = None,
    max_total: float | None = None,
    odds_key: str,
) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for m in matches:
        total = _float_or_none(m.get("projected_total_goals"))
        if total is None:
            continue
        if min_total is not None and total < min_total:
            continue
        if max_total is not None and total > max_total:
            continue
        bets.append(
            _bet_entry(
                m,
                bet_type=bet_type,
                team_name="",
                qualifier_pct=round(total, 2),
                odds=m.get(odds_key),
            )
        )
    return bets


def _make_btts_bets(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for m in matches:
        home_val = _float_or_none(m.get("home_projected_goals"))
        away_val = _float_or_none(m.get("away_projected_goals"))
        if home_val is None or away_val is None:
            continue
        if home_val < BTTS_MIN_TEAM_PROJECTED or away_val < BTTS_MIN_TEAM_PROJECTED:
            continue

        btts_pct = _float_or_none(m.get("btts_pct"))
        qualifier = btts_pct if btts_pct is not None else min(home_val, away_val)

        bets.append(
            _bet_entry(
                m,
                bet_type="btts",
                team_name="",
                qualifier_pct=round(qualifier, 2),
                odds=m.get("btts_yes_odds"),
            )
        )
    return bets


def _make_team_prop_bets(
    matches: list[dict[str, Any]],
    *,
    bet_type: str,
    min_team_goals: float,
    odds_key_home: str,
    odds_key_away: str,
) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for m in matches:
        home_val = _float_or_none(m.get("home_projected_goals"))
        away_val = _float_or_none(m.get("away_projected_goals"))
        home_team = m.get("home_team") or ""
        away_team = m.get("away_team") or ""

        if home_val is not None and home_val >= min_team_goals:
            bets.append(
                _bet_entry(
                    m,
                    bet_type=bet_type,
                    team_name=home_team,
                    qualifier_pct=round(home_val, 2),
                    odds=m.get(odds_key_home),
                )
            )
        if away_val is not None and away_val >= min_team_goals:
            bets.append(
                _bet_entry(
                    m,
                    bet_type=bet_type,
                    team_name=away_team,
                    qualifier_pct=round(away_val, 2),
                    odds=m.get(odds_key_away),
                )
            )
    return bets


def build_recommended_bets(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        *_make_moneyline_bets(matches),
        *_make_match_total_bets(
            matches,
            bet_type="over1.5",
            min_total=TOTAL_OVER_15_MIN,
            odds_key="over_1_5_odds",
        ),
        *_make_match_total_bets(
            matches,
            bet_type="over2.5",
            min_total=TOTAL_OVER_25_MIN,
            odds_key="over_2_5_odds",
        ),
        *_make_match_total_bets(
            matches,
            bet_type="over3.5",
            min_total=TOTAL_OVER_35_MIN,
            odds_key="over_3_5_odds",
        ),
        *_make_btts_bets(matches),
        *_make_team_prop_bets(
            matches,
            bet_type="team_o0.5",
            min_team_goals=TEAM_PROP_MIN,
            odds_key_home="home_o0_5_odds",
            odds_key_away="away_o0_5_odds",
        ),
        *_make_team_prop_bets(
            matches,
            bet_type="team_o1.5",
            min_team_goals=TEAM_PROP_MIN,
            odds_key_home="home_o1_5_odds",
            odds_key_away="away_o1_5_odds",
        ),
        *_make_match_total_bets(
            matches,
            bet_type="under2.5",
            max_total=TOTAL_UNDER_MAX,
            odds_key="under_2_5_odds",
        ),
        *_make_match_total_bets(
            matches,
            bet_type="under3.5",
            max_total=TOTAL_UNDER_MAX,
            odds_key="under_3_5_odds",
        ),
    ]


def sync_recommended_bets(matches: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = build_recommended_bets(matches)
    inserted = insert_bets(LOG_TYPE, candidates)
    return {"inserted": inserted, "total": len(load_bet_log())}


def resolve_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entries = load_bet_log()
    entry = next((e for e in entries if e.get("id") == bet_id), None)
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


def _avg_odds(entries: list[dict[str, Any]]) -> float | None:
    odds_vals: list[float] = []
    for entry in entries:
        raw = entry.get("odds")
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            odds_vals.append(val)
    if not odds_vals:
        return None
    return round(sum(odds_vals) / len(odds_vals), 2)


def compute_bet_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    placed = len(entries)
    won = sum(1 for e in entries if e.get("status") == "won")
    lost = sum(1 for e in entries if e.get("status") == "lost")
    pushes = sum(1 for e in entries if e.get("status") == "push")
    decided = won + lost
    win_pct = round((won / decided) * 100, 1) if decided else 0.0
    pnl = round(sum(float(e.get("pnl_units") or 0.0) for e in entries), 3)
    return {
        "placed": placed,
        "won": won,
        "lost": lost,
        "push": pushes,
        "win_pct": win_pct,
        "avg_odds": _avg_odds(entries),
        "unit_pnl": pnl,
    }


def bet_log_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = {}
    for bet_type, label, hist_hit in BET_TYPE_META:
        stats = compute_bet_stats([e for e in entries if e.get("bet_type") == bet_type])
        stats["label"] = label
        stats["hist_hit_pct"] = hist_hit
        by_type[bet_type] = stats

    moneyline = [e for e in entries if e.get("bet_type") == "moneyline"]
    over15 = [e for e in entries if e.get("bet_type") == "over1.5"]
    btts = [e for e in entries if e.get("bet_type") == "btts"]

    return {
        "all": compute_bet_stats(entries),
        "by_type": by_type,
        "moneyline": by_type.get("moneyline", compute_bet_stats(moneyline)),
        "over1_5": by_type.get("over1.5", compute_bet_stats(over15)),
        "btts": by_type.get("btts", compute_bet_stats(btts)),
    }
