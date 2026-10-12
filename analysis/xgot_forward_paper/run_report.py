#!/usr/bin/env python3
"""Generate dated xGOT forward-paper report (outcome ≠ financial ROI)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import list_bets  # noqa: E402
from app.xgot_metrics import (  # noqa: E402
    financial_stats,
    fixture_cluster_note,
    outcome_stats,
)
from app.xgot_research import LOG_TYPES, XGOT_FW_VERSION  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "output"


def _summarize(log_type: str, label: str) -> dict[str, Any]:
    entries = list_bets(log_type)
    out = outcome_stats(entries)
    fin = financial_stats(entries)
    cluster = fixture_cluster_note(entries)
    return {
        "label": label,
        "log_type": log_type,
        "strategy_version": next(
            (e.get("strategy_version") for e in entries if e.get("strategy_version")),
            None,
        ),
        **out,
        **fin,
        **cluster,
    }


def build_report() -> dict[str, Any]:
    baseline = _summarize("xgot", "A baseline")
    variants = {
        vid: _summarize(lt, f"Variant {vid}")
        for vid, lt in LOG_TYPES.items()
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "xgot_fw_version": XGOT_FW_VERSION,
        "notes": [
            "Financial ROI uses decimal odds only; null odds ⇒ ROI unavailable.",
            "Outcome win rate includes null-odds settlements.",
            "Research variants never route to LIVE / Trade Picks.",
        ],
        "baseline": baseline,
        "variants": variants,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# xGOT forward paper report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Strategy version: `{report['xgot_fw_version']}`",
        "",
        "## Notes",
        "",
    ]
    for n in report["notes"]:
        lines.append(f"- {n}")
    lines += ["", "## Baseline (A)", ""]

    def _block(s: dict[str, Any]) -> list[str]:
        roi = s.get("roi")
        roi_s = f"{roi:.1%}" if isinstance(roi, (int, float)) else "N/A"
        net = s.get("net_pnl_units")
        net_s = f"{net:+.2f}u" if isinstance(net, (int, float)) else "N/A"
        wr = s.get("win_rate")
        wr_s = f"{wr:.1%}" if isinstance(wr, (int, float)) else "N/A"
        return [
            f"- log_type: `{s['log_type']}`",
            f"- placed / settled / open: {s['placed']} / {s['settled']} / {s['open']}",
            f"- W-L-P: {s['won']}-{s['lost']}-{s['push']} (outcome WR {wr_s})",
            f"- unique fixtures: {s['unique_fixtures']} (max bets/fixture={s['max_bets_per_fixture']})",
            f"- priced settled: {s['priced_settled']}",
            f"- net PnL / ROI: {net_s} / {roi_s}",
            f"- avg entry odds: {s.get('avg_entry_odds')}",
            "",
        ]

    lines.extend(_block(report["baseline"]))
    lines += ["## Variants B–E", ""]
    for vid in ("B", "C", "D", "E"):
        s = report["variants"][vid]
        lines.append(f"### {s['label']}")
        lines.append("")
        lines.extend(_block(s))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="Output directory for dated JSON/MD",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = build_report()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.out_dir / f"forward_report_{stamp}.json"
    md_path = args.out_dir / f"forward_report_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    latest_json = args.out_dir / "forward_report_latest.json"
    latest_md = args.out_dir / "forward_report_latest.md"
    latest_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
