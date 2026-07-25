"""Unit tests for Polymarket H2H market matching / pricing (no network)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.polymarket_h2h_markets import (
    attach_polymarket_odds,
    decimal_odds_from_ask,
    gamma_outcome_price,
    match_btts,
    match_moneyline_market,
    match_totals_over,
    more_markets_event_slug,
    outcome_token_id,
    price_h2h_fixture,
    resolve_h2h_market,
)


def _m(
    *,
    mtype: str,
    slug: str,
    title: str = "",
    question: str = "",
    outcomes: list[str],
    prices: list[str],
    tokens: list[str],
    best_ask: float | None = None,
) -> dict:
    row = {
        "sportsMarketType": mtype,
        "slug": slug,
        "groupItemTitle": title,
        "question": question,
        "outcomes": json.dumps(outcomes),
        "outcomePrices": json.dumps(prices),
        "clobTokenIds": json.dumps(tokens),
    }
    if best_ask is not None:
        row["bestAsk"] = best_ask
    return row


PRIMARY_MARKETS = [
    _m(
        mtype="moneyline",
        slug="swe-deg-dju-2026-07-25-deg",
        title="Degerfors IF",
        question="Will Degerfors IF win on 2026-07-25?",
        outcomes=["Yes", "No"],
        prices=["0.25", "0.75"],
        tokens=["YES_HOME", "NO_HOME"],
        best_ask=0.26,
    ),
    _m(
        mtype="moneyline",
        slug="swe-deg-dju-2026-07-25-draw",
        title="Draw (Degerfors IF vs. Djurgardens IF)",
        question="Will Degerfors IF vs. Djurgardens IF end in a draw?",
        outcomes=["Yes", "No"],
        prices=["0.30", "0.70"],
        tokens=["YES_DRAW", "NO_DRAW"],
    ),
    _m(
        mtype="moneyline",
        slug="swe-deg-dju-2026-07-25-dju",
        title="Djurgardens IF",
        question="Will Djurgardens IF win on 2026-07-25?",
        outcomes=["Yes", "No"],
        prices=["0.45", "0.55"],
        tokens=["YES_AWAY", "NO_AWAY"],
    ),
]

MORE_MARKETS = [
    _m(
        mtype="totals",
        slug="swe-deg-dju-2026-07-25-total-2pt5",
        title="O/U 2.5",
        question="Degerfors IF vs. Djurgardens IF: O/U 2.5",
        outcomes=["Over", "Under"],
        prices=["0.55", "0.45"],
        tokens=["OVER_25", "UNDER_25"],
    ),
    _m(
        mtype="totals",
        slug="swe-deg-dju-2026-07-25-total-3pt5",
        title="O/U 3.5",
        question="Degerfors IF vs. Djurgardens IF: O/U 3.5",
        outcomes=["Over", "Under"],
        prices=["0.32", "0.68"],
        tokens=["OVER_35", "UNDER_35"],
    ),
    _m(
        mtype="both_teams_to_score",
        slug="swe-deg-dju-2026-07-25-btts",
        title="Both Teams to Score",
        question="Degerfors IF vs. Djurgardens IF: Both Teams to Score",
        outcomes=["Yes", "No"],
        prices=["0.60", "0.40"],
        tokens=["YES_BTTS", "NO_BTTS"],
    ),
    _m(
        mtype="both_teams_to_score_first_half",
        slug="swe-deg-dju-2026-07-25-btts-first-half",
        title="Both Teams to Score in First Half",
        question="…",
        outcomes=["Yes", "No"],
        prices=["0.20", "0.80"],
        tokens=["YES_BTTS_1H", "NO_BTTS_1H"],
    ),
    _m(
        mtype="first_half_totals",
        slug="swe-deg-dju-2026-07-25-first-half-total-2pt5",
        title="1st Half O/U 2.5",
        question="…",
        outcomes=["Over", "Under"],
        prices=["0.10", "0.90"],
        tokens=["OVER_1H", "UNDER_1H"],
    ),
]


class SlugTests(unittest.TestCase):
    def test_more_markets_slug(self):
        self.assertEqual(
            more_markets_event_slug("swe-deg-dju-2026-07-25"),
            "swe-deg-dju-2026-07-25-more-markets",
        )
        self.assertEqual(
            more_markets_event_slug("swe-deg-dju-2026-07-25-exact-score"),
            "swe-deg-dju-2026-07-25-more-markets",
        )


class TokenPriceTests(unittest.TestCase):
    def test_outcome_token_over(self):
        self.assertEqual(outcome_token_id(MORE_MARKETS[0], "Over"), "OVER_25")

    def test_gamma_outcome_price(self):
        self.assertEqual(gamma_outcome_price(MORE_MARKETS[0], "Over"), 0.55)

    def test_decimal_odds(self):
        self.assertEqual(decimal_odds_from_ask(0.5), 2.0)
        self.assertEqual(decimal_odds_from_ask(0.25), 4.0)
        self.assertIsNone(decimal_odds_from_ask(0))
        self.assertIsNone(decimal_odds_from_ask(1.0))


class MatchTests(unittest.TestCase):
    def test_moneyline_home_away_draw(self):
        home = match_moneyline_market(
            PRIMARY_MARKETS, side="home", home="Degerfors", away="Djurgarden"
        )
        away = match_moneyline_market(
            PRIMARY_MARKETS, side="away", home="Degerfors", away="Djurgarden"
        )
        draw = match_moneyline_market(
            PRIMARY_MARKETS, side="draw", home="Degerfors", away="Djurgarden"
        )
        self.assertEqual(home["slug"], "swe-deg-dju-2026-07-25-deg")
        self.assertEqual(away["slug"], "swe-deg-dju-2026-07-25-dju")
        self.assertIn("draw", draw["slug"])

    def test_totals_skips_half(self):
        m = match_totals_over(MORE_MARKETS, line_token="2pt5")
        self.assertEqual(m["slug"], "swe-deg-dju-2026-07-25-total-2pt5")

    def test_btts_full_match_only(self):
        m = match_btts(MORE_MARKETS)
        self.assertEqual(m["sportsMarketType"], "both_teams_to_score")

    def test_resolve_corners_returns_none(self):
        market, outcome, kind = resolve_h2h_market(
            bet_type="h2h_c_o85",
            primary_markets=PRIMARY_MARKETS,
            more_markets=MORE_MARKETS,
            home="Degerfors",
            away="Djurgarden",
        )
        self.assertIsNone(market)
        self.assertEqual(outcome, "")
        self.assertEqual(kind, "")


class PriceFixtureTests(unittest.TestCase):
    @patch("app.polymarket_h2h_markets.books_for_tokens", return_value={})
    @patch("app.polymarket_h2h_markets.fetch_gamma_event_by_slug")
    @patch("app.polymarket_h2h_markets.find_primary_event")
    def test_prices_goals_and_ml(self, mock_find, mock_fetch, _books):
        mock_find.return_value = {
            "slug": "swe-deg-dju-2026-07-25",
            "title": "Degerfors IF vs. Djurgardens IF",
            "flipped": False,
        }

        def _fetch(slug: str):
            if slug.endswith("-more-markets"):
                return {"slug": slug, "markets": MORE_MARKETS}
            return {"slug": slug, "markets": PRIMARY_MARKETS}

        mock_fetch.side_effect = _fetch

        picks = [
            {"bet_type": "h2h_home", "team_name": "Degerfors", "label": "Home Win"},
            {"bet_type": "h2h_o25", "team_name": "", "label": "Over 2.5"},
            {"bet_type": "h2h_btts", "team_name": "", "label": "BTTS Yes"},
            {"bet_type": "h2h_c_o85", "team_name": "8.5", "label": "Corners O8.5"},
            {"bet_type": "h2h_sot_o75", "team_name": "7.5", "label": "SOT O7.5"},
        ]
        result = price_h2h_fixture(
            home="Degerfors",
            away="Djurgarden",
            kickoff="2026-07-25T17:00:00+00:00",
            picks=picks,
            use_clob=False,
        )
        priced = result["priced"]
        self.assertIn("h2h_home|Degerfors|Home Win", priced)
        self.assertEqual(priced["h2h_home|Degerfors|Home Win"]["odds"], round(1 / 0.25, 3))
        self.assertEqual(priced["h2h_o25||Over 2.5"]["odds"], round(1 / 0.55, 3))
        self.assertEqual(priced["h2h_btts||BTTS Yes"]["odds"], round(1 / 0.60, 3))
        self.assertNotIn("h2h_c_o85|8.5|Corners O8.5", priced)
        self.assertNotIn("h2h_sot_o75|7.5|SOT O7.5", priced)

    @patch("app.polymarket_h2h_markets.price_h2h_fixture")
    def test_attach_fills_odds(self, mock_price):
        mock_price.return_value = {
            "error": "",
            "polymarket_url": "https://polymarket.com/event/swe-deg-dju-2026-07-25",
            "more_markets_slug": "swe-deg-dju-2026-07-25-more-markets",
            "priced": {
                "h2h_o25||Over 2.5": {
                    "odds": 1.82,
                    "price": 0.55,
                    "polymarket_url": "https://polymarket.com/event/swe-deg-dju-2026-07-25-more-markets",
                }
            },
        }
        picks = [
            {
                "home": "Degerfors",
                "away": "Djurgarden",
                "fixture_date": "2026-07-25T17:00:00Z",
                "bet_type": "h2h_o25",
                "team_name": "",
                "label": "Over 2.5",
                "odds": None,
            },
            {
                "home": "Degerfors",
                "away": "Djurgarden",
                "fixture_date": "2026-07-25T17:00:00Z",
                "bet_type": "h2h_c_o85",
                "team_name": "8.5",
                "label": "Corners O8.5",
                "odds": None,
            },
        ]
        out = attach_polymarket_odds(picks, use_clob=False)
        self.assertEqual(out[0]["odds"], 1.82)
        self.assertTrue(out[0]["polymarket_url"])
        self.assertIsNone(out[1]["odds"])


if __name__ == "__main__":
    unittest.main()
