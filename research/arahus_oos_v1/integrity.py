"""Data integrity checks for Arahus OOS — report issues; do not silently drop."""
from __future__ import annotations

from collections import Counter
from typing import Any


def audit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    ids = [str(r.get("id")) for r in rows]
    id_counts = Counter(ids)
    dup_ids = [i for i, c in id_counts.items() if c > 1]
    if dup_ids:
        issues.append(
            {
                "type": "duplicate_ids",
                "count": len(dup_ids),
                "examples": dup_ids[:10],
                "action": "reported_only",
            }
        )

    # fixture + market + fixture_date duplicates
    keys = [
        (
            str(r.get("fixture") or ""),
            str(r.get("market") or ""),
            str(r.get("fixture_date") or ""),
            str(r.get("league_name") or ""),
        )
        for r in rows
    ]
    key_counts = Counter(keys)
    dup_keys = [k for k, c in key_counts.items() if c > 1]
    if dup_keys:
        issues.append(
            {
                "type": "duplicate_fixture_market_timestamp",
                "count": len(dup_keys),
                "examples": [
                    {"fixture": k[0], "market": k[1], "fixture_date": k[2], "league": k[3]}
                    for k in dup_keys[:10]
                ],
                "action": "reported_only — app insert_bets dedupes on "
                "log_type+fixture_date+fixture+bet_type+team_name",
            }
        )

    missing_odds = sum(1 for r in rows if r.get("odds") is None)
    if missing_odds:
        issues.append({"type": "missing_odds", "count": missing_odds, "action": "excluded_from_candidate"})

    missing_result = sum(1 for r in rows if r.get("status") in {"open", None, ""})
    if missing_result:
        issues.append(
            {
                "type": "open_or_missing_result",
                "count": missing_result,
                "action": "excluded_from_settled_roi",
            }
        )

    impossible_odds = [
        {"id": r.get("id"), "odds": r.get("odds")}
        for r in rows
        if r.get("odds") is not None and float(r["odds"]) <= 1.0
    ]
    if impossible_odds:
        issues.append(
            {
                "type": "impossible_odds_lte_1",
                "count": len(impossible_odds),
                "examples": impossible_odds[:10],
                "action": "reported_only",
            }
        )

    malformed_league = sum(1 for r in rows if not str(r.get("league_name") or "").strip())
    if malformed_league:
        issues.append({"type": "blank_league_name", "count": malformed_league, "action": "reported_only"})

    market_raws = Counter(str(r.get("market_raw") or "") for r in rows)
    market_norm = Counter(str(r.get("market") or "") for r in rows)

    stake_anoms = [
        {"id": r.get("id"), "units": r.get("units")}
        for r in rows
        if r.get("units") is not None and (float(r["units"]) <= 0 or float(r["units"]) > 5)
    ]
    if stake_anoms:
        issues.append(
            {
                "type": "stake_anomalies",
                "count": len(stake_anoms),
                "examples": stake_anoms[:10],
                "action": "reported_only",
            }
        )

    unparsed_dates = sum(1 for r in rows if not r.get("fixture_date_d"))
    if unparsed_dates:
        issues.append(
            {
                "type": "unparsed_fixture_date",
                "count": unparsed_dates,
                "action": "period=unknown; excluded from chrono splits",
            }
        )

    # Closing odds / post-kickoff: Excel export has neither created_at nor closing_odds
    issues.append(
        {
            "type": "no_created_at_in_excel_export",
            "count": len(rows),
            "action": "cannot verify bet-after-kickoff; fixture_date used as chronological key",
        }
    )
    issues.append(
        {
            "type": "no_closing_odds_in_dataset",
            "count": sum(1 for r in rows if r.get("closing_odds") is None),
            "action": "CLV unavailable",
        }
    )

    return {
        "n_rows": len(rows),
        "issues": issues,
        "market_raw_counts": dict(market_raws),
        "market_normalized_counts": dict(market_norm),
        "status_counts": dict(Counter(str(r.get("status")) for r in rows)),
        "league_counts": dict(Counter(str(r.get("league_name") or "") for r in rows)),
        "dedupe_rule_in_app": (
            "UniqueConstraint(log_type, fixture_date, fixture, bet_type, team_name) "
            "on bet_entries — see app/db.py"
        ),
    }
