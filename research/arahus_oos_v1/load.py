"""Load Arahus bet log for OOS validation (CSV export or DB)."""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from research.arahus_oos_v1.config import MARKET_ALIASES

DEFAULT_CSV = Path(
    "/home/ubuntu/.cursor/projects/workspace/uploads/arahus-log_e332.csv"
)

DATE_FORMATS = (
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d",
)


def normalize_market(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    s = re.sub(r"\s+", " ", s)
    if s in MARKET_ALIASES:
        return MARKET_ALIASES[s]
    # soft: over 2.5 variants
    if "over" in s and "2.5" in s and "3.5" not in s:
        return "over_2_5"
    if "over" in s and "3.5" in s:
        return "over_3_5"
    if "btts" in s:
        return "btts_yes" if "no" not in s else "btts_no"
    if "under" in s and "2.5" in s:
        return "under_2_5"
    return s or None


def parse_datetime(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    # ISO with Z
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_date_only(raw: Any) -> date | None:
    dt = parse_datetime(raw)
    return dt.date() if dt else None


def _f(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def normalize_status(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in {"won", "win", "w"}:
        return "won"
    if s in {"lost", "loss", "l"}:
        return "lost"
    if s in {"push", "void"}:
        return "push"
    if s in {"open", "pending", ""}:
        return "open"
    return s


def row_from_csv(r: dict[str, Any], *, source: str, idx: int) -> dict[str, Any]:
    fixture_date_raw = r.get("Fixture Date") or r.get("fixture_date")
    dt = parse_datetime(fixture_date_raw)
    market_raw = r.get("Market") or r.get("market") or r.get("bet_type")
    odds = _f(r.get("Odds") if "Odds" in r else r.get("odds"))
    units = _f(r.get("Units") if "Units" in r else r.get("units"))
    if units is None:
        units = 1.0
    conf = _f(r.get("Conf") if "Conf" in r else r.get("qualifier_pct") or r.get("confidence"))
    status = normalize_status(r.get("Status") or r.get("status"))
    pnl = _f(r.get("Unit PnL") if "Unit PnL" in r else r.get("pnl_units"))
    league = str(r.get("League") or r.get("league_name") or "").strip()
    fixture = str(r.get("Fixture") or r.get("fixture") or "").strip()
    return {
        "id": r.get("id") or f"csv:{idx}",
        "fixture_date_raw": fixture_date_raw,
        "fixture_date": dt.isoformat(sep=" ") if dt else None,
        "fixture_date_d": dt.date().isoformat() if dt else None,
        "fixture": fixture,
        "league_name": league,
        "market_raw": market_raw,
        "market": normalize_market(market_raw),
        "confidence": conf,
        "odds": odds,
        "units": units,
        "status": status,
        "pnl_units_logged": pnl,
        "closing_odds": _f(r.get("closing_odds")),
        "source": source,
        "row_index": idx,
    }


def load_csv(path: Path = DEFAULT_CSV) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            rows.append(row_from_csv(r, source=str(path), idx=i))
    return rows


def load_from_database(*, log_type: str = "arahus") -> list[dict[str, Any]]:
    """Optional: load from DATABASE_URL / local SQLite via app.db."""
    from app.db import list_bets

    raw = list_bets(log_type)
    out: list[dict[str, Any]] = []
    for i, e in enumerate(raw):
        market_raw = e.get("market_label") or e.get("bet_type")
        dt = parse_datetime(e.get("fixture_date"))
        out.append(
            {
                "id": e.get("id") or f"db:{i}",
                "fixture_date_raw": e.get("fixture_date"),
                "fixture_date": dt.isoformat(sep=" ") if dt else None,
                "fixture_date_d": dt.date().isoformat() if dt else None,
                "fixture": str(e.get("fixture") or ""),
                "league_name": str(e.get("league_name") or ""),
                "market_raw": market_raw,
                "market": normalize_market(market_raw),
                "confidence": _f(e.get("qualifier_pct") or e.get("confidence")),
                "odds": _f(e.get("odds")),
                "units": _f(e.get("units")) if e.get("units") is not None else 1.0,
                "status": normalize_status(e.get("status")),
                "pnl_units_logged": _f(e.get("pnl_units")),
                "closing_odds": _f(e.get("closing_odds")),
                "source": f"database:{log_type}",
                "row_index": i,
            }
        )
    return out
