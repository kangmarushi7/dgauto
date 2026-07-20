"""Prop Model bet log — isolated from DG bet_entries (uses pm_bets only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.prop_model import _jsonable_row, uses_postgres


def _rows(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        return [_jsonable_row(dict(r._mapping)) for r in result]


def _execute(sql: str, params: dict[str, Any] | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def list_prop_bets() -> list[dict[str, Any]]:
    try:
        return _rows(
            """
            SELECT b.id, b.player_id, p.name AS player_name, p.team, p.sport,
                   b.stat_type, b.line, b.side, b.stake, b.odds, b.result, b.clv_pct, b.created_at
            FROM pm_bets b
            LEFT JOIN pm_players p ON p.id = b.player_id
            ORDER BY b.created_at DESC, b.id DESC
            """
        )
    except Exception:
        return []


def prop_bet_dashboard(entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    entries = entries if entries is not None else list_prop_bets()
    placed = len(entries)
    won = sum(1 for e in entries if str(e.get("result") or "").lower() == "won")
    lost = sum(1 for e in entries if str(e.get("result") or "").lower() == "lost")
    push = sum(1 for e in entries if str(e.get("result") or "").lower() == "push")
    open_n = sum(1 for e in entries if not e.get("result") or str(e.get("result")).lower() == "open")
    settled = won + lost + push
    win_pct = round(100.0 * won / settled, 1) if settled else 0.0

    unit_pnl = 0.0
    odds_vals = []
    for e in entries:
        stake = float(e.get("stake") or 1.0)
        odds = e.get("odds")
        if odds is not None:
            try:
                odds_vals.append(float(odds))
            except (TypeError, ValueError):
                pass
        result = str(e.get("result") or "").lower()
        if result == "won" and odds is not None:
            try:
                o = float(odds)
                # American odds → unit profit
                if o > 0:
                    unit_pnl += stake * (o / 100.0)
                elif o < 0:
                    unit_pnl += stake * (100.0 / abs(o))
            except (TypeError, ValueError):
                pass
        elif result == "lost":
            unit_pnl -= stake

    avg_odds = round(sum(odds_vals) / len(odds_vals), 2) if odds_vals else None
    return {
        "placed": placed,
        "open": open_n,
        "won": won,
        "lost": lost,
        "push": push,
        "win_pct": win_pct,
        "avg_odds": avg_odds,
        "unit_pnl": round(unit_pnl, 2),
    }


def add_prop_bet(payload: dict[str, Any]) -> dict[str, Any]:
    player_id = (payload.get("player_id") or "").strip() or None
    player_name = (payload.get("player_name") or "").strip()
    sport = (payload.get("sport") or "").strip().lower() or None
    team = (payload.get("team") or "").strip() or None
    stat_type = (payload.get("stat_type") or "").strip()
    if not stat_type:
        raise ValueError("stat_type is required")

    # Ensure player row exists when name provided without id
    if player_name and not player_id:
        slug = "-".join(player_name.lower().split())
        player_id = f"{sport or 'nba'}:{slug}"
        if sport in {"nba", "mlb"}:
            if uses_postgres():
                _execute(
                    """
                    INSERT INTO pm_players (id, name, team, sport, position, updated_at)
                    VALUES (:id, :name, :team, :sport, NULL, NOW())
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW()
                    """,
                    {"id": player_id, "name": player_name, "team": team, "sport": sport},
                )
            else:
                _execute(
                    """
                    INSERT INTO pm_players (id, name, team, sport, position, updated_at)
                    VALUES (:id, :name, :team, :sport, NULL, datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET name = excluded.name, updated_at = datetime('now')
                    """,
                    {"id": player_id, "name": player_name, "team": team, "sport": sport},
                )

    line = payload.get("line")
    side = (payload.get("side") or "").strip().lower() or None
    stake = float(payload.get("stake") or 1.0)
    odds = payload.get("odds")
    created_at = datetime.now(timezone.utc).isoformat()

    if uses_postgres():
        rows = _rows(
            """
            INSERT INTO pm_bets (player_id, stat_type, line, side, stake, odds, result, clv_pct, created_at)
            VALUES (:player_id, :stat_type, :line, :side, :stake, :odds, 'open', NULL, NOW())
            RETURNING id, player_id, stat_type, line, side, stake, odds, result, clv_pct, created_at
            """,
            {
                "player_id": player_id,
                "stat_type": stat_type,
                "line": line,
                "side": side,
                "stake": stake,
                "odds": odds,
            },
        )
        return rows[0] if rows else {"id": None}
    else:
        # SQLite: no RETURNING on older versions — insert then fetch last
        _execute(
            """
            INSERT INTO pm_bets (player_id, stat_type, line, side, stake, odds, result, clv_pct, created_at)
            VALUES (:player_id, :stat_type, :line, :side, :stake, :odds, 'open', NULL, :created_at)
            """,
            {
                "player_id": player_id,
                "stat_type": stat_type,
                "line": line,
                "side": side,
                "stake": stake,
                "odds": odds,
                "created_at": created_at,
            },
        )
        row = _rows("SELECT * FROM pm_bets ORDER BY id DESC LIMIT 1")
        return row[0] if row else {"id": None}


def resolve_prop_bet(bet_id: int, result: str) -> dict[str, Any] | None:
    result = result.lower().strip()
    if result not in {"won", "lost", "push", "open"}:
        raise ValueError("result must be won, lost, push, or open")
    _execute(
        "UPDATE pm_bets SET result = :result WHERE id = :id",
        {"result": result, "id": bet_id},
    )
    rows = _rows("SELECT * FROM pm_bets WHERE id = :id", {"id": bet_id})
    return rows[0] if rows else None


def prop_bet_log_payload() -> dict[str, Any]:
    entries = list_prop_bets()
    return {
        "entries": entries,
        "dashboard": prop_bet_dashboard(entries),
    }
