"""Load / clean Season CSV and emit schema dictionary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.plus_ev_calibration_v2.metrics import (
    clip_prob,
    ev_from_probability,
    normalize_status,
    pnl_flat,
)


def discover_columns(df: pd.DataFrame) -> dict[str, Any]:
    cols = list(df.columns)
    lower = {c.lower(): c for c in cols}

    def pick(*cands: str) -> str | None:
        for c in cands:
            if c in lower:
                return lower[c]
            if c in cols:
                return c
        return None

    mapping = {
        "id": pick("id", "bet_id"),
        "created_at": pick("created_at", "logged_at"),
        "fixture_date": pick("fixture_date", "kickoff", "match_date"),
        "fixture": pick("fixture", "match", "event"),
        "league": pick("league_name", "league"),
        "bet_type": pick("bet_type", "market_type"),
        "category": pick("category"),
        "market": pick("market", "market_label", "label"),
        "team": pick("team_name", "team"),
        "ev_raw": pick("qualifier_pct", "ev", "ev_pct", "edge"),
        "odds": pick("odds", "book_odds", "price"),
        "units": pick("units", "stake"),
        "status": pick("status", "result", "outcome"),
        "pnl": pick("pnl_units", "pnl", "profit"),
        "resolved_at": pick("resolved_at", "settled_at"),
        "closing_odds": pick("closing_odds", "close_odds", "odds_close", "closing_price"),
        "opening_odds": pick("opening_odds", "open_odds", "odds_open", "opening_price"),
        "fixture_id": pick("fixture_id", "event_id", "match_id"),
        "bookmaker": pick("bookmaker", "book", "source"),
        "model_prob": pick("model_probability", "model_prob", "sim_pct", "model_pct"),
        "opposite_odds": pick("opposite_odds", "no_odds", "under_odds", "lay_odds"),
    }
    return {"raw_columns": cols, "resolved_mapping": mapping}


def market_group(bet_type: Any, market: Any) -> str:
    bt = str(bet_type or "").lower()
    mk = str(market or "").lower()
    mapping = {
        "btts": "BTTS",
        "over1.5": "Over 1.5",
        "over2.5": "Over 2.5",
        "over3.5": "Over 3.5",
        "under2.5": "Under 2.5",
        "team_o1.5": "Team Over 1.5",
        "team_o0.5": "Team Over 0.5",
        "moneyline": "Moneyline",
        "draw": "Draw",
        "dc_1x": "Double Chance 1X",
        "dc_x2": "Double Chance X2",
    }
    if bt in mapping:
        return mapping[bt]
    if "over 2.5" in mk:
        return "Over 2.5"
    if "over 3.5" in mk:
        return "Over 3.5"
    if "btts" in mk:
        return "BTTS"
    return str(market or bet_type or "Other")


def load_bet_log(csv_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = pd.read_csv(csv_path)
    schema = discover_columns(df)
    m = schema["resolved_mapping"]

    out = pd.DataFrame()
    out["id"] = df[m["id"]] if m["id"] else range(len(df))
    out["created_at"] = pd.to_datetime(df[m["created_at"]], utc=True, errors="coerce") if m["created_at"] else pd.NaT
    out["fixture_date"] = (
        pd.to_datetime(df[m["fixture_date"]], utc=True, errors="coerce") if m["fixture_date"] else pd.NaT
    )
    out["fixture"] = df[m["fixture"]].astype(str) if m["fixture"] else ""
    out["league_name"] = df[m["league"]].astype(str) if m["league"] else ""
    out["bet_type"] = df[m["bet_type"]].astype(str) if m["bet_type"] else ""
    out["category"] = df[m["category"]].astype(str) if m["category"] else ""
    out["market"] = df[m["market"]].astype(str) if m["market"] else ""
    out["team_name"] = df[m["team"]].astype(str) if m["team"] else ""
    out["qualifier_pct"] = pd.to_numeric(df[m["ev_raw"]], errors="coerce") if m["ev_raw"] else np.nan
    out["odds"] = pd.to_numeric(df[m["odds"]], errors="coerce") if m["odds"] else np.nan
    out["units"] = pd.to_numeric(df[m["units"]], errors="coerce").fillna(1.0) if m["units"] else 1.0
    out["status_raw"] = df[m["status"]] if m["status"] else "open"
    out["pnl_units"] = pd.to_numeric(df[m["pnl"]], errors="coerce") if m["pnl"] else np.nan
    out["resolved_at"] = (
        pd.to_datetime(df[m["resolved_at"]], utc=True, errors="coerce") if m["resolved_at"] else pd.NaT
    )
    out["closing_odds"] = (
        pd.to_numeric(df[m["closing_odds"]], errors="coerce") if m["closing_odds"] else np.nan
    )
    out["opening_odds"] = (
        pd.to_numeric(df[m["opening_odds"]], errors="coerce") if m["opening_odds"] else np.nan
    )
    out["fixture_id"] = df[m["fixture_id"]].astype(str) if m["fixture_id"] else ""
    out["bookmaker"] = df[m["bookmaker"]].astype(str) if m["bookmaker"] else ""
    out["opposite_odds"] = (
        pd.to_numeric(df[m["opposite_odds"]], errors="coerce") if m["opposite_odds"] else np.nan
    )

    out["status_norm"] = out["status_raw"].map(normalize_status)
    out["is_settled"] = out["status_norm"].isin(["WON", "LOST", "PUSH"])
    out["outcome_win"] = np.where(
        out["status_norm"] == "WON",
        1.0,
        np.where(out["status_norm"] == "LOST", 0.0, np.nan),
    )
    out["ev_decimal"] = out["qualifier_pct"] / 100.0
    out["raw_market_implied_probability"] = 1.0 / out["odds"]
    # Reconstruct raw model probability from logged EV (no future outcomes).
    out["raw_model_probability"] = [
        clip_prob((1.0 + e) / o) if o and o > 0 and pd.notna(e) else np.nan
        for e, o in zip(out["ev_decimal"], out["odds"])
    ]
    out["raw_EV"] = [
        ev_from_probability(p, o) if pd.notna(p) and o and o > 0 else np.nan
        for p, o in zip(out["raw_model_probability"], out["odds"])
    ]
    out["market_group"] = [
        market_group(bt, mk) for bt, mk in zip(out["bet_type"], out["market"])
    ]
    out["pnl_calc"] = [
        pnl_flat(s, o) if settled else np.nan
        for s, o, settled in zip(out["status_norm"], out["odds"], out["is_settled"])
    ]

    out = out.sort_values(["fixture_date", "created_at"], na_position="last").reset_index(drop=True)

    quality = {
        "source_path": str(csv_path),
        "schema": schema,
        "total_rows": int(len(out)),
        "settled": int(out["is_settled"].sum()),
        "wins": int((out["status_norm"] == "WON").sum()),
        "losses": int((out["status_norm"] == "LOST").sum()),
        "pushes": int((out["status_norm"] == "PUSH").sum()),
        "open": int((out["status_norm"] == "OPEN").sum()),
        "duplicate_ids": int(out["id"].duplicated().sum()),
        "has_closing_odds": bool(out["closing_odds"].notna().any()),
        "has_opening_odds": bool(out["opening_odds"].notna().any()),
        "has_opposite_odds": bool(out["opposite_odds"].notna().any()),
        "has_fixture_id": bool((out["fixture_id"] != "").any()),
        "fixture_date_range": [str(out["fixture_date"].min()), str(out["fixture_date"].max())],
        "clv_status": (
            "available"
            if out["closing_odds"].notna().any()
            else "CLV cannot currently be measured from this dataset."
        ),
    }
    return out, quality


def write_data_audit(quality: dict[str, Any], out_path: Path) -> None:
    lines = [
        "# Data audit — Plus EV calibration v2",
        "",
        "## Source",
        f"- Path: `{quality['source_path']}`",
        f"- Rows: **{quality['total_rows']}**",
        f"- Settled / open: **{quality['settled']}** / **{quality['open']}**",
        f"- W / L / Push: **{quality['wins']}** / **{quality['losses']}** / **{quality['pushes']}**",
        f"- Duplicate ids: **{quality['duplicate_ids']}**",
        f"- Fixture date range: `{quality['fixture_date_range'][0]}` → `{quality['fixture_date_range'][1]}`",
        "",
        "## Schema / column mapping",
        "",
        "```json",
        json.dumps(quality["schema"], indent=2),
        "```",
        "",
        "## Odds snapshots",
        "",
        f"- Opening odds present: **{quality['has_opening_odds']}**",
        f"- Closing odds present: **{quality['has_closing_odds']}**",
        f"- Opposite-side odds present: **{quality['has_opposite_odds']}**",
        f"- Fixture IDs present: **{quality['has_fixture_id']}**",
        "",
        f"**CLV status:** {quality['clv_status']}",
        "",
        "## Season discovery",
        "",
        "- App seasons: Season 1 (through 2026-06-30 IST), Season 2 (from 2026-07-01).",
        "- **Season 3 / future season dataset: not found** in repo or uploads.",
        "- Only Season 2 +EV bet log CSV was available for this run.",
        "",
        "## Notes",
        "",
        "- Logged EV lives in `qualifier_pct` (percentage points).",
        "- Model probability is reconstructed as `(1 + EV_decimal) / odds`.",
        "- No production DB schemas were modified.",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
