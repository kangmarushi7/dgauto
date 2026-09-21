"""DataGaffer daily_accuracy.json — corners / SOT actuals for H2H prop settlement.

Primary settlement source for ``h2h_corners`` / ``h2h_sot`` (Football Bot style).
Pair fields like ``\"5 - 5\"`` are summed to a match total.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.dg_feeds import DAILY_ACCURACY_URL, _load_json

logger = logging.getLogger(__name__)


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


def lookup_accuracy_props(
    entry: dict[str, Any],
    *,
    force_refresh: bool = False,
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
    want_date = _date_key(entry.get("fixture_date"))

    best: dict[str, Any] | None = None
    best_score = 0.0
    for row in rows:
        if want_date and row.get("date") and row["date"] != want_date:
            # Allow ±0 days only — accuracy date is kickoff calendar day.
            continue
        rh = str(row.get("home") or "")
        ra = str(row.get("away") or "")
        if not rh or not ra:
            # Fall back to full match label similarity.
            score = _team_similarity(f"{home} vs {away}", str(row.get("match") or ""))
        else:
            score = min(_team_similarity(home, rh), _team_similarity(away, ra))
        if score > best_score:
            best_score = score
            best = row

    if best is not None and best_score >= 0.55:
        return best
    return None
