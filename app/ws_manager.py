"""WebSocket connection bus — broadcast trade-pick and result events to subscribers."""
from __future__ import annotations

import asyncio
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


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
        """Schedule a broadcast from a non-async thread (APScheduler jobs)."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)


picks_bus = ConnectionBus("trade-picks")
results_bus = ConnectionBus("results")
