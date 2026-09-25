"""Strategy bucket config — LIVE / TRACKING / LOGGING graduation pipeline.

Single source of truth for capital allocation categories. Each strategy maps to
at most one LIVE rule (no nested overlapping stake rules). Flat $1 USD stake.
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from app.db import load_state, save_state
from app.research_analytics import classify_market

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

STATE_LOGGING = "LOGGING"
STATE_TRACKING = "TRACKING"
STATE_LIVE = "LIVE"

FLAT_STAKE_USD = 1.0

# Persisted promotions / demotions (overrides initial_state).
STATE_STORE_KEY = "strategy_bucket_states"
REPORT_STORE_KEY = "strategy_bucket_status_reports"

FAV_LEAGUES_MAIN: frozenset[str] = frozenset(
    {
        "UEFA Champions League",
        "La Liga",
        "Super League",
        "Leagues Cup",
        "DFB Pokal",
        "UEFA Europa Conference League",
        "UEFA Europa League",
        "Primeira Liga",
    }
)

FAV_LEAGUES_ARAHUS: frozenset[str] = frozenset(
    {
        "Eerste Divisie",
        "Eredivisie",
        "Bundesliga",
        "Super League",
    }
)

# Seed cup / knockout leagues (extensible via is_cup_competition).
CUP_LEAGUE_META: dict[str, dict[str, Any]] = {
    "US Open Cup": {"is_cup_competition": True},
    "Canadian Championship": {"is_cup_competition": True},
}

# Strategies excluded from this pipeline entirely.
EXCLUDED_STRATEGIES: frozenset[str] = frozenset({"lm", "no", "LM", "NO"})

# Documented non-implemented slices (never stake, never paper-log).
EXPLICIT_EXCLUSIONS: dict[str, str] = {
    "CS": 'every market except "Correct score 0-1" and "Correct score 2-1"',
    "+EV": 'every market except "Over 3.5"',
    "Main": 'Moneyline (all odds), BTTS Yes, and odds outside 1.30–1.49 unless Over 2.5 / fav league / cup tracking',
    "Arahus": "BTTS Yes; odds 1.50–1.69 as a category; leagues Allsvenskan, 2. Bundesliga, Superliga, Pro League",
    "LM/NO": "entire strategies — no routing",
}

STRATEGY_ALIASES: dict[str, str] = {
    "main": "main",
    "recommended": "main",
    "cs": "cs",
    "correct_score": "cs",
    "ev": "ev",
    "+ev": "ev",
    "plus_ev": "ev",
    "h2h": "h2h",
    "arahus": "arahus",
    "arahus_v2": "arahus",  # bucket rules target Arahus family
    "arahus_live_v1": "arahus",
}


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _league_key(name: str) -> str:
    return _norm(name)


_LEAGUE_LOOKUP = {_league_key(x): x for x in FAV_LEAGUES_MAIN | FAV_LEAGUES_ARAHUS}
for _cup in CUP_LEAGUE_META:
    _LEAGUE_LOOKUP[_league_key(_cup)] = _cup


def normalize_strategy(strategy: str | None) -> str | None:
    raw = _norm(strategy)
    if not raw:
        return None
    if raw in EXCLUDED_STRATEGIES or raw in {"line movement", "no-vig", "no vig", "no-vig model"}:
        return None
    return STRATEGY_ALIASES.get(raw, raw if raw in {"main", "cs", "ev", "h2h", "arahus"} else None)


def parse_odds(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        o = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(o) or o <= 1.0:
        return None
    return o


def odds_in_130_149(odds: float | None) -> bool:
    """1.30 ≤ odds < 1.50 (covers the 1.30–1.49 book band)."""
    return odds is not None and 1.30 <= odds < 1.50


def odds_in_170_199(odds: float | None) -> bool:
    return odds is not None and 1.70 <= odds < 2.00


def odds_in_200_249(odds: float | None) -> bool:
    return odds is not None and 2.00 <= odds < 2.50


def is_cup_league(league: str | None) -> bool:
    key = _league_key(league or "")
    meta = CUP_LEAGUE_META.get(_LEAGUE_LOOKUP.get(key, league or ""))
    if meta and meta.get("is_cup_competition"):
        return True
    # Heuristic for newly appearing cups when config flag missing.
    n = _norm(league)
    return any(tok in n for tok in ("cup", "pokal", "championship", "open cup")) and "league cup" not in n


def register_cup_league(league: str, *, is_cup: bool = True) -> None:
    """Extend cup list at runtime (config-driven)."""
    name = str(league or "").strip()
    if not name:
        return
    CUP_LEAGUE_META[name] = {"is_cup_competition": bool(is_cup)}
    _LEAGUE_LOOKUP[_league_key(name)] = name


_ARAHUS_BET_TYPE_LABELS: dict[str, str] = {
    "arahus_o25": "Over 2.5",
    "arahus_o35": "Over 3.5",
    "arahus_o15": "Over 1.5",
    "arahus_u25": "Under 2.5",
    "arahus_btts": "BTTS Yes",
    "arahus_team_o15": "Team Over 1.5",
    "arahus_team_o05": "Team Over 0.5",
    "arahus_ml": "Moneyline",
    "arahus_dc_1x": "Win or Draw",
    "arahus_dc_x2": "Draw or Away",
}


def canonical_market(row: dict[str, Any]) -> str:
    """Human market label used by bucket rules."""
    strategy = normalize_strategy(row.get("strategy") or row.get("log_type"))
    bet_type = str(row.get("bet_type") or "")
    team = str(row.get("team_name") or "").strip()
    label = str(row.get("market") or row.get("market_label") or "").strip()

    if strategy == "cs" or bet_type == "correct_score":
        score = team or (label.replace("Correct score", "").strip() if label else "")
        return f"Correct score {score}" if score else (label or "Correct score")

    classified = classify_market(label, bet_type)
    mapping = {
        "over_2.5": "Over 2.5",
        "over_3.5": "Over 3.5",
        "over_1.5": "Over 1.5",
        "btts": "BTTS Yes",
        "team_o1.5": "Team Over 1.5",
        "team_o0.5": "Team Over 0.5",
        "moneyline": "Moneyline",
        "win_or_draw": "Win or Draw",
    }
    if classified in mapping:
        return mapping[classified]
    if label:
        return label
    # Fall back to Arahus-specific bet_type labels before returning raw code or "other".
    if bet_type in _ARAHUS_BET_TYPE_LABELS:
        return _ARAHUS_BET_TYPE_LABELS[bet_type]
    # Corners: arahus_corners_oXX → "Corners Over X.X"
    if bet_type.startswith("arahus_corners_o"):
        raw_num = bet_type[len("arahus_corners_o"):]
        try:
            val = float(raw_num) / 10
            return f"Corners Over {val:.1f}"
        except ValueError:
            return f"Corners {raw_num}"
    return classified or bet_type or "other"


def league_in(league: str | None, allowed: Iterable[str]) -> bool:
    key = _league_key(league or "")
    allowed_keys = {_league_key(x) for x in allowed}
    return key in allowed_keys


MatchFn = Callable[[dict[str, Any]], bool]


@dataclass
class CategoryDef:
    id: str
    strategy: str
    initial_state: str
    match: MatchFn
    stake_usd: float = FLAT_STAKE_USD
    decay_watch: bool = False
    recent_underperformance_watch: bool = False
    min_sample_watch: bool = False
    min_sample_n: int | None = None
    is_cup_competition: bool = False
    description: str = ""
    # Optional: used only for regression tests / docs
    tags: dict[str, Any] = field(default_factory=dict)


def _match_main_filtered(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "main":
        return False
    market = canonical_market(row)
    # Explicit Main exclusions — never stake / never log these slices.
    if market in {"Moneyline", "BTTS Yes"}:
        return False
    league = str(row.get("league") or row.get("league_name") or "")
    # Cups are paper-tracked separately until graduated.
    if is_cup_league(league):
        return False
    odds = parse_odds(row.get("odds"))
    return bool(
        odds_in_130_149(odds)
        or market == "Over 2.5"
        or league_in(league, FAV_LEAGUES_MAIN)
    )


def _match_cs_01(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "cs":
        return False
    return _norm(canonical_market(row)) == _norm("Correct score 0-1")


def _match_cs_21(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "cs":
        return False
    return _norm(canonical_market(row)) == _norm("Correct score 2-1")


def _match_ev_o35(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "ev":
        return False
    return canonical_market(row) == "Over 3.5"


def _match_h2h_o25(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "h2h":
        return False
    return canonical_market(row) == "Over 2.5"


def _match_arahus_filtered(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "arahus":
        return False
    market = canonical_market(row)
    if market == "BTTS Yes":
        return False
    league = str(row.get("league") or row.get("league_name") or "")
    if league_in(
        league,
        ("Allsvenskan", "2. Bundesliga", "Superliga", "Pro League"),
    ):
        return False
    odds = parse_odds(row.get("odds"))
    return bool(
        (market == "Over 2.5" and odds_in_130_149(odds))
        or league_in(league, FAV_LEAGUES_ARAHUS)
    )


def _match_h2h_btts(row: dict[str, Any]) -> bool:
    return normalize_strategy(row.get("strategy")) == "h2h" and canonical_market(row) == "BTTS Yes"


def _match_arahus_o35(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "arahus":
        return False
    if _match_arahus_filtered(row):
        return False
    return canonical_market(row) == "Over 3.5"


def _match_arahus_odds_170_199(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "arahus":
        return False
    if _match_arahus_filtered(row):
        return False
    # Prefer dedicated Over 3.5 paper bucket when both apply.
    if canonical_market(row) == "Over 3.5":
        return False
    return odds_in_170_199(parse_odds(row.get("odds")))


def _match_main_cup(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "main":
        return False
    market = canonical_market(row)
    if market in {"Moneyline", "BTTS Yes"}:
        return False
    league = str(row.get("league") or row.get("league_name") or "")
    return is_cup_league(league)


def _match_main_odds_200_249(row: dict[str, Any]) -> bool:
    if normalize_strategy(row.get("strategy")) != "main":
        return False
    market = canonical_market(row)
    if market in {"Moneyline", "BTTS Yes"}:
        return False
    if _match_main_filtered(row) or _match_main_cup(row):
        return False
    return odds_in_200_249(parse_odds(row.get("odds")))


# --- Old overlapping rule (REMOVED as standalone LIVE) — kept for regression tests ---
def match_legacy_main_team_o15_130_149(row: dict[str, Any]) -> bool:
    """Deprecated standalone rule that overlapped Main_filtered odds band."""
    if normalize_strategy(row.get("strategy")) != "main":
        return False
    if canonical_market(row) != "Team Over 1.5":
        return False
    return odds_in_130_149(parse_odds(row.get("odds")))


CATEGORIES: dict[str, CategoryDef] = {
    "Main_filtered": CategoryDef(
        id="Main_filtered",
        strategy="main",
        initial_state=STATE_LIVE,
        match=_match_main_filtered,
        description="Main odds 1.30–1.49 OR Over 2.5 OR fav leagues (includes former Team O1.5 band)",
    ),
    "CS_CorrectScore_0_1": CategoryDef(
        id="CS_CorrectScore_0_1",
        strategy="cs",
        initial_state=STATE_LIVE,
        match=_match_cs_01,
        description="CS Correct score 0-1",
    ),
    "CS_CorrectScore_2_1": CategoryDef(
        id="CS_CorrectScore_2_1",
        strategy="cs",
        initial_state=STATE_LIVE,
        match=_match_cs_21,
        decay_watch=True,
        description="CS Correct score 2-1 (decay watch)",
    ),
    "EV_Over_3_5": CategoryDef(
        id="EV_Over_3_5",
        strategy="ev",
        initial_state=STATE_LOGGING,
        match=_match_ev_o35,
        stake_usd=0.0,
        recent_underperformance_watch=True,
        description="+EV Over 3.5 — demoted from LIVE (gates fail / underperformance)",
    ),
    "H2H_Over_2_5": CategoryDef(
        id="H2H_Over_2_5",
        strategy="h2h",
        initial_state=STATE_LIVE,
        match=_match_h2h_o25,
        min_sample_watch=True,
        min_sample_n=48,
        description="H2H Over 2.5 (review at n>=100)",
    ),
    "Arahus_filtered": CategoryDef(
        id="Arahus_filtered",
        strategy="arahus",
        initial_state=STATE_LIVE,
        match=_match_arahus_filtered,
        description="Arahus O2.5 @ 1.30–1.49 OR fav leagues",
    ),
    # LOGGING
    "H2H_BTTS_Yes": CategoryDef(
        id="H2H_BTTS_Yes",
        strategy="h2h",
        initial_state=STATE_LOGGING,
        match=_match_h2h_btts,
        stake_usd=0.0,
        description="H2H BTTS Yes — paper only",
    ),
    "Arahus_Over_3_5": CategoryDef(
        id="Arahus_Over_3_5",
        strategy="arahus",
        initial_state=STATE_LOGGING,
        match=_match_arahus_o35,
        stake_usd=0.0,
        description="Arahus Over 3.5 — paper only",
    ),
    "Arahus_Odds_1_70_1_99": CategoryDef(
        id="Arahus_Odds_1_70_1_99",
        strategy="arahus",
        initial_state=STATE_LOGGING,
        match=_match_arahus_odds_170_199,
        stake_usd=0.0,
        description="Arahus odds 1.70–1.99 — paper only",
    ),
    "Main_Cup_Competitions": CategoryDef(
        id="Main_Cup_Competitions",
        strategy="main",
        initial_state=STATE_LOGGING,
        match=_match_main_cup,
        stake_usd=0.0,
        is_cup_competition=True,
        description="Main cup/knockout competitions — paper only",
    ),
    # TRACKING
    "Main_Odds_2_00_2_49": CategoryDef(
        id="Main_Odds_2_00_2_49",
        strategy="main",
        initial_state=STATE_TRACKING,
        match=_match_main_odds_200_249,
        stake_usd=0.0,
        description="Main odds 2.00–2.49 — tracking toward LIVE",
    ),
}

LIVE_CATEGORY_IDS: tuple[str, ...] = tuple(
    cid for cid, c in CATEGORIES.items() if c.initial_state == STATE_LIVE
)


def get_runtime_states() -> dict[str, str]:
    stored = load_state(STATE_STORE_KEY, {})
    out: dict[str, str] = {}
    for cid, cat in CATEGORIES.items():
        # Config demotion wins over a stale LIVE value left in the state store.
        if cat.initial_state == STATE_LOGGING and str(stored.get(cid) or "") == STATE_LIVE:
            out[cid] = STATE_LOGGING
            continue
        out[cid] = str(stored.get(cid) or cat.initial_state)
    return out


def set_runtime_state(category_id: str, state: str) -> None:
    if category_id not in CATEGORIES:
        raise KeyError(category_id)
    if state not in {STATE_LOGGING, STATE_TRACKING, STATE_LIVE}:
        raise ValueError(state)
    stored = dict(load_state(STATE_STORE_KEY, {}))
    stored[category_id] = state
    save_state(STATE_STORE_KEY, stored)


def enrich_bet_row(row: dict[str, Any], *, strategy: str | None = None) -> dict[str, Any]:
    """Normalize a bet_entries-like row for matching."""
    out = dict(row)
    strat = normalize_strategy(strategy or row.get("strategy") or row.get("log_type"))
    out["strategy"] = strat
    out["odds"] = parse_odds(row.get("odds"))
    out["league"] = str(row.get("league") or row.get("league_name") or "")
    out["market"] = canonical_market({**row, "strategy": strat})
    out["market_class"] = classify_market(
        str(row.get("market") or row.get("market_label") or ""),
        str(row.get("bet_type") or ""),
    )
    return out


def matching_categories(
    row: dict[str, Any],
    *,
    states: dict[str, str] | None = None,
    only_states: Iterable[str] | None = None,
) -> list[str]:
    """Return all category ids whose rules match this bet (respecting strategy)."""
    bet = enrich_bet_row(row)
    if not bet.get("strategy"):
        return []
    runtime = states or get_runtime_states()
    allowed_states = set(only_states) if only_states is not None else None
    hits: list[str] = []
    for cid, cat in CATEGORIES.items():
        if cat.strategy != bet["strategy"]:
            continue
        state = runtime.get(cid, cat.initial_state)
        if allowed_states is not None and state not in allowed_states:
            continue
        if cat.match(bet):
            hits.append(cid)
    return hits


def assign_live_category(row: dict[str, Any], *, states: dict[str, str] | None = None) -> str | None:
    """Exactly one LIVE category per strategy, or None if no live stake."""
    hits = matching_categories(row, states=states, only_states={STATE_LIVE})
    if not hits:
        return None
    # Strategy uniqueness: at most one LIVE rule per strategy by construction.
    return hits[0]


def stake_for_bet(row: dict[str, Any], *, states: dict[str, str] | None = None) -> float:
    cid = assign_live_category(row, states=states)
    if not cid:
        return 0.0
    cat = CATEGORIES[cid]
    runtime = states or get_runtime_states()
    if runtime.get(cid, cat.initial_state) != STATE_LIVE:
        return 0.0
    # Always flat $1 once LIVE (promoted TRACKING/LOGGING categories start at stake_usd=0).
    return FLAT_STAKE_USD


def live_dedupe_key(row: dict[str, Any]) -> tuple[Any, ...]:
    bet = enrich_bet_row(row)
    return (
        str(bet.get("fixture") or ""),
        str(bet.get("market") or ""),
        bet.get("odds"),
        str(bet.get("fixture_date") or bet.get("created_at") or ""),
    )


def find_live_overlaps(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return keys matched by >1 LIVE category (should always be empty)."""
    # Per-row multi-category hits
    bad: list[dict[str, Any]] = []
    states = {cid: STATE_LIVE for cid in LIVE_CATEGORY_IDS}  # evaluate all LIVE rules
    for row in rows:
        bet = enrich_bet_row(row)
        if not bet.get("strategy"):
            continue
        hits = []
        for cid in LIVE_CATEGORY_IDS:
            cat = CATEGORIES[cid]
            if cat.strategy != bet["strategy"]:
                continue
            if cat.match(bet):
                hits.append(cid)
        if len(hits) > 1:
            bad.append({"key": live_dedupe_key(bet), "categories": hits, "bet": bet})
    return bad


# --- Graduation metrics -------------------------------------------------------


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(IST).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(IST).date() if dt.tzinfo else dt.date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _settled_pnl(row: dict[str, Any]) -> float | None:
    status = str(row.get("status") or row.get("result") or "").lower()
    if status not in {"won", "lost", "push"}:
        return None
    pnl = row.get("pnl_units")
    if pnl is not None:
        try:
            return float(pnl)
        except (TypeError, ValueError):
            pass
    # Flat $1 counterfactual if no pnl stored
    odds = parse_odds(row.get("odds"))
    if status == "won":
        return (odds - 1.0) if odds else 1.0
    if status == "lost":
        return -1.0
    return 0.0


def category_settled_rows(
    category_id: str,
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    cat = CATEGORIES[category_id]
    out: list[dict[str, Any]] = []
    for row in rows:
        bet = enrich_bet_row(row, strategy=row.get("strategy") or row.get("log_type"))
        if bet.get("strategy") != cat.strategy:
            continue
        if not cat.match(bet):
            continue
        if _settled_pnl(bet) is None:
            continue
        bet["_pnl"] = _settled_pnl(bet)
        bet["_date"] = _parse_date(bet.get("fixture_date") or bet.get("resolved_at") or bet.get("created_at"))
        out.append(bet)
    return out


def _roi(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    pnl = sum(float(r.get("_pnl") or 0) for r in rows)
    # Flat 1u stake assumption for paper + live reporting
    staked = float(len(rows))
    return pnl / staked if staked else None


def _monthly_roi(rows: list[dict[str, Any]], months: int = 3) -> list[dict[str, Any]]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        d = r.get("_date")
        if not d:
            continue
        by_month[f"{d.year:04d}-{d.month:02d}"].append(r)
    keys = sorted(by_month.keys())[-months:]
    out = []
    for k in keys:
        subset = by_month[k]
        out.append({"month": k, "n": len(subset), "roi": _roi(subset)})
    return out


def graduation_gates(
    category_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate TRACKING→LIVE gates a–d."""
    cat = CATEGORIES[category_id]
    settled = category_settled_rows(category_id, rows)
    n = len(settled)
    min_n = 50 if cat.is_cup_competition else 100
    full_roi = _roi(settled)
    last3 = _monthly_roi(settled, months=3)

    # a. sample size
    gate_a = n >= min_n

    # b. positive ROI in >= 2 of last 3 calendar months
    pos_months = sum(1 for m in last3 if (m.get("roi") is not None and m["roi"] > 0))
    gate_b = pos_months >= 2 and len(last3) >= 2

    # c. full-sample ROI >= 5%
    gate_c = full_roi is not None and full_roi >= 0.05

    # d. not monotonically decreasing MoM ROI over last 3 months
    rois = [m.get("roi") for m in last3 if m.get("roi") is not None]
    if len(rois) >= 3:
        gate_d = not (rois[0] > rois[1] > rois[2])
    else:
        gate_d = True  # insufficient history — don't fail solely on trend

    return {
        "n": n,
        "min_n": min_n,
        "full_roi": full_roi,
        "last_3_months": last3,
        "gates": {
            "a_sample_size": gate_a,
            "b_positive_months": gate_b,
            "c_full_roi_ge_5pct": gate_c,
            "d_no_monotone_decline": gate_d,
        },
        "all_pass": gate_a and gate_b and gate_c and gate_d,
    }


def decay_triggers(
    category_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """LIVE exit conditions."""
    cat = CATEGORIES[category_id]
    settled = category_settled_rows(category_id, rows)
    last3 = _monthly_roi(settled, months=3)
    # 2 consecutive months ROI < 0
    consec_neg = False
    if len(last3) >= 2:
        r0 = last3[-1].get("roi")
        r1 = last3[-2].get("roi")
        consec_neg = r0 is not None and r1 is not None and r0 < 0 and r1 < 0
    # any single month ROI < -15%
    crash = any((m.get("roi") is not None and m["roi"] < -0.15) for m in last3)

    demote = False
    reasons: list[str] = []
    if cat.decay_watch and consec_neg:
        demote = True
        reasons.append("decay_watch_two_consecutive_negative_months")
    if crash:
        demote = True
        reasons.append("single_month_roi_below_minus_15pct")
    return {
        "demote": demote,
        "reasons": reasons,
        "last_3_months": last3,
        "decay_watch": cat.decay_watch,
    }


def category_status_report(
    rows_by_strategy: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
) -> dict[str, Any]:
    """Status for every category: state, n, ROI, MoM, graduation gates."""
    if isinstance(rows_by_strategy, list):
        flat = list(rows_by_strategy)
    else:
        flat = []
        for strat, rows in rows_by_strategy.items():
            for r in rows:
                flat.append({**r, "strategy": r.get("strategy") or strat, "log_type": r.get("log_type") or strat})

    runtime = get_runtime_states()
    categories_out: dict[str, Any] = {}
    for cid, cat in CATEGORIES.items():
        gates = graduation_gates(cid, flat)
        decay = decay_triggers(cid, flat)
        state = runtime.get(cid, cat.initial_state)
        categories_out[cid] = {
            "id": cid,
            "strategy": cat.strategy,
            "state": state,
            "initial_state": cat.initial_state,
            "stake_usd": FLAT_STAKE_USD if state == STATE_LIVE else 0.0,
            "description": cat.description,
            "flags": {
                "decay_watch": cat.decay_watch,
                "recent_underperformance_watch": cat.recent_underperformance_watch,
                "min_sample_watch": cat.min_sample_watch,
                "min_sample_n": cat.min_sample_n,
                "is_cup_competition": cat.is_cup_competition,
            },
            "n": gates["n"],
            "roi_full": gates["full_roi"],
            "roi_last_3_months": gates["last_3_months"],
            "graduation_gates": gates["gates"],
            "graduation_all_pass": gates["all_pass"],
            "decay": decay,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flat_stake_usd": FLAT_STAKE_USD,
        "live_category_ids": list(LIVE_CATEGORY_IDS),
        "excluded_strategies": sorted(EXCLUDED_STRATEGIES),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "categories": categories_out,
    }


def apply_monthly_graduation(
    rows_by_strategy: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Promote TRACKING→LIVE when gates pass; demote LIVE on decay/crash."""
    report = category_status_report(rows_by_strategy)
    transitions: list[dict[str, Any]] = []
    runtime = get_runtime_states()

    for cid, info in report["categories"].items():
        state = info["state"]
        if state == STATE_TRACKING and info["graduation_all_pass"]:
            if persist:
                set_runtime_state(cid, STATE_LIVE)
            runtime[cid] = STATE_LIVE
            transitions.append({"category": cid, "from": STATE_TRACKING, "to": STATE_LIVE, "reason": "graduation_gates"})
        elif state == STATE_LIVE and info["decay"]["demote"]:
            if persist:
                set_runtime_state(cid, STATE_LOGGING)
            runtime[cid] = STATE_LOGGING
            transitions.append(
                {
                    "category": cid,
                    "from": STATE_LIVE,
                    "to": STATE_LOGGING,
                    "reason": ",".join(info["decay"]["reasons"]),
                }
            )

    payload = {
        **report,
        "transitions": transitions,
        "runtime_states": runtime,
    }
    if persist:
        history = list(load_state(REPORT_STORE_KEY, {"reports": []}).get("reports") or [])
        history.append(
            {
                "at": payload["generated_at"],
                "transitions": transitions,
                "summary": {
                    cid: {
                        "state": info["state"],
                        "n": info["n"],
                        "roi_full": info["roi_full"],
                        "graduation_all_pass": info["graduation_all_pass"],
                    }
                    for cid, info in report["categories"].items()
                },
            }
        )
        save_state(REPORT_STORE_KEY, {"reports": history[-24:]})  # keep ~2y monthly
        logger.info("strategy_buckets monthly graduation: %s", transitions)
    return payload


def aggregate_live_pnl(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """PnL/ROI for LIVE categories only, flat $1 stake (counterfactual units)."""
    states = get_runtime_states()
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cid = assign_live_category(row, states=states)
        if not cid:
            continue
        bet = enrich_bet_row(row)
        pnl = _settled_pnl(bet)
        if pnl is None:
            continue
        by_cat[cid].append({**bet, "_pnl": pnl})

    out_cats = {}
    total_pnl = 0.0
    total_n = 0
    for cid, subset in by_cat.items():
        n = len(subset)
        pnl = sum(float(r["_pnl"]) for r in subset)
        total_pnl += pnl
        total_n += n
        out_cats[cid] = {
            "n": n,
            "pnl": round(pnl, 4),
            "roi": round(pnl / n, 4) if n else None,
            "stake_usd": FLAT_STAKE_USD,
        }
    return {
        "categories": out_cats,
        "n": total_n,
        "pnl": round(total_pnl, 4),
        "roi": round(total_pnl / total_n, 4) if total_n else None,
        "stake_usd": FLAT_STAKE_USD,
    }


def load_pipeline_bets_from_db() -> dict[str, list[dict[str, Any]]]:
    """Load main/cs/ev/h2h/arahus logs for reports (excludes LM/NO)."""
    from app.db import list_bets

    out: dict[str, list[dict[str, Any]]] = {}
    for log_type in ("main", "cs", "ev", "h2h", "arahus"):
        rows = []
        for r in list_bets(log_type):
            rows.append({**r, "strategy": log_type, "log_type": log_type})
        out[log_type] = rows
    return out
