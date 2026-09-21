"""Classifier regression for research analytics."""
from __future__ import annotations

import unittest

from app.research_analytics import classify_market


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


if __name__ == "__main__":
    unittest.main()
