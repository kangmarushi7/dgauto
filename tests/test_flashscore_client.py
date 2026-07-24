"""Unit tests for Flashscore ninja feed parse + fuzzy match (no network)."""
from __future__ import annotations

import unittest

from app.flashscore_client import (
    FlashscoreClient,
    FlashscoreFootballMatch,
    FlashscoreTennisMatch,
    SPORT_FOOTBALL,
    SPORT_TENNIS,
    match_score_football,
    match_score_tennis,
    parse_feed,
)

# Minimal synthetic ninja fragments (row=~ cell=¬ kv=÷)
FOOTBALL_FEED = (
    "ZA÷SWEDEN: Allsvenskan~"
    "AA÷matchA¬CX÷Hammarby¬AF÷Kalmar FF¬AG÷2¬AH÷1¬AB÷3¬AC÷3¬AD÷1720800000"
    "¬WU÷hammarby¬WV÷kalmar¬AI÷n~"
    "ZA÷BRAZIL: Serie A~"
    "AA÷matchB¬CX÷Botafogo RJ¬AF÷Santos FC¬AG÷0¬AH÷0¬AB÷2¬AI÷y"
    "¬WU÷botafogo¬WV÷santos~"
    "ZA÷MEXICO: Liga MX - Apertura~"
    "AA÷matchC¬CX÷Club Tijuana¬AF÷Tigres UANL¬AG÷1¬AH÷3¬AB÷3"
    "¬WU÷tijuana¬WV÷tigres~"
    "ZA÷SWEDEN: Allsvenskan U19~"
    "AA÷matchD¬CX÷Hammarby U19¬AF÷Kalmar FF U19¬AG÷5¬AH÷0¬AB÷3"
    "¬WU÷hammarby-u19¬WV÷kalmar-u19~"
)

TENNIS_FEED = (
    "ZA÷ATP: Wimbledon~"
    "AA÷t1¬CX÷Novak Djokovic¬AF÷Carlos Alcaraz¬AB÷3"
    "¬BA÷6¬BB÷4¬BC÷3¬BD÷6¬BE÷6¬BF÷3"
    "¬WU÷djokovic¬WV÷alcaraz¬AI÷n~"
    "AA÷t2¬CX÷Jannik Sinner¬AF÷Daniil Medvedev¬AB÷2¬AI÷y"
    "¬BA÷6¬BB÷3¬BC÷2¬BD÷1"
    "¬AG÷30¬AH÷15¬WU÷sinner¬WV÷medvedev~"
)


class ParseFootballTests(unittest.TestCase):
    def test_parse_football_counts_and_scores(self):
        matches = parse_feed(FOOTBALL_FEED, sport=SPORT_FOOTBALL)
        self.assertEqual(len(matches), 4)
        ham = next(m for m in matches if m.id == "matchA")
        self.assertIsInstance(ham, FlashscoreFootballMatch)
        self.assertEqual(ham.home, "Hammarby")
        self.assertEqual(ham.away, "Kalmar FF")
        self.assertEqual(ham.home_goals, 2)
        self.assertEqual(ham.away_goals, 1)
        self.assertTrue(ham.is_finished)
        self.assertFalse(ham.is_live)
        self.assertIn("mid=matchA", ham.url)

    def test_live_vs_finished(self):
        matches = parse_feed(FOOTBALL_FEED, sport=SPORT_FOOTBALL)
        live = next(m for m in matches if m.id == "matchB")
        self.assertTrue(live.is_live)
        self.assertFalse(live.is_finished)
        self.assertEqual(live.home_goals, 0)


class ParseTennisTests(unittest.TestCase):
    def test_parse_tennis_sets_and_winner(self):
        matches = parse_feed(TENNIS_FEED, sport=SPORT_TENNIS)
        self.assertEqual(len(matches), 2)
        fin = next(m for m in matches if m.id == "t1")
        self.assertIsInstance(fin, FlashscoreTennisMatch)
        self.assertEqual(fin.sets, [(6, 4), (3, 6), (6, 3)])
        self.assertTrue(fin.is_finished)
        self.assertFalse(fin.is_live)
        self.assertEqual(fin.winner(), "Novak Djokovic")

    def test_tennis_live_not_finished_by_ab_alone(self):
        matches = parse_feed(TENNIS_FEED, sport=SPORT_TENNIS)
        live = next(m for m in matches if m.id == "t2")
        self.assertTrue(live.is_live)
        self.assertFalse(live.is_finished)
        self.assertIsNone(live.winner())


class FuzzyMatchTests(unittest.TestCase):
    def setUp(self):
        self.matches = parse_feed(FOOTBALL_FEED, sport=SPORT_FOOTBALL)

    def test_accepts_senior_fixture(self):
        ham = next(m for m in self.matches if m.id == "matchA")
        score = match_score_football("Hammarby", "Kalmar FF", ham, league="Allsvenskan")
        self.assertGreaterEqual(score, 2)

    def test_penalizes_youth_when_query_senior(self):
        youth = next(m for m in self.matches if m.id == "matchD")
        score = match_score_football("Hammarby", "Kalmar FF", youth, league="Allsvenskan")
        # Youth penalty should keep this below accept threshold vs senior names.
        self.assertLess(score, 2)

    def test_client_find_match_prefers_senior(self):
        from app.flashscore_client import _CacheBucket

        client = FlashscoreClient(sport=SPORT_FOOTBALL, day_offsets=(0,), cache_ttl_sec=9999)
        client._by_day[0] = _CacheBucket(matches=self.matches, fetched_at=1e18)
        client._merge()
        client._merged_at = 1e18
        found = client.find_match("Hammarby", "Kalmar", league="Allsvenskan")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.id, "matchA")

    def test_tennis_token_overlap(self):
        matches = parse_feed(TENNIS_FEED, sport=SPORT_TENNIS)
        fin = next(m for m in matches if m.id == "t1")
        self.assertGreaterEqual(match_score_tennis("Djokovic", "Alcaraz", fin), 2)

    def test_score_for_fixture_finished(self):
        client = FlashscoreClient(sport=SPORT_FOOTBALL, day_offsets=(0,), cache_ttl_sec=9999)
        from app.flashscore_client import _CacheBucket

        client._by_day[0] = _CacheBucket(matches=self.matches, fetched_at=1e18)
        client._merge()
        client._merged_at = 1e18
        payload = client.score_for_fixture("Tijuana", "Tigres", league="Liga MX")
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["home_goals"], 1)
        self.assertEqual(payload["away_goals"], 3)
        self.assertTrue(payload["is_finished"])


class EventShapeTests(unittest.TestCase):
    def test_to_event_dict_for_settlement(self):
        matches = parse_feed(FOOTBALL_FEED, sport=SPORT_FOOTBALL)
        m = next(x for x in matches if x.id == "matchA")
        event = m.to_event_dict()
        self.assertEqual(event["strHomeTeam"], "Hammarby")
        self.assertEqual(event["intHomeScore"], 2)
        self.assertEqual(event["strStatus"], "FT")
        self.assertEqual(event["source"], "flashscore")


if __name__ == "__main__":
    unittest.main()
