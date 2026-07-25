"""Unit tests for Polymarket fixture discovery (kickoff match + query expansion)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app import polymarket_discovery as disc


def _event(slug, title, *, game_start=None, start_time=None, end_date=None):
    markets = [{"gameStartTime": game_start}] if game_start else []
    return {
        "slug": slug,
        "title": title,
        "id": slug,
        "markets": markets,
        "startTime": start_time,
        "endDate": end_date,
        # listing date — must never be used as the kickoff
        "startDate": "2020-01-01T00:00:00Z",
    }


class KickoffParseTests(unittest.TestCase):
    def test_short_offset_and_space_separator(self):
        dt = disc.parse_kickoff_dt("2026-07-26 03:00:00+00")
        self.assertEqual(dt.isoformat(), "2026-07-26T03:00:00+00:00")

    def test_zulu(self):
        dt = disc.parse_kickoff_dt("2026-07-25T23:30:00Z")
        self.assertEqual(dt.isoformat(), "2026-07-25T23:30:00+00:00")

    def test_date_only(self):
        self.assertEqual(disc.parse_kickoff_date("2026-07-26"), disc.date(2026, 7, 26))

    def test_kickoff_prefers_game_start_over_listing(self):
        ev = _event("x", "A vs. B", game_start="2026-07-26 03:00:00+00")
        self.assertEqual(disc._event_kickoff(ev).isoformat(), "2026-07-26T03:00:00+00:00")


class ScoreCandidateTests(unittest.TestCase):
    KICK = disc.parse_kickoff_dt("2026-07-26T03:00:00+00:00")

    def test_matches_on_real_kickoff_despite_wrong_slug_date(self):
        # slug says 07-24 but the market kicks off 07-26 — must still match.
        ev = _event(
            "mex-tig-asl-2026-07-24",
            "Tigres de la UANL vs. Atlético San Luis",
            game_start="2026-07-26 03:00:00+00",
        )
        scored = disc._score_candidate(ev, home="Tigres", away="San Luis", kickoff=self.KICK)
        self.assertIsNotNone(scored)
        self.assertEqual(scored["hours_off"], 0.0)
        self.assertFalse(scored["flipped"])

    def test_rejects_same_pairing_from_another_week(self):
        ev = _event(
            "mex-tig-asl-2026-01-11",
            "Tigres de la UANL vs. Atlético San Luis",
            game_start="2026-01-12 01:00:00+00",
        )
        self.assertIsNone(
            disc._score_candidate(ev, home="Tigres", away="San Luis", kickoff=self.KICK)
        )

    def test_detects_flipped_sides(self):
        ev = _event(
            "mex-asl-tig-2026-07-26",
            "Atlético San Luis vs. Tigres de la UANL",
            game_start="2026-07-26 03:00:00+00",
        )
        scored = disc._score_candidate(ev, home="Tigres", away="San Luis", kickoff=self.KICK)
        self.assertIsNotNone(scored)
        self.assertTrue(scored["flipped"])

    def test_rejects_sibling_events(self):
        ev = _event(
            "mex-tig-asl-2026-07-24-exact-score",
            "Tigres de la UANL vs. Atlético San Luis - Exact Score",
            game_start="2026-07-26 03:00:00+00",
        )
        self.assertIsNone(
            disc._score_candidate(ev, home="Tigres", away="San Luis", kickoff=self.KICK)
        )

    def test_rejects_futures_without_vs_title(self):
        ev = _event("liga-mx-2026-apertura-champion", "Liga MX: 2026 Apertura Champion")
        self.assertIsNone(
            disc._score_candidate(ev, home="Tigres", away="San Luis", kickoff=self.KICK)
        )

    def test_slug_date_fallback_when_no_kickoff_payload(self):
        ev = _event("mex-tig-asl-2026-07-26", "Tigres de la UANL vs. Atlético San Luis")
        scored = disc._score_candidate(ev, home="Tigres", away="San Luis", kickoff=self.KICK)
        self.assertIsNotNone(scored)


class QueryExpansionTests(unittest.TestCase):
    def test_short_names_expand_to_full_aliases(self):
        tiers = disc._search_queries("NYCFC", "Chicago")
        flat = [q for tier in tiers for q in tier]
        joined = " || ".join(flat).lower()
        self.assertIn("new york city fc", joined)
        self.assertIn("chicago fire", joined)

    def test_raw_query_is_tried_first(self):
        tiers = disc._search_queries("Tigres", "San Luis")
        self.assertEqual(tiers[0], ["Tigres San Luis"])


class FindPrimaryEventTests(unittest.TestCase):
    def setUp(self):
        disc.clear_slug_cache()

    def test_expands_query_when_raw_names_return_nothing(self):
        real = _event(
            "mls-nyc-chi-2026-07-25",
            "New York City FC vs. Chicago Fire FC",
            game_start="2026-07-25 23:30:00+00",
        )

        def fake_search(query, **_):
            # Short-name search returns only junk; full names return the fixture.
            if "new york city fc" in query.lower():
                return [real]
            return [_event("junk", "Which club will X play for next?")]

        with patch.object(disc, "search_events", side_effect=fake_search):
            ev = disc.find_primary_event(
                "NYCFC", "Chicago", "2026-07-25T23:30:00+00:00", use_cache=False
            )
        self.assertIsNotNone(ev)
        self.assertEqual(ev["slug"], "mls-nyc-chi-2026-07-25")

    def test_returns_none_when_unlisted(self):
        with patch.object(disc, "search_events", return_value=[]):
            ev = disc.find_primary_event(
                "Toluca", "Cruz Azul", "2026-07-26T00:30:00+00:00", use_cache=False
            )
        self.assertIsNone(ev)

    def test_picks_closest_kickoff_among_matches(self):
        near = _event(
            "mex-tig-asl-2026-07-24",
            "Tigres de la UANL vs. Atlético San Luis",
            game_start="2026-07-26 03:00:00+00",
        )
        with patch.object(disc, "search_events", return_value=[near]):
            ev = disc.find_primary_event(
                "Tigres", "San Luis", "2026-07-26T03:00:00+00:00", use_cache=False
            )
        self.assertEqual(ev["slug"], "mex-tig-asl-2026-07-24")
        self.assertEqual(ev["hours_off"], 0.0)


if __name__ == "__main__":
    unittest.main()
