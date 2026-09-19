"""Write Markdown + JSON OOS reports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_OUT = Path(__file__).resolve().parent / "output"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


def _pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{100.0 * x:.2f}%"


def _num(x: float | None, digits: int = 3) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def render_markdown(payload: dict[str, Any]) -> str:
    cfg = payload["frozen_config"]
    main = payload["main_result_logged_stake"]
    flat = payload["main_result_flat_1u"]
    lw = payload["league_whitelist_status"]
    lines: list[str] = []
    lines.append("# Arahus O2.5 OOS Validation")
    lines.append("")
    lines.append(f"_Generated: {payload['generated_at']}_")
    lines.append("")
    lines.append("**research_only = true** · **can_place_real_bet = false**")
    lines.append("")
    lines.append("## Frozen configuration")
    lines.append("")
    lines.append(f"- Candidate: `{cfg['candidate_id']}`")
    lines.append(f"- Market: Over 2.5 only (`{cfg['market']}`)")
    lines.append(f"- Odds range: {cfg['odds_min']} ≤ odds ≤ {cfg['odds_max']} (inclusive, no rounding)")
    lines.append(f"- League whitelist: **undefined in repo** — no league filter applied")
    lines.append(f"- BTTS: {cfg['btts']} · Over 3.5: {cfg['over_3_5']}")
    lines.append("- Confidence rule: **not used as a gate** (descriptive bands only)")
    lines.append("- Stake rule (primary): logged `units` from Arahus log; also flat 1.0u normalized")
    lines.append(f"- Development period: {payload['periods']['development']}")
    lines.append(f"- OOS period: {payload['periods']['oos']}")
    lines.append(f"- Data source: `{payload['data_source']}`")
    lines.append("")
    lines.append("### League whitelist ambiguity")
    lines.append("")
    lines.append(lw["ambiguity"])
    lines.append("")
    lines.append("Sources checked: " + ", ".join(f"`{s}`" for s in lw["sources_checked"]))
    lines.append("")
    lines.append("## Push / PnL convention")
    lines.append("")
    lines.append("- Won: `(odds − 1) × units`")
    lines.append("- Lost: `−units`")
    lines.append("- Push: PnL = 0; stake **included** in total staked")
    lines.append("- Open bets: excluded from settled ROI")
    lines.append("")
    lines.append("## Main result (OOS, logged stake)")
    lines.append("")
    lines.append("| Metric | OOS |")
    lines.append("|--------|-----|")
    lines.append(f"| Bets | {main['n']} ({main['sample_label']}) |")
    lines.append(f"| W-L-P | {main['won']}-{main['lost']}-{main['push']} |")
    lines.append(f"| Win% | {_pct(main['win_pct'])} |")
    lines.append(f"| Avg Odds | {_num(main['avg_odds'], 3)} |")
    lines.append(f"| Median Odds | {_num(main['median_odds'], 3)} |")
    lines.append(f"| Staked | {_num(main['staked'], 3)} |")
    lines.append(f"| PnL | {_num(main['pnl'], 3)} |")
    lines.append(f"| ROI | {_pct(main['roi'])} |")
    lines.append(f"| Avg PnL / bet | {_num(main['avg_pnl_per_bet'], 4)} |")
    lines.append(f"| Max Drawdown (u) | {_num(main['max_dd_units'], 3)} |")
    lines.append(f"| Max Drawdown % | {_pct(main['max_dd_pct'])} |")
    lines.append(f"| Longest Losing Streak | {main['longest_losing_streak']} |")
    lines.append(f"| Longest Winning Streak | {main['longest_winning_streak']} |")
    lines.append(f"| Worst loss / Best win | {_num(main['worst_single_loss'], 3)} / {_num(main['best_single_win'], 3)} |")
    lines.append(f"| Profit Factor | {_num(main['profit_factor'], 3)} |")
    lines.append(f"| Std (per-bet PnL) | {_num(main['std_per_bet_return'], 4)} |")
    lines.append(
        f"| Sharpe-like (mean/std, not annualized) | {_num(main['sharpe_like_per_bet'], 3)} |"
    )
    br = main.get("bootstrap_roi_portfolio") or {}
    lines.append(
        f"| Bootstrap 95% CI ROI | [{_pct(br.get('ci_low'))}, {_pct(br.get('ci_high'))}] "
        f"(seed={br.get('seed')}, n_boot={br.get('n_boot')}) |"
    )
    bm = main.get("bootstrap_mean_pnl_per_bet") or {}
    lines.append(
        f"| Bootstrap 95% CI mean PnL/bet | [{_num(bm.get('ci_low'), 4)}, {_num(bm.get('ci_high'), 4)}] |"
    )
    lines.append("")
    lines.append("### Flat 1.0u normalized (same OOS bets)")
    lines.append("")
    lines.append(
        f"N={flat['n']} · PnL={_num(flat['pnl'], 3)} · ROI={_pct(flat['roi'])} · "
        f"MaxDD={_num(flat['max_dd_units'], 3)}"
    )
    lines.append("")
    lines.append("## Baseline comparison (same OOS window)")
    lines.append("")
    lines.append("| Strategy | Bets | Win% | Avg Odds | Staked | PnL | ROI | Max DD |")
    lines.append("|----------|------|------|----------|--------|-----|-----|--------|")
    for row in payload["baseline_comparison"]:
        lines.append(
            f"| {row['strategy']} | {row.get('n')} | {_pct(row.get('win_pct'))} | "
            f"{_num(row.get('avg_odds'), 3)} | {_num(row.get('staked'), 2)} | "
            f"{_num(row.get('pnl'), 3)} | {_pct(row.get('roi'))} | {_num(row.get('max_dd_units'), 3)} |"
        )
    lines.append("")
    lines.append(
        "Note: Strategies B and C are identical because no league whitelist is defined in the repository."
    )
    lines.append("")
    lines.append("## League results (OOS candidate)")
    lines.append("")
    lines.append("| League | Bets | W-L-P | Win% | Avg Odds | Staked | PnL | ROI | Max DD | Sample |")
    lines.append("|--------|------|-------|------|----------|--------|-----|-----|--------|--------|")
    for row in payload["league_breakdown_oos_candidate"]:
        lines.append(
            f"| {row['league']} | {row['bets']} | {row['w_l_p']} | {_pct(row['win_pct'])} | "
            f"{_num(row['avg_odds'], 3)} | {_num(row['staked'], 2)} | {_num(row['pnl'], 3)} | "
            f"{_pct(row['roi'])} | {_num(row['max_dd'], 3)} | {row['sample_label']} |"
        )
    lines.append("")
    lines.append("### Non-selected leagues")
    lines.append("")
    lines.append(payload["non_selected_leagues"]["reason"])
    lines.append("")
    lines.append("## Odds-band breakdown (analysis only — do not retune)")
    lines.append("")
    lines.append("| Band | Bets | W-L-P | Win% | PnL | ROI |")
    lines.append("|------|------|-------|------|-----|-----|")
    for row in payload["odds_band_breakdown_oos"]:
        lines.append(
            f"| {row['band']} | {row['bets']} | {row['w_l_p']} | {_pct(row['win_pct'])} | "
            f"{_num(row['pnl'], 3)} | {_pct(row['roi'])} |"
        )
    lines.append("")
    lines.append("## Confidence-band breakdown (analysis only — do not retune)")
    lines.append("")
    lines.append("| Band | Bets | W-L-P | Win% | PnL | ROI |")
    lines.append("|------|------|-------|------|-----|-----|")
    for row in payload["confidence_band_breakdown_oos"]:
        lines.append(
            f"| {row['band']} | {row['bets']} | {row['w_l_p']} | {_pct(row['win_pct'])} | "
            f"{_num(row['pnl'], 3)} | {_pct(row['roi'])} |"
        )
    lines.append("")
    lines.append("## Time-series stability")
    lines.append("")
    lines.append("### By week")
    lines.append("")
    lines.append("| Week | Bets | Win% | PnL | ROI |")
    lines.append("|------|------|------|-----|-----|")
    for row in payload["weekly_oos"]:
        lines.append(
            f"| {row['week']} | {row['bets']} | {_pct(row['win_pct'])} | "
            f"{_num(row['pnl'], 3)} | {_pct(row['roi'])} |"
        )
    lines.append("")
    r25 = payload.get("rolling_25") or []
    r50 = payload.get("rolling_50") or []
    if r25:
        last25 = r25[-1]
        lines.append(
            f"Rolling 25 (last window ending {last25.get('end_date')}): "
            f"ROI={_pct(last25.get('roi'))}, PnL={_num(last25.get('cumulative_pnl'), 3)}, "
            f"Win%={_pct(last25.get('win_pct'))} · windows={len(r25)}"
        )
    else:
        lines.append("Rolling 25: insufficient bets.")
    lines.append("")
    if r50:
        last50 = r50[-1]
        lines.append(
            f"Rolling 50 (last window ending {last50.get('end_date')}): "
            f"ROI={_pct(last50.get('roi'))}, PnL={_num(last50.get('cumulative_pnl'), 3)}, "
            f"Win%={_pct(last50.get('win_pct'))} · windows={len(r50)}"
        )
    else:
        lines.append("Rolling 50: insufficient bets.")
    lines.append("")
    lines.append("## CLV")
    lines.append("")
    lines.append(payload["clv"].get("message") or json.dumps(payload["clv"]))
    lines.append("")
    lines.append("## Reconciliation vs full-log summary")
    lines.append("")
    rec = payload["reconciliation"]
    lines.append("| | Existing-style | Calculated |")
    lines.append("|-|----------------|------------|")
    es = rec["existing_style_summary"]
    calc = rec["calculated"]
    lines.append(f"| Bets | {es['bets']} | settled {calc['settled_bets']} (open {es['open']}) |")
    lines.append(f"| Won | {es['won']} | {calc['won']} |")
    lines.append(f"| Lost | {es['lost']} | {calc['lost']} |")
    lines.append(f"| Push | {es['push']} | {calc['push']} |")
    lines.append(f"| PnL | logged {_num(es['pnl_logged_sum'], 3)} | recomputed {_num(calc['pnl_recomputed_from_odds_units'], 3)} |")
    lines.append(f"| Match | | {rec['match_logged_vs_recomputed']} (delta={rec['delta']}) |")
    lines.append("")
    lines.append("## Data-quality issues")
    lines.append("")
    for issue in payload["integrity"]["issues"]:
        lines.append(
            f"- **{issue['type']}**: count={issue.get('count')} — {issue.get('action')}"
        )
    lines.append("")
    lines.append("## Leakage audit")
    lines.append("")
    la = payload["leakage_audit"]
    lines.append(la["verdict"])
    lines.append("")
    for lim in la["residual_limitations"]:
        lines.append(f"- {lim}")
    lines.append("")
    lines.append("## Future sample size (rough)")
    lines.append("")
    fs = payload["future_sample_size"]
    lines.append(
        f"N required for SE≈{fs.get('target_se')} on mean per-bet return: "
        f"**{fs.get('n_required')}** (σ={_num(fs.get('assumed_std'), 4)}). {fs.get('note')}"
    )
    lines.append("")
    lines.append("## Conclusion (factual only — no go/no-go verdict)")
    lines.append("")
    roi = main.get("roi")
    lines.append(f"- OOS ROI was {'positive' if (roi or 0) > 0 else 'negative' if (roi or 0) < 0 else 'zero/undefined'} "
                 f"({_pct(roi)}).")
    lines.append(f"- Sample size: N={main['n']} ({main['sample_label']}).")
    lines.append(
        f"- Bootstrap 95% CI for portfolio ROI: [{_pct(br.get('ci_low'))}, {_pct(br.get('ci_high'))}]."
    )
    lines.append(f"- Max drawdown: {_num(main['max_dd_units'], 3)}u ({_pct(main['max_dd_pct'])}).")
    lines.append(
        f"- Stability: see weekly / rolling tables; last rolling-25 ROI={_pct(r25[-1]['roi']) if r25 else 'n/a'}."
    )
    lines.append(
        "- League filtering: **could not be tested** — whitelist undefined; B ≡ C."
    )
    lines.append(f"- CLV: {payload['clv'].get('message', 'see JSON')}.")
    lines.append(f"- Leakage into OOS selection: **not detected** for parameter choice; see residual limitations.")
    lines.append("")
    lines.append("### Objective conditions before considering live (checklist, not a verdict)")
    lines.append("")
    lines.append("1. Define and freeze an explicit league whitelist in code (or formally document none).")
    lines.append("2. Accumulate larger OOS N (see future sample size note) without retuning.")
    lines.append("3. Capture closing odds at sync for CLV.")
    lines.append("4. Persist `created_at` alongside exports to prove pre-kickoff placement.")
    lines.append("5. Keep odds band / market / confidence gates frozen; do not optimize on this OOS window.")
    lines.append("")
    return "\n".join(lines)


def write_reports(payload: dict[str, Any], out_dir: Path = DEFAULT_OUT) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = payload.get("report_date") or "undated"
    md_name = f"arahus_oos_v1_{stamp}.md"
    json_name = f"arahus_oos_v1_{stamp}.json"

    md_text = render_markdown(payload)
    # JSON: drop ultra-long equity from top-level duplicate if needed — keep it
    json_payload = dict(payload)
    (out_dir / md_name).write_text(md_text, encoding="utf-8")
    (out_dir / json_name).write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")
    # Also mirror to repo reports/
    (REPORTS_DIR / md_name).write_text(md_text, encoding="utf-8")
    (REPORTS_DIR / json_name).write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")
    # Stable latest copies
    (out_dir / "report.md").write_text(md_text, encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(json_payload, indent=2, default=str), encoding="utf-8")
    return {
        "markdown": str(out_dir / md_name),
        "json": str(out_dir / json_name),
        "reports_md": str(REPORTS_DIR / md_name),
        "reports_json": str(REPORTS_DIR / json_name),
    }
