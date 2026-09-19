"""CLI entrypoint for Plus EV calibration research v2."""
from __future__ import annotations

import argparse
from pathlib import Path

from research.plus_ev_calibration_v2.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Plus EV calibration v2 (research only)")
    p.add_argument(
        "--input",
        type=Path,
        default=Path("/home/ubuntu/.cursor/projects/workspace/uploads/plus_ev_bet_log_season2_39ab.csv"),
        help="Season 2 (or development) bet log CSV",
    )
    p.add_argument(
        "--future",
        type=Path,
        default=None,
        help="Optional untouched future season CSV (e.g. Season 3)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("research/plus_ev_calibration_v2/output"),
    )
    args = p.parse_args(argv)
    paths = run_pipeline(args.input, args.out_dir, future_csv=args.future)
    print("=== Plus EV calibration v2 complete (research only) ===")
    print(f"Input: {args.input}")
    print(f"Future: {args.future or '(none — true future validation unavailable)'}")
    for k, path in paths.items():
        print(f"  {k}: {Path(path).resolve()}")
    # Concise numbers from results.json
    import json

    payload = json.loads((args.out_dir / "results.json").read_text(encoding="utf-8"))
    print("--- Key numbers ---")
    print(f"Settled baseline ROI: {payload['baseline_all_settled']['roi']:.4f}")
    print(f"OOS ROI: {payload['oos_baseline']['roi']:.4f}")
    ci = payload["oos_roi_bootstrap"]
    print(f"OOS ROI 95% CI: [{ci['ci_low']:.4f}, {ci['ci_high']:.4f}]")
    cm = payload["calibration_metrics_oos"]
    print(
        "OOS Brier raw/platt/iso: "
        f"{cm['raw']['brier']:.4f} / {cm['platt']['brier']:.4f} / {cm['isotonic']['brier']:.4f}"
    )
    print(
        "OOS ECE raw/platt/iso: "
        f"{cm['raw']['ece']:.4f} / {cm['platt']['ece']:.4f} / {cm['isotonic']['ece']:.4f}"
    )
    print(f"CLV: {payload['clv']['analysis']}")
    print(f"Fair market: {payload['fair_market']['statement'][:120]}...")
    print("Bottom line: No deployable edge established yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
