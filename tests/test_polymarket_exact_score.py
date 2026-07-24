"""Unit tests for Polymarket exact-score parsing / token mapping (no network)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.polymarket_exact_score import (
    exact_score_event_slug,
    get_orderbook_top,
    map_exact_score_markets,
    normalize_primary_slug,
    parse_scoreline,
    pull_exact_score_prices,
    yes_token_id_from_market,
)


SAMPLE_MARKET_00 = {
    "question": "Exact Score: Santos FC 0 - 0 Chapecoense?",
    "slug": "bra-san-cha-2026-07-25-exact-score-0-0",
    "sportsMarketType": "soccer_exact_score",
    "outcomes": json.dumps(["Yes", "No"]),
    "outcomePrices": json.dumps(["0.0525", "0.9475"]),
    "clobTokenIds": json.dumps(["YES_TOKEN_00", "NO_TOKEN_00"]),
    "groupItemTitle": "Santos FC 0 - 0 Chapecoense",
    "bestBid": 0.045,
    "bestAsk": 0.06,
}

SAMPLE_MARKET_ANY = {
    "question": "Exact Score: Any Other Score?",
    "slug": "bra-san-cha-2026-07-25-exact-score-any-other",
    "sportsMarketType": "soccer_exact_score",
    "outcomes": '["Yes", "No"]',
    "outcomePrices": '["0.14", "0.86"]',
    "clobTokenIds": '["YES_ANY", "NO_ANY"]',
    "groupItemTitle": "Any Other Score",
    "bestBid": 0.08,
    "bestAsk": 0.2,
}

SAMPLE_EVENT = {
    "id": "evt1",
    "slug": "bra-san-cha-2026-07-25-exact-score",
    "title": "Santos FC vs. Chapecoense - Exact Score",
    "markets": [
        SAMPLE_MARKET_00,
        {
            **SAMPLE_MARKET_00,
            "slug": "bra-san-cha-2026-07-25-exact-score-1-0",
            "question": "Exact Score: Santos FC 1 - 0 Chapecoense?",
            "groupItemTitle": "Santos FC 1 - 0 Chapecoense",
            "clobTokenIds": '["YES_10", "NO_10"]',
            "outcomePrices": '["0.115", "0.885"]',
            "bestBid": 0.11,
            "bestAsk": 0.12,
        },
        SAMPLE_MARKET_ANY,
    ],
}


class SlugTests(unittest.TestCase):
    def test_normalize_strips_exact_score(self):
        self.assertEqual(
            normalize_primary_slug("bra-san-cha-2026-07-25-exact-score"),
            "bra-san-cha-2026-07-25",
        )
        self.assertEqual(
            normalize_primary_slug("bra-san-cha-2026-07-25-exact-score-2-1"),
            "bra-san-cha-2026-07-25",
        )
        self.assertEqual(
            normalize_primary_slug("bra-san-cha-2026-07-25"),
            "bra-san-cha-2026-07-25",
        )

    def test_sibling_slug(self):
        self.assertEqual(
            exact_score_event_slug("bra-san-cha-2026-07-25"),
            "bra-san-cha-2026-07-25-exact-score",
        )


class ParseScorelineTests(unittest.TestCase):
    def test_from_slug(self):
        label, h, a = parse_scoreline(slug="foo-exact-score-2-3")
        self.assertEqual((label, h, a), ("2-3", 2, 3))

    def test_any_other(self):
        label, h, a = parse_scoreline(slug="foo-exact-score-any-other")
        self.assertEqual(label, "Any Other Score")
        self.assertIsNone(h)
        self.assertIsNone(a)

    def test_from_question_digits(self):
        label, h, a = parse_scoreline(question="Exact Score: Home 3 - 1 Away?")
        self.assertEqual((label, h, a), ("3-1", 3, 1))


class TokenMapTests(unittest.TestCase):
    def test_yes_token_from_json_strings(self):
        self.assertEqual(yes_token_id_from_market(SAMPLE_MARKET_00), "YES_TOKEN_00")

    def test_yes_when_outcomes_reversed(self):
        m = {
            "outcomes": ["No", "Yes"],
            "clobTokenIds": ["NO_X", "YES_X"],
        }
        self.assertEqual(yes_token_id_from_market(m), "YES_X")


class OrderbookTopTests(unittest.TestCase):
    def test_max_bid_min_ask(self):
        fake_book = {
            "bids": [{"price": "0.001", "size": "10"}, {"price": "0.045", "size": "5"}],
            "asks": [{"price": "0.999", "size": "10"}, {"price": "0.06", "size": "5"}],
        }
        with patch("app.polymarket_exact_score._http_get_json", return_value=fake_book):
            bid, ask = get_orderbook_top("tok")
        self.assertEqual(bid, 0.045)
        self.assertEqual(ask, 0.06)


class PullPricesTests(unittest.TestCase):
    def test_map_catalog(self):
        rows = map_exact_score_markets(SAMPLE_EVENT)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["label"], "0-0")
        self.assertEqual(rows[-1]["label"], "Any Other Score")

    def test_pull_with_clob_and_gamma_fallback(self):
        def fake_get(url: str):
            if "events?slug=" in url and url.endswith("exact-score"):
                return [SAMPLE_EVENT]
            if "events?slug=" in url:
                return [{"id": "p1", "slug": "bra-san-cha-2026-07-25", "title": "Santos vs Chape"}]
            if "/book?" in url:
                if "YES_TOKEN_00" in url:
                    return {
                        "bids": [{"price": "0.04", "size": "1"}],
                        "asks": [{"price": "0.07", "size": "1"}],
                    }
                raise TimeoutError("simulated")
            return []

        with patch("app.polymarket_exact_score._http_get_json", side_effect=fake_get):
            result = pull_exact_score_prices("bra-san-cha-2026-07-25", use_clob=True)

        self.assertTrue(result["ok"])
        prices = result["prices"]
        self.assertEqual(len(prices), 3)
        row00 = next(p for p in prices if p["label"] == "0-0")
        self.assertEqual(row00["yesTokenId"], "YES_TOKEN_00")
        self.assertEqual(row00["bid"], 0.04)
        self.assertEqual(row00["ask"], 0.07)
        self.assertAlmostEqual(row00["mid"], 0.055)
        self.assertEqual(row00["gammaYes"], 0.0525)

        # CLOB failed → Gamma bestBid/Ask fallback
        row10 = next(p for p in prices if p["label"] == "1-0")
        self.assertEqual(row10["bid"], 0.11)
        self.assertEqual(row10["ask"], 0.12)


if __name__ == "__main__":
    unittest.main()
