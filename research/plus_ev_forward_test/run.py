"""CLI for plus_ev forward-test research framework."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.plus_ev_forward_test.report import DEFAULT_OUT, generate_report
from research.plus_ev_forward_test.seed_season2 import seed_from_season2_csv
from research.plus_ev_forward_test.storage import DEFAULT_DATA_DIR


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Plus EV forward-test (research only)")
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    sub = p.add_subparsers(dest="cmd", required=True)

    seed = sub.add_parser("seed-season2", help="Seed ledger from Season 2 CSV (retrospective)")
    seed.add_argument(
        "--input",
        type=Path,
        default=Path("/home/ubuntu/.cursor/projects/workspace/uploads/plus_ev_bet_log_season2_39ab.csv"),
    )

    sub.add_parser("collect", help="Collect live +EV signals into research ledger (no real bets)")
    sub.add_parser("snapshot-closing", help="Capture latest pre-kickoff odds for open live signals")
    sub.add_parser("settle", help="Fill results from production bet log (read-only)")
    sub.add_parser("report", help="Generate portfolio report / CSV / JSON / plots")

    all_cmd = sub.add_parser("run-all", help="seed (optional) + report for current ledger")
    all_cmd.add_argument(
        "--input",
        type=Path,
        default=Path("/home/ubuntu/.cursor/projects/workspace/uploads/plus_ev_bet_log_season2_39ab.csv"),
    )
    all_cmd.add_argument("--skip-seed", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "seed-season2":
        stats = seed_from_season2_csv(args.input, args.data_dir)
        print(json.dumps(stats, indent=2))
        return 0

    if args.cmd == "collect":
        from research.plus_ev_forward_test.collect import collect_from_live_state

        print(json.dumps(collect_from_live_state(args.data_dir), indent=2))
        return 0

    if args.cmd == "snapshot-closing":
        from research.plus_ev_forward_test.collect import snapshot_pre_kickoff_odds

        print(json.dumps(snapshot_pre_kickoff_odds(args.data_dir), indent=2))
        return 0

    if args.cmd == "settle":
        from research.plus_ev_forward_test.settle import settle_from_production_bet_log

        print(json.dumps(settle_from_production_bet_log(args.data_dir), indent=2))
        return 0

    if args.cmd == "report":
        paths = generate_report(args.data_dir, args.out_dir)
        _print_summary(args.out_dir, paths)
        return 0

    if args.cmd == "run-all":
        if not args.skip_seed:
            stats = seed_from_season2_csv(args.input, args.data_dir)
            print("seed:", json.dumps(stats))
        paths = generate_report(args.data_dir, args.out_dir)
        _print_summary(args.out_dir, paths)
        return 0

    return 1


def _print_summary(out_dir: Path, paths: dict) -> None:
    payload = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    print("=== Plus EV forward-test report ===")
    print("research_only=true | can_place_real_bet=false")
    for k, path in paths.items():
        print(f"  {k}: {Path(path).resolve()}")
    print("--- Portfolios ---")
    for pid, m in payload["portfolios"].items():
        print(
            f"{m['meta']['label']}: N={m.get('n')} ROI={m.get('roi')} "
            f"CLV_mean={m.get('mean_clv')} status={m.get('status')}"
        )
    print("--- Comparison ---")
    for k, v in payload["comparison_answers"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    raise SystemExit(main())
