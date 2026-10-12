"""Tests for xGOT research variants, kickoff guard, and honest metrics."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from app.db import init_db, list_bets  # noqa: E402
from app.xgot_metrics import financial_pnl, financial_stats, outcome_stats  # noqa: E402
from app.xgot_research import (  # noqa: E402
    XGOT_FW_VERSION,
    build_variant_picks,
    filter_variant,
    sync_all_research_variants,
    sync_variant,
)
from app.xgot_strat import is_post_kickoff, sync_xgot_bets  # noqa: E402


def _side(h, a, t=None):
    return {"home": h, "away": a, "total": t if t is not None else h + a}


def _eligible_raw(*, total=3.2, home=1.4, away=1.8, sot=8.2):
    return {
        "sim_stats": {
            "projected_xg": {"xgot": _side(home, away, total)},
            "big_chances_created": _side(2.0, 1.5, 3.5),
            "shots_inside_box": _side(6.0, 7.0, 13.0),
            "shots_on_target": _side(sot / 2, sot / 2, sot),
            "xg": _side(1.2, 1.3, 2.5),
        }
    }


def _state_for_picks() -> dict:
    """Three fixtures covering B/C/D/E filter branches."""
    matches = [
        {
            "fixture_id": "101",
            "fixture_date": "2026-11-01T15:00:00+00:00",
            "fixture": "A vs B",
            "home_team": "A",
            "away_team": "B",
            "league_name": "Test",
            "over_2_5_odds": 1.9,
            "over_3_5_odds": 3.2,
            "btts_yes_odds": 1.85,
            "home_ml_odds": 2.1,
            "away_ml_odds": 3.4,
        },
        {
            "fixture_id": "102",
            "fixture_date": "2026-11-01T18:00:00+00:00",
            "fixture": "C vs D",
            "home_team": "C",
            "away_team": "D",
            "league_name": "Test",
            "over_2_5_odds": 2.0,
            "over_3_5_odds": 3.5,
            "btts_yes_odds": 1.95,
            "home_ml_odds": 1.8,
            "away_ml_odds": 4.0,
        },
        {
            "fixture_id": "103",
            "fixture_date": "2026-10-01T12:00:00+00:00",  # post-kickoff relative to freeze
            "fixture": "E vs F",
            "home_team": "E",
            "away_team": "F",
            "league_name": "Test",
            "over_2_5_odds": 1.85,
            "over_3_5_odds": 3.0,
            "btts_yes_odds": 1.9,
            "home_ml_odds": 2.2,
            "away_ml_odds": 3.1,
        },
    ]
    fixtures_by_id = {
        "101": {"fixture_id": 101, **_eligible_raw(total=3.2, home=1.4, away=1.8, sot=8.2)},
        # minHA in [1.2, 1.5): home 1.3 away 2.0 → min 1.3; total 3.3 for B too
        "102": {"fixture_id": 102, **_eligible_raw(total=2.8, home=1.3, away=2.0, sot=9.6)},
        "103": {"fixture_id": 103, **_eligible_raw(total=3.1, home=1.25, away=1.85, sot=10.8)},
    }
    return {
        "scraped_at": "2026-10-12T10:00:00+00:00",
        "last_snapshot_id": "snap-test-1",
        "matches": matches,
        "fixtures_by_id": fixtures_by_id,
        "dg_extra_indexes": {},
    }


class KickoffGuardTests(unittest.TestCase):
    def test_is_post_kickoff(self):
        now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(is_post_kickoff("2026-10-12T11:00:00+00:00", now=now))
        self.assertFalse(is_post_kickoff("2026-10-12T13:00:00+00:00", now=now))
        self.assertFalse(is_post_kickoff(None, now=now))

    def test_baseline_sync_flags_post_kickoff(self):
        init_db()
        now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        picks = [
            {
                "fixture_id": "x1",
                "fixture_date": "2026-10-12T10:00:00+00:00",
                "fixture": "Late vs Game",
                "league_name": "T",
                "bet_type": "xgot_o25",
                "team_name": "",
                "odds": 1.9,
                "units": 1.0,
                "home_team": "Late",
                "away_team": "Game",
            }
        ]
        result = sync_xgot_bets(
            picks,
            scraped_at="2026-10-12T09:00:00+00:00",
            scrape_id="s1",
            now=now,
        )
        self.assertEqual(result["post_kickoff_flagged"], 1)
        rows = [r for r in list_bets("xgot") if r.get("fixture") == "Late vs Game"]
        self.assertTrue(rows)
        self.assertTrue(rows[0].get("post_kickoff"))
        self.assertEqual(rows[0].get("strategy_version"), "xgot-baseline-v1")
        self.assertEqual(rows[0].get("scrape_id"), "s1")


class VariantFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.xgot_strat import build_xgot_picks_from_state

        cls.state = _state_for_picks()
        cls.baseline = build_xgot_picks_from_state(cls.state)

    def test_variant_b_o25_bucket(self):
        picks = filter_variant("B", self.baseline)
        self.assertTrue(picks)
        for p in picks:
            self.assertEqual(p["bet_type"], "xgot_o25")
            self.assertGreaterEqual(p["proj_xgot_total"], 3.0)
            self.assertLess(p["proj_xgot_total"], 3.5)

    def test_variant_c_btts_minha(self):
        picks = filter_variant("C", self.baseline)
        self.assertTrue(picks)
        for p in picks:
            self.assertEqual(p["bet_type"], "xgot_btts")
            mn = min(p["proj_xgot_home"], p["proj_xgot_away"])
            self.assertGreaterEqual(mn, 1.2)
            self.assertLess(mn, 1.5)

    def test_variant_d_excludes_o35(self):
        picks = filter_variant("D", self.baseline)
        self.assertTrue(any(p["bet_type"] == "xgot_o25" for p in picks))
        self.assertFalse(any(p["bet_type"] == "xgot_o35" for p in picks))

    def test_variant_e_sot_lines(self):
        picks = filter_variant("E", self.baseline)
        self.assertTrue(picks)
        for p in picks:
            self.assertTrue(str(p["bet_type"]).startswith("xgot_sot_"))
            self.assertIn(float(p["team_name"]), {7.5, 8.5, 9.5})

    def test_research_rejects_post_kickoff(self):
        now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        picks = build_variant_picks("B", self.state, now=now, allow_post_kickoff=False)
        self.assertFalse(
            any(str(p.get("fixture_id")) == "103" for p in picks),
            "post-kickoff fixture 103 must be rejected",
        )
        allowed = build_variant_picks("B", self.state, now=now, allow_post_kickoff=True)
        self.assertTrue(any(str(p.get("fixture_id")) == "103" for p in allowed))


class ResearchSyncTests(unittest.TestCase):
    def test_sync_variant_inserts_isolated_log(self):
        init_db()
        state = _state_for_picks()
        now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        result = sync_variant("B", state, now=now, allow_post_kickoff=False)
        self.assertEqual(result["log_type"], "xgot_fw_b")
        self.assertEqual(result["strategy_version"], XGOT_FW_VERSION)
        self.assertGreaterEqual(result["inserted"], 1)
        rows = list_bets("xgot_fw_b")
        self.assertTrue(all(r.get("strategy_version") == XGOT_FW_VERSION for r in rows))

    def test_sync_all_skipped_when_env_off(self):
        with patch("app.xgot_research.XGOT_RESEARCH_SYNC_ENABLED", False):
            out = sync_all_research_variants(_state_for_picks())
        self.assertTrue(out.get("skipped"))
        self.assertEqual(out.get("inserted"), 0)


class MetricsTests(unittest.TestCase):
    def test_null_odds_win_has_no_financial_pnl(self):
        entry = {"status": "won", "odds": None, "units": 1.0}
        self.assertIsNone(financial_pnl(entry))
        stats = financial_stats([entry])
        self.assertFalse(stats["financial_roi_available"])
        self.assertIsNone(stats["roi"])
        self.assertEqual(outcome_stats([entry])["won"], 1)

    def test_priced_win_matches_odds_minus_one(self):
        entry = {"status": "won", "odds": 2.5, "units": 1.0}
        self.assertAlmostEqual(financial_pnl(entry), 1.5)
        lost = {"status": "lost", "odds": 2.5, "units": 1.0}
        self.assertAlmostEqual(financial_pnl(lost), -1.0)


if __name__ == "__main__":
    unittest.main()
