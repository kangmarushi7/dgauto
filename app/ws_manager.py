"""WebSocket connection bus — broadcast trade-pick and result events to subscribers."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Uvicorn/FastAPI main loop — set from startup so APScheduler threads can broadcast.
_main_loop: Optional[asyncio.AbstractEventLoop] = None
_debounce_lock = threading.Lock()
_debounce_timer: Optional[threading.Timer] = None


def bind_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Remember the running asyncio loop for thread-safe WS broadcasts."""
    global _main_loop
    _main_loop = loop
    logger.info("ws_manager: bound event loop id=%s", id(loop))


def get_bound_loop() -> Optional[asyncio.AbstractEventLoop]:
    return _main_loop


class ConnectionBus:
    def __init__(self, name: str):
        self.name = name
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("ws/%s: client connected (%d total)", self.name, len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("ws/%s: client disconnected (%d total)", self.name, len(self._connections))

    @property
    def subscriber_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: dict) -> None:
        if not self._connections:
            return
        data = json.dumps(message, default=str)
        dead: set[WebSocket] = set()
        for ws in set(self._connections):
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)

    def broadcast_from_thread(self, message: dict) -> None:
        """Schedule a broadcast from a non-async thread (APScheduler / DB writers)."""
        loop = _main_loop
        if loop is None:
            # Fallback: only works if called from the main thread with a running loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    logger.warning(
                        "ws/%s: broadcast skipped — no event loop bound (startup missing?)",
                        self.name,
                    )
                    return
        if not loop.is_running():
            logger.warning("ws/%s: broadcast skipped — event loop not running", self.name)
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except Exception as exc:
            logger.warning("ws/%s: broadcast schedule failed: %s", self.name, exc)


picks_bus = ConnectionBus("trade-picks")
results_bus = ConnectionBus("results")


def broadcast_open_picks_snapshot() -> None:
    """Push current open trade-picks snapshot to all WS subscribers (thread-safe)."""
    if picks_bus.subscriber_count == 0:
        return
    try:
        from datetime import datetime, timezone

        from app.trade_picks import build_bot_trade_picks_feed

        payload = build_bot_trade_picks_feed(
            open_only=True, pick_date=None, category=None, strategy=None
        )
        picks_bus.broadcast_from_thread(
            {
                "type": "snapshot",
                "payload": payload,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        n = len(payload.get("picks") or payload.get("entries") or [])
        logger.info(
            "ws/trade-picks: broadcast snapshot (%d picks, %d subscribers)",
            n,
            picks_bus.subscriber_count,
        )
    except Exception as exc:
        logger.warning("picks WS broadcast failed: %s", exc)


def notify_picks_changed(delay_secs: float = 0.75) -> None:
    """Debounced notify after bets are inserted/updated (coalesces burst inserts)."""
    global _debounce_timer

    def _fire() -> None:
        global _debounce_timer
        with _debounce_lock:
            _debounce_timer = None
        broadcast_open_picks_snapshot()

    with _debounce_lock:
        if _debounce_timer is not None:
            _debounce_timer.cancel()
        timer = threading.Timer(delay_secs, _fire)
        timer.daemon = True
        _debounce_timer = timer
        timer.start()
