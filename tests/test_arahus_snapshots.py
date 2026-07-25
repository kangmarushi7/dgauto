"""Tests for Arahus pick snapshots (uses temp SQLite via DATABASE_URL)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class ArahusSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = Path(cls._tmpdir.name) / "arahus_snap_test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        # Re-import db/engine against the temp DB.
        import importlib
        import app.db as db_mod
        import app.arahus_engine as arahus_mod

        importlib.reload(db_mod)
        importlib.reload(arahus_mod)
        db_mod.init_db()
        cls.db = db_mod
        cls.arahus = arahus_mod

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.engine.dispose()
        except Exception:
            pass
        cls._tmpdir.cleanup()

    def test_snapshot_insert_and_export(self):
        cards = [
            {
                "fixture_id": "1",
                "fixture_date": "2026-07-25",
                "fixture": "Home vs Away",
                "league_name": "Test League",
                "home_team": "Home",
                "away_team": "Away",
                "projections": {
                    "archetype": "High-event",
                    "total_xg": 3.5,
                    "home_xg": 2.0,
                    "away_xg": 1.5,
                    "pace": 70,
                    "nec": 65,
                    "agix": 60,
                    "over_2_5_pct": 72,
                    "dgrtg_gap": 4,
                },
                "profile": {
                    "sim": {"over_2_5_pct": 72},
                    "xg": {"home": 2.0, "away": 1.5, "total": 3.5},
                    "indexes": {"pace": 70},
                    "ratings": {"dgrtg_gap": 4},
                    "regression": {"home_luck": 0.1, "away_luck": 0},
                    "highlights": ["Highest pace"],
                },
                "calibration": [],
                "picks": [
                    {
                        "bet_type": "arahus_o25",
                        "market_label": "Over 2.5",
                        "team_name": "",
                        "confidence": 70,
                        "model_pct": 72,
                        "odds": 1.8,
                        "implied_pct": 55.6,
                        "edge": 16.4,
                        "ev": 29.6,
                        "units": 1.0,
                        "signals": [{"name": "sim", "weight": 20, "detail": "Sim O2.5 72%"}],
                        "signal_summary": "Sim O2.5 72%",
                        "_calibrationDebug": [],
                        "_calibrationRelevant": [],
                    }
                ],
            },
            {
                "fixture_id": "2",
                "fixture_date": "2026-07-25",
                "fixture": "Skip Home vs Skip Away",
                "league_name": "Test League",
                "home_team": "Skip Home",
                "away_team": "Skip Away",
                "projections": {"archetype": "Low-event", "total_xg": 1.8},
                "profile": {"sim": {}, "xg": {"total": 1.8}, "indexes": {}, "ratings": {}, "regression": {}, "highlights": []},
                "calibration": [],
                "picks": [],
            },
        ]
        picks = self.arahus.flatten_picks(cards)
        result = self.arahus.sync_arahus_bets(picks, cards=cards)
        self.assertGreaterEqual(result["inserted"], 1)
        self.assertGreaterEqual(result["snapshots_inserted"], 2)

        rows = self.arahus.export_arahus_snapshots(date_from="2026-07-25", date_to="2026-07-25")
        self.assertGreaterEqual(len(rows), 2)
        picked = [r for r in rows if r["decision"] == "picked"]
        skipped = [r for r in rows if r["decision"] == "skipped"]
        self.assertTrue(picked)
        self.assertTrue(skipped)
        self.assertEqual(picked[0]["bet_type"], "arahus_o25")
        self.assertIsNotNone(picked[0].get("context"))
        self.assertEqual(picked[0]["status"], "open")

        # Immutable: second sync should not duplicate snapshots.
        result2 = self.arahus.sync_arahus_bets(picks, cards=cards)
        self.assertEqual(result2["snapshots_inserted"], 0)

        # Resolve updates snapshot status via resolve_bet_entry hook.
        bet_id = picked[0]["bet_id"]
        self.assertTrue(bet_id)
        updated = self.arahus.resolve_arahus_bet(bet_id, "won")
        self.assertEqual(updated["status"], "won")
        after = self.arahus.export_arahus_snapshots(decision="picked")
        settled = next(r for r in after if r.get("bet_id") == bet_id)
        self.assertEqual(settled["status"], "won")
        self.assertIsNotNone(settled.get("pnl_units"))


if __name__ == "__main__":
    unittest.main()
