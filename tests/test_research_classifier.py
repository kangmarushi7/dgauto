"""Classifier regression for research analytics."""
from __future__ import annotations

import unittest

from app.research_analytics import classify_market
from app.strategy_buckets import canonical_market


class ResearchClassifierTests(unittest.TestCase):
    def test_team_over_1_5_not_match_over(self):
        self.assertEqual(
            classify_market("Team Over 1.5 Goals", "to15_t20"),
            "team_o1.5",
        )
        self.assertEqual(
            classify_market("Benfica · Team Over 1.5 Goals", "to15_t25"),
            "team_o1.5",
        )

    def test_match_over_1_5(self):
        self.assertEqual(classify_market("Over 1.5 (unsplit)", "over1.5"), "over_1.5")
        self.assertEqual(classify_market("Over 1.5 Goals", "o15_t35"), "over_1.5")

    def test_team_over_0_5(self):
        self.assertEqual(
            classify_market("Team Over 0.5 Goals", "to05_t20"),
            "team_o0.5",
        )

    def test_over_2_5(self):
        self.assertEqual(classify_market("Over 2.5 Goals", "over2.5"), "over_2.5")

    def test_main_scenario_bet_type_codes(self):
        """DG main log uses codes like o25_t35 with empty market labels."""
        cases = {
            "o25_t35": "over_2.5",
            "o25_t40": "over_2.5",
            "o35_t40": "over_3.5",
            "u25_t20": "under_2.5",
            "u35_t20": "under_3.5",
            "ml_win60": "moneyline",
            "ml_win70": "moneyline",
            "dc_win60": "win_or_draw",
            "dc_win70": "win_or_draw",
        }
        for bt, expected in cases.items():
            with self.subTest(bt=bt):
                self.assertEqual(classify_market("", bt), expected)

    def test_canonical_market_main_scenarios_not_other(self):
        cases = {
            "o25_t35": "Over 2.5",
            "o35_t40": "Over 3.5",
            "u25_t20": "Under 2.5",
            "u35_t20": "Under 3.5",
            "ml_win60": "Moneyline",
            "dc_win60": "Win or Draw",
            "to15_t25": "Team Over 1.5",
            "o15_t40": "Over 1.5",
            "btts_both15": "BTTS Yes",
        }
        for bt, expected in cases.items():
            with self.subTest(bt=bt):
                got = canonical_market(
                    {"strategy": "main", "bet_type": bt, "team_name": "Charlotte"}
                )
                self.assertEqual(got, expected)


if __name__ == "__main__":
    unittest.main()
