"""DataGaffer daily_accuracy.json — FT scores + corners / SOT for settlement.

Primary settlement source for all soccer strategy logs (goals, 1X2, BTTS, CS,
corners, SOT). Pair fields like ``\"5 - 5\"`` are summed to a match total.
Flashscore / API-Football remain fallbacks when the accuracy feed lags or misses.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date
from typing import Any

from app.dg_feeds import DAILY_ACCURACY_URL, _load_json

logger = logging.getLogger(__name__)

# DataGaffer accuracy calendar dates can lag/lead UTC fixture_date by one day.
ACCURACY_DATE_SLACK_DAYS = 1


def _parse_fixture(label: str) -> tuple[str, str]:
    # Local copy to avoid circular import with auto_resolve.
    text = (label or "").strip()
    if " vs " in text:
        a, b = text.split(" vs ", 1)
        return a.strip(), b.strip()
    if " v " in text.lower():
        # rare " v " separator
        parts = re.split(r"\s+v\s+", text, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    return "", ""


def _team_similarity(a: str, b: str) -> float:
    from app.auto_resolve import _team_similarity as _sim

    return _sim(a, b)

ACCURACY_PROPS_TTL_SEC = 30 * 60  # 30m — feed updates after matches settle

_cache: dict[str, Any] = {
    "fetched_at": 0.0,
    "by_fixture_id": {},
    "rows": [],
}

_PAIR_RE = re.compile(r"^(\d+)\s*[-–]\s*(\d+)$")


def parse_pair_total(raw: Any) -> int | None:
    """Parse ``\"5 - 5\"`` / int / float → total corners or SOT."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)) and raw == raw:  # not NaN
        return int(round(float(raw)))
    if isinstance(raw, str):
        text = raw.strip()
        m = _PAIR_RE.match(text)
        if m:
            return int(m.group(1)) + int(m.group(2))
        try:
            return int(round(float(text)))
        except ValueError:
            return None
    return None


def parse_actual_score(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, str):
        return None
    m = _PAIR_RE.match(raw.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _date_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # ISO / datetime → YYYY-MM-DD
    if "T" in text:
        text = text.split("T", 1)[0]
    if " " in text and len(text) >= 10:
        text = text.split(" ", 1)[0]
    return text[:10]


def clear_accuracy_props_cache() -> None:
    _cache["fetched_at"] = 0.0
    _cache["by_fixture_id"] = {}
    _cache["rows"] = []


def load_accuracy_prop_rows(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Flatten ``daily[].matches`` into prop rows (cached)."""
    now = time.time()
    rows = _cache.get("rows") or []
    fetched_at = float(_cache.get("fetched_at") or 0)
    if (
        not force_refresh
        and rows
        and (now - fetched_at) < ACCURACY_PROPS_TTL_SEC
    ):
        return list(rows)

    try:
        payload = _load_json(DAILY_ACCURACY_URL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("daily_accuracy fetch failed: %s", exc)
        return list(rows) if rows else []

    days = payload.get("daily") if isinstance(payload, dict) else None
    if not isinstance(days, list):
        return list(rows) if rows else []

    out: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for day in days:
        if not isinstance(day, dict):
            continue
        day_date = _date_key(day.get("date"))
        for match in day.get("matches") or []:
            if not isinstance(match, dict):
                continue
            fid = match.get("fixture_id")
            label = str(match.get("match") or "").strip()
            corners = parse_pair_total(match.get("actual_corners"))
            sot = parse_pair_total(match.get("actual_sot"))
            score = parse_actual_score(match.get("actual_score"))
            if corners is None and sot is None and score is None:
                continue
            home, away = _parse_fixture(label)
            row = {
                "fixture_id": str(fid) if fid is not None else "",
                "date": _date_key(match.get("date")) or day_date,
                "match": label,
                "home": home,
                "away": away,
                "league": str(match.get("league") or ""),
                "corners_total": corners,
                "sot_total": sot,
                "intHomeScore": score[0] if score else None,
                "intAwayScore": score[1] if score else None,
                "source": "datagaffer_daily_accuracy",
            }
            out.append(row)
            if row["fixture_id"]:
                by_id[row["fixture_id"]] = row

    _cache["rows"] = out
    _cache["by_fixture_id"] = by_id
    _cache["fetched_at"] = now
    return list(out)


def _parse_iso_date(value: Any) -> date | None:
    text = _date_key(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _date_within_slack(want: date | None, row_date: Any, *, slack_days: int) -> bool:
    if want is None:
        return True
    got = _parse_iso_date(row_date)
    if got is None:
        return True
    return abs((got - want).days) <= slack_days


def _team_row_score(home: str, away: str, row: dict[str, Any]) -> float:
    rh = str(row.get("home") or "")
    ra = str(row.get("away") or "")
    if not rh or not ra:
        return _team_similarity(f"{home} vs {away}", str(row.get("match") or ""))
    return min(_team_similarity(home, rh), _team_similarity(away, ra))


def lookup_accuracy_props(
    entry: dict[str, Any],
    *,
    force_refresh: bool = False,
    date_slack_days: int = ACCURACY_DATE_SLACK_DAYS,
) -> dict[str, Any] | None:
    """Find corners/SOT totals for a bet log entry from daily_accuracy."""
    rows = load_accuracy_prop_rows(force_refresh=force_refresh)
    if not rows:
        return None

    fid = entry.get("fixture_id")
    if fid is not None and str(fid).strip():
        hit = (_cache.get("by_fixture_id") or {}).get(str(fid).strip())
        if hit:
            return hit

    home, away = _parse_fixture(str(entry.get("fixture") or ""))
    if not home or not away:
        return None
    want_date = _parse_iso_date(entry.get("fixture_date"))

    def _best_in_rows(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
        best: dict[str, Any] | None = None
        best_score = 0.0
        for row in candidates:
            score = _team_row_score(home, away, row)
            if score > best_score:
                best_score = score
                best = row
        return best, best_score

    # Prefer exact calendar-day matches; fall back to ±slack when DG date drifts.
    exact_rows = [
        row
        for row in rows
        if want_date is None
        or not row.get("date")
        or _parse_iso_date(row.get("date")) == want_date
    ]
    best, best_score = _best_in_rows(exact_rows)
    if best is not None and best_score >= 0.55:
        return best

    if date_slack_days > 0 and want_date is not None:
        slack_rows = [
            row
            for row in rows
            if _date_within_slack(want_date, row.get("date"), slack_days=date_slack_days)
        ]
        best, best_score = _best_in_rows(slack_rows)
        if best is not None and best_score >= 0.55:
            return best
    return None
