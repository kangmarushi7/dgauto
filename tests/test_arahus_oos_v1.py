"""Tests for Arahus OOS Candidate v1 — frozen filters + chrono split + PnL."""
from __future__ import annotations

import unittest
from datetime import date

from research.arahus_oos_v1.config import FROZEN_CONFIG, FrozenCandidateConfig
from research.arahus_oos_v1.filters import (
    league_allowed,
    odds_in_band,
    period_for_date,
    qualifies_candidate,
)
from research.arahus_oos_v1.load import normalize_market
from research.arahus_oos_v1.metrics import pnl_for_bet, summarize_bets
from research.arahus_oos_v1.pipeline import leakage_audit, run_pipeline


def _row(**kwargs):
    base = {
        "id": "t1",
        "fixture": "A vs B",
        "league_name": "Eredivisie",
        "market": "over_2_5",
        "odds": 1.40,
        "units": 1.0,
        "status": "won",
        "confidence": 70,
        "pnl_units_logged": 0.40,
        "fixture_date_d": "2026-09-05",
    }
    base.update(kwargs)
    return base


class OddsBandTests(unittest.TestCase):
    def test_odds_1_29_rejected(self):
        self.assertFalse(odds_in_band(1.29, lo=1.30, hi=1.49))
        ok, reason = qualifies_candidate(_row(odds=1.29))
        self.assertFalse(ok)
        self.assertIn("odds_out_of_band", reason)

    def test_odds_1_30_accepted(self):
        self.assertTrue(odds_in_band(1.30, lo=1.30, hi=1.49))
        ok, reason = qualifies_candidate(_row(odds=1.30))
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_odds_1_49_accepted(self):
        self.assertTrue(odds_in_band(1.49, lo=1.30, hi=1.49))
        ok, _ = qualifies_candidate(_row(odds=1.49))
        self.assertTrue(ok)

    def test_odds_1_50_rejected(self):
        self.assertFalse(odds_in_band(1.50, lo=1.30, hi=1.49))
        ok, _ = qualifies_candidate(_row(odds=1.50))
        self.assertFalse(ok)

    def test_no_rounding_before_filter(self):
        # 1.299 must not round up to 1.30
        self.assertFalse(odds_in_band(1.299, lo=1.30, hi=1.49))


class MarketTests(unittest.TestCase):
    def test_btts_rejected(self):
        self.assertEqual(normalize_market("BTTS Yes"), "btts_yes")
        ok, reason = qualifies_candidate(_row(market="btts_yes"))
        self.assertFalse(ok)
        self.assertIn("market", reason)

    def test_over_3_5_rejected(self):
        self.assertEqual(normalize_market("Over 3.5"), "over_3_5")
        ok, reason = qualifies_candidate(_row(market="over_3_5"))
        self.assertFalse(ok)

    def test_over_2_5_aliases(self):
        self.assertEqual(normalize_market("Over 2.5"), "over_2_5")
        self.assertEqual(normalize_market("arahus_o25"), "over_2_5")


class LeagueWhitelistTests(unittest.TestCase):
    def test_undefined_whitelist_passes_all(self):
        self.assertTrue(league_allowed("Anything", FROZEN_CONFIG))
        self.assertIsNone(FROZEN_CONFIG.selected_leagues)

    def test_explicit_whitelist_rejects_others(self):
        cfg = FrozenCandidateConfig(selected_leagues=("Eredivisie", "Bundesliga"))
        self.assertTrue(league_allowed("Eredivisie", cfg))
        self.assertFalse(league_allowed("Premier League", cfg))
        ok, reason = qualifies_candidate(_row(league_name="Premier League"), cfg)
        self.assertFalse(ok)
        self.assertIn("league_not_whitelisted", reason)


class MissingOddsAndOpenTests(unittest.TestCase):
    def test_missing_odds_rejected(self):
        ok, reason = qualifies_candidate(_row(odds=None))
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_odds")

    def test_open_bet_excluded_from_settled_roi(self):
        rows = [
            _row(status="won", odds=1.40, units=1.0, pnl_units_logged=0.40),
            _row(id="open1", status="open", odds=1.40, units=1.0, pnl_units_logged=None),
        ]
        m = summarize_bets(rows)
        self.assertEqual(m["n"], 1)
        self.assertEqual(m["won"], 1)


class ChronoAndLeakageTests(unittest.TestCase):
    def test_chronological_split(self):
        self.assertEqual(period_for_date(date(2026, 7, 15)), "development")
        self.assertEqual(period_for_date(date(2026, 8, 31)), "development")
        self.assertEqual(period_for_date(date(2026, 9, 1)), "oos")
        self.assertEqual(period_for_date(date(2026, 9, 20)), "oos")
        self.assertEqual(period_for_date(date(2026, 6, 30)), "pre_development")

    def test_oos_does_not_affect_configuration_selection(self):
        before = FROZEN_CONFIG.to_dict()
        # Simulate evaluating OOS payload — config object is frozen dataclass
        audit = leakage_audit(FROZEN_CONFIG)
        after = FROZEN_CONFIG.to_dict()
        self.assertEqual(before["odds_min"], after["odds_min"])
        self.assertEqual(before["odds_max"], after["odds_max"])
        self.assertEqual(before["selected_leagues"], after["selected_leagues"])
        self.assertFalse(audit["oos_used_for_league_selection"])
        self.assertFalse(audit["oos_used_for_odds_band_selection"])
        self.assertFalse(audit["settled_outcomes_used_for_qualification"])

    def test_qualification_ignores_status_and_pnl(self):
        ok_lost, _ = qualifies_candidate(_row(status="lost", pnl_units_logged=-1.0))
        ok_won, _ = qualifies_candidate(_row(status="won", pnl_units_logged=0.5))
        self.assertTrue(ok_lost)
        self.assertTrue(ok_won)


class PnlConventionTests(unittest.TestCase):
    def test_pnl_matches_arahus_convention(self):
        self.assertAlmostEqual(pnl_for_bet("won", 1.40, 1.0, prefer_logged=False), 0.40)
        self.assertAlmostEqual(pnl_for_bet("lost", 1.40, 1.0, prefer_logged=False), -1.0)
        self.assertAlmostEqual(pnl_for_bet("push", 1.40, 1.0, prefer_logged=False), 0.0)
        self.assertIsNone(pnl_for_bet("open", 1.40, 1.0, prefer_logged=False))

    def test_roi_uses_staked_including_push(self):
        rows = [
            _row(status="won", odds=2.0, units=1.0, pnl_units_logged=1.0),
            _row(id="p", status="push", odds=1.40, units=1.0, pnl_units_logged=0.0),
            _row(id="l", status="lost", odds=1.40, units=1.0, pnl_units_logged=-1.0),
        ]
        m = summarize_bets(rows, prefer_logged_pnl=True)
        self.assertEqual(m["staked"], 3.0)
        self.assertEqual(m["pnl"], 0.0)
        self.assertEqual(m["roi"], 0.0)


class PipelineSmokeTests(unittest.TestCase):
    def test_run_on_uploaded_csv(self):
        payload = run_pipeline()
        self.assertTrue(payload["research_only"])
        self.assertFalse(payload["league_whitelist_status"]["defined_in_repo"])
        self.assertIn("main_result_logged_stake", payload)
        self.assertEqual(len(payload["baseline_comparison"]), 3)
        # B and C identical N when no whitelist
        b = payload["baseline_comparison"][1]
        c = payload["baseline_comparison"][2]
        self.assertEqual(b["n"], c["n"])
        self.assertEqual(payload["clv"]["message"], "CLV unavailable in current dataset.")


if __name__ == "__main__":
    unittest.main()
