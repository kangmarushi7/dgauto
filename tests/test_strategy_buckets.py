"""Tests for strategy bucket dedupe + Team O1.5 merge into Main_filtered."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class StrategyBucketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = Path(cls._tmpdir.name) / "buckets.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        import importlib
        import app.db as db_mod
        import app.strategy_buckets as buckets

        importlib.reload(db_mod)
        importlib.reload(buckets)
        db_mod.init_db()
        cls.db = db_mod
        cls.b = buckets

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.engine.dispose()
        except Exception:
            pass
        cls._tmpdir.cleanup()

    def test_no_live_rule_overlap_on_synthetic_book(self):
        """No (fixture, market, odds, timestamp) matched by >1 LIVE rule."""
        rows = [
            {"strategy": "main", "fixture": "A vs B", "bet_type": "to15_home", "market_label": "Team Over 1.5 Goals", "team_name": "A", "odds": 1.40, "league_name": "La Liga", "fixture_date": "2026-08-01T12:00:00+00:00"},
            {"strategy": "main", "fixture": "C vs D", "bet_type": "over2.5", "market_label": "Over 2.5", "odds": 1.20, "league_name": "Serie A", "fixture_date": "2026-08-02T12:00:00+00:00"},
            {"strategy": "main", "fixture": "E vs F", "bet_type": "moneyline", "market_label": "Moneyline", "odds": 1.40, "league_name": "MLS", "fixture_date": "2026-08-03T12:00:00+00:00"},
            {"strategy": "cs", "fixture": "G vs H", "bet_type": "correct_score", "team_name": "0-1", "odds": 8.0, "league_name": "EPL", "fixture_date": "2026-08-04T12:00:00+00:00"},
            {"strategy": "cs", "fixture": "G vs H", "bet_type": "correct_score", "team_name": "2-1", "odds": 9.0, "league_name": "EPL", "fixture_date": "2026-08-04T12:00:00+00:00"},
            {"strategy": "ev", "fixture": "I vs J", "bet_type": "over3.5", "market_label": "Over 3.5", "odds": 2.1, "league_name": "La Liga", "fixture_date": "2026-08-05T12:00:00+00:00"},
            {"strategy": "h2h", "fixture": "K vs L", "bet_type": "h2h_o25", "market_label": "Over 2.5", "odds": 1.55, "league_name": "Bundesliga", "fixture_date": "2026-08-06T12:00:00+00:00"},
            {"strategy": "arahus", "fixture": "M vs N", "bet_type": "arahus_o25", "market_label": "Over 2.5", "odds": 1.42, "league_name": "MLS", "fixture_date": "2026-08-07T12:00:00+00:00"},
            {"strategy": "arahus", "fixture": "O vs P", "bet_type": "arahus_btts", "market_label": "BTTS Yes", "odds": 1.60, "league_name": "Eredivisie", "fixture_date": "2026-08-08T12:00:00+00:00"},
            # Excluded strategies must never assign
            {"strategy": "lm", "fixture": "Q vs R", "bet_type": "over1.5", "market_label": "Over 1.5", "odds": 1.40, "league_name": "MLS", "fixture_date": "2026-08-09T12:00:00+00:00"},
            {"strategy": "no", "fixture": "S vs T", "bet_type": "not_win", "market_label": "Not to win", "odds": 1.40, "league_name": "MLS", "fixture_date": "2026-08-10T12:00:00+00:00"},
        ]
        overlaps = self.b.find_live_overlaps(rows)
        self.assertEqual(overlaps, [], msg=f"Live overlaps found: {overlaps}")

        # Each strategy's LIVE hit is unique
        assigned = [self.b.assign_live_category(r) for r in rows]
        self.assertEqual(assigned[0], "Main_filtered")  # team o1.5 @ 1.40
        self.assertEqual(assigned[1], "Main_filtered")  # over 2.5
        self.assertIsNone(assigned[2])  # Moneyline explicitly excluded
        self.assertEqual(assigned[3], "CS_CorrectScore_0_1")
        self.assertEqual(assigned[4], "CS_CorrectScore_2_1")
        self.assertEqual(assigned[5], "EV_Over_3_5")
        self.assertEqual(assigned[6], "H2H_Over_2_5")
        self.assertEqual(assigned[7], "Arahus_filtered")  # o25 @ 1.42
        self.assertIsNone(assigned[8])  # BTTS excluded even on fav league
        self.assertIsNone(assigned[9])
        self.assertIsNone(assigned[10])

    def test_main_filtered_superset_of_legacy_team_o15_rule(self):
        """Main_filtered matched set ⊇ old Team Over 1.5 @ 1.30–1.49 rule."""
        candidates = [
            {"strategy": "main", "bet_type": "to15_home", "market_label": "Team Over 1.5 Goals", "team_name": "Home", "odds": 1.30, "league_name": "MLS"},
            {"strategy": "main", "bet_type": "to15_away", "market_label": "Team Over 1.5", "odds": 1.49, "league_name": "Serie A"},
            {"strategy": "main", "bet_type": "to15_home", "market_label": "Team Over 1.5 Goals", "odds": 1.399, "league_name": "EPL"},
            {"strategy": "main", "bet_type": "to15_home", "market_label": "Team Over 1.5 Goals", "odds": 1.50, "league_name": "MLS"},  # outside old rule
            {"strategy": "main", "bet_type": "to15_home", "market_label": "Team Over 1.5 Goals", "odds": 1.20, "league_name": "MLS"},  # outside
            {"strategy": "main", "bet_type": "over2.5", "market_label": "Over 2.5", "odds": 1.20, "league_name": "MLS"},  # Main_filtered via market
        ]
        legacy_hits = [r for r in candidates if self.b.match_legacy_main_team_o15_130_149(r)]
        self.assertEqual(len(legacy_hits), 3)
        for r in legacy_hits:
            self.assertTrue(
                self.b._match_main_filtered(self.b.enrich_bet_row(r)),
                msg=f"Main_filtered must cover legacy Team O1.5 hit: {r}",
            )
            self.assertEqual(self.b.assign_live_category(r), "Main_filtered")

    def test_flat_stake_one_dollar(self):
        row = {
            "strategy": "h2h",
            "bet_type": "h2h_o25",
            "market_label": "Over 2.5",
            "odds": 1.60,
            "league_name": "Bundesliga",
        }
        self.assertEqual(self.b.stake_for_bet(row), 1.0)

    def test_logging_categories_do_not_stake(self):
        row = {
            "strategy": "h2h",
            "bet_type": "h2h_btts",
            "market_label": "BTTS Yes",
            "odds": 1.70,
            "league_name": "MLS",
        }
        self.assertIsNone(self.b.assign_live_category(row))
        self.assertEqual(self.b.stake_for_bet(row), 0.0)
        hits = self.b.matching_categories(row, only_states={self.b.STATE_LOGGING})
        self.assertIn("H2H_BTTS_Yes", hits)

    def test_graduation_report_structure(self):
        rows = [
            {
                "strategy": "main",
                "bet_type": "over2.5",
                "market_label": "Over 2.5",
                "odds": 1.40,
                "league_name": "La Liga",
                "status": "won",
                "pnl_units": 0.4,
                "fixture_date": "2026-07-01T12:00:00+00:00",
            }
        ]
        report = self.b.category_status_report(rows)
        self.assertIn("Main_filtered", report["categories"])
        info = report["categories"]["Main_filtered"]
        self.assertEqual(info["state"], self.b.STATE_LIVE)
        self.assertIn("a_sample_size", info["graduation_gates"])
        self.assertEqual(info["n"], 1)

    def test_historical_bet_log_no_live_overlap(self):
        """Full historical Main CSV: no tuple matched by >1 of the 6 LIVE rules."""
        import csv
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "bet_log_main_all.csv"
        if not path.exists():
            self.skipTest("bet_log_main_all.csv not present")

        rows = []
        with path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(
                    {
                        "strategy": r.get("strategy") or "main",
                        "fixture": r.get("fixture"),
                        "market": r.get("market"),
                        "market_label": r.get("market"),
                        "bet_type": "",
                        "odds": r.get("odds"),
                        "league_name": r.get("league"),
                        "league": r.get("league"),
                        "fixture_date": f"{r.get('date') or ''}T{r.get('time') or '00:00'}:00+00:00",
                        "status": r.get("status") or r.get("result"),
                        "pnl_units": r.get("pnl_units"),
                    }
                )
        # Multi-strategy cover for the other five LIVE rules (synthetic).
        rows.extend(
            [
                {"strategy": "cs", "fixture": "X vs Y", "bet_type": "correct_score", "team_name": "0-1", "odds": 8.0, "league_name": "EPL", "fixture_date": "2026-01-01T12:00:00+00:00"},
                {"strategy": "cs", "fixture": "X vs Y", "bet_type": "correct_score", "team_name": "2-1", "odds": 9.0, "league_name": "EPL", "fixture_date": "2026-01-01T12:00:00+00:00"},
                {"strategy": "ev", "fixture": "A vs B", "bet_type": "over3.5", "market_label": "Over 3.5", "odds": 2.2, "league_name": "La Liga", "fixture_date": "2026-01-02T12:00:00+00:00"},
                {"strategy": "h2h", "fixture": "C vs D", "bet_type": "h2h_o25", "market_label": "Over 2.5", "odds": 1.7, "league_name": "MLS", "fixture_date": "2026-01-03T12:00:00+00:00"},
                {"strategy": "arahus", "fixture": "E vs F", "bet_type": "arahus_o25", "market_label": "Over 2.5", "odds": 1.35, "league_name": "MLS", "fixture_date": "2026-01-04T12:00:00+00:00"},
            ]
        )
        overlaps = self.b.find_live_overlaps(rows)
        self.assertEqual(overlaps, [], msg=f"Live overlaps on historical log: {overlaps[:5]}")


if __name__ == "__main__":
    unittest.main()
