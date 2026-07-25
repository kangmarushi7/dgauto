"""Export Arahus decision-log rows for analysis / fine-tuning.

Usage:
  python scripts/export_decision_log.py
  python scripts/export_decision_log.py --format csv --from 2026-07-01 --to 2026-07-31
  python scripts/export_decision_log.py --status skipped_low_edge --league "Brazil Serie A"
  python scripts/export_decision_log.py --format json -o data/arahus_decisions.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

# Allow running as `python scripts/export_decision_log.py` from repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import init_db, list_arahus_decision_log  # noqa: E402


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "fixture_id": row.get("fixture_id"),
        "synced_at": row.get("synced_at"),
        "match_date": row.get("match_date"),
        "league": row.get("league"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "fixture": row.get("fixture"),
        "bet_type": row.get("bet_type"),
        "team_name": row.get("team_name"),
        "status": row.get("status"),
        "model_pct": row.get("model_pct"),
        "confidence": row.get("confidence"),
        "odds": row.get("odds"),
        "edge": row.get("edge"),
        "ev": row.get("ev"),
        "units": row.get("units"),
        "xg_home": row.get("xg_home"),
        "xg_away": row.get("xg_away"),
        "xg_total": row.get("xg_total"),
        "pace_score": row.get("pace_score"),
        "nec_index": row.get("nec_index"),
        "agix_index": row.get("agix_index"),
        "dgrtg_gap": row.get("dgrtg_gap"),
        "archetype": row.get("archetype"),
        "luck_regression_value": row.get("luck_regression_value"),
        "engine_version": row.get("engine_version"),
        "result": row.get("result"),
        "pnl": row.get("pnl"),
        "hypothetical_pnl": row.get("hypothetical_pnl"),
        "resolved_at": row.get("resolved_at"),
        "signals": json.dumps(row.get("signals") or [], ensure_ascii=False),
        "calibration_debug": json.dumps(
            row.get("calibration_debug") or [], ensure_ascii=False
        ),
        "engine_config_snapshot": json.dumps(
            row.get("engine_config_snapshot") or {}, ensure_ascii=False
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="date_from", default=None, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD")
    parser.add_argument("--league", default=None)
    parser.add_argument(
        "--status",
        default=None,
        help="picked | skipped_low_confidence | skipped_low_edge | skipped_other",
    )
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    parser.add_argument("-o", "--output", default=None, help="Output file path")
    args = parser.parse_args()

    init_db()
    rows = list_arahus_decision_log(
        date_from=args.date_from,
        date_to=args.date_to,
        league=args.league,
        status=args.status,
    )

    if args.format == "json":
        payload = json.dumps({"count": len(rows), "rows": rows}, indent=2, default=str)
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
            print(f"Wrote {len(rows)} rows -> {args.output}")
        else:
            print(payload)
        return

    flat = [_flatten(r) for r in rows]
    fieldnames = list(flat[0].keys()) if flat else ["id", "status", "bet_type"]
    if args.output:
        out_path = Path(args.output)
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat)
        print(f"Wrote {len(flat)} rows -> {out_path}")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat)


if __name__ == "__main__":
    main()
