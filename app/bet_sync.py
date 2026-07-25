"""Auto-sync strategy bet logs after a fixture refresh."""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from app.db import load_state

logger = logging.getLogger(__name__)

# Set AUTO_SYNC_BETS_ON_REFRESH=false to skip (fixture pull still runs).
AUTO_SYNC_ENABLED = os.getenv("AUTO_SYNC_BETS_ON_REFRESH", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# CS hits Polymarket — can be slow; default on with the rest.
AUTO_SYNC_CS = os.getenv("AUTO_SYNC_CS_ON_REFRESH", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# H2H Polymarket pricing on auto-sync — off by default (manual Sync always prices).
AUTO_SYNC_H2H_PM = os.getenv("AUTO_SYNC_H2H_PM_ON_REFRESH", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _safe(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = fn()
        inserted = result.get("inserted")
        logger.info("Auto-sync %s: inserted=%s", name, inserted)
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Auto-sync %s failed: %s", name, exc)
        return {"ok": False, "error": str(exc).strip() or repr(exc), "inserted": 0}


def sync_all_strategy_bets(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build picks from the latest slate and insert new rows into every strategy log.

    Existing bets are never duplicated (insert_bets dedupes). Failures in one
    strategy do not block the others.
    """
    if not AUTO_SYNC_ENABLED:
        return {"skipped": True, "reason": "AUTO_SYNC_BETS_ON_REFRESH disabled"}

    state = state or load_state(
        "latest_data",
        {"scraped_at": None, "matches": [], "fixtures_by_id": {}, "dg_extra_indexes": {}},
    )
    matches = state.get("matches") or []
    summary: dict[str, Any] = {}

    from app.bet_log import sync_recommended_bets
    from app.lm_strat import build_lm_strat_picks, sync_lm_bets
    from app.no_strat import build_no_strat_picks, sync_no_bets
    from app.h2h_strat import build_h2h_strat_picks, sync_h2h_bets
    from app.plus_ev_strat import build_plus_ev_picks, sync_plus_ev_bets
    from app.arahus_engine import build_arahus_slate, flatten_picks, sync_arahus_bets

    summary["main"] = _safe("main", lambda: sync_recommended_bets(matches))
    summary["lm"] = _safe("lm", lambda: sync_lm_bets(build_lm_strat_picks(matches)))
    summary["no"] = _safe("no", lambda: sync_no_bets(build_no_strat_picks(matches)))
    summary["h2h"] = _safe(
        "h2h",
        lambda: sync_h2h_bets(
            build_h2h_strat_picks(matches),
            fetch_pm_odds=AUTO_SYNC_H2H_PM,
        ),
    )
    summary["ev"] = _safe("ev", lambda: sync_plus_ev_bets(build_plus_ev_picks(state)))
    summary["arahus"] = _safe(
        "arahus",
        lambda: sync_arahus_bets(flatten_picks(build_arahus_slate(state))),
    )

    if AUTO_SYNC_CS:
        from app.correct_score_strat import build_correct_score_picks, sync_correct_score_bets

        def _sync_cs() -> dict[str, Any]:
            picks = build_correct_score_picks(state, include_rejected=False)
            qualified = [p for p in picks if p.get("qualified")]
            return sync_correct_score_bets(qualified)

        summary["cs"] = _safe("cs", _sync_cs)
    else:
        summary["cs"] = {"ok": True, "skipped": True, "inserted": 0}

    try:
        from app.unified_bets import _FLAGGED_EV_CACHE

        _FLAGGED_EV_CACHE["at"] = 0.0
    except Exception:  # noqa: BLE001
        pass

    inserted_total = sum(int(v.get("inserted") or 0) for v in summary.values() if isinstance(v, dict))
    summary["inserted_total"] = inserted_total
    return summary


def resync_todays_bets(
    state: dict[str, Any] | None = None,
    *,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Replace today's OPEN logged bets with freshly-built picks.

    Only bets whose fixture kicks off today (IST) and are still ``open`` are
    deleted first; settled/resolved history is preserved. Each strategy log is
    then re-synced from the latest slate, re-inserting today's picks with the
    newest odds. When ``strategy`` is provided, only that log is rebuilt.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.db import delete_bets_by_ids, list_bets
    from app.seasons import fixture_date_ist

    state = state or load_state(
        "latest_data",
        {"scraped_at": None, "matches": [], "fixtures_by_id": {}, "dg_extra_indexes": {}},
    )
    matches = state.get("matches") or []
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    def _wipe_today(log_type: str) -> int:
        ids: list[str] = []
        for entry in list_bets(log_type):
            if str(entry.get("status") or "").lower() != "open":
                continue
            if fixture_date_ist(entry) == today:
                ids.append(str(entry.get("id")))
        return delete_bets_by_ids(log_type, ids)

    from app.bet_log import sync_recommended_bets
    from app.lm_strat import build_lm_strat_picks, sync_lm_bets
    from app.no_strat import build_no_strat_picks, sync_no_bets
    from app.h2h_strat import build_h2h_strat_picks, sync_h2h_bets
    from app.plus_ev_strat import build_plus_ev_picks, sync_plus_ev_bets
    from app.arahus_engine import build_arahus_slate, flatten_picks, sync_arahus_bets

    jobs: dict[str, Callable[[], dict[str, Any]]] = {
        "main": lambda: sync_recommended_bets(matches),
        "lm": lambda: sync_lm_bets(build_lm_strat_picks(matches)),
        "no": lambda: sync_no_bets(build_no_strat_picks(matches)),
        "h2h": lambda: sync_h2h_bets(build_h2h_strat_picks(matches), fetch_pm_odds=True),
        "ev": lambda: sync_plus_ev_bets(build_plus_ev_picks(state)),
        "arahus": lambda: sync_arahus_bets(flatten_picks(build_arahus_slate(state))),
    }

    from app.correct_score_strat import build_correct_score_picks, sync_correct_score_bets

    def _sync_cs() -> dict[str, Any]:
        picks = build_correct_score_picks(state, include_rejected=False)
        qualified = [p for p in picks if p.get("qualified")]
        return sync_correct_score_bets(qualified)

    jobs["cs"] = _sync_cs

    log_types = {
        "main": "main",
        "lm": "lm",
        "no": "no",
        "h2h": "h2h",
        "ev": "ev",
        "arahus": "arahus",
        "cs": "cs",
    }
    requested = str(strategy or "").strip().lower()
    if requested:
        if requested not in jobs:
            allowed = ", ".join(sorted(jobs))
            raise ValueError(f"Unknown strategy '{requested}'. Expected one of: {allowed}")
        jobs = {requested: jobs[requested]}

    summary: dict[str, Any] = {}
    deleted_total = 0
    inserted_total = 0
    for key, fn in jobs.items():
        try:
            deleted = _wipe_today(log_types[key])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Resync %s wipe failed: %s", key, exc)
            summary[key] = {"ok": False, "error": str(exc).strip() or repr(exc), "deleted": 0, "inserted": 0}
            continue
        result = _safe(key, fn)
        result["deleted"] = deleted
        deleted_total += deleted
        inserted_total += int(result.get("inserted") or 0)
        summary[key] = result

    try:
        from app.unified_bets import _FLAGGED_EV_CACHE

        _FLAGGED_EV_CACHE["at"] = 0.0
    except Exception:  # noqa: BLE001
        pass

    summary["deleted_total"] = deleted_total
    summary["inserted_total"] = inserted_total
    return summary
