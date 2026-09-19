"""Fixed forward-test portfolios — hypotheses only, never re-tuned."""
from __future__ import annotations

from typing import Any

# Fixed paper portfolios for the current test.
# Do NOT optimize or combine.
PORTFOLIOS: dict[str, dict[str, Any]] = {
    "P1_ODDS_2_10_2_50": {
        "id": "P1_ODDS_2_10_2_50",
        "label": "Portfolio 1 — Odds 2.10–2.50",
        "hypothesis": "Qualifying bets priced 2.10–2.50 are repeatable",
        "description": "Every qualifying +EV signal with bet-time odds in [2.10, 2.50]. No market restriction.",
    },
    "P2_DC_X2": {
        "id": "P2_DC_X2",
        "label": "Portfolio 2 — DC X2",
        "hypothesis": "Qualifying Double Chance X2 is repeatable",
        "description": "Every qualifying DC X2 signal. No additional optimization.",
    },
    "P3_O3_5": {
        "id": "P3_O3_5",
        "label": "Portfolio 3 — Over 3.5 (benchmark)",
        "hypothesis": "Qualifying Over 3.5 is a useful benchmark/control",
        "description": "Every qualifying O3.5 signal. Benchmark/control.",
    },
    "P4_O2_5": {
        "id": "P4_O2_5",
        "label": "Portfolio 4 — Over 2.5 (benchmark)",
        "hypothesis": "Qualifying Over 2.5 is a useful benchmark/control",
        "description": "Every qualifying O2.5 signal. Benchmark/control.",
    },
}


def portfolio_membership(signal: dict[str, Any]) -> list[str]:
    """Return portfolio ids this signal belongs to (independent, can overlap)."""
    ids: list[str] = []
    bt = str(signal.get("bet_type") or signal.get("market_key") or "").lower()
    market = str(signal.get("market") or "").lower()
    try:
        odds = float(signal.get("odds_at_signal") or signal.get("odds") or 0)
    except (TypeError, ValueError):
        odds = 0.0

    if 2.10 <= odds <= 2.50:
        ids.append("P1_ODDS_2_10_2_50")
    if bt == "dc_x2" or "dc x2" in market or market.strip() == "dc x2":
        ids.append("P2_DC_X2")
    if bt == "over3.5" or "over 3.5" in market:
        ids.append("P3_O3_5")
    if bt == "over2.5" or "over 2.5" in market:
        ids.append("P4_O2_5")
    return ids
