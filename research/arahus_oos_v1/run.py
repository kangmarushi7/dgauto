"""CLI: python3 -m research.arahus_oos_v1.run"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.arahus_oos_v1.pipeline import run_pipeline
from research.arahus_oos_v1.report import DEFAULT_OUT, write_reports


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Arahus O2.5 chronological OOS validation (research only)")
    p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to Arahus log CSV export (Excel/CSV columns)",
    )
    p.add_argument("--from-db", action="store_true", help="Load from DATABASE_URL / local SQLite")
    p.add_argument("--log-type", default="arahus", help="DB log_type when --from-db")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)

    payload = run_pipeline(
        csv_path=str(args.input) if args.input else None,
        from_db=args.from_db,
        log_type=args.log_type,
    )
    paths = write_reports(payload, args.out_dir)
    main = payload["main_result_logged_stake"]
    print("=== Arahus O2.5 OOS Validation ===")
    print("research_only=true | can_place_real_bet=false")
    print(f"league_whitelist_defined={payload['league_whitelist_status']['defined_in_repo']}")
    print(
        f"OOS candidate: N={main['n']} ROI={main['roi']} PnL={main['pnl']} "
        f"MaxDD={main['max_dd_units']} status_sample={main['sample_label']}"
    )
    for k, v in paths.items():
        print(f"  {k}: {v}")
    print("baseline:")
    for row in payload["baseline_comparison"]:
        print(
            f"  {row['id']}: N={row.get('n')} ROI={row.get('roi')} PnL={row.get('pnl')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
