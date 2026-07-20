"""Prop Model Engine — shared DB access + dashboard payloads.

Uses the app SQLAlchemy engine (DATABASE_URL Postgres in prod, local SQLite otherwise).
Tables are prefixed pm_* so they never mix with DG bet_entries logs.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.db import engine

ROOT = Path(__file__).resolve().parents[1]
PG_SCHEMA_PATH = ROOT / "prop-model-engine" / "db" / "schema.postgres.sql"
SQLITE_SCHEMA_PATH = ROOT / "prop-model-engine" / "db" / "schema.sqlite.sql"

_scrape_lock = threading.Lock()
_scrape_state: dict[str, Any] = {
    "running": False,
    "sport": None,
    "started_at": None,
    "finished_at": None,
    "result": None,
    "error": None,
}


def uses_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


def _jsonable(value: Any) -> Any:
    """Make DB values safe for JSONResponse / Jinja tojson."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in row.items()}


def _run_schema_file(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with engine.begin() as conn:
        for stmt in statements:
            lines = [ln for ln in stmt.splitlines() if ln.strip() and not ln.strip().startswith("--")]
            if not lines:
                continue
            conn.execute(text("\n".join(lines)))


def init_prop_model_tables() -> None:
    """Create pm_* tables on the shared app engine."""
    path = PG_SCHEMA_PATH if uses_postgres() else SQLITE_SCHEMA_PATH
    if not path.exists():
        raise FileNotFoundError(f"Missing schema: {path}")
    _run_schema_file(path)


def _rows(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return [_jsonable_row(dict(r._mapping)) for r in result]
    except Exception:
        return []


def _one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = _rows(sql, params)
    return rows[0] if rows else None


def _execute(sql: str, params: dict[str, Any] | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def db_status() -> dict[str, Any]:
    row = _one("SELECT COUNT(*) AS count FROM pm_players")
    ok = row is not None
    return {
        "ok": ok,
        "backend": "postgres" if uses_postgres() else "sqlite",
        "path": "DATABASE_URL" if uses_postgres() else "data/dgauto.db (shared app DB)",
        "exists": ok,
        "phase": 1,
        "phase_label": "Stats scrapers + normalizer",
    }


def player_counts() -> dict[str, int]:
    rows = _rows("SELECT sport, COUNT(*) AS count FROM pm_players GROUP BY sport")
    out = {"nba": 0, "mlb": 0, "total": 0}
    for r in rows:
        sport = str(r.get("sport") or "").lower()
        count = int(r.get("count") or 0)
        if sport in out:
            out[sport] = count
        out["total"] += count
    return out


def last_scrape_by_source() -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT source, status, error_message, scraped_at
        FROM pm_scrape_log
        WHERE id IN (SELECT MAX(id) FROM pm_scrape_log GROUP BY source)
        ORDER BY scraped_at DESC
        """
    )


def recent_scrape_log(limit: int = 40) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id, source, status, error_message, detail_json, scraped_at
        FROM pm_scrape_log
        ORDER BY scraped_at DESC, id DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )


def recent_stats(limit: int = 50) -> list[dict[str, Any]]:
    rows = _rows(
        """
        SELECT ps.id, ps.player_id, p.name AS player_name, p.team, p.sport,
               ps.source, ps.scraped_at, ps.stat_json
        FROM pm_player_stats_raw ps
        LEFT JOIN pm_players p ON p.id = ps.player_id
        ORDER BY ps.scraped_at DESC, ps.id DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    for row in rows:
        raw = row.get("stat_json")
        if isinstance(raw, dict):
            row["stat_type"] = raw.get("stat_type")
            row["value"] = raw.get("value")
        elif isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                row["stat_type"] = parsed.get("stat_type")
                row["value"] = parsed.get("value")
            except json.JSONDecodeError:
                row["stat_type"] = None
                row["value"] = None
        else:
            row["stat_type"] = None
            row["value"] = None
        row.pop("stat_json", None)
    return rows


def edge_counts() -> dict[str, int]:
    row = _one("SELECT COUNT(*) AS count FROM pm_edges")
    return {"edges": int((row or {}).get("count") or 0)}


def bet_counts() -> dict[str, int]:
    row = _one("SELECT COUNT(*) AS count FROM pm_bets")
    open_row = _one("SELECT COUNT(*) AS count FROM pm_bets WHERE result IS NULL OR result = 'open'")
    return {
        "total": int((row or {}).get("count") or 0),
        "open": int((open_row or {}).get("count") or 0),
    }


def insert_scrape_log(
    source: str,
    status: str,
    error_message: str | None = None,
    detail: dict | list | None = None,
) -> None:
    detail_json = json.dumps(detail) if detail is not None else None
    if uses_postgres():
        _execute(
            """
            INSERT INTO pm_scrape_log (source, status, error_message, detail_json, scraped_at)
            VALUES (:source, :status, :error_message, CAST(:detail_json AS jsonb), NOW())
            """,
            {
                "source": source,
                "status": status,
                "error_message": error_message,
                "detail_json": detail_json,
            },
        )
    else:
        _execute(
            """
            INSERT INTO pm_scrape_log (source, status, error_message, detail_json, scraped_at)
            VALUES (:source, :status, :error_message, :detail_json, datetime('now'))
            """,
            {
                "source": source,
                "status": status,
                "error_message": error_message,
                "detail_json": detail_json,
            },
        )


def upsert_player(player_id: str, name: str, team: str | None, sport: str, position: str | None = None) -> None:
    if uses_postgres():
        _execute(
            """
            INSERT INTO pm_players (id, name, team, sport, position, updated_at)
            VALUES (:id, :name, :team, :sport, :position, NOW())
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name,
              team = COALESCE(EXCLUDED.team, pm_players.team),
              sport = EXCLUDED.sport,
              position = COALESCE(EXCLUDED.position, pm_players.position),
              updated_at = NOW()
            """,
            {"id": player_id, "name": name, "team": team, "sport": sport, "position": position},
        )
    else:
        _execute(
            """
            INSERT INTO pm_players (id, name, team, sport, position, updated_at)
            VALUES (:id, :name, :team, :sport, :position, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
              name = excluded.name,
              team = COALESCE(excluded.team, pm_players.team),
              sport = excluded.sport,
              position = COALESCE(excluded.position, pm_players.position),
              updated_at = datetime('now')
            """,
            {"id": player_id, "name": name, "team": team, "sport": sport, "position": position},
        )


def insert_stat_raw(player_id: str | None, source: str, stat: dict[str, Any], scraped_at: str) -> None:
    payload = json.dumps(stat)
    if uses_postgres():
        _execute(
            """
            INSERT INTO pm_player_stats_raw (player_id, source, stat_json, scraped_at)
            VALUES (:player_id, :source, CAST(:stat_json AS jsonb), :scraped_at)
            """,
            {"player_id": player_id, "source": source, "stat_json": payload, "scraped_at": scraped_at},
        )
    else:
        _execute(
            """
            INSERT INTO pm_player_stats_raw (player_id, source, stat_json, scraped_at)
            VALUES (:player_id, :source, :stat_json, :scraped_at)
            """,
            {"player_id": player_id, "source": source, "stat_json": payload, "scraped_at": scraped_at},
        )


def get_scrape_job_status() -> dict[str, Any]:
    with _scrape_lock:
        return dict(_scrape_state)


def set_scrape_job(**kwargs: Any) -> None:
    with _scrape_lock:
        _scrape_state.update(kwargs)


def build_prop_model_dashboard() -> dict[str, Any]:
    status = db_status()
    ready = bool(status.get("exists"))
    return {
        "status": status,
        "players": player_counts() if ready else {"nba": 0, "mlb": 0, "total": 0},
        "bets": bet_counts() if ready else {"total": 0, "open": 0},
        "last_scrapes": last_scrape_by_source() if ready else [],
        "scrape_log": recent_scrape_log() if ready else [],
        "recent_stats": recent_stats() if ready else [],
        "edges": edge_counts() if ready else {"edges": 0},
        "scrape_job": get_scrape_job_status(),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
