from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    Float,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
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


def init_db() -> None:
    metadata.create_all(engine)


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
        return updated
