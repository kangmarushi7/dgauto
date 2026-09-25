"""Tests for daily_accuracy as primary bet settlement source."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.dg_accuracy_props import clear_accuracy_props_cache


class EventFromDailyAccuracyTests(unittest.TestCase):
    def setUp(self):
        clear_accuracy_props_cache()

    def tearDown(self):
        clear_accuracy_props_cache()

    def test_builds_ft_event_with_score_and_props(self):
        from app.auto_resolve import _event_from_daily_accuracy

        payload = {
            "daily": [
                {
                    "date": "2026-09-20",
                    "matches": [
                        {
                            "fixture_id": 1557416,
                            "date": "2026-09-20",
                            "match": "Tottenham vs Aston Villa",
                            "actual_score": "2 - 1",
                            "actual_corners": "6 - 4",
                            "actual_sot": "5 - 3",
                            "league": "Premier League",
                        }
                    ],
                }
            ]
        }
        entry = {
            "fixture": "Tottenham vs Aston Villa",
            "fixture_date": "2026-09-20T15:00:00+00:00",
            "league_name": "Premier League",
        }
        with patch("app.dg_accuracy_props._load_json", return_value=payload):
            event = _event_from_daily_accuracy(entry)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["intHomeScore"], 2)
        self.assertEqual(event["intAwayScore"], 1)
        self.assertEqual(event["corners_total"], 10)
        self.assertEqual(event["sot_total"], 8)
        self.assertEqual(event["strStatus"], "FT")
        self.assertEqual(event["source"], "daily_accuracy")
        self.assertEqual(str(event["fixtureId"]), "1557416")

    def test_returns_none_without_score(self):
        from app.auto_resolve import _event_from_daily_accuracy

        payload = {
            "daily": [
                {
                    "date": "2026-09-20",
                    "matches": [
                        {
                            "fixture_id": 1,
                            "date": "2026-09-20",
                            "match": "A vs B",
                            "actual_corners": "5 - 5",
                        }
                    ],
                }
            ]
        }
        with patch("app.dg_accuracy_props._load_json", return_value=payload):
            event = _event_from_daily_accuracy(
                {"fixture": "A vs B", "fixture_date": "2026-09-20"}
            )
        self.assertIsNone(event)


class SettlementSourceOrderTests(unittest.TestCase):
    def setUp(self):
        clear_accuracy_props_cache()

    def tearDown(self):
        clear_accuracy_props_cache()

    def test_default_sources_put_daily_accuracy_first(self):
        import app.auto_resolve as ar

        with patch.object(
            ar, "SETTLE_SOURCE", "daily_accuracy,flashscore,api_football"
        ):
            self.assertEqual(
                ar._settle_sources(),
                ["daily_accuracy", "flashscore", "api_football"],
            )

    def test_find_settlement_prefers_daily_accuracy(self):
        import app.auto_resolve as ar

        dg_event = {
            "intHomeScore": 1,
            "intAwayScore": 0,
            "strStatus": "FT",
            "source": "daily_accuracy",
        }
        fs_event = {
            "intHomeScore": 9,
            "intAwayScore": 9,
            "strStatus": "FT",
            "source": "flashscore",
        }
        entry = {"fixture": "A vs B", "fixture_date": "2026-09-20"}

        with patch.object(
            ar, "SETTLE_SOURCE", "daily_accuracy,flashscore,api_football"
        ), patch.object(
            ar, "_event_from_daily_accuracy", return_value=dg_event
        ) as mock_dg, patch.object(
            ar, "_event_from_flashscore", return_value=fs_event
        ) as mock_fs, patch.object(
            ar, "api_football_configured", return_value=True
        ), patch.object(
            ar, "_find_best_event", return_value={"intHomeScore": 3, "intAwayScore": 0}
        ) as mock_api:
            event, source = ar._find_settlement_event(entry, {}, {}, {}, {})

        self.assertEqual(source, "daily_accuracy")
        self.assertEqual(event["intHomeScore"], 1)
        mock_dg.assert_called_once()
        mock_fs.assert_not_called()
        mock_api.assert_not_called()

    def test_falls_back_to_flashscore_when_accuracy_misses(self):
        import app.auto_resolve as ar

        fs_event = {
            "intHomeScore": 2,
            "intAwayScore": 2,
            "strStatus": "FT",
            "source": "flashscore",
        }
        entry = {"fixture": "A vs B", "fixture_date": "2026-09-20"}

        with patch.object(
            ar, "SETTLE_SOURCE", "daily_accuracy,flashscore,api_football"
        ), patch.object(
            ar, "_event_from_daily_accuracy", return_value=None
        ), patch.object(
            ar, "_event_from_flashscore", return_value=fs_event
        ), patch.object(
            ar, "api_football_configured", return_value=False
        ):
            event, source = ar._find_settlement_event(entry, {}, {}, {}, {})

        self.assertEqual(source, "flashscore")
        self.assertEqual(event["intHomeScore"], 2)


if __name__ == "__main__":
    unittest.main()
