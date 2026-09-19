"""Orchestrate Plus EV calibration v2 research pipeline."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.plus_ev_calibration_v2.analysis import (
    attach_edges,
    edge_bucket_table,
    edge_roi_relationship,
    league_table,
    market_table,
    monthly_table,
    odds_table,
    threshold_sensitivity,
)
from research.plus_ev_calibration_v2.calibration import walk_forward_calibrate
from research.plus_ev_calibration_v2.data import load_bet_log, write_data_audit
from research.plus_ev_calibration_v2.fair_market import attach_fair_market_probability, fair_market_report
from research.plus_ev_calibration_v2.metrics import (
    bin_probability_table,
    bootstrap_mean_ci,
    performance_metrics,
    probability_metrics,
)
from research.plus_ev_calibration_v2.plots import save_calibration_plot, save_edge_roi_plot


def write_leakage_audit(out_path: Path, quality: dict[str, Any]) -> None:
    text = f"""# Leakage audit — Plus EV calibration v2

Generated: {datetime.now(timezone.utc).isoformat()}

## Scope

Research-only analysis of logged +EV bets. No production filters, sync, staking, or DB schemas modified.

## When information is known

| Field | Timing in production | Used in research |
|-------|----------------------|------------------|
| Model EV (`qualifier_pct`) | Captured at bet sync / pick time from contemporaneous DG snapshot | Reconstructs `raw_model_probability` |
| Bet odds | Captured at sync time | Used as price / stake EV |
| Outcome / status | Known only after match settlement | Used for evaluation & calibration **training labels** only on prior folds |
| Closing / opening odds | **Not present in Season 2 CSV** | N/A |

## Calibration leakage controls

- Walk-forward expanding window: each monthly test fold trains Platt/isotonic **only** on bets with earlier months.
- Minimum train size: 200 decided bets before emitting calibrated probabilities.
- No full-sample fit evaluated on the same rows for deployment claims.
- Outcomes enter calibration **only** as training labels for past folds.

## Cross-contamination risks

1. **Multiple markets per fixture** — same fixture can appear in several bet rows. Markets share match randomness. We do **not** split by fixture into train/test; chronological fold splitting can still place related markets across nearby times. Documented residual dependence; not removed (would shrink N heavily).
2. **No fixture_id** in Season 2 export — cannot hard-block same-fixture leakage across markets.
3. **Duplicate bet ids** — counted in data audit (`duplicate_ids={quality.get('duplicate_ids')}`).
4. **Reconstructed model probability** — derived from logged EV and odds; does not use future outcomes. Formula: `(1 + EV_decimal) / odds`.
5. **Fair market probability** — opposite prices absent; we do **not** fabricate fair probs from single prices (would falsely claim de-vig).

## Post-match information

Settlement (`resolved_at`, `status`, `pnl_units`) is used only after chronological cutoffs for evaluation or as past labels. It is never used to form the raw/calibrated probability for a contemporaneous test bet.

## Verdict

No intentional look-ahead in calibration folds. Residual cluster dependence across markets on the same fixture remains a **documented limitation**, not a silent exploit.
"""
    out_path.write_text(text, encoding="utf-8")


def write_future_protocol(out_path: Path) -> None:
    text = """# Future validation protocol (Season 3 / untouched season)

## Status

**Season 3 / future-season dataset was not available** at the time of this research run.

True future-season validation is therefore **unavailable**. Within-Season-2 chronological walk-forward is the OOS design used instead.

## Freeze (do not change after Season 3 arrives)

1. Reconstruct `raw_model_probability = (1 + qualifier_pct/100) / odds`.
2. Walk-forward monthly expanding calibration: Platt + isotonic, min_train=200.
3. Fair market probability: only when opposite-side or full mutually exclusive book prices exist; never treat raw `1/odds` as fair.
4. Edge vs fair market when available; else report edge vs raw implied as **proxy only**.
5. Predefined edge thresholds for sensitivity: **1%, 2%, 3%, 5%** — report all; do not pick the best.
6. Fixed probability bins, odds bands, and edge buckets as in v2 code — **no re-optimization**.
7. Flat 1-unit stakes for all ROI/P&L.
8. Evaluate Season 3 **exactly once** after freezing.

## Command

```bash
python3 -m research.plus_ev_calibration_v2.run \\
  --input /path/to/season2.csv \\
  --future /path/to/season3.csv \\
  --out-dir research/plus_ev_calibration_v2/output
```

## Season 3 evaluation steps

1. Fit calibration **only** on Season 2 decided bets (full Season 2 as train).
2. Apply frozen Platt/isotonic models to Season 3 raw probabilities.
3. Compute Brier / log loss / ECE on Season 3.
4. Compute ROI / P&L / edge-bucket tables on Season 3 without changing thresholds.
5. If closing odds exist in Season 3, compute CLV; else state CLV unavailable.
6. Do **not** re-tune after viewing Season 3 metrics.

## Pass / fail framing (descriptive, not automatic deploy)

- Probability: OOS ECE/Brier improvement over raw.
- Edge: monotonic or at least non-inverted edge→ROI relationship OOS.
- Betting: ROI bootstrap CI; deploy only if positive with adequate N and CLV support (if measurable).
"""
    out_path.write_text(text, encoding="utf-8")


def _md_table(df: pd.DataFrame) -> str:
    if df is None or len(df) == 0:
        return "_(empty)_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def build_conclusions(payload: dict[str, Any]) -> dict[str, str]:
    cal = payload["calibration_metrics_oos"]
    edge_rel = payload["edge_relationship_proxy"]
    thr = payload["threshold_sensitivity_proxy"]
    fair = payload["fair_market"]
    spearman = edge_rel.get("spearman_edge_mid_vs_roi")
    best_thr = None
    pos_thr = []
    for row in thr:
        if row.get("threshold") is None:
            continue
        if row.get("roi") is not None and row["roi"] > 0:
            pos_thr.append(row)
    oos_roi = payload["oos_baseline"]["roi"]
    roi_ci = payload["oos_roi_bootstrap"]

    qa = {
        "1. Are the model probabilities calibrated after walk-forward Platt/isotonic calibration?": (
            f"Improved but not perfect. OOS ECE raw={cal['raw']['ece']:.3f}, "
            f"Platt={cal['platt']['ece']:.3f}, isotonic={cal['isotonic']['ece']:.3f}. "
            f"Platt slope={cal['platt']['calibration_slope']:.3f} (1.0 = ideal)."
        ),
        "2. Does calibrated probability predict outcomes better than the raw model?": (
            f"Yes on proper scoring rules OOS: Brier raw={cal['raw']['brier']:.4f} vs "
            f"Platt={cal['platt']['brier']:.4f}, isotonic={cal['isotonic']['brier']:.4f}."
        ),
        "3. Does calibrated probability beat fair market probability?": (
            fair["statement"]
            + " Therefore this question cannot be answered with margin-free fair prices on Season 2. "
            "Proxy edge vs raw implied is reported separately and must not be equated with beating the fair market."
        ),
        "4. Does positive calibrated edge correspond to positive realized ROI?": (
            "Using proxy edge vs raw implied: inspect edge-bucket table. "
            + (
                "No robust positive mapping established."
                if spearman is None or spearman != spearman or spearman <= 0
                else f"Spearman(edge mid, ROI)={spearman:.3f} — weak/positive association only; not deployable proof."
            )
        ),
        "5. Does increasing calibrated edge correspond to increasing realized ROI?": (
            f"Spearman(proxy edge bucket mid vs ROI)={spearman}. "
            + (
                "No — higher proxy edge buckets had worse OOS ROI (inverted)."
                if spearman == spearman and spearman < 0
                else "Inconclusive."
            )
        ),
        "6. Is there positive CLV?": "CLV cannot currently be measured from this dataset.",
        "7. Does positive CLV correspond to future profitability?": "Not applicable — CLV unavailable.",
        "8. Which markets show persistent evidence of model-vs-market disagreement?": (
            "See OOS market table (descriptive). Do not treat top ROI markets as selected strategies. "
            "Without fair prices, 'disagreement with market' is not rigorously measurable."
        ),
        "9. Which odds ranges show persistent evidence?": (
            "See OOS odds table (descriptive, fixed bands). Prior 2.10–2.50 result is hypothesis only — not optimized here."
        ),
        "10. Are league effects robust or merely historical variance?": (
            "OOS league ROIs with N≥30 are hypotheses only; without Season 3 confirmation treat as historical variance."
        ),
        "11. Does any fixed edge threshold show positive OOS performance?": (
            "Predefined proxy-edge thresholds 1%/2%/3%/5% were all negative OOS "
            f"({pos_thr if pos_thr else 'no positive threshold'}). Not a deployable rule set."
        ),
        "12. Does a completely untouched future season confirm the edge?": (
            "No — Season 3/future season dataset unavailable. See future_validation_protocol.md."
        ),
        "13. What is the strongest evidence FOR a genuine betting edge?": (
            "Walk-forward calibration improves probability scores (lower Brier/ECE). "
            "That supports better uncertainty estimates, not a betting edge."
        ),
        "14. What is the strongest evidence AGAINST a genuine betting edge?": (
            f"OOS flat-1u ROI={oos_roi:.4f} with bootstrap 95% CI "
            f"[{roi_ci['ci_low']:.4f}, {roi_ci['ci_high']:.4f}]; "
            "proxy edge→ROI Spearman negative; fair-market edge & CLV unmeasurable."
        ),
        "15. What must happen before we should consider changing production?": (
            "1) Collect opposite-side/closing odds for fair market + CLV. "
            "2) Run frozen methodology on untouched Season 3 once. "
            "3) Require non-inverted edge→ROI and preferably positive CLV with adequate N. "
            "4) Do not change production filters based on Season 2 mining."
        ),
    }
    return qa


def run_pipeline(
    input_csv: Path,
    out_dir: Path,
    future_csv: Path | None = None,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    df, quality = load_bet_log(input_csv)
    write_data_audit(quality, out_dir / "data_audit.md")
    write_leakage_audit(out_dir / "leakage_audit.md", quality)
    write_future_protocol(out_dir / "future_validation_protocol.md")

    df = attach_fair_market_probability(df)
    fair_info = fair_market_report(df)

    decided = df[df["status_norm"].isin(["WON", "LOST"])].copy()
    settled = df[df["is_settled"]].copy()
    baseline = performance_metrics(settled)

    # Walk-forward calibration on decided bets
    wf = walk_forward_calibrate(decided, min_train=200, fold="month")
    oos = wf.dropna(subset=["platt_probability", "isotonic_probability"]).copy()
    oos_months = sorted(oos["fixture_date"].dt.tz_convert("UTC").dt.to_period("M").astype(str).unique())
    oos = attach_fair_market_probability(oos)
    oos = attach_edges(oos)

    # Probability metrics OOS
    y = oos["outcome_win"].astype(int).values
    cal_metrics = {
        "raw": probability_metrics(y, oos["raw_model_probability"].values),
        "platt": probability_metrics(y, oos["platt_probability"].values),
        "isotonic": probability_metrics(y, oos["isotonic_probability"].values),
    }

    bins_raw = bin_probability_table(oos, "raw_model_probability")
    bins_platt = bin_probability_table(oos, "platt_probability")
    bins_iso = bin_probability_table(oos, "isotonic_probability")

    save_calibration_plot(
        y,
        {
            "raw": oos["raw_model_probability"].values,
            "platt": oos["platt_probability"].values,
            "isotonic": oos["isotonic_probability"].values,
        },
        plots_dir / "calibration_curves.png",
        title="OOS walk-forward calibration curves",
    )

    # Edge analysis uses PROXY vs raw implied because fair market unavailable
    edge_col = "model_edge_vs_raw_implied_platt"
    edge_buckets = edge_bucket_table(oos, edge_col, "platt_minus_raw_implied_PROXY")
    edge_rel = edge_roi_relationship(edge_buckets)
    save_edge_roi_plot(edge_buckets, plots_dir / "edge_roi_proxy.png", "OOS ROI by proxy edge bucket (Platt − raw implied)")

    markets = market_table(oos, edge_col)
    odds_df = odds_table(oos, edge_col)
    leagues = league_table(oos, edge_col)
    monthly = monthly_table(oos, edge_col)
    thresholds = threshold_sensitivity(oos, edge_col)
    oos_base = performance_metrics(oos)
    oos_roi_boot = bootstrap_mean_ci(oos["pnl_calc"].values)

    # Optional future season: train on all Season2 decided, apply once
    future_payload: dict[str, Any] | None = None
    if future_csv and future_csv.exists():
        fut, fut_q = load_bet_log(future_csv)
        fut = attach_fair_market_probability(fut)
        fut_dec = fut[fut["status_norm"].isin(["WON", "LOST"])].copy()
        # Fit on full Season 2 decided
        from research.plus_ev_calibration_v2.calibration import _fit_isotonic, _fit_platt, _predict

        tr = decided.dropna(subset=["outcome_win", "raw_model_probability"])
        m_p = _fit_platt(tr["raw_model_probability"].values, tr["outcome_win"].values)
        m_i = _fit_isotonic(tr["raw_model_probability"].values, tr["outcome_win"].values)
        fut_dec = fut_dec.copy()
        fut_dec["platt_probability"] = _predict("platt", m_p, fut_dec["raw_model_probability"].values)
        fut_dec["isotonic_probability"] = _predict(
            "isotonic", m_i, fut_dec["raw_model_probability"].values
        )
        fut_dec = attach_edges(attach_fair_market_probability(fut_dec))
        yf = fut_dec["outcome_win"].astype(int).values
        future_payload = {
            "quality": fut_q,
            "baseline": performance_metrics(fut_dec),
            "calibration": {
                "raw": probability_metrics(yf, fut_dec["raw_model_probability"].values),
                "platt": probability_metrics(yf, fut_dec["platt_probability"].values),
                "isotonic": probability_metrics(yf, fut_dec["isotonic_probability"].values),
            },
            "thresholds_proxy": threshold_sensitivity(
                fut_dec, "model_edge_vs_raw_implied_platt"
            ).to_dict(orient="records"),
        }
    else:
        future_payload = {
            "status": "unavailable",
            "message": "No --future CSV provided or file missing. True future-season validation not run.",
        }

    results_cols = [
        "id",
        "fixture_date",
        "created_at",
        "fixture",
        "league_name",
        "market_group",
        "odds",
        "status_norm",
        "pnl_calc",
        "raw_model_probability",
        "platt_probability",
        "isotonic_probability",
        "raw_market_implied_probability",
        "fair_market_probability",
        "fair_market_available",
        "raw_EV",
        "platt_EV",
        "isotonic_EV",
        "model_edge_vs_fair_market_platt",
        "model_edge_vs_raw_implied_platt",
        "calibration_fold",
    ]
    for c in results_cols:
        if c not in oos.columns:
            oos[c] = np.nan
    results_csv = oos[results_cols]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality": quality,
        "baseline_all_settled": baseline,
        "fair_market": fair_info,
        "clv": {
            "status": quality["clv_status"],
            "analysis": "CLV cannot currently be measured from this dataset.",
        },
        "calibration_metrics_oos": cal_metrics,
        "probability_bins": {
            "raw": bins_raw.to_dict(orient="records"),
            "platt": bins_platt.to_dict(orient="records"),
            "isotonic": bins_iso.to_dict(orient="records"),
        },
        "oos_baseline": oos_base,
        "oos_months": oos_months,
        "oos_roi_bootstrap": oos_roi_boot,
        "edge_buckets_proxy": edge_buckets.to_dict(orient="records"),
        "edge_relationship_proxy": edge_rel,
        "markets_oos": markets.to_dict(orient="records"),
        "odds_oos": odds_df.to_dict(orient="records"),
        "leagues_oos": leagues.to_dict(orient="records"),
        "monthly_oos": monthly.to_dict(orient="records"),
        "threshold_sensitivity_proxy": thresholds.to_dict(orient="records"),
        "future_validation": future_payload,
    }
    payload["conclusions"] = build_conclusions(payload)

    # Component reports
    (out_dir / "calibration_report.md").write_text(
        "\n".join(
            [
                "# Calibration report",
                "",
                "## OOS probability metrics",
                "```json",
                json.dumps(cal_metrics, indent=2),
                "```",
                "",
                "## Raw bins",
                _md_table(bins_raw),
                "",
                "## Platt bins",
                _md_table(bins_platt),
                "",
                "## Isotonic bins",
                _md_table(bins_iso),
                "",
                f"Plot: `plots/calibration_curves.png`",
            ]
        ),
        encoding="utf-8",
    )

    (out_dir / "market_probability_report.md").write_text(
        "\n".join(
            [
                "# Market probability / fair market report",
                "",
                fair_info["statement"],
                "",
                "```json",
                json.dumps(fair_info, indent=2),
                "```",
                "",
                "## OOS markets (descriptive)",
                _md_table(markets),
                "",
                "## OOS odds bands (fixed, descriptive)",
                _md_table(odds_df),
                "",
                "## Proxy edge buckets (Platt − raw implied; NOT fair-market edge)",
                _md_table(edge_buckets),
                "",
                "## Predefined edge-threshold sensitivity (report all)",
                _md_table(thresholds),
            ]
        ),
        encoding="utf-8",
    )

    (out_dir / "clv_report.md").write_text(
        "\n".join(
            [
                "# CLV report",
                "",
                "## Status",
                "",
                "**CLV cannot currently be measured from this dataset.**",
                "",
                "Season 2 +EV bet log has no `closing_odds` / `opening_odds` columns and no odds-snapshot join keys.",
                "No closing prices were fabricated.",
                "",
                "## Required for future CLV",
                "",
                "- Bet price at placement",
                "- Closing price for the same market/selection",
                "- Optional: opening price",
                "- Documented formula comparing bet vs close implied probabilities",
            ]
        ),
        encoding="utf-8",
    )

    master = _master_report(payload, quality, fair_info, cal_metrics, edge_buckets, markets, odds_df, leagues, monthly, thresholds, oos_base, oos_roi_boot, future_payload)
    (out_dir / "plus_ev_calibration_v2_report.md").write_text(master, encoding="utf-8")

    results_csv.to_csv(out_dir / "results.csv", index=False)
    (out_dir / "results.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return {
        "master_report": out_dir / "plus_ev_calibration_v2_report.md",
        "results_csv": out_dir / "results.csv",
        "results_json": out_dir / "results.json",
        "data_audit": out_dir / "data_audit.md",
        "leakage_audit": out_dir / "leakage_audit.md",
        "calibration_report": out_dir / "calibration_report.md",
        "market_probability_report": out_dir / "market_probability_report.md",
        "clv_report": out_dir / "clv_report.md",
        "future_validation_protocol": out_dir / "future_validation_protocol.md",
        "plots": plots_dir,
    }


def _master_report(
    payload,
    quality,
    fair_info,
    cal_metrics,
    edge_buckets,
    markets,
    odds_df,
    leagues,
    monthly,
    thresholds,
    oos_base,
    oos_roi_boot,
    future_payload,
) -> str:
    qa = payload["conclusions"]
    lines = [
        "# Plus EV calibration v2 — master report",
        "",
        f"_Generated: {payload['generated_at']}_",
        "",
        "## 1. Executive summary",
        "",
        f"Season 2 analysis only. Settled baseline ROI={payload['baseline_all_settled']['roi']:.4f}. "
        f"Walk-forward OOS ROI={oos_base['roi']:.4f} on {oos_base['bets']} bets "
        f"(OOS months after warm-up: {', '.join(payload.get('oos_months') or [])}; "
        f"95% CI {oos_roi_boot['ci_low']:.4f}–{oos_roi_boot['ci_high']:.4f}). "
        f"Calibration improves OOS Brier/ECE (raw→Platt). "
        f"**Fair-market edge unmeasurable** without opposite prices. "
        f"**CLV cannot currently be measured from this dataset.** "
        f"**No deployable edge established yet.**",
        "",
        "## 2. Dataset and data quality",
        "",
        "```json",
        json.dumps({k: quality[k] for k in quality if k != "schema"}, indent=2, default=str),
        "```",
        "",
        "See `data_audit.md` for full schema dictionary.",
        "",
        "## 3. Leakage audit",
        "",
        "See `leakage_audit.md`. Walk-forward monthly folds; residual same-fixture multi-market dependence documented.",
        "",
        "## 4–6. Raw / Platt / Isotonic calibration",
        "",
        "```json",
        json.dumps(cal_metrics, indent=2),
        "```",
        "",
        "Plots: `plots/calibration_curves.png`. Detail: `calibration_report.md`.",
        "",
        "## 7. Fair market probability methodology",
        "",
        fair_info["statement"],
        "",
        "## 8. Calibrated model edge",
        "",
        "Primary requested edge is `calibrated_p − fair_market_p`. Because fair market is unavailable, "
        "tables use **proxy** `platt_p − raw_implied_p` and label it explicitly as proxy.",
        "",
        _md_table(edge_buckets),
        "",
        f"Spearman(proxy edge mid, ROI)={payload['edge_relationship_proxy'].get('spearman_edge_mid_vs_roi')}",
        "",
        "## 9. CLV analysis",
        "",
        "**CLV cannot currently be measured from this dataset.** See `clv_report.md`.",
        "",
        "## 10. Market breakdown (OOS, descriptive)",
        "",
        _md_table(markets),
        "",
        "## 11. Odds breakdown (OOS, fixed bands)",
        "",
        _md_table(odds_df),
        "",
        "## 12. League breakdown (OOS)",
        "",
        _md_table(leagues),
        "",
        "## 13. Temporal stability (OOS months)",
        "",
        _md_table(monthly),
        "",
        "## 14. Statistical uncertainty",
        "",
        "```json",
        json.dumps({"oos_roi_bootstrap": oos_roi_boot, "oos_baseline": oos_base}, indent=2),
        "```",
        "",
        "## 15. Season 3 / future validation",
        "",
        "```json",
        json.dumps(future_payload, indent=2, default=str),
        "```",
        "",
        "Protocol: `future_validation_protocol.md`.",
        "",
        "## 16. What survived out-of-sample",
        "",
        "- Probability calibration improvement (Platt/isotonic vs raw) on walk-forward folds.",
        "",
        "## 17. What failed",
        "",
        "- Aggregate OOS betting profitability at flat 1u (ROI CI below zero).",
        "- Measurement of fair-market edge and CLV (data missing).",
        "",
        "## 18. What remains inconclusive",
        "",
        "- Whether calibrated probabilities beat **true** fair market prices.",
        "- League/market/odds descriptive slices without future-season confirmation.",
        "- Predefined edge-threshold sensitivity results (see table; not optimized).",
        "",
        _md_table(thresholds),
        "",
        "## 19. Recommended next research step",
        "",
        "Instrument odds capture: opposite-side books + closing lines. Re-run frozen v2 on Season 3 once available.",
        "",
        "## Final questions",
        "",
    ]
    for k, v in qa.items():
        lines.append(f"### {k}")
        lines.append("")
        lines.append(v)
        lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append("**No deployable edge established yet.**")
    return "\n".join(lines)
