"""Read-only forensic metrics for log_type=xgot from bet_entries.

Run inside the app environment (local or dgauto container):
  PYTHONPATH=/app python analysis/xgot_forensic_audit/run_xgot_audit.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import os

from app.db import init_db, list_bets
from app.xgot_strat import enrich_xgot_entries, market_label_for_entry

OUT = Path(os.environ.get("XGOT_AUDIT_OUT") or Path(__file__).resolve().parent)


def _pnl(e: dict[str, Any]) -> float | None:
    v = e.get("pnl_units")
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _odds(e: dict[str, Any]) -> float | None:
    try:
        o = float(e.get("odds") or 0)
        return o if o > 0 else None
    except (TypeError, ValueError):
        return None


def _recompute(e: dict[str, Any]) -> float | None:
    st = str(e.get("status") or "").lower()
    u = float(e.get("units") or 1)
    o = _odds(e)
    if st == "won":
        return round((o - 1) * u, 3) if o else None
    if st == "lost":
        return round(-u, 3)
    if st == "push":
        return 0.0
    return None


def _bucket_xgot(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "missing"
    if v < 2.0:
        return "<2.0"
    if v < 2.5:
        return "2.0-2.49"
    if v < 3.0:
        return "2.5-2.99"
    if v < 3.5:
        return "3.0-3.49"
    if v < 4.0:
        return "3.5-3.99"
    return "4.0+"


def _market_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_m: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "n": 0,
            "won": 0,
            "lost": 0,
            "push": 0,
            "open": 0,
            "stake": 0.0,
            "pnl": 0.0,
            "odds_sum": 0.0,
            "odds_n": 0,
            "null_odds_settled": 0,
            "null_odds_open": 0,
        }
    )
    for e in rows:
        bt = str(e.get("bet_type") or "")
        st = str(e.get("status") or "").lower()
        b = by_m[bt]
        b["n"] += 1
        u = float(e.get("units") or 1)
        if st in {"won", "lost", "push"}:
            b[st] += 1
            b["stake"] += u
            p = _pnl(e)
            if p is not None:
                b["pnl"] += p
            o = _odds(e)
            if o:
                b["odds_sum"] += o
                b["odds_n"] += 1
            else:
                b["null_odds_settled"] += 1
        elif st == "open":
            b["open"] += 1
            if not _odds(e):
                b["null_odds_open"] += 1

    out = []
    for bt, b in sorted(by_m.items()):
        settled_n = b["won"] + b["lost"] + b["push"]
        denom = b["won"] + b["lost"]
        out.append(
            {
                "bet_type": bt,
                "label": market_label_for_entry({"bet_type": bt, "team_name": ""}),
                "n": b["n"],
                "settled": settled_n,
                "won": b["won"],
                "lost": b["lost"],
                "push": b["push"],
                "open": b["open"],
                "win_pct": round(100 * b["won"] / denom, 2) if denom else None,
                "avg_odds": round(b["odds_sum"] / b["odds_n"], 3) if b["odds_n"] else None,
                "unit_pnl": round(b["pnl"], 3),
                "roi": round(b["pnl"] / b["stake"], 4) if b["stake"] else None,
                "null_odds_settled": b["null_odds_settled"],
                "null_odds_open": b["null_odds_open"],
            }
        )
    return out


def _bucket_table(rows: list[dict[str, Any]], bet_type: str) -> list[dict[str, Any]]:
    labels = ["missing", "<2.0", "2.0-2.49", "2.5-2.99", "3.0-3.49", "3.5-3.99", "4.0+"]
    out = []
    for label in labels:
        es = [
            e
            for e in rows
            if e.get("bet_type") == bet_type
            and str(e.get("status") or "").lower() in {"won", "lost", "push"}
            and _bucket_xgot(e.get("proj_xgot_total")) == label
        ]
        if not es:
            continue
        won = sum(1 for e in es if str(e.get("status")).lower() == "won")
        lost = sum(1 for e in es if str(e.get("status")).lower() == "lost")
        push = sum(1 for e in es if str(e.get("status")).lower() == "push")
        stake = sum(float(e.get("units") or 1) for e in es)
        p = sum(_pnl(e) or 0 for e in es)
        denom = won + lost
        out.append(
            {
                "bet_type": bet_type,
                "xgot_bucket": label,
                "n": len(es),
                "won": won,
                "lost": lost,
                "push": push,
                "win_pct": round(100 * won / denom, 2) if denom else None,
                "unit_pnl": round(p, 3),
                "roi": round(p / stake, 4) if stake else None,
            }
        )
    return out


def main() -> None:
    init_db()
    rows = enrich_xgot_entries(list_bets("xgot"))
    OUT.mkdir(parents=True, exist_ok=True)

    fields = [
        "id",
        "created_at",
        "resolved_at",
        "fixture_id",
        "fixture_date",
        "fixture",
        "home_team",
        "away_team",
        "league_name",
        "bet_type",
        "team_name",
        "odds",
        "units",
        "status",
        "pnl_units",
        "proj_xgot_home",
        "proj_xgot_away",
        "proj_xgot_total",
        "proj_big_chances_home",
        "proj_big_chances_away",
        "proj_big_chances_total",
        "proj_box_shots_home",
        "proj_box_shots_away",
        "proj_box_shots_total",
        "proj_sot_home",
        "proj_sot_away",
        "proj_sot_total",
        "market_label",
        "xgot_display_label",
        "xgot_breakdown",
    ]
    csv_path = OUT / "xgot_bet_log_export.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

    settled = [e for e in rows if str(e.get("status") or "").lower() in {"won", "lost", "push"}]
    open_rows = [e for e in rows if str(e.get("status") or "").lower() == "open"]
    mism = []
    for e in settled:
        rc = _recompute(e)
        stored = _pnl(e)
        if rc is not None and stored is not None and abs(rc - stored) > 1e-6:
            mism.append({"id": e.get("id"), "stored": stored, "recomputed": rc, "status": e.get("status")})

    fixture_counts = Counter(str(e.get("fixture_id") or e.get("fixture")) for e in settled)
    overall_pnl = sum(_pnl(e) or 0 for e in settled)
    overall_stake = sum(float(e.get("units") or 1) for e in settled)

    dates = [e.get("fixture_date") for e in rows if e.get("fixture_date")]
    created = [e.get("created_at") for e in rows if e.get("created_at")]

    summary = {
        "total_rows": len(rows),
        "status_counts": dict(Counter(str(r.get("status") or "").lower() for r in rows)),
        "bet_type_counts": dict(Counter(str(r.get("bet_type") or "") for r in rows)),
        "settled": len(settled),
        "open": len(open_rows),
        "pnl_mismatches": len(mism),
        "mismatch_samples": mism[:10],
        "unique_fixtures_settled": len(fixture_counts),
        "max_bets_per_settled_fixture": max(fixture_counts.values()) if fixture_counts else 0,
        "fixture_date_min": min(dates) if dates else None,
        "fixture_date_max": max(dates) if dates else None,
        "created_at_min": min(created) if created else None,
        "created_at_max": max(created) if created else None,
        "feat_xgot_total": sum(1 for e in rows if e.get("proj_xgot_total") is not None),
        "feat_xgot_home": sum(1 for e in rows if e.get("proj_xgot_home") is not None),
        "feat_bc_total": sum(1 for e in rows if e.get("proj_big_chances_total") is not None),
        "feat_box_total": sum(1 for e in rows if e.get("proj_box_shots_total") is not None),
        "feat_sot_total": sum(1 for e in rows if e.get("proj_sot_total") is not None),
        "overall_settled_unit_pnl": round(overall_pnl, 3),
        "overall_settled_stake_units": overall_stake,
        "overall_settled_roi": round(overall_pnl / overall_stake, 4) if overall_stake else None,
        "by_market": _market_stats(rows),
        "o25_by_xgot_bucket": _bucket_table(rows, "xgot_o25"),
        "o35_by_xgot_bucket": _bucket_table(rows, "xgot_o35"),
        "btts_by_xgot_bucket": _bucket_table(rows, "xgot_btts"),
        "export_csv": str(csv_path),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
