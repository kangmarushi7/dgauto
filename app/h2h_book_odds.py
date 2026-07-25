"""DataGaffer book odds helpers for H2H Strat (corners).

``all_odds.json`` posts one main corners O/U line per fixture (e.g. Over 9.5 / 10.5).
We attach the decimal price only when that line matches the H2H market line.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.auto_resolve import _team_similarity
from app.dg_feeds import FEED_PATHS, _load_json, _match_key, _num

logger = logging.getLogger(__name__)

_CORNER_BET_TYPES = {
    "h2h_c_o85": 8.5,
    "h2h_c_o95": 9.5,
    "h2h_c_o105": 10.5,
}

_OVER_LINE_RE = re.compile(r"over\s*(\d+(?:\.\d+)?)", re.I)


def _parse_over_line(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    m = _OVER_LINE_RE.search(text)
    if m:
        return _num(m.group(1))
    return _num(text)


def load_corners_odds_index() -> dict[str, dict[str, Any]]:
    """``match_key → {line, odd, label, home, away}`` from DataGaffer all_odds."""
    raw = _load_json(FEED_PATHS["all_odds"])
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for label, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        home = str(payload.get("home_team") or "").strip()
        away = str(payload.get("away_team") or "").strip()
        if " vs " in str(label) and (not home or not away):
            parts = str(label).split(" vs ", 1)
            home, away = parts[0].strip(), parts[1].strip()
        markets = payload.get("markets") if isinstance(payload.get("markets"), dict) else {}
        corner = markets.get("corners_over_under") if isinstance(markets, dict) else None
        if not isinstance(corner, dict):
            continue
        line_obj = corner.get("line") if isinstance(corner.get("line"), dict) else {}
        line = _parse_over_line(line_obj.get("value"))
        odd = _num(line_obj.get("odd"))
        if line is None or odd is None or odd <= 1:
            continue
        key = _match_key(home, away)
        out[key] = {
            "line": line,
            "odd": round(odd, 3),
            "label": label,
            "home": home,
            "away": away,
        }
    return out


def _lookup_corner_row(
    index: dict[str, dict[str, Any]],
    home: str,
    away: str,
) -> dict[str, Any] | None:
    key = _match_key(home, away)
    if key in index:
        return index[key]
    # Fuzzy fallback when DG abbreviations differ from slate names.
    best: dict[str, Any] | None = None
    best_score = 0.0
    for row in index.values():
        hs = _team_similarity(home, str(row.get("home") or ""))
        aws = _team_similarity(away, str(row.get("away") or ""))
        score = min(hs, aws)
        if score > best_score:
            best_score = score
            best = row
    if best is not None and best_score >= 0.55:
        return best
    return None


def corner_book_odds(
    home: str,
    away: str,
    line: float,
    *,
    index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return ``{odds, book_line, source}`` when DG main corner line matches ``line``."""
    idx = index if index is not None else load_corners_odds_index()
    row = _lookup_corner_row(idx, home, away)
    if not row:
        return None
    book_line = float(row["line"])
    if abs(book_line - float(line)) > 0.01:
        return None
    return {
        "odds": float(row["odd"]),
        "book_line": book_line,
        "source": "datagaffer",
        "odds_source": "datagaffer",
    }


def attach_datagaffer_corner_odds(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill missing odds on H2H corner picks from DataGaffer all_odds."""
    if not picks:
        return []
    try:
        index = load_corners_odds_index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load DataGaffer all_odds for corners: %s", exc)
        return [dict(p) for p in picks]

    out: list[dict[str, Any]] = []
    for p in picks:
        row = dict(p)
        bt = str(row.get("bet_type") or "")
        want = _CORNER_BET_TYPES.get(bt)
        if want is None:
            out.append(row)
            continue
        if row.get("odds") is not None and float(row.get("odds") or 0) > 1:
            out.append(row)
            continue
        home = str(row.get("home") or "").strip()
        away = str(row.get("away") or "").strip()
        # Fallback: parse "Home vs Away" from fixture string.
        if (not home or not away) and " vs " in str(row.get("fixture") or ""):
            parts = str(row["fixture"]).split(" vs ", 1)
            home, away = parts[0].strip(), parts[1].strip()
        priced = corner_book_odds(home, away, want, index=index)
        if priced:
            row["odds"] = priced["odds"]
            row["odds_source"] = "datagaffer"
            row.pop("polymarket_url", None)
        out.append(row)
    return out
