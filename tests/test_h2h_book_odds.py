"""Unit tests for DataGaffer H2H corner odds matching."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.h2h_book_odds import (
    attach_datagaffer_corner_odds,
    corner_book_odds,
    load_corners_odds_index,
)


SAMPLE_ALL_ODDS = {
    "Kalmar FF vs Mjallby AIF": {
        "home_team": "Kalmar FF",
        "away_team": "Mjallby AIF",
        "markets": {
            "corners_over_under": {
                "line": {"value": "Over 9.5", "odd": "1.80"},
                "sim_probability": 56.4,
            }
        },
    },
    "Viborg vs Odense": {
        "home_team": "Viborg",
        "away_team": "Odense",
        "markets": {
            "corners_over_under": {
                "line": {"value": "Over 10.5", "odd": "1.91"},
            }
        },
    },
}


class CornerOddsTests(unittest.TestCase):
    @patch("app.h2h_book_odds._load_json", return_value=SAMPLE_ALL_ODDS)
    def test_index_and_exact_line(self, _load):
        idx = load_corners_odds_index()
        hit = corner_book_odds("Kalmar FF", "Mjallby AIF", 9.5, index=idx)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["odds"], 1.8)
        self.assertEqual(hit["source"], "datagaffer")
        miss = corner_book_odds("Kalmar FF", "Mjallby AIF", 8.5, index=idx)
        self.assertIsNone(miss)

    @patch("app.h2h_book_odds._load_json", return_value=SAMPLE_ALL_ODDS)
    def test_attach_fills_matching_corners_only(self, _load):
        picks = [
            {
                "home": "Kalmar FF",
                "away": "Mjallby AIF",
                "bet_type": "h2h_c_o95",
                "label": "Corners O9.5",
                "odds": None,
            },
            {
                "home": "Kalmar FF",
                "away": "Mjallby AIF",
                "bet_type": "h2h_c_o85",
                "label": "Corners O8.5",
                "odds": None,
            },
            {
                "home": "Kalmar FF",
                "away": "Mjallby AIF",
                "bet_type": "h2h_sot_o75",
                "label": "SOT O7.5",
                "odds": None,
            },
            {
                "home": "Viborg",
                "away": "Odense",
                "bet_type": "h2h_c_o105",
                "label": "Corners O10.5",
                "odds": None,
            },
        ]
        out = attach_datagaffer_corner_odds(picks)
        self.assertEqual(out[0]["odds"], 1.8)
        self.assertEqual(out[0]["odds_source"], "datagaffer")
        self.assertIsNone(out[1]["odds"])
        self.assertIsNone(out[2]["odds"])
        self.assertEqual(out[3]["odds"], 1.91)


if __name__ == "__main__":
    unittest.main()
