"""Tests for WS broadcast loop binding (Option C picks push)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app import ws_manager


class BroadcastFromThreadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        ws_manager._main_loop = None
        ws_manager.picks_bus._connections.clear()

    def tearDown(self) -> None:
        ws_manager._main_loop = None
        ws_manager.picks_bus._connections.clear()

    async def test_bind_and_broadcast_from_worker_thread(self) -> None:
        loop = asyncio.get_running_loop()
        ws_manager.bind_event_loop(loop)

        received: list[dict] = []

        class FakeWs:
            async def send_text(self, data: str) -> None:
                import json

                received.append(json.loads(data))

        ws_manager.picks_bus._connections.add(FakeWs())  # type: ignore[arg-type]

        def worker() -> None:
            ws_manager.picks_bus.broadcast_from_thread(
                {"type": "snapshot", "payload": {"picks": [{"id": "x"}]}}
            )

        await asyncio.to_thread(worker)
        # Allow run_coroutine_threadsafe to complete
        await asyncio.sleep(0.1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["type"], "snapshot")

    def test_broadcast_skips_without_loop(self) -> None:
        ws_manager._main_loop = None
        # Should not raise
        ws_manager.picks_bus.broadcast_from_thread({"type": "heartbeat"})


if __name__ == "__main__":
    unittest.main()
