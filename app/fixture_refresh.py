"""Pull latest fixtures from DataGaffer and persist merged slate."""
from __future__ import annotations

from typing import Any

from app.db import save_state
from app.scraper import scrape_datagaffer_sync
from app.signals import merge_outlooks


def refresh_fixtures_sync() -> dict[str, Any]:
    """Scrape DataGaffer feeds and write latest slate to storage."""
    scraped = scrape_datagaffer_sync()
    merged = merge_outlooks(scraped["win_rows"], scraped["goal_rows"])
    save_state(
        "latest_data",
        {
            "scraped_at": scraped["scraped_at"],
            "matches": merged,
            "fixtures_by_id": scraped.get("fixtures_by_id") or {},
            "dg_extra_indexes": scraped.get("dg_extra_indexes") or {},
        },
    )
    return {
        "success": True,
        "scraped_at": scraped["scraped_at"],
        "match_count": len(merged),
    }
