"""Fixed forward-test portfolios — hypotheses only, never re-tuned."""
from __future__ import annotations

from typing import Any, Callable

# Fixed hypotheses. Do NOT optimize or combine.
PORTFOLIOS: dict[str, dict[str, Any]] = {
    "A_O3_5": {
        "id": "A_O3_5",
        "label": "Portfolio A — Over 3.5",
        "hypothesis": "H1: Over 3.5 is profitable/repeatable",
        "description": "Every qualifying O3.5 signal. No odds/league filter.",
    },
    "B_O2_5": {
        "id": "B_O2_5",
        "label": "Portfolio B — Over 2.5",
        "hypothesis": "H2: Over 2.5 is profitable/repeatable",
        "description": "Every qualifying O2.5 signal. No odds/league filter.",
    },
    "C_SERIE_A": {
        "id": "C_SERIE_A",
        "label": "Portfolio C — Serie A",
        "hypothesis": "H3: Serie A has better model performance",
        "description": "Every qualifying signal in Serie A. No market/odds filter.",
    },
    "D_ODDS_2_10_2_50": {
        "id": "D_ODDS_2_10_2_50",
        "label": "Portfolio D — Odds 2.10–2.50",
        "hypothesis": "H4: Odds 2.10–2.50 have better model performance",
        "description": "Every qualifying signal with bet-time odds in [2.10, 2.50]. No market filter.",
    },
}


def _is_serie_a(league: str) -> bool:
    name = (league or "").strip().lower()
    return name in {"serie a", "italy serie a", "serie a (italy)"} or name.startswith("serie a")


def portfolio_membership(signal: dict[str, Any]) -> list[str]:
    """Return portfolio ids this signal belongs to (independent, can overlap)."""
    ids: list[str] = []
    bt = str(signal.get("bet_type") or signal.get("market_key") or "").lower()
    market = str(signal.get("market") or "").lower()
    league = str(signal.get("league") or signal.get("league_name") or "")
    try:
        odds = float(signal.get("odds_at_signal") or signal.get("odds") or 0)
    except (TypeError, ValueError):
        odds = 0.0

    if bt == "over3.5" or "over 3.5" in market:
        ids.append("A_O3_5")
    if bt == "over2.5" or "over 2.5" in market:
        ids.append("B_O2_5")
    if _is_serie_a(league):
        ids.append("C_SERIE_A")
    if 2.10 <= odds <= 2.50:
        ids.append("D_ODDS_2_10_2_50")
    return ids
