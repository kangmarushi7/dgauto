"""Formula / fair-market helpers for calibration v2."""
from __future__ import annotations

import unittest

from research.plus_ev_calibration_v2.fair_market import fair_1x2, fair_two_way
from research.plus_ev_calibration_v2.metrics import clip_prob, ev_from_probability


class FairMarketTests(unittest.TestCase):
    def test_two_way_removes_overround(self):
        yes, no = fair_two_way(1.90, 1.90)
        self.assertAlmostEqual(yes + no, 1.0, places=6)
        self.assertAlmostEqual(yes, 0.5, places=6)

    def test_1x2_sums_to_one(self):
        h, d, a = fair_1x2(2.10, 3.40, 3.50)
        self.assertAlmostEqual(h + d + a, 1.0, places=6)

    def test_ev_identity(self):
        p = clip_prob(0.55)
        self.assertAlmostEqual(ev_from_probability(p, 2.0), 0.10, places=6)


if __name__ == "__main__":
    unittest.main()
