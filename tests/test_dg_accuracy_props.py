"""Tests for DataGaffer daily_accuracy corners/SOT helpers."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.dg_accuracy_props import (
    clear_accuracy_props_cache,
    lookup_accuracy_props,
    parse_actual_score,
    parse_pair_total,
)


class ParsePairTotalTests(unittest.TestCase):
    def test_pair_string(self):
        self.assertEqual(parse_pair_total("5 - 5"), 10)
        self.assertEqual(parse_pair_total("10 - 1"), 11)
        self.assertEqual(parse_pair_total("4 – 3"), 7)  # en-dash

    def test_numeric(self):
        self.assertEqual(parse_pair_total(12), 12)
        self.assertEqual(parse_pair_total(9.0), 9)

    def test_invalid(self):
        self.assertIsNone(parse_pair_total(None))
        self.assertIsNone(parse_pair_total(""))
        self.assertIsNone(parse_pair_total("nope"))


class ParseScoreTests(unittest.TestCase):
    def test_score(self):
        self.assertEqual(parse_actual_score("2 - 1"), (2, 1))
        self.assertIsNone(parse_actual_score("x"))


class LookupAccuracyPropsTests(unittest.TestCase):
    def setUp(self):
        clear_accuracy_props_cache()

    def tearDown(self):
        clear_accuracy_props_cache()

    def test_lookup_by_fixture_name_and_date(self):
        payload = {
            "daily": [
                {
                    "date": "2026-09-20",
                    "matches": [
                        {
                            "fixture_id": 1557416,
                            "date": "2026-09-20",
                            "match": "Tottenham vs Aston Villa",
                            "actual_score": "1 - 0",
                            "actual_corners": "11 - 1",
                            "actual_sot": "7 - 6",
                            "league": "Premier League",
                        }
                    ],
                }
            ]
        }
        with patch("app.dg_accuracy_props._load_json", return_value=payload):
            hit = lookup_accuracy_props(
                {
                    "fixture": "Tottenham vs Aston Villa",
                    "fixture_date": "2026-09-20T15:00:00+00:00",
                },
                force_refresh=True,
            )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["corners_total"], 12)
        self.assertEqual(hit["sot_total"], 13)
        self.assertEqual(hit["intHomeScore"], 1)
        self.assertEqual(hit["intAwayScore"], 0)
        self.assertEqual(hit["fixture_id"], "1557416")


class CornersMarketMatchTests(unittest.TestCase):
    def test_match_corners_over_line(self):
        from app.polymarket_h2h_markets import (
            is_main_match_total_corners_market,
            match_corners_over,
            resolve_h2h_market,
            total_corners_event_slug,
        )

        markets = [
            {
                "slug": "eng-tot-avl-2026-09-20-corners-total-9pt5",
                "question": "O/U 9.5 Total Corners",
                "outcomes": '["Over", "Under"]',
                "outcomePrices": '["0.52", "0.48"]',
                "clobTokenIds": '["YES_C", "NO_C"]',
            },
            {
                "slug": "eng-tot-avl-2026-09-20-corners-first-half-4pt5",
                "question": "1st Half O/U 4.5 Total Corners",
                "outcomes": '["Over", "Under"]',
                "outcomePrices": '["0.40", "0.60"]',
                "clobTokenIds": '["YES_FH", "NO_FH"]',
            },
        ]
        self.assertTrue(is_main_match_total_corners_market(markets[0]))
        self.assertFalse(is_main_match_total_corners_market(markets[1]))
        self.assertEqual(match_corners_over(markets, line=9.5), markets[0])
        self.assertIsNone(match_corners_over(markets, line=8.5))

        m, outcome, kind = resolve_h2h_market(
            bet_type="h2h_c_o95",
            primary_markets=[],
            more_markets=[],
            corners_markets=markets,
            home="Tottenham",
            away="Aston Villa",
        )
        self.assertEqual(m, markets[0])
        self.assertEqual(outcome, "Over")
        self.assertEqual(kind, "corners")
        self.assertEqual(
            total_corners_event_slug("eng-tot-avl-2026-09-20"),
            "eng-tot-avl-2026-09-20-total-corners",
        )


if __name__ == "__main__":
    unittest.main()
