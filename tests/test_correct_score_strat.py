"""Unit tests for correct-score basket sizing and settlement (no network)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.auto_resolve import _compute_pnl, _resolve_result
from app.correct_score_strat import (
    PRICE_BUFFER,
    _best_basket,
    dutch_basket,
    group_into_baskets,
    price_fixture_scorelines,
)


def _legs(*prices: float) -> list[dict[str, float | str]]:
    return [
        {"label": f"{i}-0", "dg_pct": 12.0 - i, "price": price}
        for i, price in enumerate(prices)
    ]


class DutchBasketTests(unittest.TestCase):
    def test_every_leg_returns_the_same_payout(self):
        basket = dutch_basket(_legs(0.09, 0.12, 0.10, 0.06, 0.08))
        payouts = [leg["payout_units"] for leg in basket["legs"]]
        self.assertAlmostEqual(max(payouts), min(payouts), places=2)

    def test_any_single_hit_profits(self):
        basket = dutch_basket(_legs(0.09, 0.12, 0.10, 0.06, 0.08))
        self.assertTrue(basket["qualified"])
        staked = basket["staked_units"]
        for winner in basket["legs"]:
            self.assertGreater(winner["payout_units"] - staked, 0)
            self.assertGreater(winner["profit_if_hits"], 0)

    def test_stakes_consume_the_whole_budget(self):
        basket = dutch_basket(_legs(0.09, 0.12, 0.10, 0.06, 0.08), budget=2.0)
        self.assertAlmostEqual(basket["staked_units"], 2.0, places=2)

    def test_slippage_buffer_is_priced_in(self):
        basket = dutch_basket(_legs(0.10))
        self.assertAlmostEqual(basket["legs"][0]["fill_price"], 0.10 + PRICE_BUFFER, places=6)

    def test_over_100_percent_is_not_qualified(self):
        basket = dutch_basket(_legs(0.30, 0.30, 0.25, 0.20))
        self.assertFalse(basket["qualified"])
        self.assertLessEqual(basket["guaranteed_profit_units"], 0)
        self.assertIn("no margin left", basket["reason"])

    def test_thin_margin_rejected_by_roi_floor(self):
        with patch("app.correct_score_strat.MIN_GUARANTEED_ROI", 0.25):
            basket = dutch_basket(_legs(0.20, 0.20, 0.20, 0.19))
        self.assertFalse(basket["qualified"])
        self.assertGreater(basket["guaranteed_profit_units"], 0)
        self.assertIn("below 25% floor", basket["reason"])

    def test_edge_and_ev_use_model_probability(self):
        basket = dutch_basket(
            [
                {"label": "1-0", "dg_pct": 30.0, "price": 0.20},
                {"label": "1-1", "dg_pct": 30.0, "price": 0.20},
            ]
        )
        self.assertAlmostEqual(basket["model_hit_pct"], 60.0, places=2)
        self.assertAlmostEqual(basket["implied_hit_pct"], 41.0, places=2)
        self.assertAlmostEqual(basket["edge_pct"], 19.0, places=2)
        self.assertGreater(basket["ev_units"], 0)

    def test_empty_legs(self):
        self.assertIsNone(dutch_basket([]))


class BasketSelectionTests(unittest.TestCase):
    def test_takes_five_legs_when_the_fifth_is_cheap(self):
        basket = _best_basket(_legs(0.09, 0.12, 0.10, 0.06, 0.02))
        self.assertEqual(basket["size"], 5)
        self.assertTrue(basket["qualified"])

    def test_drops_the_fifth_leg_when_it_is_overpriced(self):
        # dg_pct descends with position, so the 0.35 leg is the one dropped.
        basket = _best_basket(_legs(0.20, 0.20, 0.20, 0.20, 0.35))
        self.assertEqual(basket["size"], 4)
        self.assertTrue(basket["qualified"])

    def test_wider_basket_wins_an_ev_tie(self):
        prices = (0.09, 0.12, 0.10, 0.06, 0.08)
        self.assertGreater(
            dutch_basket(_legs(*prices[:4]))["ev_units"],
            dutch_basket(_legs(*prices))["ev_units"],
        )
        self.assertEqual(_best_basket(_legs(*prices))["size"], 4)
        with patch("app.correct_score_strat.EV_TIE_TOLERANCE", 1.0):
            self.assertEqual(_best_basket(_legs(*prices))["size"], 5)

    def test_returns_best_effort_when_nothing_qualifies(self):
        basket = _best_basket(_legs(0.30, 0.30, 0.30, 0.25, 0.25))
        self.assertFalse(basket["qualified"])
        self.assertTrue(basket["reason"])

    def test_no_basket_without_enough_legs(self):
        self.assertIsNone(_best_basket(_legs(0.10, 0.10, 0.10)))


class PriceFixtureTests(unittest.TestCase):
    CATALOG = [
        {"label": "2-1", "homeGoals": 2, "awayGoals": 1, "yesTokenId": "T21", "gammaAsk": 0.11},
        {"label": "1-2", "homeGoals": 1, "awayGoals": 2, "yesTokenId": "T12", "gammaAsk": 0.09},
    ]

    def _price(self, *, flipped: bool, books: dict | None = None):
        event = {"slug": "mex-abc-xyz-2026-07-24", "flipped": flipped, "title": "A vs. B"}
        with (
            patch("app.correct_score_strat.find_primary_event", return_value=event),
            patch("app.correct_score_strat.fetch_exact_score_sibling", return_value={"markets": []}),
            patch("app.correct_score_strat.map_exact_score_markets", return_value=self.CATALOG),
            patch("app.correct_score_strat.books_for_tokens", return_value=books or {}),
        ):
            return price_fixture_scorelines(
                home_team="A",
                away_team="B",
                kickoff="2026-07-24T20:00:00+00:00",
                top_scores=[{"score": "2-1", "pct": 11.0}],
            )

    def test_straight_orientation(self):
        result = self._price(flipped=False)
        self.assertEqual([leg["label"] for leg in result["legs"]], ["2-1"])
        self.assertEqual(result["legs"][0]["pm_label"], "2-1")

    def test_flipped_orientation_buys_the_mirrored_market(self):
        result = self._price(flipped=True)
        # DataGaffer's 2-1 is Polymarket's 1-2 when the sides are reversed.
        self.assertEqual(result["legs"][0]["label"], "2-1")
        self.assertEqual(result["legs"][0]["pm_label"], "1-2")

    def test_live_book_ask_beats_gamma(self):
        result = self._price(flipped=False, books={"T21": {"ask": 0.07, "askSize": 500}})
        leg = result["legs"][0]
        self.assertEqual(leg["price"], 0.07)
        self.assertEqual(leg["price_source"], "clob_ask")
        self.assertEqual(leg["ask_shares"], 500)

    def test_expensive_legs_are_dropped(self):
        with patch("app.correct_score_strat.MAX_LEG_PRICE", 0.05):
            result = self._price(flipped=False)
        self.assertEqual(result["legs"], [])
        self.assertEqual(result["error"], "no tradeable exact-score legs")

    def test_unlisted_fixture(self):
        with patch("app.correct_score_strat.find_primary_event", return_value=None):
            result = price_fixture_scorelines(
                home_team="A", away_team="B", kickoff=None, top_scores=[]
            )
        self.assertEqual(result["legs"], [])
        self.assertIn("not listed", result["error"])


class SettlementTests(unittest.TestCase):
    EVENT = {"intHomeScore": 2, "intAwayScore": 1, "strHomeTeam": "A", "strAwayTeam": "B"}

    def _resolve(self, label: str):
        return _resolve_result({"bet_type": "correct_score", "team_name": label}, self.EVENT)

    def test_exact_hit_wins(self):
        self.assertEqual(self._resolve("2-1"), "won")

    def test_mirror_score_loses(self):
        self.assertEqual(self._resolve("1-2"), "lost")

    def test_other_scores_lose(self):
        self.assertEqual(self._resolve("0-0"), "lost")

    def test_unparseable_label_stays_open(self):
        self.assertIsNone(self._resolve("Team A"))

    def test_basket_pnl_positive_for_every_winning_line(self):
        basket = dutch_basket(_legs(0.09, 0.12, 0.10, 0.06, 0.08))
        entries = [
            {
                "id": str(i),
                "odds": leg["decimal_odds"],
                "units": leg["stake_units"],
            }
            for i, leg in enumerate(basket["legs"])
        ]
        for winner in entries:
            pnl = sum(
                _compute_pnl(e, "won" if e["id"] == winner["id"] else "lost") for e in entries
            )
            self.assertGreater(round(pnl, 4), 0)


class BasketGroupingTests(unittest.TestCase):
    ENTRIES = [
        {
            "fixture": "A vs B",
            "fixture_date": "2026-07-25T03:00:00+00:00",
            "league_name": "Liga MX",
            "team_name": "2-1",
            "odds": 10.0,
            "units": 0.5,
            "qualifier_pct": 12.0,
            "status": "won",
            "pnl_units": 4.5,
        },
        {
            "fixture": "A vs B",
            "fixture_date": "2026-07-25T03:00:00+00:00",
            "league_name": "Liga MX",
            "team_name": "1-1",
            "odds": 10.0,
            "units": 0.5,
            "qualifier_pct": 10.0,
            "status": "lost",
            "pnl_units": -0.5,
        },
    ]

    def test_legs_collapse_into_one_basket(self):
        baskets = group_into_baskets(self.ENTRIES)
        self.assertEqual(len(baskets), 1)
        basket = baskets[0]
        self.assertEqual(basket["size"], 2)
        self.assertEqual(basket["scores"], ["1-1", "2-1"])
        self.assertEqual(basket["staked_units"], 1.0)
        self.assertEqual(basket["pnl_units"], 4.0)
        self.assertEqual(basket["hit_score"], "2-1")
        self.assertEqual(basket["status"], "won")
        self.assertTrue(basket["settled"])
        self.assertEqual(basket["model_hit_pct"], 22.0)

    def test_open_basket_while_a_leg_is_unsettled(self):
        entries = [dict(self.ENTRIES[0]), {**self.ENTRIES[1], "status": "open", "pnl_units": None}]
        basket = group_into_baskets(entries)[0]
        self.assertFalse(basket["settled"])
        self.assertEqual(basket["status"], "open")

    def test_separate_fixtures_stay_separate(self):
        entries = [*self.ENTRIES, {**self.ENTRIES[0], "fixture": "C vs D"}]
        self.assertEqual(len(group_into_baskets(entries)), 2)


if __name__ == "__main__":
    unittest.main()
