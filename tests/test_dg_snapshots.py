"""Immutable DG fixture snapshot tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

# Isolate DB for this module.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from app.db import init_db  # noqa: E402
from app.dg_snapshots import content_hash, get_snapshot, save_fixtures_snapshot  # noqa: E402


class DgSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_save_is_immutable_for_same_scraped_at(self):
        fixtures_a = [{"fixture_id": 1, "sim_stats": {"projected_xg": {"xgot": {"total": "2.1"}}}}]
        fixtures_b = [{"fixture_id": 1, "sim_stats": {"projected_xg": {"xgot": {"total": "9.9"}}}}]
        scraped = "2026-10-12T12:00:00+00:00"
        first = save_fixtures_snapshot(scraped_at=scraped, fixtures=fixtures_a)
        self.assertFalse(first.get("deduped"))
        self.assertEqual(first["content_hash"], content_hash(fixtures_a))

        second = save_fixtures_snapshot(scraped_at=scraped, fixtures=fixtures_b)
        self.assertTrue(second.get("deduped"))
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["content_hash"], first["content_hash"])

        stored = get_snapshot(scraped_at=scraped)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored["content_hash"], content_hash(fixtures_a))
        self.assertEqual(stored["payload"][0]["sim_stats"]["projected_xg"]["xgot"]["total"], "2.1")

    def test_different_scraped_at_inserts_new_row(self):
        fixtures = [{"fixture_id": 2}]
        a = save_fixtures_snapshot(scraped_at="2026-10-12T13:00:00+00:00", fixtures=fixtures)
        b = save_fixtures_snapshot(scraped_at="2026-10-12T14:00:00+00:00", fixtures=fixtures)
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(a["content_hash"], b["content_hash"])


if __name__ == "__main__":
    unittest.main()
