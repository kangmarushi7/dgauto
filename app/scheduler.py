from __future__ import annotations

import logging
import os
from datetime import timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.auto_resolve import auto_resolve_open_bets
from app.fixture_refresh import refresh_fixtures_sync

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

# Fixed IST when system tzdata / Python tzdata package is unavailable (minimal Linux images).
IST_FIXED = timezone(timedelta(hours=5, minutes=30), name="IST")

DEFAULT_FIXTURE_REFRESH_INTERVAL_HOURS = 6
DEFAULT_FIXTURE_REFRESH_ANCHOR_HOUR = 9


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


def _parse_positive_int(raw: str, *, default: int, name: str) -> int:
    text = (raw or str(default)).strip()
    try:
        value = int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {name} {raw!r}; expected positive integer") from exc
    if value <= 0:
        raise ValueError(f"Invalid {name} {raw!r}; must be > 0")
    return value


def _resolve_timezone(tz_name: str):
    """Return a tzinfo for scheduling. Never raises — falls back to fixed IST or UTC."""
    name = (tz_name or "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ModuleNotFoundError, Exception) as exc:
        logger.warning("ZoneInfo(%r) unavailable (%s)", name, exc)

    if name in {"Asia/Kolkata", "Asia/Calcutta"}:
        logger.info("Using fixed IST offset (UTC+5:30) for scheduled jobs")
        return IST_FIXED
    if name == "UTC":
        return timezone.utc

    logger.warning("Falling back to UTC for timezone %r", name)
    return timezone.utc


def fixture_refresh_hours(anchor_hour: int, interval_hours: int) -> list[int]:
    """Hours (0–23) for recurring refresh, anchored so anchor_hour is always included."""
    if not (0 <= anchor_hour <= 23):
        raise ValueError(f"Invalid anchor hour {anchor_hour}; expected 0–23")
    if interval_hours <= 0 or 24 % interval_hours != 0:
        raise ValueError(
            f"Invalid interval {interval_hours}; must divide 24 evenly (e.g. 6 → 4 runs/day)"
        )
    hours: list[int] = []
    hour = anchor_hour
    for _ in range(24 // interval_hours):
        hours.append(hour % 24)
        hour += interval_hours
    return sorted(set(hours))


def run_fixture_refresh() -> dict[str, Any]:
    """Scheduled pull of DataGaffer fixtures (same as POST /api/refresh)."""
    try:
        result = refresh_fixtures_sync()
        logger.info(
            "Fixture refresh completed: %s matches at %s",
            result.get("match_count"),
            result.get("scraped_at"),
        )
        return result
    except Exception as exc:
        logger.exception("Fixture refresh failed: %s", exc)
        return {
            "success": False,
            "error": str(exc).strip() or repr(exc),
        }


def run_all_auto_resolves() -> dict[str, Any]:
    """Resolve open bets for main bet log (incl. legacy), LM, and NO strat bet logs."""
    summary: dict[str, Any] = {"main": None, "lm": None, "no": None, "ev": None}
    for log_type in ("main", "lm", "no", "ev"):
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


def _add_fixture_refresh_job(scheduler: BackgroundScheduler, tz) -> None:
    if not _env_flag("FIXTURE_REFRESH_SCHEDULE_ENABLED", default=True):
        logger.info("Scheduled fixture refresh is disabled (FIXTURE_REFRESH_SCHEDULE_ENABLED=false)")
        return

    try:
        interval = _parse_positive_int(
            os.getenv("FIXTURE_REFRESH_INTERVAL_HOURS", str(DEFAULT_FIXTURE_REFRESH_INTERVAL_HOURS)),
            default=DEFAULT_FIXTURE_REFRESH_INTERVAL_HOURS,
            name="FIXTURE_REFRESH_INTERVAL_HOURS",
        )
        anchor = _parse_positive_int(
            os.getenv("FIXTURE_REFRESH_ANCHOR_HOUR", str(DEFAULT_FIXTURE_REFRESH_ANCHOR_HOUR)),
            default=DEFAULT_FIXTURE_REFRESH_ANCHOR_HOUR,
            name="FIXTURE_REFRESH_ANCHOR_HOUR",
        )
        if anchor > 23:
            raise ValueError(f"Invalid FIXTURE_REFRESH_ANCHOR_HOUR {anchor}; expected 0–23")
        hours = fixture_refresh_hours(anchor, interval)
    except ValueError as exc:
        logger.error("%s — fixture refresh scheduler not started", exc)
        return

    scheduler.add_job(
        run_fixture_refresh,
        trigger=CronTrigger(hour=",".join(str(h) for h in hours), minute=0, timezone=tz),
        id="fixture_refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )
    tz_label = getattr(tz, "key", tz)
    hour_labels = ", ".join(f"{h:02d}:00" for h in hours)
    logger.info(
        "Scheduled fixture refresh every %dh (anchor %02d:00) at %s %s",
        interval,
        anchor,
        hour_labels,
        tz_label,
    )


def start_auto_resolve_scheduler() -> BackgroundScheduler | None:
    """Start background jobs: daily auto-resolve + periodic fixture refresh."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    tz_name = (
        os.getenv("FIXTURE_REFRESH_TIMEZONE")
        or os.getenv("AUTO_RESOLVE_TIMEZONE", "Asia/Kolkata")
    ).strip() or "Asia/Kolkata"
    tz = _resolve_timezone(tz_name)

    try:
        scheduler = BackgroundScheduler(timezone=tz)
    except Exception as exc:
        logger.exception("Failed to create scheduler: %s", exc)
        return None

    if _env_flag("AUTO_RESOLVE_SCHEDULE_ENABLED", default=True):
        try:
            hour, minute = _parse_hhmm(os.getenv("AUTO_RESOLVE_TIME", "04:30"))
            # Primary daily run (default 04:30 IST) plus extra daytime passes so
            # finished fixtures are not stuck open for days after a timeout/miss.
            resolve_hours = sorted({hour, 10, 16, 22})
            scheduler.add_job(
                run_all_auto_resolves,
                trigger=CronTrigger(
                    hour=",".join(str(h) for h in resolve_hours),
                    minute=minute,
                    timezone=tz,
                ),
                id="daily_auto_resolve",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            logger.info(
                "Scheduled auto-resolve at %s :%02d %s (main + lm + no + ev bet logs)",
                ", ".join(f"{h:02d}" for h in resolve_hours),
                minute,
                getattr(tz, "key", tz),
            )
        except ValueError as exc:
            logger.error("%s — auto-resolve job not scheduled", exc)
    else:
        logger.info("Scheduled auto-resolve is disabled (AUTO_RESOLVE_SCHEDULE_ENABLED=false)")

    _add_fixture_refresh_job(scheduler, tz)

    if not scheduler.get_jobs():
        logger.warning("No scheduled jobs configured — scheduler not started")
        return None

    try:
        scheduler.start()
    except Exception as exc:
        logger.exception("Failed to start scheduler: %s", exc)
        return None

    _scheduler = scheduler
    return scheduler


def stop_auto_resolve_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Background scheduler stopped")
