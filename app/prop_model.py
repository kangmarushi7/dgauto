"""Read-only bridge to the prop-model-engine SQLite package."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "prop-model-engine" / "data" / "prop-model.db"


def prop_model_db_path() -> Path:
    raw = os.getenv("PROP_MODEL_DB_PATH", "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_DB


def _connect() -> sqlite3.Connection | None:
    path = prop_model_db_path()
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn = _connect()
    if conn is None:
        return []
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    rows = _rows(sql, params)
    return rows[0] if rows else None


def db_status() -> dict[str, Any]:
    path = prop_model_db_path()
    exists = path.exists()
    return {
        "ok": exists,
        "path": str(path),
        "exists": exists,
        "phase": 1,
        "phase_label": "Stats scrapers + normalizer",
    }


def player_counts() -> dict[str, int]:
    rows = _rows("SELECT sport, COUNT(*) AS count FROM players GROUP BY sport")
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
        FROM scrape_log
        WHERE id IN (SELECT MAX(id) FROM scrape_log GROUP BY source)
        ORDER BY scraped_at DESC
        """
    )


def recent_scrape_log(limit: int = 40) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id, source, status, error_message, detail_json, scraped_at
        FROM scrape_log
        ORDER BY scraped_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )


def recent_stats(limit: int = 50) -> list[dict[str, Any]]:
    rows = _rows(
        """
        SELECT ps.id, ps.player_id, p.name AS player_name, p.team, p.sport,
               ps.source, ps.scraped_at, ps.stat_json
        FROM player_stats_raw ps
        LEFT JOIN players p ON p.id = ps.player_id
        ORDER BY ps.scraped_at DESC, ps.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    for row in rows:
        raw = row.get("stat_json")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                row["stat_type"] = parsed.get("stat_type")
                row["value"] = parsed.get("value")
            except json.JSONDecodeError:
                row["stat_type"] = None
                row["value"] = None
        row.pop("stat_json", None)
    return rows


def edge_counts() -> dict[str, int]:
    """Phase 4 stub — safe if table empty."""
    row = _one("SELECT COUNT(*) AS count FROM edges")
    return {"edges": int((row or {}).get("count") or 0)}


def build_prop_model_dashboard() -> dict[str, Any]:
    status = db_status()
    return {
        "status": status,
        "players": player_counts() if status["exists"] else {"nba": 0, "mlb": 0, "total": 0},
        "last_scrapes": last_scrape_by_source() if status["exists"] else [],
        "scrape_log": recent_scrape_log() if status["exists"] else [],
        "recent_stats": recent_stats() if status["exists"] else [],
        "edges": edge_counts() if status["exists"] else {"edges": 0},
        "setup": {
            "package": "prop-model-engine",
            "commands": [
                "cd prop-model-engine",
                "npm install && npx playwright install chromium",
                "npm run db:init",
                "npm run scrape:nba",
                "npm run scrape:mlb",
            ],
        },
    }
