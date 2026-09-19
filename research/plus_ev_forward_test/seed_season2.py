"""Seed research ledger from Season 2 bet log (retrospective; CLV usually unavailable)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from research.plus_ev_forward_test.clv import clv_from_odds
from research.plus_ev_forward_test.fair_market import fair_probability_for_selection
from research.plus_ev_forward_test.storage import DEFAULT_DATA_DIR, make_signal, upsert_signals


def _status(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if s in {"won", "lost", "push", "open"}:
        return s
    return s or "open"


def _pnl(result: str | None, odds: float) -> float | None:
    if result == "won":
        return round(odds - 1.0, 4)
    if result == "lost":
        return -1.0
    if result == "push":
        return 0.0
    return None


def seed_from_season2_csv(
    csv_path: Path,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                odds = float(r.get("odds") or 0)
            except ValueError:
                continue
            if odds <= 1:
                continue
            try:
                ev_pct = float(r.get("qualifier_pct") or 0)
            except ValueError:
                ev_pct = 0.0
            ev = ev_pct / 100.0
            model_p = (1.0 + ev) / odds if odds > 0 else None
            result = _status(str(r.get("status") or ""))
            # Historical seed: no closing / opposite odds in export.
            outcome_odds: dict[str, float] = {}
            fair_p = fair_probability_for_selection(str(r.get("bet_type") or ""), outcome_odds)
            clv_info = clv_from_odds(odds, None)
            signal = make_signal(
                signal_id=f"s2:{r.get('id')}",
                fixture_id=None,
                kickoff_time=r.get("fixture_date"),
                timestamp_signal_created=r.get("created_at"),
                league=r.get("league_name"),
                market=r.get("market"),
                bet_type=r.get("bet_type"),
                selection=r.get("team_name") or r.get("market"),
                bookmaker="datagaffer",
                odds_at_signal=odds,
                model_probability=model_p,
                raw_EV=ev,
                calibrated_probability=None,
                calibrated_EV=None,
                result=result,
                pnl_units=_pnl(result, odds),
                opposite_odds=None,
                outcome_odds=outcome_odds,
                fair_probability=fair_p,
                fair_market_edge=(model_p - fair_p) if (model_p is not None and fair_p is not None) else None,
                odds_timestamp=r.get("created_at"),
                closing_odds=None,
                closing_odds_timestamp=None,
                clv=clv_info.get("clv"),
                sample_kind="historical_retrospective_seed",
                source="season2_bet_log_csv",
                notes=[
                    "Seeded from Season 2 settled/open log.",
                    "Closing odds unavailable — CLV cannot be measured for these rows.",
                    "Opposite-side odds unavailable — fair probability is null.",
                    "Not a live prospective signal.",
                ],
            )
            signal["fixture"] = r.get("fixture")
            if signal["portfolios"]:
                rows.append(signal)

    stats = upsert_signals(data_dir, rows)
    stats["seeded_with_portfolio"] = len(rows)
    stats["csv"] = str(csv_path)
    return stats
