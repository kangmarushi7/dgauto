"""H2H Strat — DataGaffer head-to-head trend filters (Goals / SOT / Corners / Win-Draw).

Source: https://www.datagaffer.com/head_2_head (backed by head2head.json)

Rules (match Trends tab defaults):
  - Min 3 historical H2H meetings
  - Hit rate >= 75% on the selected market
  - 1 unit stake per logged bet
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from app.bet_log import compute_bet_stats
from app.db import insert_bets, list_bets, resolve_bet_entry
from app.dg_feeds import _load_json, FEED_PATHS

LOG_TYPE = "h2h"
MIN_H2H = 6
MIN_HIT_PCT = 75.0
STAKE_UNITS = 1.0

# category → (json key, bet_type slug, label, resolve_kind, line_or_side)
# resolve_kind is consumed by auto_resolve._resolve_result / H2H-specific helpers.
H2H_MARKETS: list[tuple[str, str, str, str, str, float | str | None]] = [
    ("goals", "over_2_5", "h2h_o25", "Over 2.5", "over2.5", None),
    ("goals", "over_3_5", "h2h_o35", "Over 3.5", "over3.5", None),
    ("goals", "btts", "h2h_btts", "BTTS Yes", "btts", None),
    ("corners", "over_8_5", "h2h_c_o85", "Corners O8.5", "h2h_corners", 8.5),
    ("corners", "over_9_5", "h2h_c_o95", "Corners O9.5", "h2h_corners", 9.5),
    ("corners", "over_10_5", "h2h_c_o105", "Corners O10.5", "h2h_corners", 10.5),
    ("shots_on_target", "over_7_5", "h2h_sot_o75", "SOT O7.5", "h2h_sot", 7.5),
    ("shots_on_target", "over_8_5", "h2h_sot_o85", "SOT O8.5", "h2h_sot", 8.5),
    ("shots_on_target", "over_9_5", "h2h_sot_o95", "SOT O9.5", "h2h_sot", 9.5),
    ("win_draw", "home_win", "h2h_home", "Home Win", "h2h_home_win", None),
    ("win_draw", "draw", "h2h_draw", "Draw", "draw", None),
    ("win_draw", "away_win", "h2h_away", "Away Win", "h2h_away_win", None),
]

CATEGORY_LABELS = {
    "goals": "Goals",
    "corners": "Corners",
    "shots_on_target": "SOT",
    "win_draw": "Win/Draw",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_head2head_rows() -> list[dict[str, Any]]:
    raw = _load_json(FEED_PATHS["head2head"])
    return raw if isinstance(raw, list) else []


def _match_lookup(matches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in matches:
        fid = m.get("fixture_id")
        if fid is not None:
            out[str(fid)] = m
    return out


def build_h2h_strat_picks(
    matches: list[dict[str, Any]] | None = None,
    *,
    min_h2h: int = MIN_H2H,
    min_hit_pct: float = MIN_HIT_PCT,
    h2h_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build qualified H2H trend bets from DataGaffer head2head.json."""
    rows = h2h_rows if h2h_rows is not None else fetch_head2head_rows()
    by_id = _match_lookup(matches or [])
    picks: list[dict[str, Any]] = []

    for row in rows:
        fid = row.get("fixture_id")
        h2h = row.get("h2h") if isinstance(row.get("h2h"), dict) else {}
        meetings = int(h2h.get("matches") or 0)
        if meetings < min_h2h:
            continue

        probs = h2h.get("market_probs") if isinstance(h2h.get("market_probs"), dict) else {}
        slate = by_id.get(str(fid), {}) if fid is not None else {}
        home = str(row.get("home") or slate.get("home_team") or "").strip()
        away = str(row.get("away") or slate.get("away_team") or "").strip()
        if not home or not away:
            continue

        fixture = str(slate.get("fixture") or f"{home} vs {away}")
        league = str(slate.get("league_name") or "")
        fixture_date = slate.get("fixture_date") or slate.get("date")

        for category, key, bet_type, label, resolve_kind, line in H2H_MARKETS:
            cat_probs = probs.get(category) if isinstance(probs.get(category), dict) else {}
            pct = _float_or_none(cat_probs.get(key))
            if pct is None or pct < min_hit_pct:
                continue

            # team_name encodes line for corners/SOT (e.g. "8.5") or side for ML.
            if resolve_kind == "h2h_home_win":
                team_name = home
            elif resolve_kind == "h2h_away_win":
                team_name = away
            elif line is not None:
                team_name = str(line)
            else:
                team_name = ""

            picks.append(
                {
                    "fixture_id": fid,
                    "fixture_date": fixture_date,
                    "fixture": fixture,
                    "league_name": league,
                    "home": home,
                    "away": away,
                    "category": category,
                    "category_label": CATEGORY_LABELS.get(category, category),
                    "market_key": key,
                    "bet_type": bet_type,
                    "label": label,
                    "resolve_kind": resolve_kind,
                    "line": line,
                    "team_name": team_name,
                    "h2h_meetings": meetings,
                    "hit_pct": round(pct, 1),
                    "units": STAKE_UNITS,
                    "odds": None,
                }
            )

    picks.sort(
        key=lambda p: (
            -float(p.get("hit_pct") or 0),
            -int(p.get("h2h_meetings") or 0),
            str(p.get("fixture") or ""),
            str(p.get("label") or ""),
        )
    )
    return picks


def load_h2h_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def sync_h2h_bets(picks: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for p in picks:
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": p.get("bet_type") or "h2h",
                "team_name": p.get("team_name") or "",
                "qualifier_pct": p.get("hit_pct"),
                "odds": p.get("odds"),
                "units": float(p.get("units") or STAKE_UNITS),
                "status": "open",
                "pnl_units": None,
            }
        )
    inserted = insert_bets(LOG_TYPE, candidates)
    return {"inserted": inserted, "total": len(load_h2h_bet_log())}


def resolve_h2h_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entries = load_h2h_bet_log()
    entry = next((e for e in entries if e.get("id") == bet_id), None)
    if not entry:
        raise ValueError("Bet not found.")
    odds = float(entry.get("odds") or 0)
    units = float(entry.get("units") or STAKE_UNITS)
    if result == "won":
        # Flat 1u win when no book odds logged (H2H is hit-rate based).
        pnl = round((odds - 1) * units, 3) if odds > 1 else round(1.0 * units, 3)
    elif result == "lost":
        pnl = round(-1.0 * units, 3)
    else:
        pnl = 0.0
    updated = resolve_bet_entry(LOG_TYPE, bet_id, result, pnl, _now_iso())
    if not updated:
        raise ValueError("Bet not found.")
    return updated


def h2h_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    base = compute_bet_stats(entries)
    by_cat: dict[str, list] = {"goals": [], "corners": [], "shots_on_target": [], "win_draw": [], "other": []}
    for e in entries:
        bt = str(e.get("bet_type") or "")
        if bt.startswith("h2h_o") or bt == "h2h_btts":
            by_cat["goals"].append(e)
        elif bt.startswith("h2h_c_"):
            by_cat["corners"].append(e)
        elif bt.startswith("h2h_sot_"):
            by_cat["shots_on_target"].append(e)
        elif bt in {"h2h_home", "h2h_draw", "h2h_away"}:
            by_cat["win_draw"].append(e)
        else:
            by_cat["other"].append(e)
    base["by_category"] = {
        CATEGORY_LABELS.get(k, k): compute_bet_stats(v)
        for k, v in by_cat.items()
        if v and k != "other"
    }
    return base


def enrich_h2h_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    label_map = {bt: label for _, _, bt, label, _, _ in H2H_MARKETS}
    out: list[dict[str, Any]] = []
    for e in entries:
        row = dict(e)
        bt = str(row.get("bet_type") or "")
        row["market_label"] = label_map.get(bt, bt)
        if bt.startswith("h2h_c_"):
            row["category_label"] = "Corners"
        elif bt.startswith("h2h_sot_"):
            row["category_label"] = "SOT"
        elif bt in {"h2h_home", "h2h_draw", "h2h_away"}:
            row["category_label"] = "Win/Draw"
        elif bt.startswith("h2h_"):
            row["category_label"] = "Goals"
        else:
            row["category_label"] = "Other"
        out.append(row)
    return out
