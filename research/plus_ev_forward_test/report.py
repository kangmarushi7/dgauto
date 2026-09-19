"""Forward-test metrics, plots, and reports for the four fixed portfolios."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research.plus_ev_forward_test.clv import summarize_clv
from research.plus_ev_forward_test.portfolios import PORTFOLIOS
from research.plus_ev_forward_test.status import classify_portfolio, sample_milestone
from research.plus_ev_forward_test.storage import DEFAULT_DATA_DIR, load_signals

DEFAULT_OUT = Path("research/plus_ev_forward_test/output")
ROLLING_WINDOWS = (50, 100, 250, 500)
RNG = np.random.default_rng(42)


def _signals_frame(signals: list[dict[str, Any]]) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    df = pd.DataFrame(signals)
    # explode portfolios
    rows = []
    for _, r in df.iterrows():
        ports = r.get("portfolios") or []
        if isinstance(ports, str):
            ports = json.loads(ports)
        if not ports:
            continue
        for p in ports:
            row = r.to_dict()
            row["portfolio_id"] = p
            rows.append(row)
    return pd.DataFrame(rows)


def _perf(sub: pd.DataFrame) -> dict[str, Any]:
    if sub is None or len(sub) == 0:
        return {"n": 0, "bets": 0}
    settled = sub[sub["result"].isin(["won", "lost", "push"])].copy()
    decided = sub[sub["result"].isin(["won", "lost"])].copy()
    wins = int((settled["result"] == "won").sum())
    losses = int((settled["result"] == "lost").sum())
    pushes = int((settled["result"] == "push").sum())
    open_n = int((sub["result"] == "open").sum()) if "result" in sub else 0
    if "pnl_units" in settled.columns:
        pnl = pd.to_numeric(settled["pnl_units"], errors="coerce").fillna(0.0)
    else:
        pnl = pd.Series([0.0] * len(settled))
    total_pnl = float(pnl.sum())
    stake = float(len(settled)) if len(settled) else 0.0
    roi = total_pnl / stake if stake else None
    cum = pnl.cumsum()
    dd = float((cum - cum.cummax()).min()) if len(pnl) else 0.0
    odds = pd.to_numeric(settled.get("odds_at_signal"), errors="coerce")
    clv_vals = pd.to_numeric(settled.get("clv"), errors="coerce").dropna().tolist()
    clv_sum = summarize_clv(clv_vals)
    fair_edge = pd.to_numeric(settled.get("fair_market_edge"), errors="coerce")
    return {
        "n": int(len(settled)),
        "bets": int(len(settled)),
        "open": open_n,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": wins / (wins + losses) if (wins + losses) else None,
        "average_odds": float(odds.mean()) if len(odds.dropna()) else None,
        "total_stake": stake,
        "total_pnl": total_pnl,
        "roi": roi,
        "max_drawdown": dd,
        "avg_model_probability": float(pd.to_numeric(settled.get("model_probability"), errors="coerce").mean())
        if len(settled)
        else None,
        "avg_calibrated_probability": float(
            pd.to_numeric(settled.get("calibrated_probability"), errors="coerce").mean()
        )
        if len(settled)
        else None,
        "avg_raw_EV": float(pd.to_numeric(settled.get("raw_EV"), errors="coerce").mean())
        if len(settled)
        else None,
        "avg_calibrated_EV": float(pd.to_numeric(settled.get("calibrated_EV"), errors="coerce").mean())
        if len(settled)
        else None,
        "avg_fair_market_edge": float(fair_edge.mean()) if fair_edge.notna().any() else None,
        "mean_clv": clv_sum.get("mean_clv"),
        "median_clv": clv_sum.get("median_clv"),
        "pct_positive_clv": clv_sum.get("pct_positive_clv"),
        "clv_n": clv_sum.get("n", 0),
    }


def _bootstrap_roi_ci(pnl: np.ndarray, n_boot: int = 2000) -> dict[str, float | None]:
    pnl = np.asarray(pnl, dtype=float)
    pnl = pnl[~np.isnan(pnl)]
    if len(pnl) < 20:
        return {"ci_low": None, "ci_high": None, "mean": float(pnl.mean()) if len(pnl) else None}
    samples = [float(RNG.choice(pnl, size=len(pnl), replace=True).mean()) for _ in range(n_boot)]
    return {
        "mean": float(np.mean(samples)),
        "ci_low": float(np.percentile(samples, 2.5)),
        "ci_high": float(np.percentile(samples, 97.5)),
    }


def _rolling(sub: pd.DataFrame) -> dict[str, Any]:
    settled = sub[sub["result"].isin(["won", "lost", "push"])].copy()
    if settled.empty:
        return {}
    settled = settled.sort_values("kickoff_time")
    pnl = pd.to_numeric(settled["pnl_units"], errors="coerce").fillna(0.0).values
    clv = pd.to_numeric(settled["clv"], errors="coerce").values
    won = (settled["result"] == "won").astype(float).values
    out: dict[str, Any] = {}
    for w in ROLLING_WINDOWS:
        if len(pnl) < w:
            out[f"rolling_{w}"] = {"available": False, "n": len(pnl)}
            continue
        window = settled.iloc[-w:]
        decided_w = window[window["result"].isin(["won", "lost"])]
        out[f"rolling_{w}"] = {
            "available": True,
            "roi": float(pnl[-w:].mean()),
            "win_rate": float((decided_w["result"] == "won").mean()) if len(decided_w) else None,
            "mean_clv": float(np.nanmean(clv[-w:])) if np.isfinite(clv[-w:]).any() else None,
        }
    return out


def _monthly(sub: pd.DataFrame) -> list[dict[str, Any]]:
    settled = sub[sub["result"].isin(["won", "lost", "push"])].copy()
    if settled.empty:
        return []
    settled["kickoff_time"] = pd.to_datetime(settled["kickoff_time"], utc=True, errors="coerce")
    settled["month"] = settled["kickoff_time"].dt.to_period("M").astype(str)
    rows = []
    for month, g in settled.groupby("month"):
        m = _perf(g)
        rows.append({"month": month, **m})
    return rows


def generate_report(data_dir: Path = DEFAULT_DATA_DIR, out_dir: Path = DEFAULT_OUT) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plots = out_dir / "plots"
    plots.mkdir(exist_ok=True)

    signals = load_signals(data_dir)
    df = _signals_frame(signals)

    portfolio_payload: dict[str, Any] = {}
    for pid, meta in PORTFOLIOS.items():
        sub = df[df["portfolio_id"] == pid] if len(df) else pd.DataFrame()
        metrics = _perf(sub)
        settled = sub[sub["result"].isin(["won", "lost", "push"])] if len(sub) else pd.DataFrame()
        pnl = pd.to_numeric(settled["pnl_units"], errors="coerce").fillna(0.0).values if len(settled) else np.array([])
        ci = _bootstrap_roi_ci(pnl)
        metrics["roi_bootstrap"] = ci
        metrics["status"] = classify_portfolio(metrics)
        metrics["sample_milestone"] = sample_milestone(int(metrics.get("n") or 0))
        metrics["rolling"] = _rolling(sub) if len(sub) else {}
        metrics["monthly"] = _monthly(sub) if len(sub) else []
        metrics["meta"] = meta
        # sample composition
        if len(sub):
            metrics["live_forward_n"] = int((sub["sample_kind"] == "live_forward").sum())
            metrics["historical_seed_n"] = int((sub["sample_kind"] == "historical_retrospective_seed").sum())
        else:
            metrics["live_forward_n"] = 0
            metrics["historical_seed_n"] = 0
        portfolio_payload[pid] = metrics

        # plots
        if len(settled):
            settled_sorted = settled.sort_values("kickoff_time")
            pnl_s = pd.to_numeric(settled_sorted["pnl_units"], errors="coerce").fillna(0.0)
            cum = pnl_s.cumsum()
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(range(len(cum)), cum.values, color="#2f5d50")
            ax.set_title(f"{meta['label']} — cumulative P&L")
            ax.set_xlabel("Settled bet #")
            ax.set_ylabel("Units")
            ax.axhline(0, color="black", lw=0.8)
            fig.tight_layout()
            fig.savefig(plots / f"{pid}_cum_pnl.png", dpi=130)
            plt.close(fig)

            if settled_sorted["clv"].notna().any():
                clv_cum = pd.to_numeric(settled_sorted["clv"], errors="coerce").fillna(0).cumsum()
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.plot(range(len(clv_cum)), clv_cum.values, color="#6b4f2a")
                ax.set_title(f"{meta['label']} — cumulative CLV (prob points)")
                fig.tight_layout()
                fig.savefig(plots / f"{pid}_cum_clv.png", dpi=130)
                plt.close(fig)

    # Comparison answers
    answers = _comparison_answers(portfolio_payload)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "n_signals_total": len(signals),
        "portfolios": portfolio_payload,
        "comparison_answers": answers,
        "clv_global_note": (
            "CLV requires closing_odds. Historical Season 2 seed rows have null closing odds. "
            "Live forward collector captures latest pre-kickoff odds going forward."
        ),
    }

    # CSV flat export
    if len(df):
        df.to_csv(out_dir / "results.csv", index=False)
    else:
        (out_dir / "results.csv").write_text("", encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    report_md = _render_markdown(payload)
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")

    return {
        "report": out_dir / "report.md",
        "results_csv": out_dir / "results.csv",
        "results_json": out_dir / "results.json",
        "plots": plots,
    }


def _comparison_answers(portfolios: dict[str, Any]) -> dict[str, Any]:
    pos_clv = []
    pos_roi = []
    both = []
    meaningful = []
    inconclusive = []
    for pid, m in portfolios.items():
        label = m["meta"]["label"]
        if m.get("mean_clv") is not None and m.get("clv_n", 0) >= 20 and m["mean_clv"] > 0:
            pos_clv.append(label)
        if m.get("roi") is not None and m["roi"] > 0 and m.get("n", 0) > 0:
            pos_roi.append(label)
        if (
            m.get("roi") is not None
            and m["roi"] > 0
            and m.get("mean_clv") is not None
            and m.get("clv_n", 0) >= 20
            and m["mean_clv"] > 0
        ):
            both.append(label)
        if m.get("n", 0) >= 100:
            meaningful.append(label)
        if m.get("status") in {"INSUFFICIENT SAMPLE", "MIXED", "PROMISING — NEEDS MORE DATA"}:
            inconclusive.append(label)

    return {
        "1_positive_clv": pos_clv or ["none (or CLV unavailable)"],
        "2_positive_roi": pos_roi or ["none"],
        "3_positive_clv_and_roi": both or ["none"],
        "4_enough_sample_meaningful": meaningful or ["none yet (≥100 settled)"],
        "5_inconclusive": inconclusive,
        "6_evidence_better_prices_than_market": (
            "Insufficient — closing odds not available on historical seed; "
            "await live forward CLV accumulation."
            if not pos_clv
            else f"Portfolios with positive mean CLV (n_clv≥20): {pos_clv}"
        ),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Plus EV forward-test report",
        "",
        f"_Generated: {payload['generated_at']}_",
        "",
        "**research_only = true** — no real bets placed by this module.",
        "",
        payload["clv_global_note"],
        "",
        f"Total signals in ledger: **{payload['n_signals_total']}**",
        "",
        "## Portfolio comparison (independent hypotheses)",
        "",
    ]
    for pid, m in payload["portfolios"].items():
        meta = m["meta"]
        lines.extend(
            [
                f"### {meta['label']}",
                "",
                f"- Hypothesis: {meta['hypothesis']}",
                f"- Status: **{m.get('status')}**",
                f"- Sample milestone: {m.get('sample_milestone')}",
                f"- N settled: **{m.get('n')}** (historical seed {m.get('historical_seed_n')}, live {m.get('live_forward_n')})",
                f"- W/L/P: {m.get('wins')}/{m.get('losses')}/{m.get('pushes')}",
                f"- Win rate: {m.get('win_rate')}",
                f"- Avg odds: {m.get('average_odds')}",
                f"- P&L: {m.get('total_pnl')}u · ROI: {m.get('roi')}",
                f"- Max drawdown: {m.get('max_drawdown')}",
                f"- Avg model p / raw EV: {m.get('avg_model_probability')} / {m.get('avg_raw_EV')}",
                f"- Avg calibrated p / EV: {m.get('avg_calibrated_probability')} / {m.get('avg_calibrated_EV')}",
                f"- Avg fair-market edge: {m.get('avg_fair_market_edge')}",
                f"- Mean/median CLV: {m.get('mean_clv')} / {m.get('median_clv')} (n={m.get('clv_n')}, pct+: {m.get('pct_positive_clv')})",
                f"- ROI bootstrap 95% CI: {m.get('roi_bootstrap')}",
                "",
            ]
        )
    lines.append("## Comparison answers")
    lines.append("")
    for k, v in payload["comparison_answers"].items():
        lines.append(f"- **{k}**: {v}")
    lines.extend(
        [
            "",
            "## Rules reminder",
            "",
            "- Portfolios are FIXED. Do not combine or retune after seeing results.",
            "- Do not declare proven profitable from small N.",
            "- Positive CLV with negative ROI is still informative — report separately.",
            "",
        ]
    )
    return "\n".join(lines)
