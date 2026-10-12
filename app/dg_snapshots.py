"""Immutable DataGaffer fixtures.json snapshots for point-in-time research."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import dg_fixture_snapshots, engine, init_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(fixtures: list[Any]) -> bytes:
    return json.dumps(
        fixtures, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_hash(fixtures: list[Any]) -> str:
    return hashlib.sha256(_canonical_bytes(fixtures)).hexdigest()


def save_fixtures_snapshot(
    *,
    scraped_at: str,
    fixtures: list[Any] | None,
) -> dict[str, Any]:
    """INSERT-only snapshot. Never updates an existing scraped_at payload.

    If ``scraped_at`` already exists, returns the stored row unchanged
    (immutability), even if the caller passes different fixtures.
    """
    init_db()
    fixtures_list = list(fixtures or [])
    digest = content_hash(fixtures_list)
    scraped = str(scraped_at or "").strip() or _now_iso()

    with engine.begin() as conn:
        existing = (
            conn.execute(
                select(dg_fixture_snapshots).where(
                    dg_fixture_snapshots.c.scraped_at == scraped
                )
            )
            .mappings()
            .first()
        )
        if existing:
            return {
                "id": existing["id"],
                "scraped_at": existing["scraped_at"],
                "content_hash": existing["content_hash"],
                "fixture_count": int(existing["fixture_count"] or 0),
                "created_at": existing["created_at"],
                "deduped": True,
            }

        row_id = str(uuid.uuid4())
        created = _now_iso()
        conn.execute(
            dg_fixture_snapshots.insert().values(
                id=row_id,
                scraped_at=scraped,
                content_hash=digest,
                fixture_count=len(fixtures_list),
                payload=fixtures_list,
                created_at=created,
            )
        )
        return {
            "id": row_id,
            "scraped_at": scraped,
            "content_hash": digest,
            "fixture_count": len(fixtures_list),
            "created_at": created,
            "deduped": False,
        }


def get_snapshot(
    *,
    snapshot_id: str | None = None,
    scraped_at: str | None = None,
) -> dict[str, Any] | None:
    init_db()
    with engine.begin() as conn:
        if snapshot_id:
            row = (
                conn.execute(
                    select(dg_fixture_snapshots).where(
                        dg_fixture_snapshots.c.id == str(snapshot_id)
                    )
                )
                .mappings()
                .first()
            )
        elif scraped_at:
            row = (
                conn.execute(
                    select(dg_fixture_snapshots).where(
                        dg_fixture_snapshots.c.scraped_at == str(scraped_at)
                    )
                )
                .mappings()
                .first()
            )
        else:
            return None
        return dict(row) if row else None
