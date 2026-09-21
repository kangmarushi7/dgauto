"""Smoke tests for Trade Picks LIVE filtering."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class TradePicksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = Path(cls._tmpdir.name) / "trade.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        import importlib
        import app.db as db_mod
        import app.strategy_buckets as buckets
        import app.trade_picks as tp

        importlib.reload(db_mod)
        importlib.reload(buckets)
        importlib.reload(tp)
        db_mod.init_db()
        cls.db = db_mod
        cls.tp = tp

        cls.db.insert_bets(
            "main",
            [
                {
                    "id": "open-o25",
                    "created_at": "2026-09-21T10:00:00+00:00",
                    "fixture": "A vs B",
                    "league_name": "MLS",
                    "bet_type": "over2.5",
                    "team_name": "",
                    "odds": 1.55,
                    "units": 1.0,
                    "status": "open",
                    "fixture_date": "2026-09-21T12:00:00+00:00",
                },
                {
                    "id": "settled-band",
                    "created_at": "2026-09-20T10:00:00+00:00",
                    "fixture": "C vs D",
                    "league_name": "MLS",
                    "bet_type": "to15_home",
                    "team_name": "Home",
                    "odds": 1.40,
                    "units": 1.0,
                    "status": "won",
                    "pnl_units": 0.4,
                    "fixture_date": "2026-09-20T12:00:00+00:00",
                },
                {
                    "id": "moneyline-skip",
                    "created_at": "2026-09-21T11:00:00+00:00",
                    "fixture": "E vs F",
                    "league_name": "MLS",
                    "bet_type": "moneyline",
                    "team_name": "E",
                    "odds": 1.40,
                    "units": 1.0,
                    "status": "open",
                    "fixture_date": "2026-09-21T13:00:00+00:00",
                },
            ],
        )

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.engine.dispose()
        except Exception:
            pass
        cls._tmpdir.cleanup()

    def test_open_only_default(self):
        payload = self.tp.trade_picks_payload(include_settled=False)
        ids = {e["id"] for e in payload["entries"]}
        self.assertIn("open-o25", ids)
        self.assertNotIn("settled-band", ids)
        self.assertNotIn("moneyline-skip", ids)
        hit = next(e for e in payload["entries"] if e["id"] == "open-o25")
        self.assertEqual(hit["live_category"], "Main_filtered")
        self.assertEqual(hit["stake_usd"], 1.0)

    def test_include_settled(self):
        payload = self.tp.trade_picks_payload(include_settled=True)
        ids = {e["id"] for e in payload["entries"]}
        self.assertIn("open-o25", ids)
        self.assertIn("settled-band", ids)
        self.assertNotIn("moneyline-skip", ids)


if __name__ == "__main__":
    unittest.main()
