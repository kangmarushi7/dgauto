"""Unit tests for forward-test portfolios / CLV / fair market."""
from __future__ import annotations

import unittest

from research.plus_ev_forward_test.clv import clv_from_odds
from research.plus_ev_forward_test.fair_market import fair_from_outcome_odds
from research.plus_ev_forward_test.portfolios import portfolio_membership
from research.plus_ev_forward_test.status import classify_portfolio


class ForwardTestBasics(unittest.TestCase):
    def test_portfolios_independent(self):
        s = {
            "bet_type": "over3.5",
            "market": "Over 3.5",
            "league": "Serie A",
            "odds_at_signal": 2.20,
        }
        ports = portfolio_membership(s)
        self.assertIn("A_O3_5", ports)
        self.assertIn("C_SERIE_A", ports)
        self.assertIn("D_ODDS_2_10_2_50", ports)
        self.assertNotIn("B_O2_5", ports)

    def test_fair_two_way(self):
        info = fair_from_outcome_odds({"over": 2.0, "under": 1.80})
        self.assertTrue(info["fair_available"])
        probs = info["fair_probabilities"]
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=6)

    def test_clv_positive_when_odds_shorten(self):
        info = clv_from_odds(2.20, 2.00)
        self.assertTrue(info["clv_available"])
        self.assertGreater(info["clv"], 0)

    def test_status_insufficient(self):
        self.assertEqual(classify_portfolio({"n": 10, "roi": 0.2}), "INSUFFICIENT SAMPLE")


if __name__ == "__main__":
    unittest.main()
