from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List

import cv2
import numpy as np
import pandas as pd
import pytesseract
from rapidfuzz import fuzz, process


FIXTURE_SPLIT_RE = re.compile(r"\s+(?:vs|v|-)\s+", re.IGNORECASE)
PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


@dataclass
class ParsedRow:
    source: str
    fixture_raw: str
    fixture_key: str
    line_text: str
    max_pct: float | None
    pcts: list[float]


def normalize_fixture(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", " ", text).lower()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    parts = FIXTURE_SPLIT_RE.split(text)
    if len(parts) >= 2:
        parts = [p.strip() for p in parts[:2]]
        parts = sorted(parts)
        return " vs ".join(parts)
    return text


def preprocess_image(path: Path) -> np.ndarray:
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=12)
    thr = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    return thr


def extract_lines(path: Path, source_name: str) -> list[ParsedRow]:
    img = preprocess_image(path)
    data = pytesseract.image_to_data(
        img, output_type=pytesseract.Output.DICT, config="--oem 3 --psm 6"
    )

    rows = {}
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        if not txt:
            continue
        conf = float(data["conf"][i]) if data["conf"][i] != "-1" else -1
        if conf < 30:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        rows.setdefault(key, []).append(txt)

    parsed: list[ParsedRow] = []
    for parts in rows.values():
        line = " ".join(parts).strip()
        if len(line) < 6:
            continue

        pcts = [float(p) / 100 for p in PCT_RE.findall(line)]
        max_pct = max(pcts) if pcts else None
        fixture_key = normalize_fixture(line)
        parsed.append(
            ParsedRow(
                source=source_name,
                fixture_raw=line,
                fixture_key=fixture_key,
                line_text=line,
                max_pct=max_pct,
                pcts=pcts,
            )
        )
    return parsed


def best_match_lookup(query: str, choices: Iterable[str], score_cutoff: int) -> str | None:
    if not query:
        return None
    match = process.extractOne(query, choices, scorer=fuzz.token_set_ratio, score_cutoff=score_cutoff)
    if not match:
        return None
    return match[0]


def load_rules(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def classify_candidate(win_row: ParsedRow, goals_row: ParsedRow | None, rules: dict) -> dict:
    win_pct = win_row.max_pct or 0.0
    goals_pct = goals_row.max_pct if goals_row else 0.0
    goals_pct = goals_pct or 0.0

    signals = []
    if win_pct >= rules["min_win_prob"]:
        signals.append("win-prob")
    if goals_pct >= rules["min_goals_25_prob"]:
        signals.append("goals-prob")

    confidence = round(((win_pct + goals_pct) / 2) * 100, 2)
    tier = "A" if confidence >= 75 else "B" if confidence >= 65 else "C"

    return {
        "fixture": win_row.fixture_raw,
        "fixture_key": win_row.fixture_key,
        "win_source_text": win_row.line_text,
        "goals_source_text": goals_row.line_text if goals_row else "",
        "win_max_pct": round(win_pct * 100, 2),
        "goals_max_pct": round(goals_pct * 100, 2),
        "signals": ",".join(signals),
        "confidence_score": confidence,
        "tier": tier,
        "is_shortlisted": bool(signals),
    }


def automate(win_img: Path, goals_img: Path, rules_path: Path, out_csv: Path, out_json: Path) -> None:
    rules = load_rules(rules_path)

    win_rows = extract_lines(win_img, "win")
    goals_rows = extract_lines(goals_img, "goals")

    goals_index = {r.fixture_key: r for r in goals_rows if r.fixture_key}
    goal_keys = list(goals_index.keys())

    results = []
    for win_row in win_rows:
        matched_key = best_match_lookup(
            win_row.fixture_key, goal_keys, score_cutoff=rules.get("fixture_match_score", 78)
        )
        goals_row = goals_index.get(matched_key) if matched_key else None
        results.append(classify_candidate(win_row, goals_row, rules))

    df = pd.DataFrame(results)
    if df.empty:
        print("No rows extracted from screenshots.")
        return

    df.sort_values(["is_shortlisted", "confidence_score"], ascending=[False, False], inplace=True)
    df.to_csv(out_csv, index=False)

    payload = {
        "summary": {
            "total_rows": int(len(df)),
            "shortlisted": int(df["is_shortlisted"].sum()),
        },
        "results": df.to_dict(orient="records"),
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Saved: {out_csv}")
    print(f"Saved: {out_json}")
    print(f"Shortlisted picks: {payload['summary']['shortlisted']} / {payload['summary']['total_rows']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate daily football screenshot comparison with OCR + rule-based filtering."
    )
    parser.add_argument("--win-img", type=Path, required=True, help="Win probability screenshot path")
    parser.add_argument("--goals-img", type=Path, required=True, help="Goals probability screenshot path")
    parser.add_argument("--rules", type=Path, default=Path("rules.json"), help="Rules JSON file")
    parser.add_argument("--out-csv", type=Path, default=Path("daily_shortlist.csv"), help="CSV output path")
    parser.add_argument("--out-json", type=Path, default=Path("daily_shortlist.json"), help="JSON output path")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    automate(
        win_img=args.win_img,
        goals_img=args.goals_img,
        rules_path=args.rules,
        out_csv=args.out_csv,
        out_json=args.out_json,
    )
