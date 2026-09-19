"""Sanity checks for +EV calibration research formulas."""
from __future__ import annotations

import unittest

from research.plus_ev_calibration.backtest import (
    ev_decimal_from_qualifier,
    ev_from_probability,
    raw_model_probability,
)


class PlusEvFormulaTests(unittest.TestCase):
    def test_raw_probability_matches_ev_identity(self):
        ev = ev_decimal_from_qualifier(10.2)
        odds = 1.67
        p = raw_model_probability(ev, odds)
        self.assertAlmostEqual(ev_from_probability(p, odds), ev, places=6)

    def test_high_reported_ev_can_imply_low_probability_at_long_odds(self):
        ev = ev_decimal_from_qualifier(68.5)
        p = raw_model_probability(ev, 3.9)
        self.assertLess(p, 0.5)


if __name__ == "__main__":
    unittest.main()
