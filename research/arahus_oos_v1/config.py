"""Frozen Arahus OOS Candidate v1 — do not alter from OOS outcomes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# League whitelist status (critical)
# ---------------------------------------------------------------------------
# Searched: app/arahus_engine.py, app/arahus_v2_engine.py, rules.json, env
# templates, research/. There is NO selected-league whitelist constant or
# filter in this repository. Arahus evaluates every fixture in the scraped
# slate; league_name is informational only.
#
# Therefore selected_leagues is explicitly None (= no league filter).
# Baseline "O2.5 + odds + selected leagues" is identical to
# "O2.5 + odds without league filtering" until a whitelist is defined in code.
# ---------------------------------------------------------------------------

LEAGUE_WHITELIST_STATUS = {
    "defined_in_repo": False,
    "selected_leagues": None,
    "ambiguity": (
        "No CURRENT_ARAHUS_SELECTED_LEAGUE_WHITELIST (or equivalent) exists. "
        "Arahus v1/v2 do not gate picks by league. Flashscore league aliases "
        "in app/flashscore_client.py are settlement matching only, not a pick "
        "whitelist. Do not invent a league list from OOS results."
    ),
    "sources_checked": [
        "app/arahus_engine.py",
        "app/arahus_v2_engine.py",
        "app/flashscore_client.py (settlement aliases only)",
        "rules.json",
        "research/",
    ],
}


# Market aliases → canonical key
MARKET_ALIASES: dict[str, str] = {
    "over 2.5": "over_2_5",
    "o2.5": "over_2_5",
    "o 2.5": "over_2_5",
    "arahus_o25": "over_2_5",
    "over2.5": "over_2_5",
    "over 3.5": "over_3_5",
    "o3.5": "over_3_5",
    "arahus_o35": "over_3_5",
    "over3.5": "over_3_5",
    "btts yes": "btts_yes",
    "btts": "btts_yes",
    "arahus_btts": "btts_yes",
    "btts no": "btts_no",
    "under 2.5": "under_2_5",
    "arahus_u25": "under_2_5",
}

ALLOWED_MARKET = "over_2_5"
REJECTED_MARKETS = frozenset({"over_3_5", "btts_yes", "btts_no", "under_2_5"})


@dataclass(frozen=True)
class FrozenCandidateConfig:
    """Exact reproducible strategy definition — frozen before OOS evaluation."""

    candidate_id: str = "arahus_oos_candidate_v1"
    label: str = "Arahus OOS Candidate v1 — O2.5 odds 1.30–1.49"
    market: str = ALLOWED_MARKET
    odds_min: float = 1.30
    odds_max: float = 1.49
    # None = no league filter (whitelist not defined in repo)
    selected_leagues: tuple[str, ...] | None = None
    btts: bool = False
    over_3_5: bool = False
    # Confidence is NOT a gate for this candidate (descriptive breakdown only)
    confidence_min: float | None = None
    confidence_max: float | None = None
    # Primary analysis uses logged stake; also report flat 1.0u
    primary_stake_mode: str = "logged_units"
    normalized_stake: float = 1.0
    development_start: date = field(default_factory=lambda: date(2026, 7, 1))
    development_end: date = field(default_factory=lambda: date(2026, 8, 31))
    oos_start: date = field(default_factory=lambda: date(2026, 9, 1))
    # OOS end = latest settled bet date in dataset (filled at runtime)
    random_seed: int = 42
    bootstrap_n: int = 2000
    notes: tuple[str, ...] = (
        "Validation only — do not optimize odds/leagues/confidence from OOS.",
        "League whitelist undefined in repo; no league filter applied.",
        "Push PnL = 0; push stake included in total staked (Arahus convention).",
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["development_start"] = self.development_start.isoformat()
        d["development_end"] = self.development_end.isoformat()
        d["oos_start"] = self.oos_start.isoformat()
        d["league_whitelist_status"] = LEAGUE_WHITELIST_STATUS
        return d


FROZEN_CONFIG = FrozenCandidateConfig()

# Descriptive analysis bands (NOT strategy gates)
ODDS_BANDS_ANALYSIS = (
    (1.30, 1.34, "1.30–1.34"),
    (1.35, 1.39, "1.35–1.39"),
    (1.40, 1.44, "1.40–1.44"),
    (1.45, 1.49, "1.45–1.49"),
)

CONF_BANDS_ANALYSIS = (
    (60, 64, "60–64"),
    (65, 69, "65–69"),
    (70, 74, "70–74"),
    (75, 79, "75–79"),
    (80, 200, "80+"),
)
