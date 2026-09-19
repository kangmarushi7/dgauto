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
        self.assertIn("P3_O3_5", ports)
        self.assertIn("P1_ODDS_2_10_2_50", ports)
        self.assertNotIn("P4_O2_5", ports)
        self.assertNotIn("P2_DC_X2", ports)

    def test_dc_x2_portfolio(self):
        ports = portfolio_membership(
            {"bet_type": "dc_x2", "market": "DC X2", "odds_at_signal": 1.85}
        )
        self.assertEqual(ports, ["P2_DC_X2"])

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

    def test_entry_to_signal_assigns_portfolios(self):
        from research.plus_ev_forward_test.seed_db import entry_to_signal

        sig = entry_to_signal(
            {
                "id": "abc",
                "odds": 2.25,
                "qualifier_pct": 12.0,
                "status": "won",
                "bet_type": "over3.5",
                "market": "Over 3.5",
                "league_name": "EPL",
                "team_name": "",
                "fixture_date": "2026-01-01",
                "created_at": "2026-01-01T00:00:00Z",
                "fixture": "A vs B",
            },
            sample_kind="test",
            source="test",
        )
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertIn("P1_ODDS_2_10_2_50", sig["portfolios"])
        self.assertIn("P3_O3_5", sig["portfolios"])


if __name__ == "__main__":
    unittest.main()
