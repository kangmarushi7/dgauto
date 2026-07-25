"""Tests for arahus_decision_log insert + settle semantics."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class DecisionLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = Path(cls._tmpdir.name) / "arahus_decision_test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        import importlib
        import app.db as db_mod
        import app.arahus_engine as arahus_mod
        import app.auto_resolve as ar_mod

        importlib.reload(db_mod)
        importlib.reload(arahus_mod)
        importlib.reload(ar_mod)
        db_mod.init_db()
        cls.db = db_mod
        cls.arahus = arahus_mod
        cls.ar = ar_mod

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.engine.dispose()
        except Exception:
            pass
        cls._tmpdir.cleanup()

    def test_insert_picked_and_skipped_nulls(self):
        cfg = self.arahus.engine_config_snapshot()
        rows = [
            {
                "fixture_id": "100",
                "synced_at": "2026-07-25T12:00:00+00:00",
                "match_date": "2026-07-24T18:00:00+00:00",
                "league": "Test League",
                "home_team": "Home",
                "away_team": "Away",
                "fixture": "Home vs Away",
                "bet_type": "arahus_o25",
                "team_name": "",
                "status": "picked",
                "model_pct": 72.0,
                "confidence": 70.0,
                "odds": 1.85,
                "edge": 10.0,
                "ev": 15.0,
                "units": 1.0,
                "signals": ["Sim O2.5 72%"],
                "xg_home": 2.0,
                "xg_away": 1.5,
                "xg_total": 3.5,
                "pace_score": 70.0,
                "nec_index": 65.0,
                "agix_index": 60.0,
                "dgrtg_gap": 4.0,
                "archetype": "High-event",
                "luck_regression_value": 0.1,
                "calibration_debug": [],
                "engine_config_snapshot": cfg,
                "engine_version": "arahus-1",
                "result": None,
                "pnl": None,
                "hypothetical_pnl": None,
                "resolved_at": None,
            },
            {
                "fixture_id": "100",
                "synced_at": "2026-07-25T12:00:00+00:00",
                "match_date": "2026-07-24T18:00:00+00:00",
                "league": "Test League",
                "home_team": "Home",
                "away_team": "Away",
                "fixture": "Home vs Away",
                "bet_type": "arahus_u25",
                "team_name": "",
                "status": "skipped_low_confidence",
                "model_pct": 40.0,
                "confidence": 40.0,
                "odds": 2.1,
                "edge": -5.0,
                "ev": -10.0,
                "units": None,
                "signals": [],
                "xg_home": 2.0,
                "xg_away": 1.5,
                "xg_total": 3.5,
                "pace_score": 70.0,
                "nec_index": 65.0,
                "agix_index": 60.0,
                "dgrtg_gap": 4.0,
                "archetype": "High-event",
                "luck_regression_value": 0.1,
                "calibration_debug": [],
                "engine_config_snapshot": cfg,
                "engine_version": "arahus-1",
                "result": None,
                "pnl": None,
                "hypothetical_pnl": None,
                "resolved_at": None,
            },
        ]
        n = self.db.insert_arahus_decision_log(rows)
        self.assertEqual(n, 2)
        stored = self.db.list_arahus_decision_log()
        picked = next(r for r in stored if r["status"] == "picked")
        skipped = next(r for r in stored if r["status"] == "skipped_low_confidence")
        self.assertEqual(picked["units"], 1.0)
        self.assertIsNone(skipped["units"])
        self.assertIsNone(skipped["pnl"])
        self.assertIsNone(skipped["result"])

    def test_resolve_skipped_sets_hyp_pnl_not_real_pnl(self):
        cfg = self.arahus.engine_config_snapshot()
        self.db.insert_arahus_decision_log(
            [
                {
                    "fixture_id": "200",
                    "synced_at": "2026-07-25T12:00:00+00:00",
                    "match_date": "2026-07-20T18:00:00+00:00",
                    "league": "Test League",
                    "home_team": "A",
                    "away_team": "B",
                    "fixture": "A vs B",
                    "bet_type": "arahus_o25",
                    "team_name": "",
                    "status": "skipped_low_edge",
                    "model_pct": 70.0,
                    "confidence": 70.0,
                    "odds": 1.90,
                    "edge": 1.0,
                    "ev": 1.0,
                    "units": None,
                    "signals": [],
                    "xg_home": 2.1,
                    "xg_away": 1.4,
                    "xg_total": 3.5,
                    "pace_score": 66.0,
                    "nec_index": 60.0,
                    "agix_index": 55.0,
                    "dgrtg_gap": 2.0,
                    "archetype": "High-event",
                    "luck_regression_value": 0.0,
                    "calibration_debug": [],
                    "engine_config_snapshot": cfg,
                    "engine_version": "arahus-1",
                    "result": None,
                    "pnl": None,
                    "hypothetical_pnl": None,
                    "resolved_at": None,
                }
            ]
        )
        row = next(
            r
            for r in self.db.list_arahus_decision_log(unresolved_only=True)
            if r["fixture_id"] == "200" and r["status"] == "skipped_low_edge"
        )
        # Simulate a winning O2.5 at odds 1.90 with REFERENCE_UNIT=1
        # hyp = (1.90-1)*1 = 0.9
        updated = self.db.update_arahus_decision_log_result(
            int(row["id"]),
            result="W",
            pnl=None,
            hypothetical_pnl=self.ar._hypothetical_pnl(
                "won", 1.90, self.arahus.REFERENCE_UNIT
            ),
            resolved_at="2026-07-25T20:00:00+00:00",
        )
        self.assertEqual(updated["result"], "W")
        self.assertIsNone(updated["pnl"])
        self.assertAlmostEqual(updated["hypothetical_pnl"], 0.9, places=3)

        # Second resolve is a no-op (already resolved).
        again = self.db.update_arahus_decision_log_result(
            int(row["id"]),
            result="L",
            pnl=-1.0,
            hypothetical_pnl=-1.0,
            resolved_at="2026-07-25T21:00:00+00:00",
        )
        self.assertEqual(again["result"], "W")
        self.assertIsNone(again["pnl"])

    def test_resolve_picked_still_sets_real_pnl(self):
        cfg = self.arahus.engine_config_snapshot()
        self.db.insert_arahus_decision_log(
            [
                {
                    "fixture_id": "300",
                    "synced_at": "2026-07-25T12:00:00+00:00",
                    "match_date": "2026-07-20T18:00:00+00:00",
                    "league": "Test League",
                    "home_team": "C",
                    "away_team": "D",
                    "fixture": "C vs D",
                    "bet_type": "arahus_o25",
                    "team_name": "",
                    "status": "picked",
                    "model_pct": 72.0,
                    "confidence": 70.0,
                    "odds": 1.80,
                    "edge": 12.0,
                    "ev": 20.0,
                    "units": 1.0,
                    "signals": ["Sim O2.5"],
                    "xg_home": 2.0,
                    "xg_away": 1.5,
                    "xg_total": 3.5,
                    "pace_score": 70.0,
                    "nec_index": 60.0,
                    "agix_index": 55.0,
                    "dgrtg_gap": 3.0,
                    "archetype": "High-event",
                    "luck_regression_value": 0.0,
                    "calibration_debug": [],
                    "engine_config_snapshot": cfg,
                    "engine_version": "arahus-1",
                    "result": None,
                    "pnl": None,
                    "hypothetical_pnl": None,
                    "resolved_at": None,
                }
            ]
        )
        row = next(r for r in self.db.list_arahus_decision_log() if r["fixture_id"] == "300")
        # won at 1.80 * 1u => pnl 0.8
        entry = {"odds": 1.80, "units": 1.0, "log_type": "arahus"}
        pnl = self.ar._compute_pnl(entry, "won")
        hyp = self.ar._hypothetical_pnl("won", 1.80, 1.0)
        updated = self.db.update_arahus_decision_log_result(
            int(row["id"]),
            result="W",
            pnl=pnl,
            hypothetical_pnl=hyp,
            resolved_at="2026-07-25T20:00:00+00:00",
        )
        self.assertEqual(updated["result"], "W")
        self.assertAlmostEqual(updated["pnl"], 0.8, places=3)
        self.assertAlmostEqual(updated["hypothetical_pnl"], 0.8, places=3)

    def test_score_market_skip_reasons(self):
        low = self.arahus._score_market(
            bet_type="arahus_o25",
            label="Over 2.5",
            team_name="",
            model_pct=70.0,
            odds=1.8,
            signals=[{"name": "sim", "weight": 20, "detail": "weak"}],
        )
        self.assertEqual(low["status"], "skipped_low_confidence")
        self.assertIsNone(low["units"])

        # High confidence but terrible odds -> low edge
        edge_skip = self.arahus._score_market(
            bet_type="arahus_o25",
            label="Over 2.5",
            team_name="",
            model_pct=70.0,
            odds=1.05,
            signals=[
                {"name": "sim", "weight": 30, "detail": "a"},
                {"name": "xg", "weight": 20, "detail": "b"},
                {"name": "pace", "weight": 15, "detail": "c"},
            ],
        )
        self.assertEqual(edge_skip["status"], "skipped_low_edge")


if __name__ == "__main__":
    unittest.main()
