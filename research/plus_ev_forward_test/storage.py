"""Research-only JSONL signal store. Never used for live bet placement."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from research.plus_ev_forward_test.portfolios import portfolio_membership

DEFAULT_DATA_DIR = Path("research/plus_ev_forward_test/data")
SIGNALS_FILE = "signals.jsonl"
SNAPSHOTS_FILE = "odds_snapshots.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs(data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def new_signal_id() -> str:
    return str(uuid.uuid4())


def make_signal(**fields: Any) -> dict[str, Any]:
    """Create a research signal with required schema defaults."""
    signal = {
        "research_only": True,
        "can_place_real_bet": False,
        "signal_id": fields.get("signal_id") or new_signal_id(),
        "fixture_id": fields.get("fixture_id"),
        "kickoff_time": fields.get("kickoff_time"),
        "timestamp_signal_created": fields.get("timestamp_signal_created") or _now(),
        "league": fields.get("league"),
        "market": fields.get("market"),
        "bet_type": fields.get("bet_type"),
        "selection": fields.get("selection"),
        "bookmaker": fields.get("bookmaker") or "datagaffer",
        "odds_at_signal": fields.get("odds_at_signal"),
        "model_probability": fields.get("model_probability"),
        "raw_EV": fields.get("raw_EV"),
        "calibrated_probability": fields.get("calibrated_probability"),
        "calibrated_EV": fields.get("calibrated_EV"),
        "stake_units": 1.0,
        "result": fields.get("result"),  # won/lost/push/open/null
        "pnl_units": fields.get("pnl_units"),
        "opposite_odds": fields.get("opposite_odds"),
        "outcome_odds": fields.get("outcome_odds") or {},
        "fair_probability": fields.get("fair_probability"),
        "fair_market_edge": fields.get("fair_market_edge"),
        "odds_timestamp": fields.get("odds_timestamp"),
        "closing_odds": fields.get("closing_odds"),
        "closing_odds_timestamp": fields.get("closing_odds_timestamp"),
        "clv": fields.get("clv"),
        "sample_kind": fields.get("sample_kind") or "live_forward",
        "source": fields.get("source"),
        "portfolios": fields.get("portfolios"),
        "notes": fields.get("notes") or [],
    }
    if signal["portfolios"] is None:
        signal["portfolios"] = portfolio_membership(signal)
    return signal


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")
            n += 1
    return n


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def rewrite_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    n = 0
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")
            n += 1
    tmp.replace(path)
    return n


def signals_path(data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    return ensure_dirs(data_dir) / SIGNALS_FILE


def snapshots_path(data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    return ensure_dirs(data_dir) / SNAPSHOTS_FILE


def load_signals(data_dir: Path = DEFAULT_DATA_DIR) -> list[dict[str, Any]]:
    return load_jsonl(signals_path(data_dir))


def upsert_signals(data_dir: Path, new_rows: list[dict[str, Any]], key: str = "signal_id") -> dict[str, int]:
    existing = {r[key]: r for r in load_signals(data_dir) if key in r}
    inserted = 0
    updated = 0
    for row in new_rows:
        k = row[key]
        if k in existing:
            existing[k] = {**existing[k], **row}
            updated += 1
        else:
            existing[k] = row
            inserted += 1
    rewrite_jsonl(signals_path(data_dir), existing.values())
    return {"inserted": inserted, "updated": updated, "total": len(existing)}
