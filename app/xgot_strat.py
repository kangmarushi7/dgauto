"""xGOT paper research strategy — log all projected fixtures, slice later."""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from app.bet_log import compute_bet_stats
from app.db import insert_bets, list_bets, resolve_bet_entry

LOG_TYPE = "xgot"
STAKE_UNITS = 1.0
SOT_LINES: tuple[float, ...] = (7.5, 8.5, 9.5, 10.5)

MARKET_LABELS: dict[str, str] = {
    "xgot_o25": "Over 2.5",
    "xgot_o35": "Over 3.5",
    "xgot_btts": "BTTS Yes",
    "xgot_ml": "Moneyline",
    "xgot_sot_o75": "SOT O7.5",
    "xgot_sot_o85": "SOT O8.5",
    "xgot_sot_o95": "SOT O9.5",
    "xgot_sot_o105": "SOT O10.5",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _side_total(block: Any) -> tuple[float | None, float | None, float | None]:
    if not isinstance(block, dict):
        return None, None, None
    home = _num(block.get("home"))
    away = _num(block.get("away"))
    total = _num(block.get("total"))
    if total is None and home is not None and away is not None:
        total = home + away
    return home, away, total


def extract_projections(
    fixture: dict[str, Any] | None,
    *,
    heat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pull home/away/total projections from sim_stats (+ heat big-chances fallback)."""
    raw = fixture if isinstance(fixture, dict) else {}
    sim = raw.get("sim_stats") if isinstance(raw.get("sim_stats"), dict) else {}
    projected_xg = sim.get("projected_xg") if isinstance(sim.get("projected_xg"), dict) else {}

    xgot_h, xgot_a, xgot_total = _side_total(projected_xg.get("xgot"))
    bc_h, bc_a, bc_total = _side_total(sim.get("big_chances_created"))
    box_h, box_a, box_total = _side_total(sim.get("shots_inside_box"))
    sot_h, sot_a, sot_total = _side_total(sim.get("shots_on_target"))
    _, _, xg_total = _side_total(sim.get("xg"))

    if (bc_h is None or bc_a is None or bc_total is None) and isinstance(heat, dict):
        ps = heat.get("projected_stats") if isinstance(heat.get("projected_stats"), dict) else {}
        home_ps = ps.get("home") if isinstance(ps.get("home"), dict) else {}
        away_ps = ps.get("away") if isinstance(ps.get("away"), dict) else {}
        h = _num(home_ps.get("big_chances_created"))
        a = _num(away_ps.get("big_chances_created"))
        if bc_h is None:
            bc_h = h
        if bc_a is None:
            bc_a = a
        if bc_total is None and bc_h is not None and bc_a is not None:
            bc_total = bc_h + bc_a
        elif bc_total is None:
            bc_total = bc_h if bc_h is not None else bc_a

    return {
        "proj_xgot_home": xgot_h,
        "proj_xgot_away": xgot_a,
        "proj_xgot_total": xgot_total,
        "proj_big_chances_home": bc_h,
        "proj_big_chances_away": bc_a,
        "proj_big_chances_total": bc_total,
        "proj_box_shots_home": box_h,
        "proj_box_shots_away": box_a,
        "proj_box_shots_total": box_total,
        "proj_sot_home": sot_h,
        "proj_sot_away": sot_a,
        "proj_sot_total": sot_total,
        "proj_xg_total": xg_total,
    }


def _norm_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def team_side_for_entry(entry: dict[str, Any]) -> str | None:
    """Return 'home' / 'away' when the bet is team-based (e.g. ML)."""
    bt = str(entry.get("bet_type") or "")
    if bt != "xgot_ml":
        return None
    team = _norm_name(entry.get("team_name"))
    if not team:
        return None
    home = _norm_name(entry.get("home_team"))
    away = _norm_name(entry.get("away_team"))
    if not home or not away:
        fixture = str(entry.get("fixture") or "")
        for sep in (" vs ", " v "):
            if sep in fixture.lower():
                # Case-preserving split on first occurrence (case-insensitive).
                idx = fixture.lower().find(sep)
                home = _norm_name(fixture[:idx])
                away = _norm_name(fixture[idx + len(sep) :])
                break
    if home and team == home:
        return "home"
    if away and team == away:
        return "away"
    return None


def display_metric_for_entry(entry: dict[str, Any], prefix: str) -> float | None:
    """Team side for ML bets; match total otherwise.

    prefix examples: proj_xgot, proj_big_chances, proj_box_shots, proj_sot
    """
    side = team_side_for_entry(entry)
    if side == "home":
        return _num(entry.get(f"{prefix}_home"))
    if side == "away":
        return _num(entry.get(f"{prefix}_away"))
    return _num(entry.get(f"{prefix}_total"))


def format_ha_total(home: Any, away: Any, total: Any) -> str:
    """Compact H / A (T) label for strat / log cells."""
    h = _num(home)
    a = _num(away)
    t = _num(total)
    if h is None and a is None and t is None:
        return "—"
    if h is None and a is None:
        return str(t)
    left = "—" if h is None else str(h)
    right = "—" if a is None else str(a)
    if t is None and h is not None and a is not None:
        t = round(h + a, 4)
        if abs(t - round(t)) < 1e-9:
            t = float(round(t))
    if t is None:
        return f"{left} / {right}"
    return f"{left} / {right} ({t})"


def is_eligible(projections: dict[str, Any]) -> bool:
    if _num(projections.get("proj_xgot_total")) is not None:
        return True
    bc = _num(projections.get("proj_big_chances_total"))
    box = _num(projections.get("proj_box_shots_total"))
    return bc is not None and box is not None


def pick_sot_line(sot_total: float | None) -> float | None:
    """Nearest half-line at or below projected SOT from the fixed ladder."""
    total = _num(sot_total)
    if total is None:
        return None
    chosen: float | None = None
    for line in SOT_LINES:
        if line <= total:
            chosen = line
    return chosen


def _sot_bet_type(line: float) -> str:
    # 7.5 → o75, 10.5 → o105
    return f"xgot_sot_o{str(line).replace('.', '')}"


def market_label_for_entry(entry: dict[str, Any]) -> str:
    bt = str(entry.get("bet_type") or "")
    if bt == "xgot_ml":
        team = str(entry.get("team_name") or "").strip()
        return f"{team} ML" if team else "Moneyline"
    if bt.startswith("xgot_sot_"):
        line = str(entry.get("team_name") or "").strip()
        if line:
            return f"SOT O{line}"
        return MARKET_LABELS.get(bt, bt)
    return MARKET_LABELS.get(bt, bt)


def _fixture_lookup(fixtures_by_id: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(fixtures_by_id, dict):
        return out
    for key, raw in fixtures_by_id.items():
        if not isinstance(raw, dict):
            continue
        fid = raw.get("fixture_id", key)
        out[str(fid)] = raw
        out[str(key)] = raw
    return out


def _heat_lookup(heat_by_id: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(heat_by_id, dict):
        return out
    for key, raw in heat_by_id.items():
        if isinstance(raw, dict):
            out[str(key)] = raw
            fid = raw.get("fixture_id")
            if fid is not None:
                out[str(fid)] = raw
    return out


def build_xgot_picks(
    matches: list[dict[str, Any]] | None,
    fixtures_by_id: dict[str, Any] | None = None,
    heat_by_id: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build paper bets for every eligible slate fixture × markets."""
    by_fx = _fixture_lookup(fixtures_by_id)
    by_heat = _heat_lookup(heat_by_id)
    picks: list[dict[str, Any]] = []

    for m in matches or []:
        fid = m.get("fixture_id")
        if fid is None or fid == "":
            continue
        fid_s = str(fid)
        raw = by_fx.get(fid_s) or {}
        heat = by_heat.get(fid_s)
        proj = extract_projections(raw, heat=heat)
        if not is_eligible(proj):
            continue

        home = str(m.get("home_team") or "").strip()
        away = str(m.get("away_team") or "").strip()
        fixture = str(m.get("fixture") or (f"{home} vs {away}" if home and away else "")).strip()
        if not fixture:
            continue

        base = {
            "fixture_id": fid_s,
            "fixture_date": m.get("fixture_date") or m.get("date"),
            "fixture": fixture,
            "league_name": str(m.get("league_name") or ""),
            "home_team": home,
            "away_team": away,
            "units": STAKE_UNITS,
            "proj_xgot_home": proj.get("proj_xgot_home"),
            "proj_xgot_away": proj.get("proj_xgot_away"),
            "proj_xgot_total": proj.get("proj_xgot_total"),
            "proj_big_chances_home": proj.get("proj_big_chances_home"),
            "proj_big_chances_away": proj.get("proj_big_chances_away"),
            "proj_big_chances_total": proj.get("proj_big_chances_total"),
            "proj_box_shots_home": proj.get("proj_box_shots_home"),
            "proj_box_shots_away": proj.get("proj_box_shots_away"),
            "proj_box_shots_total": proj.get("proj_box_shots_total"),
            "proj_sot_home": proj.get("proj_sot_home"),
            "proj_sot_away": proj.get("proj_sot_away"),
            "proj_sot_total": proj.get("proj_sot_total"),
            "proj_xg_total": proj.get("proj_xg_total"),
        }

        def _add(bet_type: str, *, odds: Any, team_name: str = "") -> None:
            odds_f = _num(odds)
            # Required odds for non-SOT markets.
            if not bet_type.startswith("xgot_sot_") and (odds_f is None or odds_f <= 1.0):
                return
            row = dict(base)
            row["bet_type"] = bet_type
            row["team_name"] = team_name
            row["odds"] = odds_f
            row["label"] = market_label_for_entry(row)
            picks.append(row)

        _add("xgot_o25", odds=m.get("over_2_5_odds"))
        _add("xgot_o35", odds=m.get("over_3_5_odds"))
        _add("xgot_btts", odds=m.get("btts_yes_odds"))

        sot_line = pick_sot_line(proj.get("proj_sot_total"))
        if sot_line is not None:
            # SOT odds rarely on slate; allow null for research volume.
            _add(_sot_bet_type(sot_line), odds=m.get("sot_over_odds"), team_name=str(sot_line))

        home_ml = _num(m.get("home_ml_odds"))
        away_ml = _num(m.get("away_ml_odds"))
        if home_ml is not None and away_ml is not None and home_ml != away_ml:
            if home_ml < away_ml and home:
                _add("xgot_ml", odds=home_ml, team_name=home)
            elif away_ml < home_ml and away:
                _add("xgot_ml", odds=away_ml, team_name=away)
        elif home_ml is not None and away_ml is None and home:
            _add("xgot_ml", odds=home_ml, team_name=home)
        elif away_ml is not None and home_ml is None and away:
            _add("xgot_ml", odds=away_ml, team_name=away)

    picks.sort(
        key=lambda p: (
            str(p.get("fixture_date") or "9999"),
            str(p.get("fixture") or ""),
            str(p.get("bet_type") or ""),
        )
    )
    return picks


def build_xgot_picks_from_state(state: dict[str, Any] | None) -> list[dict[str, Any]]:
    state = state or {}
    extras = state.get("dg_extra_indexes") if isinstance(state.get("dg_extra_indexes"), dict) else {}
    heat = extras.get("heat_by_id") if isinstance(extras.get("heat_by_id"), dict) else {}
    return build_xgot_picks(
        state.get("matches") or [],
        state.get("fixtures_by_id") or {},
        heat,
    )


def group_xgot_candidates(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per fixture for the strat page."""
    by_fid: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for p in picks:
        fid = str(p.get("fixture_id") or "")
        if not fid:
            continue
        if fid not in by_fid:
            by_fid[fid] = {
                "fixture_id": fid,
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture"),
                "league_name": p.get("league_name"),
                "home_team": p.get("home_team"),
                "away_team": p.get("away_team"),
                "proj_xgot_home": p.get("proj_xgot_home"),
                "proj_xgot_away": p.get("proj_xgot_away"),
                "proj_xgot_total": p.get("proj_xgot_total"),
                "proj_big_chances_home": p.get("proj_big_chances_home"),
                "proj_big_chances_away": p.get("proj_big_chances_away"),
                "proj_big_chances_total": p.get("proj_big_chances_total"),
                "proj_box_shots_home": p.get("proj_box_shots_home"),
                "proj_box_shots_away": p.get("proj_box_shots_away"),
                "proj_box_shots_total": p.get("proj_box_shots_total"),
                "proj_sot_home": p.get("proj_sot_home"),
                "proj_sot_away": p.get("proj_sot_away"),
                "proj_sot_total": p.get("proj_sot_total"),
                "xgot_label": format_ha_total(
                    p.get("proj_xgot_home"), p.get("proj_xgot_away"), p.get("proj_xgot_total")
                ),
                "big_chances_label": format_ha_total(
                    p.get("proj_big_chances_home"),
                    p.get("proj_big_chances_away"),
                    p.get("proj_big_chances_total"),
                ),
                "box_shots_label": format_ha_total(
                    p.get("proj_box_shots_home"),
                    p.get("proj_box_shots_away"),
                    p.get("proj_box_shots_total"),
                ),
                "sot_label": format_ha_total(
                    p.get("proj_sot_home"), p.get("proj_sot_away"), p.get("proj_sot_total")
                ),
                "markets": [],
            }
            order.append(fid)
        by_fid[fid]["markets"].append(
            {
                "bet_type": p.get("bet_type"),
                "label": p.get("label") or market_label_for_entry(p),
                "odds": p.get("odds"),
                "team_name": p.get("team_name"),
            }
        )
    return [by_fid[fid] for fid in order]


def select_fixture_ids_for_slice(
    entries: list[dict[str, Any]],
    *,
    rank_by: str = "proj_xgot_total",
    percentile: float | None = None,
    min_value: float | None = None,
) -> set[str]:
    """Select fixture_ids for bet-log slicing (must match JS algorithm).

    fixtures = unique by fixture_id
    sort by rank_metric desc, then fixture_id asc
    keep ceil(n * pct); All (percentile None/1) keeps all
    optional min_value drops fixtures below floor (nulls drop)
    """
    best: dict[str, float | None] = {}
    for e in entries:
        fid = str(e.get("fixture_id") or "").strip()
        if not fid:
            # Fall back to fixture+date key when fixture_id missing.
            fid = f"{e.get('fixture_date')}|{e.get('fixture')}"
        metric = _num(e.get(rank_by))
        if fid not in best:
            best[fid] = metric
        else:
            prev = best[fid]
            if metric is not None and (prev is None or metric > prev):
                best[fid] = metric

    items = list(best.items())
    items.sort(key=lambda kv: (-(kv[1] if kv[1] is not None else float("-inf")), kv[0]))

    if min_value is not None:
        floor = float(min_value)
        items = [(fid, m) for fid, m in items if m is not None and m >= floor]

    if percentile is None or percentile >= 1.0:
        return {fid for fid, _ in items}

    pct = max(0.0, float(percentile))
    n = len(items)
    keep_n = int(math.ceil(n * pct)) if n else 0
    return {fid for fid, _ in items[:keep_n]}


def load_xgot_bet_log() -> list[dict[str, Any]]:
    return list_bets(LOG_TYPE)


def sync_xgot_bets(picks: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for p in picks:
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _now_iso(),
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": p.get("bet_type"),
                "team_name": p.get("team_name") or "",
                "odds": p.get("odds"),
                "units": float(p.get("units") or STAKE_UNITS),
                "status": "open",
                "pnl_units": None,
                "fixture_id": str(p.get("fixture_id") or "") or None,
                "home_team": p.get("home_team") or "",
                "away_team": p.get("away_team") or "",
                "proj_xgot_home": p.get("proj_xgot_home"),
                "proj_xgot_away": p.get("proj_xgot_away"),
                "proj_xgot_total": p.get("proj_xgot_total"),
                "proj_big_chances_home": p.get("proj_big_chances_home"),
                "proj_big_chances_away": p.get("proj_big_chances_away"),
                "proj_big_chances_total": p.get("proj_big_chances_total"),
                "proj_box_shots_home": p.get("proj_box_shots_home"),
                "proj_box_shots_away": p.get("proj_box_shots_away"),
                "proj_box_shots_total": p.get("proj_box_shots_total"),
                "proj_sot_home": p.get("proj_sot_home"),
                "proj_sot_away": p.get("proj_sot_away"),
                "proj_sot_total": p.get("proj_sot_total"),
            }
        )
    inserted = insert_bets(LOG_TYPE, candidates)
    return {"inserted": inserted, "total": len(load_xgot_bet_log())}


def resolve_xgot_bet(bet_id: str, result: str) -> dict[str, Any]:
    result = result.lower().strip()
    if result not in {"won", "lost", "push"}:
        raise ValueError("Result must be one of: won, lost, push")

    entries = load_xgot_bet_log()
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


def xgot_dashboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return compute_bet_stats(entries)


def enrich_xgot_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in entries:
        row = dict(e)
        row["market_label"] = market_label_for_entry(row)
        side = team_side_for_entry(row)
        row["proj_side"] = side
        row["display_xgot"] = display_metric_for_entry(row, "proj_xgot")
        row["display_big_chances"] = display_metric_for_entry(row, "proj_big_chances")
        row["display_box_shots"] = display_metric_for_entry(row, "proj_box_shots")
        row["display_sot"] = display_metric_for_entry(row, "proj_sot")
        row["xgot_breakdown"] = format_ha_total(
            row.get("proj_xgot_home"), row.get("proj_xgot_away"), row.get("proj_xgot_total")
        )
        # ML / team bets: primary cell is the selected team value + side tag.
        if side:
            val = row["display_xgot"]
            tag = "H" if side == "home" else "A"
            row["xgot_display_label"] = "—" if val is None else f"{val} ({tag})"
        else:
            row["xgot_display_label"] = (
                "—" if row["display_xgot"] is None else str(row["display_xgot"])
            )
        out.append(row)
    return out
