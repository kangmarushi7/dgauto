"""Unit tests for xGOT paper strategy pick builder, resolve kinds, and slice helper."""
from __future__ import annotations

import math
import unittest

from app.bet_scenarios import resolve_kind_for_entry
from app.xgot_strat import (
    build_xgot_picks,
    display_metric_for_entry,
    enrich_xgot_entries,
    extract_projections,
    format_ha_total,
    is_eligible,
    market_label_for_entry,
    pick_sot_line,
    select_fixture_ids_for_slice,
    team_side_for_entry,
)


def _side(h, a, t=None):
    return {"home": h, "away": a, "total": t if t is not None else h + a}


class ExtractProjectionsTests(unittest.TestCase):
    def test_primary_sim_stats_paths(self):
        raw = {
            "fixture_id": 1,
            "sim_stats": {
                "projected_xg": {"xgot": _side(1.1, 1.4, 2.5)},
                "big_chances_created": _side(2.0, 1.5, 3.5),
                "shots_inside_box": _side(6.0, 7.0, 13.0),
                "shots_on_target": _side(3.0, 4.0, 7.0),
                "xg": _side(1.2, 1.3, 2.5),
            },
        }
        p = extract_projections(raw)
        self.assertEqual(p["proj_xgot_home"], 1.1)
        self.assertEqual(p["proj_xgot_away"], 1.4)
        self.assertEqual(p["proj_xgot_total"], 2.5)
        self.assertEqual(p["proj_big_chances_total"], 3.5)
        self.assertEqual(p["proj_box_shots_total"], 13.0)
        self.assertEqual(p["proj_sot_total"], 7.0)
        self.assertTrue(is_eligible(p))

    def test_heat_fallback_for_big_chances(self):
        raw = {
            "fixture_id": 2,
            "sim_stats": {
                "shots_inside_box": _side(5.0, 6.0, 11.0),
                "shots_on_target": _side(3.5, 4.0, 7.5),
            },
        }
        heat = {
            "projected_stats": {
                "home": {"big_chances_created": 2.2},
                "away": {"big_chances_created": 1.3},
            }
        }
        p = extract_projections(raw, heat=heat)
        self.assertIsNone(p["proj_xgot_total"])
        self.assertEqual(p["proj_big_chances_home"], 2.2)
        self.assertEqual(p["proj_big_chances_away"], 1.3)
        self.assertAlmostEqual(p["proj_big_chances_total"], 3.5)
        self.assertTrue(is_eligible(p))

    def test_ineligible_without_metrics(self):
        p = extract_projections({"fixture_id": 3, "sim_stats": {}})
        self.assertFalse(is_eligible(p))


class SotLineTests(unittest.TestCase):
    def test_nearest_at_or_below(self):
        self.assertEqual(pick_sot_line(8.4), 7.5)
        self.assertEqual(pick_sot_line(8.5), 8.5)
        self.assertEqual(pick_sot_line(10.5), 10.5)
        self.assertEqual(pick_sot_line(12.0), 10.5)
        self.assertIsNone(pick_sot_line(7.0))
        self.assertIsNone(pick_sot_line(None))


class BuildPicksTests(unittest.TestCase):
    def test_builds_markets_and_skips_missing_odds_except_sot(self):
        matches = [
            {
                "fixture_id": 10,
                "fixture_date": "2026-10-05T12:00:00+00:00",
                "fixture": "Home vs Away",
                "league_name": "Test",
                "home_team": "Home",
                "away_team": "Away",
                "over_2_5_odds": 1.9,
                "over_3_5_odds": 3.1,
                "btts_yes_odds": 1.85,
                "home_ml_odds": 2.4,
                "away_ml_odds": 2.9,
            }
        ]
        fixtures_by_id = {
            "10": {
                "fixture_id": 10,
                "sim_stats": {
                    "projected_xg": {"xgot": _side(1.2, 1.5, 2.7)},
                    "big_chances_created": _side(2.0, 2.0, 4.0),
                    "shots_inside_box": _side(7.0, 8.0, 15.0),
                    "shots_on_target": _side(4.0, 4.5, 8.5),
                },
            }
        }
        picks = build_xgot_picks(matches, fixtures_by_id)
        types = {p["bet_type"] for p in picks}
        self.assertIn("xgot_o25", types)
        self.assertIn("xgot_o35", types)
        self.assertIn("xgot_btts", types)
        self.assertIn("xgot_sot_o85", types)
        self.assertIn("xgot_ml", types)
        ml = next(p for p in picks if p["bet_type"] == "xgot_ml")
        self.assertEqual(ml["team_name"], "Home")
        self.assertEqual(ml["odds"], 2.4)
        self.assertEqual(ml["proj_xgot_home"], 1.2)
        self.assertEqual(ml["proj_xgot_away"], 1.5)
        self.assertEqual(team_side_for_entry(ml), "home")
        self.assertEqual(display_metric_for_entry(ml, "proj_xgot"), 1.2)
        enriched = enrich_xgot_entries([ml])[0]
        self.assertEqual(enriched["xgot_display_label"], "1.2 (H)")
        self.assertEqual(enriched["xgot_breakdown"], "1.2 / 1.5 (2.7)")
        o25 = next(p for p in picks if p["bet_type"] == "xgot_o25")
        self.assertEqual(display_metric_for_entry(o25, "proj_xgot"), 2.7)
        sot = next(p for p in picks if p["bet_type"].startswith("xgot_sot_"))
        self.assertEqual(sot["team_name"], "8.5")

    def test_format_ha_total(self):
        self.assertEqual(format_ha_total(1.1, 1.4, 2.5), "1.1 / 1.4 (2.5)")
        self.assertEqual(format_ha_total(None, None, 2.5), "2.5")
        self.assertEqual(format_ha_total(None, None, None), "—")

    def test_skips_o25_without_odds(self):
        matches = [
            {
                "fixture_id": 11,
                "fixture": "A vs B",
                "home_team": "A",
                "away_team": "B",
                "home_ml_odds": 1.8,
                "away_ml_odds": 4.0,
            }
        ]
        fixtures_by_id = {
            "11": {
                "fixture_id": 11,
                "sim_stats": {
                    "projected_xg": {"xgot": _side(1.0, 1.0, 2.0)},
                    "shots_inside_box": _side(5.0, 5.0, 10.0),
                    "shots_on_target": _side(3.0, 3.0, 6.0),
                },
            }
        }
        picks = build_xgot_picks(matches, fixtures_by_id)
        types = {p["bet_type"] for p in picks}
        self.assertNotIn("xgot_o25", types)
        self.assertIn("xgot_ml", types)


class ResolveKindTests(unittest.TestCase):
    def test_resolve_kinds(self):
        cases = [
            ("xgot_o25", "over2.5"),
            ("xgot_o35", "over3.5"),
            ("xgot_btts", "btts"),
            ("xgot_sot_o75", "h2h_sot"),
            ("xgot_sot_o105", "h2h_sot"),
            ("xgot_ml", "moneyline"),
        ]
        for bt, kind in cases:
            with self.subTest(bt=bt):
                self.assertEqual(resolve_kind_for_entry({"bet_type": bt}), kind)

    def test_market_labels(self):
        self.assertEqual(market_label_for_entry({"bet_type": "xgot_o25"}), "Over 2.5")
        self.assertEqual(
            market_label_for_entry({"bet_type": "xgot_sot_o95", "team_name": "9.5"}),
            "SOT O9.5",
        )
        self.assertEqual(
            market_label_for_entry({"bet_type": "xgot_ml", "team_name": "Arsenal"}),
            "Arsenal ML",
        )


class SliceHelperTests(unittest.TestCase):
    def test_top_10_percent_stable_ties(self):
        entries = [
            {"fixture_id": "a", "proj_xgot_total": 3.0},
            {"fixture_id": "b", "proj_xgot_total": 2.0},
            {"fixture_id": "c", "proj_xgot_total": 2.0},
            {"fixture_id": "d", "proj_xgot_total": 1.0},
            {"fixture_id": "e", "proj_xgot_total": 0.5},
            {"fixture_id": "f", "proj_xgot_total": 0.4},
            {"fixture_id": "g", "proj_xgot_total": 0.3},
            {"fixture_id": "h", "proj_xgot_total": 0.2},
            {"fixture_id": "i", "proj_xgot_total": 0.1},
            {"fixture_id": "j", "proj_xgot_total": 0.05},
        ]
        # top 10% of 10 → ceil(1) = 1 → fixture a
        kept = select_fixture_ids_for_slice(
            entries, rank_by="proj_xgot_total", percentile=0.10
        )
        self.assertEqual(kept, {"a"})
        # top 20% → ceil(2) = 2 → a, then b before c (same metric, fixture_id asc)
        kept20 = select_fixture_ids_for_slice(
            entries, rank_by="proj_xgot_total", percentile=0.20
        )
        self.assertEqual(kept20, {"a", "b"})
        n = len(entries)
        self.assertEqual(math.ceil(n * 0.10), 1)


if __name__ == "__main__":
    unittest.main()
