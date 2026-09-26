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
                    "id": "dup-o25-t35",
                    "created_at": "2026-09-27T10:00:00+00:00",
                    "fixture": "Montreal vs Cincinnati",
                    "league_name": "Major League Soccer",
                    "bet_type": "o25_t35",
                    "team_name": "",
                    "odds": 1.40,
                    "units": 1.0,
                    "status": "open",
                    "fixture_date": "2026-09-26T23:30:00+00:00",
                },
                {
                    "id": "dup-o25-t40",
                    "created_at": "2026-09-27T10:00:00+00:00",
                    "fixture": "Montreal vs Cincinnati",
                    "league_name": "Major League Soccer",
                    "bet_type": "o25_t40",
                    "team_name": "",
                    "odds": 1.40,
                    "units": 1.0,
                    "status": "open",
                    "fixture_date": "2026-09-26T23:30:00+00:00",
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

    def test_dedupes_same_fixture_market_scenarios(self):
        """o25_t35 + o25_t40 are two Main scenarios — Trade Picks stakes once."""
        payload = self.tp.trade_picks_payload(include_settled=False)
        montreal = [
            e
            for e in payload["entries"]
            if e.get("fixture") == "Montreal vs Cincinnati" and e.get("market") == "Over 2.5"
        ]
        self.assertEqual(len(montreal), 1)
        self.assertEqual(montreal[0]["id"], "dup-o25-t40")
        self.assertEqual(montreal[0]["bet_type"], "o25_t40")

        feed = self.tp.build_bot_trade_picks_feed(open_only=True)
        feed_montreal = [
            p for p in feed["picks"] if "Montreal" in str(p.get("fixture") or "")
        ]
        if not feed_montreal:
            feed_montreal = [
                p
                for p in feed["picks"]
                if p.get("home_team") == "Montreal" and p.get("away_team") == "Cincinnati"
            ]
        self.assertEqual(len(feed_montreal), 1)

    def test_include_settled(self):
        payload = self.tp.trade_picks_payload(include_settled=True)
        ids = {e["id"] for e in payload["entries"]}
        self.assertIn("open-o25", ids)
        self.assertIn("settled-band", ids)
        self.assertNotIn("moneyline-skip", ids)

    def test_pick_date_filters_kickoff_day(self):
        payload = self.tp.trade_picks_payload(pick_date="2026-09-20")
        ids = {e["id"] for e in payload["entries"]}
        self.assertEqual(ids, {"settled-band"})
        self.assertEqual(payload["pick_date"], "2026-09-20")

        payload2 = self.tp.trade_picks_payload(pick_date="2026-09-21")
        ids2 = {e["id"] for e in payload2["entries"]}
        self.assertIn("open-o25", ids2)
        self.assertNotIn("settled-band", ids2)

    def test_bot_feed_open_only(self):
        feed = self.tp.build_bot_trade_picks_feed(open_only=True)
        self.assertEqual(feed["kind"], "trade_picks")
        self.assertEqual(feed["schema_version"], 1)
        self.assertEqual(feed["flat_stake_usd"], 1.0)
        ids = {p["id"] for p in feed["picks"]}
        self.assertIn("open-o25", ids)
        self.assertNotIn("settled-band", ids)
        hit = next(p for p in feed["picks"] if p["id"] == "open-o25")
        self.assertEqual(hit["home_team"], "A")
        self.assertEqual(hit["away_team"], "B")
        self.assertEqual(hit["stake_usd"], 1.0)
        self.assertEqual(hit["live_category"], "Main_filtered")


if __name__ == "__main__":
    unittest.main()
