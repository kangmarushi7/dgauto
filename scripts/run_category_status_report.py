#!/usr/bin/env python3
"""Run strategy bucket status report (+ optional monthly graduation)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graduate", action="store_true", help="Apply TRACKING→LIVE / demotions")
    parser.add_argument("--json", action="store_true", help="Print full JSON")
    args = parser.parse_args()

    from app.db import init_db
    from app.strategy_buckets import (
        apply_monthly_graduation,
        category_status_report,
        load_pipeline_bets_from_db,
    )

    init_db()
    rows = load_pipeline_bets_from_db()
    if args.graduate:
        payload = apply_monthly_graduation(rows, persist=True)
    else:
        payload = category_status_report(rows)

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print(f"generated_at={payload.get('generated_at')}")
    for cid, info in (payload.get("categories") or {}).items():
        roi = info.get("roi_full")
        roi_s = f"{roi*100:.1f}%" if roi is not None else "—"
        print(
            f"{cid:28} state={info.get('state'):8} n={info.get('n'):5} "
            f"roi={roi_s:>8} gates={info.get('graduation_all_pass')}"
        )
    for t in payload.get("transitions") or []:
        print(f"TRANSITION {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
