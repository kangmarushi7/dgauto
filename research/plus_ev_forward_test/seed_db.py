"""Seed research ledger from production +EV bet log (DATABASE_URL / HTTP API)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from research.plus_ev_forward_test.clv import clv_from_odds
from research.plus_ev_forward_test.fair_market import fair_probability_for_selection
from research.plus_ev_forward_test.storage import DEFAULT_DATA_DIR, make_signal, upsert_signals

DEFAULT_APP_BASE_URL = "https://dgauto-production.up.railway.app"


def _status(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in {"won", "lost", "push", "open"}:
        return s
    return s or "open"


def _pnl(result: str | None, odds: float) -> float | None:
    if result == "won":
        return round(odds - 1.0, 4)
    if result == "lost":
        return -1.0
    if result == "push":
        return 0.0
    return None


def entry_to_signal(e: dict[str, Any], *, sample_kind: str, source: str) -> dict[str, Any] | None:
    try:
        odds = float(e.get("odds") or 0)
    except (TypeError, ValueError):
        return None
    if odds <= 1:
        return None
    try:
        ev_pct = float(e.get("qualifier_pct") or 0)
    except (TypeError, ValueError):
        ev_pct = 0.0
    ev = ev_pct / 100.0
    model_p = (1.0 + ev) / odds
    result = _status(str(e.get("status") or ""))
    outcome_odds: dict[str, float] = {}
    fair_p = fair_probability_for_selection(str(e.get("bet_type") or ""), outcome_odds)
    clv_info = clv_from_odds(odds, e.get("closing_odds"))
    signal = make_signal(
        signal_id=f"db:{e.get('id')}",
        fixture_id=e.get("fixture_id"),
        kickoff_time=e.get("fixture_date"),
        timestamp_signal_created=e.get("created_at"),
        league=e.get("league_name"),
        market=e.get("market") or e.get("bet_type"),
        bet_type=e.get("bet_type"),
        selection=e.get("team_name") or e.get("market") or e.get("bet_type"),
        bookmaker="datagaffer",
        odds_at_signal=odds,
        model_probability=model_p,
        raw_EV=ev,
        calibrated_probability=None,
        calibrated_EV=None,
        result=result,
        pnl_units=_pnl(result, odds) if result in {"won", "lost", "push"} else None,
        opposite_odds=None,
        outcome_odds=outcome_odds,
        fair_probability=fair_p,
        fair_market_edge=(model_p - fair_p) if fair_p is not None else None,
        odds_timestamp=e.get("created_at"),
        closing_odds=e.get("closing_odds"),
        closing_odds_timestamp=None,
        clv=clv_info.get("clv"),
        sample_kind=sample_kind,
        source=source,
        notes=[
            "Seeded from +EV bet log (log_type=ev).",
            "Closing/opposite odds usually unavailable historically — CLV/fair market may be null.",
            "research_only=true; can_place_real_bet=false",
        ],
    )
    signal["fixture"] = e.get("fixture")
    if not signal["portfolios"]:
        return None
    return signal


def _entries_to_signals(
    entries: list[dict[str, Any]],
    *,
    sample_kind: str,
    source: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for e in entries:
        sig = entry_to_signal(e, sample_kind=sample_kind, source=source)
        if sig:
            rows.append(sig)
    return rows


def load_entries_from_database(*, season: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load +EV bets via app.db. Requires DATABASE_URL or local data/dgauto.db."""
    from app.plus_ev_strat import load_plus_ev_bet_log
    from app.seasons import filter_entries_by_season

    meta = {
        "database_url_set": bool(os.getenv("DATABASE_URL", "").strip()),
        "source": "database_ev_bet_log",
    }
    entries = load_plus_ev_bet_log()
    if season is not None:
        entries = filter_entries_by_season(entries, season)
    meta["raw_ev_entries"] = len(entries)
    return entries, meta


def load_entries_from_api(
    *,
    base_url: str | None = None,
    season: int | None = None,
    timeout_sec: float = 60.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load +EV bets from production HTTP API (same data as VPS DB via the app)."""
    base = (base_url or os.getenv("APP_BASE_URL") or DEFAULT_APP_BASE_URL).rstrip("/")
    url = f"{base}/api/plus-ev-bet-log"
    if season is not None:
        url = f"{url}?season={int(season)}"
    meta: dict[str, Any] = {"source": "http_api_plus_ev_bet_log", "api_url": url, "base_url": base}
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "plus-ev-forward-test/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"API HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"API unreachable at {url}: {exc}") from exc

    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError(f"Unexpected API payload from {url} (missing entries list)")
    meta["raw_ev_entries"] = len(entries)
    meta["http_ok"] = True
    return entries, meta


def seed_from_database(
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    season: int | None = None,
) -> dict[str, Any]:
    """
    Load production +EV bets via app.db list_bets('ev').

    Requires DATABASE_URL (VPS/Railway Postgres) or local data/dgauto.db.
    """
    entries, meta = load_entries_from_database(season=season)
    rows = _entries_to_signals(
        entries,
        sample_kind="db_retrospective_seed",
        source="database_ev_bet_log",
    )
    stats = upsert_signals(data_dir, rows)
    stats.update(meta)
    stats.update({"seeded_with_portfolio": len(rows), "season_filter": season})
    return stats


def seed_from_api(
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    season: int | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Seed from live app HTTP API (reads the same Postgres-backed +EV log)."""
    entries, meta = load_entries_from_api(base_url=base_url, season=season)
    rows = _entries_to_signals(
        entries,
        sample_kind="api_retrospective_seed",
        source="http_api_plus_ev_bet_log",
    )
    stats = upsert_signals(data_dir, rows)
    stats.update(meta)
    stats.update({"seeded_with_portfolio": len(rows), "season_filter": season})
    return stats


def seed_from_vps(
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    season: int | None = None,
    base_url: str | None = None,
    prefer: str = "auto",
) -> dict[str, Any]:
    """
    Prefer DATABASE_URL when set; otherwise fall back to APP_BASE_URL HTTP API.

    prefer: 'auto' | 'db' | 'api'
    """
    mode = (prefer or "auto").strip().lower()
    db_url_set = bool(os.getenv("DATABASE_URL", "").strip())
    errors: list[str] = []

    if mode in {"auto", "db"} and (mode == "db" or db_url_set):
        try:
            stats = seed_from_database(data_dir, season=season)
            stats["seed_path"] = "database"
            if stats.get("raw_ev_entries", 0) > 0 or mode == "db":
                return stats
            errors.append("database returned 0 +EV entries")
        except Exception as exc:  # noqa: BLE001 — research CLI; report and fall through
            errors.append(f"database: {exc}")
            if mode == "db":
                raise

    if mode in {"auto", "api"}:
        try:
            stats = seed_from_api(data_dir, season=season, base_url=base_url)
            stats["seed_path"] = "api"
            stats["prior_errors"] = errors
            return stats
        except Exception as exc:  # noqa: BLE001
            errors.append(f"api: {exc}")
            if mode == "api":
                raise

    raise RuntimeError(
        "Could not seed from VPS data. Set DATABASE_URL (Postgres) or APP_BASE_URL "
        f"(app currently expected at {DEFAULT_APP_BASE_URL}). Errors: "
        + "; ".join(errors)
    )
