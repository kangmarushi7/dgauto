from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from app.bet_scenarios import (
    BTTS_MIN_TEAM_PROJECTED,
    CATEGORY_ORDER,
    LEGACY_BET_TYPE_MAP,
    SCENARIO_BY_BET_TYPE,
    SCENARIO_DEFS,
    TEAM_GOALS_20_MIN,
    TEAM_GOALS_25_MIN,
    TOTAL_OVER_35_MIN,
    TOTAL_OVER_40_MIN,
    TOTAL_UNDER_20_MAX,
    WIN_MIN_60,
    WIN_MIN_70,
    is_legacy_entry,
    scenario_meta_for_entry,
)
from app.db import insert_bets, list_bets, resolve_bet_entry

LOG_TYPE = "main"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def filter_bet_entries(
    entries: list[dict[str, Any]], *, legacy: bool | None = None
) -> list[dict[str, Any]]:
    if legacy is None:
        return list(entries)
    if legacy:
        return [e for e in entries if is_legacy_entry(e)]
    return [e for e in entries if not is_legacy_entry(e)]


def enrich_bet_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for entry in entries:
        meta = scenario_meta_for_entry(entry)
        enriched.append(
            {
                **entry,
                "scenario_category": meta["category"],
                "scenario_label": meta["label"],
            }
        )
    return enriched


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


def _make_win_outright_bets(
    matches: list[dict[str, Any]],
    *,
    bet_type: str,
    min_win_pct: float,
) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for m in matches:
        home_win = _float_or_none(m.get("win_pct")) or 0.0
        away_win = _float_or_none(m.get("away_win_pct")) or 0.0
        home_team = m.get("home_team") or ""
        away_team = m.get("away_team") or ""

        if home_win >= min_win_pct:
            bets.append(
                _bet_entry(
                    m,
                    bet_type=bet_type,
                    team_name=home_team,
                    qualifier_pct=round(home_win, 1),
                    odds=m.get("home_ml_odds"),
                )
            )
        if away_win >= min_win_pct:
            bets.append(
                _bet_entry(
                    m,
                    bet_type=bet_type,
                    team_name=away_team,
                    qualifier_pct=round(away_win, 1),
                    odds=m.get("away_ml_odds"),
                )
            )
    return bets


def _make_win_or_draw_bets(
    matches: list[dict[str, Any]],
    *,
    bet_type: str,
    min_win_pct: float,
) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for m in matches:
        home_win = _float_or_none(m.get("win_pct")) or 0.0
        away_win = _float_or_none(m.get("away_win_pct")) or 0.0
        home_team = m.get("home_team") or ""
        away_team = m.get("away_team") or ""

        if home_win >= min_win_pct:
            bets.append(
                _bet_entry(
                    m,
                    bet_type=bet_type,
                    team_name=home_team,
                    qualifier_pct=round(home_win, 1),
                    odds=m.get("dc_home_draw_odds"),
                )
            )
        if away_win >= min_win_pct:
            bets.append(
                _bet_entry(
                    m,
                    bet_type=bet_type,
                    team_name=away_team,
                    qualifier_pct=round(away_win, 1),
                    odds=m.get("dc_draw_away_odds"),
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
                bet_type="btts_both15",
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
        *_make_win_outright_bets(matches, bet_type="ml_win60", min_win_pct=WIN_MIN_60),
        *_make_win_or_draw_bets(matches, bet_type="dc_win60", min_win_pct=WIN_MIN_60),
        *_make_win_outright_bets(matches, bet_type="ml_win70", min_win_pct=WIN_MIN_70),
        *_make_win_or_draw_bets(matches, bet_type="dc_win70", min_win_pct=WIN_MIN_70),
        *_make_match_total_bets(
            matches, bet_type="o15_t35", min_total=TOTAL_OVER_35_MIN, odds_key="over_1_5_odds"
        ),
        *_make_match_total_bets(
            matches, bet_type="o25_t35", min_total=TOTAL_OVER_35_MIN, odds_key="over_2_5_odds"
        ),
        *_make_match_total_bets(
            matches, bet_type="o15_t40", min_total=TOTAL_OVER_40_MIN, odds_key="over_1_5_odds"
        ),
        *_make_match_total_bets(
            matches, bet_type="o25_t40", min_total=TOTAL_OVER_40_MIN, odds_key="over_2_5_odds"
        ),
        *_make_match_total_bets(
            matches, bet_type="o35_t40", min_total=TOTAL_OVER_40_MIN, odds_key="over_3_5_odds"
        ),
        *_make_team_prop_bets(
            matches,
            bet_type="to05_t20",
            min_team_goals=TEAM_GOALS_20_MIN,
            odds_key_home="home_o0_5_odds",
            odds_key_away="away_o0_5_odds",
        ),
        *_make_team_prop_bets(
            matches,
            bet_type="to15_t20",
            min_team_goals=TEAM_GOALS_20_MIN,
            odds_key_home="home_o1_5_odds",
            odds_key_away="away_o1_5_odds",
        ),
        *_make_team_prop_bets(
            matches,
            bet_type="to05_t25",
            min_team_goals=TEAM_GOALS_25_MIN,
            odds_key_home="home_o0_5_odds",
            odds_key_away="away_o0_5_odds",
        ),
        *_make_team_prop_bets(
            matches,
            bet_type="to15_t25",
            min_team_goals=TEAM_GOALS_25_MIN,
            odds_key_home="home_o1_5_odds",
            odds_key_away="away_o1_5_odds",
        ),
        *_make_btts_bets(matches),
        *_make_match_total_bets(
            matches, bet_type="u25_t20", max_total=TOTAL_UNDER_20_MAX, odds_key="under_2_5_odds"
        ),
        *_make_match_total_bets(
            matches, bet_type="u35_t20", max_total=TOTAL_UNDER_20_MAX, odds_key="under_3_5_odds"
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


def bet_log_dashboard(entries: list[dict[str, Any]], *, scope: str = "scenarios") -> dict[str, Any]:
    """scope: 'scenarios' (split DataGaffer), 'legacy' (old bet types), 'all'."""
    if scope == "scenarios":
        entries = filter_bet_entries(entries, legacy=False)
    elif scope == "legacy":
        entries = filter_bet_entries(entries, legacy=True)

    by_scenario: dict[str, dict[str, Any]] = {}

    if scope in {"scenarios", "all"}:
        for sdef in SCENARIO_DEFS:
            bt = sdef["bet_type"]
            stats = compute_bet_stats([e for e in entries if e.get("bet_type") == bt])
            stats["bet_type"] = bt
            stats["category"] = sdef["category"]
            stats["label"] = sdef["label"]
            stats["hist_hit_pct"] = sdef["hist_hit_pct"]
            by_scenario[bt] = stats

    if scope in {"legacy", "all"}:
        legacy_bet_types = sorted(
            {str(e.get("bet_type") or "") for e in entries if is_legacy_entry(e)}
        )
        for bt in legacy_bet_types:
            if bt not in LEGACY_BET_TYPE_MAP:
                continue
            meta = LEGACY_BET_TYPE_MAP[bt]
            stats = compute_bet_stats([e for e in entries if e.get("bet_type") == bt])
            stats["bet_type"] = bt
            stats["category"] = "Legacy bet types"
            stats["label"] = meta["label"]
            stats["hist_hit_pct"] = 0.0
            by_scenario[bt] = stats

    if scope == "all":
        other_types = sorted(
            {str(e.get("bet_type") or "") for e in entries}
            - set(SCENARIO_BY_BET_TYPE.keys())
            - set(LEGACY_BET_TYPE_MAP.keys())
            - {""}
        )
        for bt in other_types:
            meta = scenario_meta_for_entry({"bet_type": bt})
            stats = compute_bet_stats([e for e in entries if e.get("bet_type") == bt])
            stats["bet_type"] = bt
            stats["category"] = meta["category"]
            stats["label"] = meta["label"]
            stats["hist_hit_pct"] = meta.get("hist_hit_pct", 0.0)
            by_scenario[bt] = stats

    by_category: list[dict[str, Any]] = []
    if scope == "legacy":
        categories = ["Legacy bet types"]
    elif scope == "scenarios":
        categories = [c for c in CATEGORY_ORDER if c != "Legacy"]
    else:
        categories = list(CATEGORY_ORDER)
    extra_cats = sorted({by_scenario[k]["category"] for k in by_scenario} - set(categories))
    for category in categories + extra_cats:
        scenario_keys = [k for k, v in by_scenario.items() if v.get("category") == category]
        if not scenario_keys:
            continue
        ordered = [sdef["bet_type"] for sdef in SCENARIO_DEFS if sdef["bet_type"] in scenario_keys]
        ordered += [k for k in scenario_keys if k not in ordered]
        by_category.append(
            {
                "category": category,
                "scenarios": [by_scenario[k] for k in ordered],
            }
        )

    return {
        "all": compute_bet_stats(entries),
        "by_scenario": by_scenario,
        "by_category": by_category,
        "by_type": by_scenario,
    }
