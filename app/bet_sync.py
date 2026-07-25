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
