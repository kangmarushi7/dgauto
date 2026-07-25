"""Unit tests for DG scenario-validation calibration (no network)."""
from __future__ import annotations

import unittest

from app.dg_calibration import (
    MIN_SAMPLE,
    calibration_ratio,
    calibrate_fixture,
    pick_scenario_bucket,
)


SAMPLE_VALIDATION = {
    "win_60": {"games": 151, "win": 101, "win_or_draw": 131},
    "win_70": {"games": 28, "win": 20, "win_or_draw": 25},
    "tot_35": {"games": 89, "o15": 76, "o25": 57, "o35": 34},
    "tot_40": {"games": 18, "o15": 15, "o25": 12, "o35": 7},
    "team_20": {"games": 188, "o05": 165, "o15": 117},
    "team_25": {"games": 36, "o05": 33, "o15": 23, "o25": 18},
    "btts_15": {"games": 99, "btts": 66},
    "under_20": {"games": 6, "u25": 3, "u35": 5},
}


class CalibrationRatioTests(unittest.TestCase):
    def test_win_60_calibrated_ratio(self):
        # 101/151 ≈ 66.887% / 60 ≈ 1.115
        result = calibration_ratio(SAMPLE_VALIDATION, "win_60", "win", 60.0)
        self.assertEqual(result["status"], "calibrated")
        self.assertEqual(result["n"], 151)
        self.assertAlmostEqual(result["historicalHitPct"], 66.9, places=1)
        self.assertAlmostEqual(result["ratio"], 1.115, places=3)

    def test_min_sample_floor_under_20(self):
        result = calibration_ratio(SAMPLE_VALIDATION, "under_20", "u25", 55.0)
        self.assertEqual(result["status"], "uncalibrated")
        self.assertEqual(result["ratio"], 1.0)
        self.assertIsNone(result["historicalHitPct"])
        self.assertEqual(result["n"], 6)
        self.assertLess(result["n"], MIN_SAMPLE)

    def test_tot_40_below_min_sample(self):
        result = calibration_ratio(SAMPLE_VALIDATION, "tot_40", "o25", 70.0)
        self.assertEqual(result["status"], "uncalibrated")
        self.assertEqual(result["n"], 18)

    def test_zero_sim_pct_uncalibrated(self):
        result = calibration_ratio(SAMPLE_VALIDATION, "win_60", "win", 0)
        self.assertEqual(result["status"], "uncalibrated")
        self.assertEqual(result["ratio"], 1.0)


class PickScenarioBucketTests(unittest.TestCase):
    def test_win_72_matches_win_70_not_win_60(self):
        matches = pick_scenario_bucket(
            {
                "sim_home_win_pct": 72.0,
                "sim_away_win_pct": 15.0,
                "sim_total_goals": 2.5,
                "sim_home_goals": 1.2,
                "sim_away_goals": 1.3,
                "sim_over_2_5_pct": 50.0,
                "sim_under_2_5_pct": 50.0,
                "sim_btts_pct": 55.0,
            }
        )
        keys = [m["scenarioKey"] for m in matches]
        self.assertIn("win_70", keys)
        self.assertNotIn("win_60", keys)

    def test_tot_40_beats_tot_35(self):
        matches = pick_scenario_bucket(
            {
                "sim_home_win_pct": 40.0,
                "sim_away_win_pct": 35.0,
                "sim_total_goals": 4.2,
                "sim_home_goals": 2.1,
                "sim_away_goals": 2.1,
                "sim_over_2_5_pct": 79.0,
                "sim_under_2_5_pct": 21.0,
                "sim_btts_pct": 70.0,
                "sim_home_o1_5_pct": 65.0,
                "sim_away_o1_5_pct": 65.0,
            }
        )
        keys = [m["scenarioKey"] for m in matches]
        self.assertIn("tot_40", keys)
        self.assertNotIn("tot_35", keys)
        tot = next(m for m in matches if m["scenarioKey"] == "tot_40")
        self.assertEqual(tot["subKey"], "o25")
        self.assertEqual(tot["simPct"], 79.0)

    def test_btts_requires_both_sides_xg_15(self):
        no = pick_scenario_bucket(
            {
                "sim_total_goals": 2.8,
                "sim_home_goals": 1.6,
                "sim_away_goals": 1.2,  # away below 1.5
                "sim_over_2_5_pct": 55.0,
                "sim_btts_pct": 60.0,
            }
        )
        self.assertNotIn("btts_15", [m["scenarioKey"] for m in no])

        yes = pick_scenario_bucket(
            {
                "sim_total_goals": 3.2,
                "sim_home_goals": 1.6,
                "sim_away_goals": 1.6,
                "sim_over_2_5_pct": 60.0,
                "sim_btts_pct": 66.0,
            }
        )
        self.assertIn("btts_15", [m["scenarioKey"] for m in yes])

    def test_team_side_aware_highest_threshold(self):
        matches = pick_scenario_bucket(
            {
                "sim_total_goals": 4.5,
                "sim_home_goals": 2.6,
                "sim_away_goals": 2.1,
                "sim_over_2_5_pct": 70.0,
                "sim_home_o1_5_pct": 68.0,
                "sim_away_o1_5_pct": 55.0,
                "sim_btts_pct": 70.0,
            }
        )
        team = [m for m in matches if m["scenarioKey"].startswith("team_")]
        by_side = {m["side"]: m["scenarioKey"] for m in team}
        self.assertEqual(by_side.get("home"), "team_25")
        self.assertEqual(by_side.get("away"), "team_20")


class CalibrateFixtureTests(unittest.TestCase):
    def test_end_to_end_includes_status(self):
        rows = calibrate_fixture(
            {
                "sim_home_win_pct": 62.0,
                "sim_away_win_pct": 20.0,
                "sim_total_goals": 3.6,
                "sim_home_goals": 1.9,
                "sim_away_goals": 1.7,
                "sim_over_2_5_pct": 64.0,
                "sim_under_2_5_pct": 36.0,
                "sim_btts_pct": 58.0,
            },
            SAMPLE_VALIDATION,
        )
        keys = {r["scenarioKey"] for r in rows}
        self.assertIn("win_60", keys)
        self.assertIn("tot_35", keys)
        win = next(r for r in rows if r["scenarioKey"] == "win_60")
        self.assertEqual(win["status"], "calibrated")
        tot = next(r for r in rows if r["scenarioKey"] == "tot_35")
        # 57/89 ≈ 64.0% / 64 ≈ 1.001
        self.assertEqual(tot["status"], "calibrated")


if __name__ == "__main__":
    unittest.main()
