"""Tests for Arahus Live Candidate V1 — frozen O2.5 / odds band filter."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class ArahusLiveV1QualifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = Path(cls._tmpdir.name) / "arahus_live_v1_test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        import importlib
        import app.db as db_mod
        import app.arahus_live_v1_engine as live

        importlib.reload(db_mod)
        importlib.reload(live)
        db_mod.init_db()
        cls.db = db_mod
        cls.live = live

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.engine.dispose()
        except Exception:
            pass
        cls._tmpdir.cleanup()

    def test_market_o25_accepted(self):
        ok, reason = self.live.qualifies_for_arahus_live_v1(
            market="Over 2.5", bet_type="arahus_o25", odds=1.40
        )
        self.assertTrue(ok)
        self.assertEqual(reason, self.live.QUALIFIED)

    def test_btts_rejected(self):
        ok, reason = self.live.qualifies_for_arahus_live_v1(
            market="BTTS Yes", bet_type="arahus_btts", odds=1.40
        )
        self.assertFalse(ok)
        self.assertEqual(reason, self.live.REJECT_MARKET)

    def test_o35_rejected(self):
        ok, reason = self.live.qualifies_for_arahus_live_v1(
            market="Over 3.5", bet_type="arahus_o35", odds=1.40
        )
        self.assertFalse(ok)
        self.assertEqual(reason, self.live.REJECT_MARKET)

    def test_odds_edges(self):
        cases = [
            (1.29, False, self.live.REJECT_ODDS_BELOW),
            (1.299, False, self.live.REJECT_ODDS_BELOW),
            (1.30, True, self.live.QUALIFIED),
            (1.31, True, self.live.QUALIFIED),
            (1.49, True, self.live.QUALIFIED),
            (1.491, False, self.live.REJECT_ODDS_ABOVE),
            (1.50, False, self.live.REJECT_ODDS_ABOVE),
            (None, False, self.live.REJECT_MISSING_ODDS),
        ]
        for odds, expect_ok, expect_reason in cases:
            with self.subTest(odds=odds):
                ok, reason = self.live.qualifies_for_arahus_live_v1(
                    market="Over 2.5", bet_type="arahus_o25", odds=odds
                )
                self.assertEqual(ok, expect_ok)
                self.assertEqual(reason, expect_reason)

    def test_any_league_allowed(self):
        # No whitelist in config
        self.assertIsNone(self.live.ARAHUS_LIVE_V1["league_whitelist"])
        for league in ("Eerste Divisie", "MLS", "Unknown Cup", "Super League"):
            ok, _ = self.live.qualifies_for_arahus_live_v1(
                market="Over 2.5", bet_type="arahus_o25", odds=1.40
            )
            self.assertTrue(ok, league)

    def test_confidence_not_a_gate(self):
        low = self.live._build_o25_decision(
            {
                "odds": {"over_2_5": 1.40},
                "fixture_id": "1",
                "fixture": "A vs B",
                "fixture_date": "2026-09-10T12:00:00+00:00",
                "league_name": "Test League",
                "home_team": "A",
                "away_team": "B",
                "indexes": {},
                "highlights": [],
            },
            {"over_2_5_pct": 55.0, "pace": 50, "nec": 50, "luck": 0.2},
            signal_timestamp="2026-09-10T10:00:00+00:00",
        )
        # Even with low signal weights / confidence, odds band alone qualifies
        self.assertTrue(low["qualification_result"])
        self.assertLess(low["confidence"], 66)


class ArahusLiveV1SyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = Path(cls._tmpdir.name) / "arahus_live_v1_sync.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        import importlib
        import app.db as db_mod
        import app.arahus_live_v1_engine as live

        importlib.reload(db_mod)
        importlib.reload(live)
        db_mod.init_db()
        cls.db = db_mod
        cls.live = live

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.engine.dispose()
        except Exception:
            pass
        cls._tmpdir.cleanup()

    def test_duplicate_sync_no_second_bet(self):
        pick = {
            "fixture_date": "2026-09-10T18:00:00+00:00",
            "fixture": "Alpha vs Beta",
            "league_name": "Test League",
            "bet_type": "arahus_o25",
            "team_name": "",
            "confidence": 50,
            "odds": 1.42,
            "entry_odds": 1.42,
            "units": 1.0,
            "edge": 1.0,
            "signal_timestamp": "2026-09-10T12:00:00+00:00",
            "qualification_result": True,
        }
        card = {
            "fixture_id": "fx1",
            "fixture": pick["fixture"],
            "fixture_date": pick["fixture_date"],
            "league_name": pick["league_name"],
            "home_team": "Alpha",
            "away_team": "Beta",
            "signal_timestamp": pick["signal_timestamp"],
            "decisions": [
                {
                    **pick,
                    "market_label": "Over 2.5",
                    "market": "Over 2.5",
                    "decision": "BET",
                    "status": "picked",
                    "rejection_reason": None,
                    "signals": [],
                    "kickoff_timestamp": pick["fixture_date"],
                }
            ],
            "picks": [pick],
        }
        r1 = self.live.sync_arahus_live_v1_bets([pick], cards=[card])
        self.assertEqual(r1["inserted"], 1)
        r2 = self.live.sync_arahus_live_v1_bets(
            [{**pick, "odds": 1.45, "entry_odds": 1.45}], cards=[card]
        )
        self.assertEqual(r2["inserted"], 0)
        alpha = [
            e
            for e in self.live.load_arahus_live_v1_bet_log()
            if e.get("fixture") == "Alpha vs Beta"
        ]
        self.assertEqual(len(alpha), 1)
        self.assertAlmostEqual(float(alpha[0]["odds"]), 1.42, places=2)

    def test_decision_log_schema_fields(self):
        pick = {
            "fixture_date": "2026-09-11T18:00:00+00:00",
            "fixture": "Gamma vs Delta",
            "league_name": "Another League",
            "bet_type": "arahus_o25",
            "team_name": "",
            "confidence": 72,
            "odds": 1.35,
            "entry_odds": 1.35,
            "units": 1.0,
            "edge": 2.0,
            "signal_timestamp": "2026-09-11T09:00:00+00:00",
            "qualification_result": True,
        }
        card = {
            "fixture_id": "fx2",
            "fixture": pick["fixture"],
            "fixture_date": pick["fixture_date"],
            "league_name": pick["league_name"],
            "home_team": "Gamma",
            "away_team": "Delta",
            "signal_timestamp": pick["signal_timestamp"],
            "decisions": [
                {
                    **pick,
                    "market_label": "Over 2.5",
                    "market": "Over 2.5",
                    "decision": "BET",
                    "status": "picked",
                    "rejection_reason": None,
                    "signals": [{"detail": "sim", "name": "sim", "weight": 20}],
                    "kickoff_timestamp": pick["fixture_date"],
                    "odds_source": "datagaffer",
                    "bookmaker": "datagaffer",
                    "closing_odds": None,
                    "closing_timestamp": None,
                    "clv": None,
                }
            ],
            "picks": [pick],
        }
        self.live.sync_arahus_live_v1_bets([pick], cards=[card])
        rows = self.db.list_arahus_live_v1_decision_log()
        self.assertTrue(rows)
        row = rows[-1]
        for key in (
            "strategy_version",
            "signal_timestamp",
            "league",
            "market",
            "confidence",
            "entry_odds",
            "qualification_result",
            "rejection_reason",
        ):
            self.assertIn(key, row)
        self.assertEqual(row["strategy_version"], self.live.ENGINE_VERSION)
        self.assertTrue(row["qualification_result"])
        self.assertIsNone(row["closing_odds"])

    def test_pnl_convention(self):
        pick = {
            "fixture_date": "2026-09-12T18:00:00+00:00",
            "fixture": "Echo vs Foxtrot",
            "league_name": "L",
            "bet_type": "arahus_o25",
            "team_name": "",
            "confidence": 70,
            "odds": 1.40,
            "entry_odds": 1.40,
            "units": 1.0,
            "signal_timestamp": "2026-09-12T10:00:00+00:00",
            "qualification_result": True,
        }
        self.live.sync_arahus_live_v1_bets([pick], cards=[])
        bet = next(
            e
            for e in self.live.load_arahus_live_v1_bet_log()
            if e.get("fixture") == "Echo vs Foxtrot"
        )
        self.assertAlmostEqual(float(bet["odds"]), 1.40, places=2)
        self.assertAlmostEqual(float(bet["units"]), 1.0, places=2)
        updated = self.live.resolve_arahus_live_v1_bet(bet["id"], "won")
        expected = round((float(bet["odds"]) - 1.0) * float(bet["units"]), 3)
        self.assertAlmostEqual(float(updated["pnl_units"]), expected, places=3)
        self.assertAlmostEqual(float(updated["pnl_units"]), 0.40, places=2)

    def test_isolated_log_type(self):
        self.assertEqual(self.live.LOG_TYPE, "arahus_live_v1")
        self.assertNotEqual(self.live.LOG_TYPE, "arahus")
        self.assertNotEqual(self.live.LOG_TYPE, "arahus_v2")


class ArahusLiveV1SanityOOSTests(unittest.TestCase):
    """Reproduce O2.5 + 1.30–1.49 filter on the uploaded Arahus log (no tuning)."""

    def test_historical_filter_matches_oos_n(self):
        csv_path = Path("/home/ubuntu/.cursor/projects/workspace/uploads/arahus-log_e332.csv")
        if not csv_path.exists():
            self.skipTest("uploaded Arahus CSV not available")
        import csv
        from datetime import datetime

        from app.arahus_live_v1_engine import qualifies_for_arahus_live_v1

        with csv_path.open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        oos = []
        for r in rows:
            try:
                dt = datetime.strptime(r["Fixture Date"].strip(), "%d/%m/%Y %H:%M")
            except ValueError:
                continue
            if dt.date() < datetime(2026, 9, 1).date():
                continue
            status = (r.get("Status") or "").strip().lower()
            if status not in {"won", "lost", "push"}:
                continue
            try:
                odds = float(r["Odds"])
            except (TypeError, ValueError):
                continue
            ok, _ = qualifies_for_arahus_live_v1(
                market=r.get("Market"), bet_type=None, odds=odds
            )
            if ok:
                oos.append(r)
        self.assertEqual(len(oos), 62)


if __name__ == "__main__":
    unittest.main()
