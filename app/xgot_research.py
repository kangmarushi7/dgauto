"""Frozen xGOT forward-paper research variants (env-gated; never LIVE)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.db import insert_bets, list_bets
from app.xgot_strat import (
    BASELINE_STRATEGY_VERSION,
    build_xgot_picks_from_state,
    is_post_kickoff,
)

XGOT_FW_VERSION = "xgot-fw-2026-10-12.1"

# Research ledgers — isolated from baseline log_type=xgot.
LOG_TYPES: dict[str, str] = {
    "B": "xgot_fw_b",
    "C": "xgot_fw_c",
    "D": "xgot_fw_d",
    "E": "xgot_fw_e",
}

RESEARCH_SOT_LINES = {7.5, 8.5, 9.5}

XGOT_RESEARCH_SYNC_ENABLED = os.getenv("XGOT_RESEARCH_SYNC_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
XGOT_RESEARCH_ALLOW_POST_KICKOFF = os.getenv(
    "XGOT_RESEARCH_ALLOW_POST_KICKOFF", "false"
).strip().lower() in {"1", "true", "yes", "on"}


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sot_line_from_pick(pick: dict[str, Any]) -> float | None:
    bt = str(pick.get("bet_type") or "")
    if not bt.startswith("xgot_sot_"):
        return None
    # Prefer team_name (stores the line as string in baseline builder).
    line = _num(pick.get("team_name"))
    if line is not None:
        return line
    mapping = {
        "xgot_sot_o75": 7.5,
        "xgot_sot_o85": 8.5,
        "xgot_sot_o95": 9.5,
        "xgot_sot_o105": 10.5,
    }
    return mapping.get(bt)


def filter_variant_b(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """O2.5 only when 3.0 ≤ proj_xgot_total < 3.5."""
    out: list[dict[str, Any]] = []
    for p in picks:
        if str(p.get("bet_type") or "") != "xgot_o25":
            continue
        total = _num(p.get("proj_xgot_total"))
        if total is None or not (3.0 <= total < 3.5):
            continue
        out.append(p)
    return out


def filter_variant_c(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """BTTS only when 1.2 ≤ min(home, away) xGOT < 1.5."""
    out: list[dict[str, Any]] = []
    for p in picks:
        if str(p.get("bet_type") or "") != "xgot_btts":
            continue
        home = _num(p.get("proj_xgot_home"))
        away = _num(p.get("proj_xgot_away"))
        if home is None or away is None:
            continue
        mn = min(home, away)
        if not (1.2 <= mn < 1.5):
            continue
        out.append(p)
    return out


def filter_variant_d(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Baseline minus O3.5."""
    return [p for p in picks if str(p.get("bet_type") or "") != "xgot_o35"]


def filter_variant_e(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """SOT lines in {7.5, 8.5, 9.5} only."""
    out: list[dict[str, Any]] = []
    for p in picks:
        line = _sot_line_from_pick(p)
        if line is None or line not in RESEARCH_SOT_LINES:
            continue
        out.append(p)
    return out


VARIANT_FILTERS: dict[str, Callable[[list[dict[str, Any]]], list[dict[str, Any]]]] = {
    "B": filter_variant_b,
    "C": filter_variant_c,
    "D": filter_variant_d,
    "E": filter_variant_e,
}


def filter_variant(variant_id: str, picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key = str(variant_id or "").strip().upper()
    fn = VARIANT_FILTERS.get(key)
    if fn is None:
        raise ValueError(f"Unknown xGOT research variant: {variant_id!r}")
    return fn(picks)


def build_variant_picks(
    variant_id: str,
    state: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    allow_post_kickoff: bool | None = None,
) -> list[dict[str, Any]]:
    """Filter baseline picks into a frozen research variant.

    Uses unchanged ``build_xgot_picks_from_state``. Post-kickoff picks are
    dropped unless ``allow_post_kickoff`` is true.
    """
    allow = (
        XGOT_RESEARCH_ALLOW_POST_KICKOFF
        if allow_post_kickoff is None
        else bool(allow_post_kickoff)
    )
    baseline = build_xgot_picks_from_state(state)
    filtered = filter_variant(variant_id, baseline)
    if allow:
        return filtered
    return [p for p in filtered if not is_post_kickoff(p.get("fixture_date"), now=now)]


def sync_variant(
    variant_id: str,
    state: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    allow_post_kickoff: bool | None = None,
) -> dict[str, Any]:
    key = str(variant_id or "").strip().upper()
    log_type = LOG_TYPES.get(key)
    if log_type is None:
        raise ValueError(f"Unknown xGOT research variant: {variant_id!r}")

    state = state or {}
    scraped_at = state.get("scraped_at")
    scrape_id = state.get("last_snapshot_id")
    picks = build_variant_picks(
        key, state, now=now, allow_post_kickoff=allow_post_kickoff
    )
    created = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    candidates: list[dict[str, Any]] = []
    for p in picks:
        post = is_post_kickoff(p.get("fixture_date"), now=now)
        candidates.append(
            {
                "id": str(uuid.uuid4()),
                "created_at": created,
                "fixture_date": p.get("fixture_date"),
                "fixture": p.get("fixture", ""),
                "league_name": p.get("league_name", ""),
                "bet_type": p.get("bet_type"),
                "team_name": p.get("team_name") or "",
                "odds": p.get("odds"),
                "units": float(p.get("units") or 1.0),
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
                "strategy_version": XGOT_FW_VERSION,
                "scrape_id": scrape_id,
                "source_scraped_at": scraped_at,
                "post_kickoff": post,
            }
        )
    inserted = insert_bets(log_type, candidates)
    return {
        "variant": key,
        "log_type": log_type,
        "candidates": len(candidates),
        "inserted": inserted,
        "total": len(list_bets(log_type)),
        "strategy_version": XGOT_FW_VERSION,
        "baseline_version": BASELINE_STRATEGY_VERSION,
    }


def sync_all_research_variants(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sync B–E when ``XGOT_RESEARCH_SYNC_ENABLED`` is true; otherwise skip."""
    if not XGOT_RESEARCH_SYNC_ENABLED:
        return {
            "skipped": True,
            "reason": "XGOT_RESEARCH_SYNC_ENABLED=false",
            "inserted": 0,
            "strategy_version": XGOT_FW_VERSION,
        }
    results: dict[str, Any] = {}
    inserted_total = 0
    for vid in ("B", "C", "D", "E"):
        try:
            results[vid] = sync_variant(vid, state)
            inserted_total += int(results[vid].get("inserted") or 0)
        except Exception as exc:  # noqa: BLE001
            results[vid] = {"ok": False, "error": str(exc).strip() or repr(exc), "inserted": 0}
    return {
        "skipped": False,
        "inserted": inserted_total,
        "variants": results,
        "strategy_version": XGOT_FW_VERSION,
    }


def research_log_types() -> list[str]:
    return list(LOG_TYPES.values())
