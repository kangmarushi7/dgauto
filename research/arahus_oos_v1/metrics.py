"""Performance / risk metrics for Arahus OOS (matches Arahus PnL conventions)."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from research.arahus_oos_v1.config import FROZEN_CONFIG


def pnl_for_bet(
    status: str,
    odds: float | None,
    units: float,
    *,
    logged_pnl: float | None = None,
    prefer_logged: bool = True,
) -> float | None:
    """
    Arahus convention (resolve_arahus_bet):
      won  -> (odds - 1) * units
      lost -> -units
      push -> 0
    Open / unknown -> None (excluded from settled ROI).
    Push stake is included in total staked when the bet is in the settled set.
    """
    st = str(status or "").lower()
    if st not in {"won", "lost", "push"}:
        return None
    if prefer_logged and logged_pnl is not None and st in {"won", "lost", "push"}:
        # Prefer logged PnL when present (matches dashboard), but recompute if missing
        return float(logged_pnl)
    u = float(units)
    if st == "push":
        return 0.0
    if st == "lost":
        return -u
    # won
    if odds is None or odds <= 0:
        return u
    return round((float(odds) - 1.0) * u, 6)


def sample_size_label(n: int) -> str:
    if n < 10:
        return "very small sample"
    if n < 25:
        return "small sample"
    if n < 50:
        return "moderate sample"
    return "larger sample"


def max_drawdown(equity: list[float]) -> dict[str, float]:
    if not equity:
        return {"max_dd_units": 0.0, "max_dd_pct": 0.0, "peak": 0.0}
    peak = equity[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for x in equity:
        peak = max(peak, x)
        dd = peak - x
        max_dd = max(max_dd, dd)
        if peak != 0:
            max_dd_pct = max(max_dd_pct, dd / abs(peak) if peak != 0 else 0.0)
        # Prefer stake-relative: dd / peak when peak > 0
        if peak > 0:
            max_dd_pct = max(max_dd_pct, dd / peak)
    return {
        "max_dd_units": float(max_dd),
        "max_dd_pct": float(max_dd_pct),
        "peak": float(peak),
    }


def streaks(results: list[str]) -> dict[str, int]:
    longest_loss = longest_win = 0
    cur_loss = cur_win = 0
    for r in results:
        if r == "lost":
            cur_loss += 1
            cur_win = 0
            longest_loss = max(longest_loss, cur_loss)
        elif r == "won":
            cur_win += 1
            cur_loss = 0
            longest_win = max(longest_win, cur_win)
        else:
            cur_loss = cur_win = 0
    return {
        "longest_losing_streak": longest_loss,
        "longest_winning_streak": longest_win,
    }


def bootstrap_mean_ci(
    values: list[float],
    *,
    n_boot: int | None = None,
    seed: int | None = None,
    alpha: float = 0.05,
) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "ci_low": None, "ci_high": None, "n": 0}
    rng = np.random.default_rng(seed if seed is not None else FROZEN_CONFIG.random_seed)
    n_boot = n_boot or FROZEN_CONFIG.bootstrap_n
    arr = np.asarray(values, dtype=float)
    means = []
    n = len(arr)
    for _ in range(n_boot):
        sample = arr[rng.integers(0, n, size=n)]
        means.append(float(sample.mean()))
    lo = float(np.quantile(means, alpha / 2))
    hi = float(np.quantile(means, 1 - alpha / 2))
    return {
        "mean": float(arr.mean()),
        "ci_low": lo,
        "ci_high": hi,
        "n": n,
        "n_boot": n_boot,
        "seed": int(seed if seed is not None else FROZEN_CONFIG.random_seed),
    }


def summarize_bets(
    rows: list[dict[str, Any]],
    *,
    stake_mode: str = "logged_units",
    normalized_stake: float = 1.0,
    prefer_logged_pnl: bool = True,
) -> dict[str, Any]:
    """
    stake_mode:
      - logged_units: use row['units'] and logged pnl when available
      - flat_1u: force 1.0u and recompute pnl from odds/status
    """
    settled = [r for r in rows if r.get("status") in {"won", "lost", "push"}]
    pnls: list[float] = []
    stakes: list[float] = []
    odds_list: list[float] = []
    results: list[str] = []
    equity: list[float] = []
    cum = 0.0

    for r in settled:
        status = str(r["status"])
        odds = r.get("odds")
        if stake_mode == "flat_1u":
            units = float(normalized_stake)
            pnl = pnl_for_bet(status, odds, units, prefer_logged=False)
        else:
            units = float(r.get("units") if r.get("units") is not None else 1.0)
            pnl = pnl_for_bet(
                status,
                odds,
                units,
                logged_pnl=r.get("pnl_units_logged"),
                prefer_logged=prefer_logged_pnl,
            )
        if pnl is None:
            continue
        pnls.append(float(pnl))
        stakes.append(units)
        if odds is not None:
            odds_list.append(float(odds))
        results.append(status)
        cum += float(pnl)
        equity.append(cum)

    won = sum(1 for x in results if x == "won")
    lost = sum(1 for x in results if x == "lost")
    push = sum(1 for x in results if x == "push")
    decided = won + lost
    staked = float(sum(stakes))
    total_pnl = float(sum(pnls))
    roi = (total_pnl / staked) if staked else None
    dd = max_drawdown(equity)
    st = streaks(results)
    per_bet = pnls
    std = float(np.std(per_bet, ddof=1)) if len(per_bet) > 1 else 0.0
    # Sharpe-like: mean return per bet / std (not annualized) — label clearly
    sharpe_like = (float(np.mean(per_bet)) / std) if std > 0 else None
    gross_win = float(sum(p for p in pnls if p > 0))
    gross_loss = float(abs(sum(p for p in pnls if p < 0)))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None

    # Drawdown % of capital at risk ≈ max_dd / total staked (clearer than peak-equity %)
    max_dd_pct_of_staked = (dd["max_dd_units"] / staked) if staked else None

    roi_returns = [p / s if s else 0.0 for p, s in zip(pnls, stakes)]
    roi_ci = bootstrap_mean_ci(roi_returns)
    # Bootstrap of portfolio ROI = sum(pnl)/sum(stake) via resampling bets
    portfolio_rois: list[float] = []
    if settled:
        rng = np.random.default_rng(FROZEN_CONFIG.random_seed)
        n = len(pnls)
        for _ in range(FROZEN_CONFIG.bootstrap_n):
            idx = rng.integers(0, n, size=n)
            sp = sum(pnls[i] for i in idx)
            ss = sum(stakes[i] for i in idx)
            portfolio_rois.append(sp / ss if ss else 0.0)
        port_ci = {
            "mean": float(np.mean(portfolio_rois)),
            "ci_low": float(np.quantile(portfolio_rois, 0.025)),
            "ci_high": float(np.quantile(portfolio_rois, 0.975)),
            "n": n,
            "n_boot": FROZEN_CONFIG.bootstrap_n,
            "seed": FROZEN_CONFIG.random_seed,
        }
    else:
        port_ci = {"mean": None, "ci_low": None, "ci_high": None, "n": 0}

    mean_ci = bootstrap_mean_ci(per_bet)

    return {
        "n": len(settled),
        "n_with_pnl": len(pnls),
        "won": won,
        "lost": lost,
        "push": push,
        "win_pct": (won / decided) if decided else None,
        "avg_odds": float(np.mean(odds_list)) if odds_list else None,
        "median_odds": float(np.median(odds_list)) if odds_list else None,
        "staked": staked,
        "pnl": total_pnl,
        "roi": roi,
        "avg_pnl_per_bet": float(np.mean(pnls)) if pnls else None,
        "max_dd_units": dd["max_dd_units"],
        "max_dd_pct": max_dd_pct_of_staked,
        "max_dd_pct_of_peak_equity": dd["max_dd_pct"],
        "max_dd_pct_note": "max_dd_pct = max_dd_units / total staked",
        "longest_losing_streak": st["longest_losing_streak"],
        "longest_winning_streak": st["longest_winning_streak"],
        "worst_single_loss": float(min(pnls)) if pnls else None,
        "best_single_win": float(max(pnls)) if pnls else None,
        "equity_curve": equity,
        "std_per_bet_return": std,
        "volatility_per_bet": std,
        "sharpe_like_per_bet": sharpe_like,
        "sharpe_like_note": "mean(pnl)/std(pnl); not annualized; not a financial Sharpe",
        "profit_factor": profit_factor,
        "bootstrap_roi_portfolio": port_ci,
        "bootstrap_mean_pnl_per_bet": mean_ci,
        "bootstrap_mean_return_per_unit_staked": roi_ci,
        "sample_label": sample_size_label(len(settled)),
        "stake_mode": stake_mode,
        "push_accounting": "PnL=0; stake included in total staked",
    }


def bets_needed_for_precision(
    *,
    target_se: float = 0.05,
    assumed_std: float | None = None,
    observed_std: float | None = None,
) -> dict[str, Any]:
    """Rough N for SE of mean return ≈ target_se (normal approximation)."""
    std = assumed_std if assumed_std is not None else observed_std
    if std is None or std <= 0:
        return {
            "target_se": target_se,
            "n_required": None,
            "note": "Cannot estimate without positive observed/assumed std of per-bet returns",
        }
    n = math.ceil((std / target_se) ** 2)
    return {
        "target_se": target_se,
        "assumed_std": std,
        "n_required": int(n),
        "note": "N ≈ (σ/SE)^2 for mean per-bet return; not a power calculation for ROI>0",
    }
