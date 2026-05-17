from __future__ import annotations

import logging
import os
from datetime import timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.auto_resolve import auto_resolve_open_bets

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

# Fixed IST when system tzdata / Python tzdata package is unavailable (minimal Linux images).
IST_FIXED = timezone(timedelta(hours=5, minutes=30), name="IST")


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _parse_hhmm(raw: str) -> tuple[int, int]:
    text = (raw or "04:30").strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time {raw!r}; expected HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time {raw!r}")
    return hour, minute


def _resolve_timezone(tz_name: str):
    """Return a tzinfo for scheduling. Never raises — falls back to fixed IST or UTC."""
    name = (tz_name or "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ModuleNotFoundError, Exception) as exc:
        logger.warning("ZoneInfo(%r) unavailable (%s)", name, exc)

    if name in {"Asia/Kolkata", "Asia/Calcutta"}:
        logger.info("Using fixed IST offset (UTC+5:30) for scheduled auto-resolve")
        return IST_FIXED
    if name == "UTC":
        return timezone.utc

    logger.warning("Falling back to UTC for timezone %r", name)
    return timezone.utc


def run_all_auto_resolves() -> dict[str, Any]:
    """Resolve open bets for main bet log (incl. legacy) and LM strat bet log."""
    summary: dict[str, Any] = {"main": None, "lm": None}
    for log_type in ("main", "lm"):
        try:
            summary[log_type] = auto_resolve_open_bets(log_type)
        except Exception as exc:
            logger.exception("Auto-resolve failed for log_type=%s", log_type)
            summary[log_type] = {
                "open_checked": 0,
                "resolved": 0,
                "error": str(exc).strip() or repr(exc),
            }
    logger.info("Auto-resolve run finished: %s", summary)
    return summary


def start_auto_resolve_scheduler() -> BackgroundScheduler | None:
    """Schedule daily auto-resolve at AUTO_RESOLVE_TIME in AUTO_RESOLVE_TIMEZONE (default 04:30 IST)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if not _env_flag("AUTO_RESOLVE_SCHEDULE_ENABLED", default=True):
        logger.info("Scheduled auto-resolve is disabled (AUTO_RESOLVE_SCHEDULE_ENABLED=false)")
        return None

    try:
        hour, minute = _parse_hhmm(os.getenv("AUTO_RESOLVE_TIME", "04:30"))
    except ValueError as exc:
        logger.error("%s — scheduler not started", exc)
        return None

    tz_name = os.getenv("AUTO_RESOLVE_TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"
    tz = _resolve_timezone(tz_name)

    try:
        scheduler = BackgroundScheduler(timezone=tz)
        scheduler.add_job(
            run_all_auto_resolves,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
            id="daily_auto_resolve",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        scheduler.start()
    except Exception as exc:
        logger.exception("Failed to start auto-resolve scheduler: %s", exc)
        return None

    _scheduler = scheduler
    logger.info(
        "Scheduled auto-resolve daily at %02d:%02d %s (main + lm bet logs)",
        hour,
        minute,
        getattr(tz, "key", tz),
    )
    return scheduler


def stop_auto_resolve_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Auto-resolve scheduler stopped")
