from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from app.bet_log import compute_bet_stats
from app.db import insert_bets, list_bets, resolve_bet_entry
from app.dg_feeds import lookup_extra_for_fixture
from app.ev_bet_filters import is_actionable_plus_ev_market, resolve_kind_for_market
from app.fixture_dashboard import build_fixture_dashboard
from app.fixture_detail import find_raw_fixture

LOG_TYPE = "ev"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pick_from_dashboard(detail: dict[str, Any], *, perc: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    home = detail.get("home_team") or "Home"
    away = detail.get("away_team") or "Away"
    hx = detail.get("hero_v2", {}).get("right", {})
    xg = {
        "home": hx.get("xg_home") or detail.get("hero", {}).get("xg_home"),
        "away": hx.get("xg_away") or detail.get("hero", {}).get("xg_away"),
        "total": hx.get("xg_total") or detail.get("hero", {}).get("xg_total"),
    }
    perc = perc or {}
    match = detail.get("match") or {}
    picks: list[dict[str, Any]] = []

    for m in detail.get("all_markets") or detail.get("recommended_bets") or []:
        if not is_actionable_plus_ev_market(m, home_name=home, away_name=away, xg=xg, perc=perc):
            continue
        market = str(m.get("market") or "")
        bet_type, team_name = resolve_kind_for_market(market, home, away)
        picks.append(
            {
                "fixture_id": detail.get("fixture_id"),
                "fixture_date": detail.get("kickoff"),
                "fixture": detail.get("fixture", ""),
                "league_name": detail.get("league_name", ""),
                "market": market,
                "bet_type": bet_type,
                "team_name": team_name or "",
                "edge": m.get("edge"),
                "edge_fmt": m.get("edge_fmt"),
                "ev": m.get("ev"),
                "ev_fmt": m.get("ev_fmt"),
                "model_pct_fmt": m.get("model_pct_fmt"),
                "book_odds_fmt": m.get("book_odds_fmt"),
                "verdict": m.get("verdict"),
                "certainty_label": m.get("certainty_label"),
                "odds": m.get("book_odds"),
                "units": m.get("units") or 1.0,
            }
        )
    return picks


def build_plus_ev_picks(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan all fixtures in latest state for model-valid +EV markets."""
    fixtures_by_id = state.get("fixtures_by_id") or {}
    indexes = state.get("dg_extra_indexes") or {}
    matches_by_id = {
        str(m.get("fixture_id")): m for m in (state.get("matches") or []) if m.get("fixture_id")
    }
    all_picks: list[dict[str, Any]] = []

    for fid in fixtures_by_id:
        raw = find_raw_fixture(fixtures_by_id, fid)
        if not raw:
            continue
        match = matches_by_id.get(str(raw.get("fixture_id")))
        extra = lookup_extra_for_fixture(raw, indexes) if indexes else {}
        try:
            detail = build_fixture_dashboard(raw, match, extra=extra)
        except Exception:
            continue
        perc = (raw.get("sim_stats") or {}).get("percents") or {}
        picks = _pick_from_dashboard(detail, perc=perc)
        for p in picks:
            p["fixture_date"] = raw.get("date") or p.get("fixture_date")
        all_picks.extend(picks)

    all_picks.sort(
        key=lambda x: (num_or_zero(x.get("ev")), num_or_zero(x.get("edge"))),
        reverse=True,
    )
    return all_picks


def num_or_zero(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def load_plus_ev_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def sync_plus_ev_bets(picks: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for p in picks:
        market = p.get("market") or ""
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": p.get("bet_type") or "unknown",
                "team_name": p.get("team_name") or "",
                "qualifier_pct": p.get("ev"),
                "odds": p.get("odds"),
                "units": float(p.get("units") or 1.0),
                "status": "open",
                "pnl_units": None,
            }
        )
    inserted = insert_bets(LOG_TYPE, candidates)
    return {"inserted": inserted, "total": len(load_plus_ev_bet_log())}


def resolve_plus_ev_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entries = load_plus_ev_bet_log()
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


def plus_ev_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return compute_bet_stats(entries)


_BET_LABELS: dict[str, str] = {
    "team_o1.5": "O1.5",
    "team_o0.5": "O0.5",
    "over1.5": "Over 1.5",
    "over2.5": "Over 2.5",
    "over3.5": "Over 3.5",
    "under2.5": "Under 2.5",
    "btts": "BTTS Yes",
    "moneyline": "Win",
    "draw": "Draw",
    "dc_1x": "DC 1X",
    "dc_x2": "DC X2",
}


def market_label_for_entry(entry: dict[str, Any]) -> str:
    bt = str(entry.get("bet_type") or "")
    team = str(entry.get("team_name") or "").strip()
    label = _BET_LABELS.get(bt, bt)
    if team and bt in ("team_o1.5", "team_o0.5", "moneyline"):
        return f"{team} {label}"
    return label


def enrich_plus_ev_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in entries:
        row = dict(e)
        ev = row.get("qualifier_pct")
        row["market_label"] = market_label_for_entry(row)
        row["ev_fmt"] = f"{float(ev):+.1f}%" if ev is not None else "—"
        out.append(row)
    return out
