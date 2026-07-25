"""Unit tests for the Arahus Engine (no network)."""
from __future__ import annotations

import unittest

from app.arahus_engine import (
    _poisson_cdf_ge,
    build_fixture_profile,
    pick_markets,
    project_match,
)
from app.bet_scenarios import ARAHUS_BET_TYPE_MAP, resolve_kind_for_entry


def _profile(**overrides):
    base = {
        "home_team": "Home FC",
        "away_team": "Away FC",
        "sim": {
            "home_win_pct": 48.0,
            "draw_pct": 24.0,
            "away_win_pct": 28.0,
            "over_1_5_pct": 78.0,
            "over_2_5_pct": 62.0,
            "over_3_5_pct": 38.0,
            "under_2_5_pct": 38.0,
            "btts_pct": 58.0,
        },
        "xg": {"home": 1.7, "away": 1.2, "total": 2.9},
        "volume": {"corners": 10.2, "shots": 24.0, "sot": 8.5, "fh_goals": 1.2},
        "ratings": {
            "home": {"DGRtg": 62, "ORtg": 60, "DRtg": 55, "pace_index": 61, "nec_index": 60, "agix_index": 58},
            "away": {"DGRtg": 54, "ORtg": 52, "DRtg": 58, "pace_index": 57, "nec_index": 52, "agix_index": 50},
            "dgrtg_gap": 8.0,
            "ortg_gap": 8.0,
            "drtg_gap": -3.0,
        },
        "indexes": {
            "pace": 63.0,
            "nec": 58.0,
            "agix": 56.0,
            "control": 55.0,
            "ppda": 9.5,
            "consistency": 60.0,
            "pace_bucket_o25": 61.0,
            "pace_bucket_btts": 57.0,
            "pace_bucket": "high",
        },
        "regression": {"home_luck": 0.1, "away_luck": -0.1},
        "highlights": ["Highest pace"],
        "odds": {
            "home_ml": 2.1,
            "away_ml": 3.6,
            "over_1_5": 1.35,
            "over_2_5": 1.85,
            "over_3_5": 3.2,
            "under_2_5": 2.05,
            "btts_yes": 1.8,
            "home_o0_5": 1.25,
            "away_o0_5": 1.4,
            "home_o1_5": 2.4,
            "away_o1_5": 3.1,
            "dc_1x": 1.35,
            "dc_x2": 1.55,
        },
    }
    base.update(overrides)
    return base


class PoissonTests(unittest.TestCase):
    def test_ge_zero(self):
        self.assertEqual(_poisson_cdf_ge(0, 2.0), 1.0)

    def test_over_25_around_three(self):
        # P(X>=3) for λ=2.9 should be well above 50%
        self.assertGreater(_poisson_cdf_ge(3, 2.9), 0.5)


class ProfileTests(unittest.TestCase):
    def test_build_profile_from_raw(self):
        raw = {
            "fixture_id": 1,
            "date": "2026-07-26T00:00:00+00:00",
            "home": {"name": "Alpha"},
            "away": {"name": "Beta"},
            "league": {"name": "Test"},
            "sim_stats": {
                "percents": {"home_win_pct": 55, "over_2_5_pct": 60, "btts_pct": 52},
                "xg": {"home": 1.5, "away": 1.1, "total": 2.6},
                "corners": {"total": 9.5},
                "shots": {"total": 22},
            },
        }
        match = {
            "fixture_id": 1,
            "fixture": "Alpha vs Beta",
            "home_team": "Alpha",
            "away_team": "Beta",
            "win_pct": 55,
            "over_2_5_odds": 1.9,
        }
        extra = {
            "home_rating": {"DGRtg": 60, "pace_index": 58, "nec_index": 55},
            "away_rating": {"DGRtg": 52, "pace_index": 54, "nec_index": 50},
            "matchup_pace": {"score": 59, "nec_index": 54, "agix_index": 51},
            "highlight_roles": ["Highest BTTS"],
            "home_xg_regression": {},
            "away_xg_regression": {},
        }
        profile = build_fixture_profile(raw, match, extra)
        self.assertEqual(profile["home_team"], "Alpha")
        self.assertAlmostEqual(profile["xg"]["total"], 2.6)
        self.assertEqual(profile["indexes"]["pace"], 59)
        self.assertIn("Highest BTTS", profile["highlights"])


class ProjectionTests(unittest.TestCase):
    def test_high_pace_lifts_total(self):
        proj = project_match(_profile())
        self.assertIsNotNone(proj["total_xg"])
        self.assertGreater(proj["total_xg"], 2.9)
        self.assertIn(proj["archetype"], {"High-event", "Mismatch", "BTTS lean"})

    def test_low_pace_low_xg_is_low_event(self):
        p = _profile()
        p["xg"] = {"home": 0.9, "away": 0.8, "total": 1.7}
        p["indexes"]["pace"] = 48
        p["indexes"]["nec"] = 45
        p["ratings"]["dgrtg_gap"] = 1.0
        proj = project_match(p)
        self.assertEqual(proj["archetype"], "Low-event")


class PickTests(unittest.TestCase):
    def test_high_event_fixture_can_produce_overs(self):
        profile = _profile()
        proj = project_match(profile)
        picks = pick_markets(profile, proj)
        self.assertTrue(picks)
        types = {p["bet_type"] for p in picks}
        # Should not stack O2.5 and U2.5
        self.assertFalse({"arahus_o25", "arahus_u25"} <= types)
        for p in picks:
            self.assertGreaterEqual(p["confidence"], 62)

    def test_value_required_when_odds_present(self):
        profile = _profile()
        # Crush the edge: set O2.5 odds so implied >> model
        profile["odds"]["over_2_5"] = 1.05
        profile["odds"]["over_1_5"] = 1.05
        profile["odds"]["over_3_5"] = 1.05
        profile["odds"]["btts_yes"] = 1.05
        profile["odds"]["home_ml"] = 1.05
        profile["odds"]["away_ml"] = 1.05
        profile["odds"]["home_o1_5"] = 1.05
        profile["odds"]["away_o1_5"] = 1.05
        profile["odds"]["home_o0_5"] = 1.05
        profile["odds"]["away_o0_5"] = 1.05
        profile["odds"]["dc_1x"] = 1.05
        profile["odds"]["dc_x2"] = 1.05
        profile["odds"]["under_2_5"] = 1.05
        proj = project_match(profile)
        picks = pick_markets(profile, proj)
        # Corners may still qualify (no odds). Goal markets with bad odds should not.
        for p in picks:
            if p["odds"] is not None:
                self.assertGreaterEqual(p["edge"] or -99, 2.0)


class ResolveMapTests(unittest.TestCase):
    def test_arahus_types_resolve(self):
        self.assertEqual(
            resolve_kind_for_entry({"bet_type": "arahus_o25"}),
            "over2.5",
        )
        self.assertEqual(
            resolve_kind_for_entry({"bet_type": "arahus_corners_o95"}),
            "h2h_corners",
        )
        self.assertEqual(
            resolve_kind_for_entry({"bet_type": "arahus_dc_1x"}),
            "dc_1x",
        )
        self.assertTrue(all("resolve" in v for v in ARAHUS_BET_TYPE_MAP.values()))


if __name__ == "__main__":
    unittest.main()
