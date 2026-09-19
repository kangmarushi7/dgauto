"""Frozen candidate filters — use only bet-time fields (no look-ahead)."""
from __future__ import annotations

from datetime import date
from typing import Any

from research.arahus_oos_v1.config import (
    ALLOWED_MARKET,
    FROZEN_CONFIG,
    FrozenCandidateConfig,
    REJECTED_MARKETS,
)


def odds_in_band(odds: float | None, *, lo: float, hi: float) -> bool:
    """Inclusive band; no rounding. Missing odds never qualify."""
    if odds is None:
        return False
    # Reject non-finite / impossible
    if not (odds == odds) or odds <= 1.0:  # NaN check
        return False
    return lo <= odds <= hi


def market_allowed(market: str | None, cfg: FrozenCandidateConfig = FROZEN_CONFIG) -> bool:
    if market is None:
        return False
    if market in REJECTED_MARKETS:
        return False
    if market == "btts_yes" and not cfg.btts:
        return False
    if market == "over_3_5" and not cfg.over_3_5:
        return False
    return market == cfg.market == ALLOWED_MARKET


def league_allowed(league: str | None, cfg: FrozenCandidateConfig = FROZEN_CONFIG) -> bool:
    """Pass-through when selected_leagues is None (whitelist undefined)."""
    if cfg.selected_leagues is None:
        return True
    name = (league or "").strip()
    return name in cfg.selected_leagues


def qualifies_candidate(
    row: dict[str, Any],
    cfg: FrozenCandidateConfig = FROZEN_CONFIG,
) -> tuple[bool, str]:
    """
    Return (ok, reason). Decisions use only fields known at bet time:
    market, odds, league, confidence (confidence not gated here).
    Never uses status / pnl / closing odds for qualification.
    """
    if not market_allowed(row.get("market"), cfg):
        m = row.get("market")
        if m in REJECTED_MARKETS or m in {"btts_yes", "over_3_5"}:
            return False, f"market_rejected:{m}"
        return False, f"market_not_o25:{m}"
    odds = row.get("odds")
    if odds is None:
        return False, "missing_odds"
    if not odds_in_band(float(odds), lo=cfg.odds_min, hi=cfg.odds_max):
        return False, f"odds_out_of_band:{odds}"
    if not league_allowed(row.get("league_name"), cfg):
        return False, f"league_not_whitelisted:{row.get('league_name')}"
    return True, "ok"


def period_for_date(d: date | None, cfg: FrozenCandidateConfig = FROZEN_CONFIG) -> str:
    if d is None:
        return "unknown"
    if cfg.development_start <= d <= cfg.development_end:
        return "development"
    if d >= cfg.oos_start:
        return "oos"
    if d < cfg.development_start:
        return "pre_development"
    return "gap"


def assign_periods(rows: list[dict[str, Any]], cfg: FrozenCandidateConfig = FROZEN_CONFIG) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        d = None
        if r.get("fixture_date_d"):
            d = date.fromisoformat(str(r["fixture_date_d"]))
        period = period_for_date(d, cfg)
        ok, reason = qualifies_candidate(r, cfg)
        out.append({**r, "period": period, "candidate_ok": ok, "reject_reason": reason})
    return out


def filter_strategy(
    rows: list[dict[str, Any]],
    *,
    period: str | None = "oos",
    require_o25: bool = True,
    odds_band: bool = True,
    apply_league_whitelist: bool = True,
    settled_only: bool = True,
    cfg: FrozenCandidateConfig = FROZEN_CONFIG,
) -> list[dict[str, Any]]:
    """
    Build strategy subsets for comparison.

    apply_league_whitelist: when True and cfg.selected_leagues is None, no-op.
    """
    selected: list[dict[str, Any]] = []
    for r in rows:
        if period is not None and r.get("period") != period:
            continue
        if require_o25 and r.get("market") != ALLOWED_MARKET:
            continue
        if odds_band:
            o = r.get("odds")
            if o is None or not odds_in_band(float(o), lo=cfg.odds_min, hi=cfg.odds_max):
                continue
        if apply_league_whitelist and not league_allowed(r.get("league_name"), cfg):
            continue
        if settled_only and r.get("status") not in {"won", "lost", "push"}:
            continue
        selected.append(r)
    return selected
