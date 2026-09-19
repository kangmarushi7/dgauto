"""Tests for strategy bet log CSV export helpers."""

import unittest

from app.bet_log_export import (
    CS_LEG_FIELDS,
    STANDARD_BET_FIELDS,
    cs_leg_rows,
    dicts_to_csv,
    standard_bet_rows,
)


class BetLogExportTests(unittest.TestCase):
    def test_standard_bet_rows_and_csv(self):
        entries = [
            {
                "id": "abc",
                "created_at": "2026-01-01T00:00:00+00:00",
                "fixture_date": "2026-01-02T12:00:00+00:00",
                "fixture": "A vs B",
                "league_name": "Test League",
                "bet_type": "lm_o15",
                "team_name": "",
                "qualifier_pct": 72.5,
                "odds": 1.85,
                "units": 1.0,
                "status": "won",
                "pnl_units": 0.85,
                "resolved_at": "2026-01-02T20:00:00+00:00",
            }
        ]
        rows = standard_bet_rows(entries)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["market"], rows[0]["bet_type"])  # fallback label
        csv_text = dicts_to_csv(rows, STANDARD_BET_FIELDS)
        self.assertIn("fixture", csv_text.splitlines()[0])
        self.assertIn("A vs B", csv_text)

    def test_cs_leg_rows(self):
        entries = [
            {
                "id": "1",
                "fixture_date": "2026-02-01",
                "fixture": "X vs Y",
                "league_name": "L",
                "team_name": "1-0",
                "bet_type": "cs_score",
                "qualifier_pct": 8.5,
                "price_cents": 12.3,
                "odds": 8.1,
                "units": 0.2,
                "status": "open",
                "pnl_units": None,
            }
        ]
        rows = cs_leg_rows(entries)
        csv_text = dicts_to_csv(rows, CS_LEG_FIELDS)
        self.assertIn("scoreline", csv_text.splitlines()[0])
        self.assertIn("1-0", csv_text)


if __name__ == "__main__":
    unittest.main()
