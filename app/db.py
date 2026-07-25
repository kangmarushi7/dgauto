from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    text,
    select,
)


def _database_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if raw:
        if raw.startswith("postgres://"):
            # Railway often provides postgres://, SQLAlchemy expects postgresql://
            raw = raw.replace("postgres://", "postgresql+psycopg://", 1)
        elif raw.startswith("postgresql://"):
            raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)
        return raw
    Path("data").mkdir(exist_ok=True)
    return "sqlite:///data/dgauto.db"


engine = create_engine(_database_url(), future=True)
metadata = MetaData()

app_state = Table(
    "app_state",
    metadata,
    Column("state_key", String(120), primary_key=True),
    Column("state_json", JSON, nullable=False),
)

bet_entries = Table(
    "bet_entries",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("log_type", String(40), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("fixture_date", String(64)),
    Column("fixture", Text, nullable=False),
    Column("league_name", String(200), nullable=False, default=""),
    Column("bet_type", String(50), nullable=False),
    Column("team_name", String(200), nullable=False, default=""),
    Column("qualifier_pct", Float),
    Column("odds", Float),
    Column("units", Float, nullable=False, default=1.0),
    Column("status", String(20), nullable=False, default="open"),
    Column("pnl_units", Float),
    Column("resolved_at", String(64)),
    UniqueConstraint(
        "log_type",
        "fixture_date",
        "fixture",
        "bet_type",
        "team_name",
        name="uq_bet_entries_dedupe",
    ),
)

# Immutable Arahus decision snapshots for export / fine-tuning analysis.
arahus_pick_snapshots = Table(
    "arahus_pick_snapshots",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("bet_id", String(64)),
    Column("created_at", String(64), nullable=False),
    Column("fixture_id", String(64)),
    Column("fixture_date", String(64)),
    Column("fixture", Text, nullable=False),
    Column("league_name", String(200), nullable=False, default=""),
    Column("home_team", String(200), nullable=False, default=""),
    Column("away_team", String(200), nullable=False, default=""),
    Column("decision", String(20), nullable=False, default="picked"),  # picked | skipped
    Column("bet_type", String(50), nullable=False, default=""),
    Column("team_name", String(200), nullable=False, default=""),
    Column("market_label", String(200), nullable=False, default=""),
    Column("confidence", Float),
    Column("model_pct", Float),
    Column("odds", Float),
    Column("implied_pct", Float),
    Column("edge", Float),
    Column("ev", Float),
    Column("units", Float),
    Column("archetype", String(80)),
    Column("engine_config", JSON),
    Column("context", JSON),
    Column("status", String(20), nullable=False, default="open"),
    Column("pnl_units", Float),
    Column("resolved_at", String(64)),
    UniqueConstraint(
        "fixture_date",
        "fixture",
        "bet_type",
        "team_name",
        "decision",
        name="uq_arahus_snap_dedupe",
    ),
)

# Immutable Arahus decision-log ("why" layer). Additive to bet_entries ledger.
# TODO(retention): volume is ~5–10× bet_entries (all evaluated markets + skips
# per sync). Consider archiving rows older than N months later — not implemented.
arahus_decision_log = Table(
    "arahus_decision_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fixture_id", String(64), index=True),
    Column("synced_at", String(64), nullable=False, index=True),
    Column("match_date", String(64), index=True),
    Column("league", String(200), index=True),
    Column("home_team", String(200), nullable=False, default=""),
    Column("away_team", String(200), nullable=False, default=""),
    Column("bet_type", String(80), nullable=False, default="", index=True),
    Column("status", String(40), nullable=False, index=True),
    Column("model_pct", Float),
    Column("confidence", Float),
    Column("odds", Float),
    Column("edge", Float),
    Column("ev", Float),
    Column("units", Float),
    Column("signals", JSON),
    Column("xg_home", Float),
    Column("xg_away", Float),
    Column("xg_total", Float),
    Column("pace_score", Float),
    Column("nec_index", Float),
    Column("agix_index", Float),
    Column("dgrtg_gap", Float),
    Column("archetype", String(80)),
    Column("luck_regression_value", Float),
    Column("calibration_debug", JSON),
    Column("engine_config_snapshot", JSON, nullable=False),
    Column("engine_version", String(40), nullable=False, default=""),
    Column("result", String(10)),  # W | L | push
    Column("pnl", Float),  # real money — only for status=picked
    Column("hypothetical_pnl", Float),
    Column("resolved_at", String(64)),
    Column("team_name", String(200), nullable=False, default=""),
    Column("fixture", Text, nullable=False, default=""),
)


def init_db() -> None:
    metadata.create_all(engine)
    # Prop Model Engine tables (pm_*) live on the same DATABASE_URL Postgres.
    try:
        from app.prop_model import init_prop_model_tables

        init_prop_model_tables()
    except Exception as exc:
        # Don't block app boot if prop-model schema file is missing locally.
        print(f"[prop_model] schema init skipped/failed: {exc}")


def load_state(key: str, default: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            select(app_state.c.state_json).where(app_state.c.state_key == key)
        ).first()
    if not row:
        return default
    value = row[0]
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value or default


def save_state(key: str, payload: dict[str, Any]) -> None:
    with engine.begin() as conn:
        existing = conn.execute(
            select(app_state.c.state_key).where(app_state.c.state_key == key)
        ).first()
        if existing:
            conn.execute(
                app_state.update().where(app_state.c.state_key == key).values(state_json=payload)
            )
        else:
            conn.execute(app_state.insert().values(state_key=key, state_json=payload))


def list_bets(log_type: str) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            select(bet_entries).where(bet_entries.c.log_type == log_type)
        ).mappings()
        return [dict(r) for r in rows]


def insert_bets(log_type: str, bets: list[dict[str, Any]]) -> int:
    existing_keys = {
        (e.get("fixture_date"), e.get("fixture", ""), e.get("bet_type", ""), e.get("team_name", ""))
        for e in list_bets(log_type)
    }
    to_insert = []
    for b in bets:
        key = (b.get("fixture_date"), b.get("fixture", ""), b.get("bet_type", ""), b.get("team_name", ""))
        if key in existing_keys:
            continue
        existing_keys.add(key)
        row = dict(b)
        row["log_type"] = log_type
        to_insert.append(row)

    if not to_insert:
        return 0
    with engine.begin() as conn:
        conn.execute(bet_entries.insert(), to_insert)
    return len(to_insert)


def delete_bets_by_ids(log_type: str, bet_ids: list[str]) -> int:
    """Hard-delete specific bet rows (used by resync-today)."""
    ids = [str(b) for b in bet_ids if b]
    if not ids:
        return 0
    with engine.begin() as conn:
        result = conn.execute(
            bet_entries.delete().where(
                bet_entries.c.log_type == log_type,
                bet_entries.c.id.in_(ids),
            )
        )
    return int(result.rowcount or 0)


def update_bet_odds(log_type: str, bet_id: str, odds: float) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(bet_entries).where(
                bet_entries.c.log_type == log_type,
                bet_entries.c.id == bet_id,
            )
        ).mappings().first()
        if not row:
            return None
        conn.execute(
            bet_entries.update()
            .where(bet_entries.c.id == bet_id, bet_entries.c.log_type == log_type)
            .values(odds=odds)
        )
        updated = dict(row)
        updated["odds"] = odds
        return updated


def update_bet_stake_and_pnl(
    log_type: str,
    bet_id: str,
    *,
    units: float,
    pnl_units: float | None = None,
) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(bet_entries).where(
                bet_entries.c.log_type == log_type,
                bet_entries.c.id == bet_id,
            )
        ).mappings().first()
        if not row:
            return None
        values: dict[str, Any] = {"units": units}
        if pnl_units is not None:
            values["pnl_units"] = pnl_units
        conn.execute(
            bet_entries.update()
            .where(bet_entries.c.id == bet_id, bet_entries.c.log_type == log_type)
            .values(**values)
        )
        updated = dict(row)
        updated.update(values)
        return updated


def resolve_bet_entry(log_type: str, bet_id: str, result: str, pnl_units: float, resolved_at: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(bet_entries).where(
                bet_entries.c.log_type == log_type, bet_entries.c.id == bet_id
            )
        ).mappings().first()
        if not row:
            return None
        conn.execute(
            bet_entries.update()
            .where(bet_entries.c.log_type == log_type, bet_entries.c.id == bet_id)
            .values(status=result, pnl_units=pnl_units, resolved_at=resolved_at)
        )
        updated = dict(row)
        updated["status"] = result
        updated["pnl_units"] = pnl_units
        updated["resolved_at"] = resolved_at

    if log_type == "arahus":
        try:
            update_arahus_snapshot_result(
                bet_id=str(bet_id),
                fixture_date=updated.get("fixture_date"),
                fixture=str(updated.get("fixture") or ""),
                bet_type=str(updated.get("bet_type") or ""),
                team_name=str(updated.get("team_name") or ""),
                status=result,
                pnl_units=pnl_units,
                resolved_at=resolved_at,
            )
        except Exception:
            pass
    return updated


def insert_arahus_snapshots(rows: list[dict[str, Any]]) -> int:
    """Insert immutable Arahus snapshots; skip rows that already exist (dedupe key)."""
    if not rows:
        return 0
    inserted = 0
    with engine.begin() as conn:
        existing = {
            (
                r.get("fixture_date"),
                r.get("fixture") or "",
                r.get("bet_type") or "",
                r.get("team_name") or "",
                r.get("decision") or "picked",
            )
            for r in conn.execute(select(arahus_pick_snapshots)).mappings()
        }
        to_insert: list[dict[str, Any]] = []
        for row in rows:
            key = (
                row.get("fixture_date"),
                row.get("fixture") or "",
                row.get("bet_type") or "",
                row.get("team_name") or "",
                row.get("decision") or "picked",
            )
            if key in existing:
                continue
            existing.add(key)
            to_insert.append(row)
        if to_insert:
            conn.execute(arahus_pick_snapshots.insert(), to_insert)
            inserted = len(to_insert)
    return inserted


def update_arahus_snapshot_result(
    *,
    bet_id: str | None,
    fixture_date: str | None,
    fixture: str,
    bet_type: str,
    team_name: str,
    status: str,
    pnl_units: float,
    resolved_at: str,
) -> int:
    """Backfill settle fields on matching snapshot(s). Prefer bet_id, else dedupe key."""
    values = {"status": status, "pnl_units": pnl_units, "resolved_at": resolved_at}
    with engine.begin() as conn:
        if bet_id:
            result = conn.execute(
                arahus_pick_snapshots.update()
                .where(arahus_pick_snapshots.c.bet_id == bet_id)
                .values(**values)
            )
            if int(result.rowcount or 0) > 0:
                return int(result.rowcount or 0)
        result = conn.execute(
            arahus_pick_snapshots.update()
            .where(
                arahus_pick_snapshots.c.fixture_date == fixture_date,
                arahus_pick_snapshots.c.fixture == fixture,
                arahus_pick_snapshots.c.bet_type == bet_type,
                arahus_pick_snapshots.c.team_name == team_name,
                arahus_pick_snapshots.c.decision == "picked",
            )
            .values(**values, bet_id=bet_id)
        )
        return int(result.rowcount or 0)


def list_arahus_snapshots(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    decision: str | None = None,
) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        stmt = select(arahus_pick_snapshots)
        rows = [dict(r) for r in conn.execute(stmt).mappings()]

    def _in_range(row: dict[str, Any]) -> bool:
        d = str(row.get("fixture_date") or row.get("created_at") or "")[:10]
        if date_from and d and d < date_from[:10]:
            return False
        if date_to and d and d > date_to[:10]:
            return False
        if decision and str(row.get("decision") or "") != decision:
            return False
        return True

    out = [r for r in rows if _in_range(r)]
    out.sort(
        key=lambda r: (
            str(r.get("fixture_date") or ""),
            str(r.get("fixture") or ""),
            str(r.get("bet_type") or ""),
        )
    )
    return out


def insert_arahus_decision_log(rows: list[dict[str, Any]]) -> int:
    """Append decision-log rows (one sync = new immutable rows; no dedupe)."""
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(arahus_decision_log.insert(), rows)
    return len(rows)


def list_arahus_decision_log(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    league: str | None = None,
    status: str | None = None,
    unresolved_only: bool = False,
) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = [dict(r) for r in conn.execute(select(arahus_decision_log)).mappings()]

    out: list[dict[str, Any]] = []
    for row in rows:
        d = str(row.get("match_date") or row.get("synced_at") or "")[:10]
        if date_from and d and d < date_from[:10]:
            continue
        if date_to and d and d > date_to[:10]:
            continue
        if league and str(row.get("league") or "") != league:
            continue
        if status and str(row.get("status") or "") != status:
            continue
        if unresolved_only and row.get("resolved_at"):
            continue
        out.append(row)
    out.sort(
        key=lambda r: (
            str(r.get("match_date") or ""),
            str(r.get("fixture") or ""),
            str(r.get("bet_type") or ""),
            int(r.get("id") or 0),
        )
    )
    return out


def update_arahus_decision_log_result(
    row_id: int,
    *,
    result: str,
    pnl: float | None,
    hypothetical_pnl: float | None,
    resolved_at: str,
) -> dict[str, Any] | None:
    """Settle one decision-log row. No-op if already resolved (caller should check)."""
    with engine.begin() as conn:
        row = conn.execute(
            select(arahus_decision_log).where(arahus_decision_log.c.id == row_id)
        ).mappings().first()
        if not row:
            return None
        if row.get("resolved_at"):
            return dict(row)
        conn.execute(
            arahus_decision_log.update()
            .where(arahus_decision_log.c.id == row_id)
            .values(
                result=result,
                pnl=pnl,
                hypothetical_pnl=hypothetical_pnl,
                resolved_at=resolved_at,
            )
        )
        updated = dict(row)
        updated["result"] = result
        updated["pnl"] = pnl
        updated["hypothetical_pnl"] = hypothetical_pnl
        updated["resolved_at"] = resolved_at
        return updated


def check_db_health() -> dict[str, Any]:
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True, "database_url_set": bool(os.getenv("DATABASE_URL", "").strip())}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
