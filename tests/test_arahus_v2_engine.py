"""Arahus v2 eligibility gates + isolation from v1 log_type."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class ArahusV2EligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = Path(cls._tmpdir.name) / "arahus_v2_test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        import importlib
        import app.db as db_mod
        import app.arahus_v2_engine as v2

        importlib.reload(db_mod)
        importlib.reload(v2)
        db_mod.init_db()
        cls.db = db_mod
        cls.v2 = v2

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.engine.dispose()
        except Exception:
            pass
        cls._tmpdir.cleanup()

    def test_v2a_eligible_when_gates_pass(self):
        row = self.v2._classify_candidate(
            bet_type="arahus_o25",
            label="Over 2.5",
            model_pct=72.0,
            odds=1.40,
            signals=[
                {"name": "sim", "weight": 20, "detail": "Sim"},
                {"name": "xg", "weight": 14, "detail": "xG"},
                {"name": "pace", "weight": 12, "detail": "Pace"},
                {"name": "nec", "weight": 10, "detail": "NEC"},
                {"name": "reg", "weight": 8, "detail": "Luck"},
                {"name": "hl", "weight": 8, "detail": "HL"},
            ],
            live_market=True,
        )
        self.assertIsNotNone(row)
        assert row is not None
        # implied ~71.4 → edge ~0.6 — NOT enough for v2A
        self.assertFalse(row["eligible_v2A"])
        self.assertEqual(row["skip_reason"], self.v2.SKIP_LOW_EDGE)

        row2 = self.v2._classify_candidate(
            bet_type="arahus_o25",
            label="Over 2.5",
            model_pct=78.0,
            odds=1.40,
            signals=[
                {"name": "sim", "weight": 22, "detail": "Sim"},
                {"name": "xg", "weight": 14, "detail": "xG"},
                {"name": "pace", "weight": 12, "detail": "Pace"},
                {"name": "nec", "weight": 10, "detail": "NEC"},
                {"name": "reg", "weight": 8, "detail": "Luck"},
            ],
            live_market=True,
        )
        assert row2 is not None
        # implied 71.4, model 78 → edge 6.6 → v2A + v2B
        self.assertTrue(row2["eligible_v2A"])
        self.assertTrue(row2["eligible_v2B"])
        self.assertEqual(row2["skip_reason"], self.v2.SKIP_ELIGIBLE)

    def test_odds_band_and_missing_odds(self):
        signals = [{"name": "sim", "weight": 70, "detail": "x"}]
        miss = self.v2._classify_candidate(
            bet_type="arahus_o25",
            label="Over 2.5",
            model_pct=75.0,
            odds=None,
            signals=signals,
            live_market=True,
        )
        assert miss is not None
        self.assertEqual(miss["skip_reason"], self.v2.SKIP_MISSING_ODDS)
        self.assertFalse(miss["eligible_v2A"])

        out = self.v2._classify_candidate(
            bet_type="arahus_o25",
            label="Over 2.5",
            model_pct=75.0,
            odds=1.55,
            signals=signals,
            live_market=True,
        )
        assert out is not None
        self.assertEqual(out["skip_reason"], self.v2.SKIP_ODDS_RANGE)

    def test_o35_never_live(self):
        row = self.v2._classify_candidate(
            bet_type="arahus_o35",
            label="Over 3.5 (watch)",
            model_pct=60.0,
            odds=1.40,
            signals=[{"name": "sim", "weight": 70, "detail": "x"}],
            live_market=False,
        )
        assert row is not None
        self.assertEqual(row["skip_reason"], self.v2.SKIP_MARKET)
        self.assertFalse(row["eligible_v2A"])

    def test_sync_uses_isolated_log_type(self):
        picks = [
            {
                "fixture_date": "2026-09-10T18:00:00+00:00",
                "fixture": "Home vs Away",
                "league_name": "Test",
                "bet_type": "arahus_o25",
                "team_name": "",
                "confidence": 70,
                "odds": 1.40,
                "units": 1.0,
            }
        ]
        cards = [
            {
                "fixture_id": "1",
                "fixture": "Home vs Away",
                "fixture_date": "2026-09-10T18:00:00+00:00",
                "league_name": "Test",
                "home_team": "Home",
                "away_team": "Away",
                "projections": {"home_xg": 1.5, "away_xg": 1.4, "total_xg": 2.9, "pace": 62},
                "decisions": [
                    {
                        "bet_type": "arahus_o25",
                        "team_name": "",
                        "status": "picked",
                        "model_pct": 78.0,
                        "confidence": 70.0,
                        "odds": 1.40,
                        "implied_pct": 71.4,
                        "edge": 6.6,
                        "ev": 9.2,
                        "stake": 1.0,
                        "eligible_v2A": True,
                        "eligible_v2B": True,
                        "eligible_secondary": True,
                        "skip_reason": "eligible",
                        "signals": [{"detail": "Sim"}],
                    }
                ],
            }
        ]
        result = self.v2.sync_arahus_v2_bets(picks, cards=cards)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["report_log_inserted"], 1)
        bets = self.db.list_bets("arahus_v2")
        self.assertEqual(len(bets), 1)
        self.assertEqual(bets[0]["units"], 1.0)
        self.assertEqual(len(self.db.list_bets("arahus")), 0)
        report = self.db.list_arahus_v2_report_log()
        self.assertEqual(len(report), 1)
        self.assertTrue(report[0]["eligible_v2A"])
        self.assertEqual(report[0]["skip_reason"], "eligible")


if __name__ == "__main__":
    unittest.main()
