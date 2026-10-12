"""Pull latest fixtures from DataGaffer and persist merged slate."""
from __future__ import annotations

import logging
from typing import Any

from app.db import save_state
from app.scraper import scrape_datagaffer_sync
from app.signals import merge_outlooks

logger = logging.getLogger(__name__)


def refresh_fixtures_sync(*, sync_bets: bool = True) -> dict[str, Any]:
    """Scrape DataGaffer feeds, write latest slate, then auto-sync strategy bet logs."""
    scraped = scrape_datagaffer_sync()

    snapshot: dict[str, Any] | None = None
    try:
        from app.dg_snapshots import save_fixtures_snapshot

        fixtures = scraped.get("fixtures")
        if fixtures is None:
            fixtures = list((scraped.get("fixtures_by_id") or {}).values())
        snapshot = save_fixtures_snapshot(
            scraped_at=str(scraped.get("scraped_at") or ""),
            fixtures=list(fixtures or []),
        )
        logger.info(
            "DG snapshot saved: id=%s hash=%s count=%s deduped=%s",
            snapshot.get("id"),
            snapshot.get("content_hash"),
            snapshot.get("fixture_count"),
            snapshot.get("deduped"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("DG snapshot save failed: %s", exc)
        snapshot = {"ok": False, "error": str(exc).strip() or repr(exc)}

    merged = merge_outlooks(scraped["win_rows"], scraped["goal_rows"])
    state = {
        "scraped_at": scraped["scraped_at"],
        "matches": merged,
        "fixtures_by_id": scraped.get("fixtures_by_id") or {},
        "dg_extra_indexes": scraped.get("dg_extra_indexes") or {},
        "last_snapshot_id": (snapshot or {}).get("id"),
    }
    save_state("latest_data", state)

    bet_sync: dict[str, Any] | None = None
    if sync_bets:
        try:
            from app.bet_sync import sync_all_strategy_bets

            bet_sync = sync_all_strategy_bets(state)
            logger.info(
                "Post-refresh bet sync: inserted_total=%s",
                (bet_sync or {}).get("inserted_total"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Post-refresh bet sync failed: %s", exc)
            bet_sync = {"ok": False, "error": str(exc).strip() or repr(exc)}

    return {
        "success": True,
        "scraped_at": scraped["scraped_at"],
        "match_count": len(merged),
        "snapshot": snapshot,
        "bet_sync": bet_sync,
    }
