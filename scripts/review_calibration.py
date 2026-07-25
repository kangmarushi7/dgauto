"""Summarize Arahus scenario-calibration debug log (2-week review helper).

Usage:
  python scripts/review_calibration.py
  python scripts/review_calibration.py --relevant-only
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from app.arahus_engine import load_arahus_calibration_log
from app.dg_calibration import MIN_SAMPLE


def _summarize(entries: list[dict[str, Any]], *, relevant_only: bool) -> None:
    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "picks": 0,
            "ratios": [],
            "calibrated": 0,
            "uncalibrated": 0,
            "ns": [],
        }
    )
    pick_count = 0
    for entry in entries:
        pick_count += 1
        rows = entry.get("_calibrationDebug") or []
        if relevant_only:
            rows = [r for r in rows if r.get("relevantToPick")] or (
                entry.get("_calibrationRelevant") or []
            )
        for row in rows:
            key = (str(row.get("scenarioKey") or "?"), str(row.get("subKey") or "?"))
            agg = buckets[key]
            agg["picks"] += 1
            status = row.get("status")
            if status == "calibrated":
                agg["calibrated"] += 1
                if row.get("ratio") is not None:
                    agg["ratios"].append(float(row["ratio"]))
            else:
                agg["uncalibrated"] += 1
            if row.get("n") is not None:
                agg["ns"].append(int(row["n"]))

    print(f"Calibration log entries (picks synced): {pick_count}")
    print(f"MIN_SAMPLE floor: {MIN_SAMPLE}")
    print(f"Mode: {'relevant-to-pick only' if relevant_only else 'all matched scenarios'}")
    print()
    header = (
        f"{'scenario':<10} {'sub':<6} {'rows':>5} {'calib':>5} {'uncal':>5} "
        f"{'avg_ratio':>9} {'n_hint':>7}"
    )
    print(header)
    print("-" * len(header))
    for (scenario, sub), agg in sorted(buckets.items()):
        ratios = agg["ratios"]
        avg = sum(ratios) / len(ratios) if ratios else None
        n_hint = max(agg["ns"]) if agg["ns"] else 0
        avg_s = f"{avg:.3f}" if avg is not None else "—"
        print(
            f"{scenario:<10} {sub:<6} {agg['picks']:>5} {agg['calibrated']:>5} "
            f"{agg['uncalibrated']:>5} {avg_s:>9} {n_hint:>7}"
        )
    if not buckets:
        print("(no calibration rows yet — sync Arahus picks first)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--relevant-only",
        action="store_true",
        help="Only count scenario rows tagged relevantToPick for that bet",
    )
    args = parser.parse_args()
    entries = load_arahus_calibration_log()
    _summarize(entries, relevant_only=args.relevant_only)


if __name__ == "__main__":
    main()
