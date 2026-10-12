"""Website helpers for xGOT forward hub and forensic audit page."""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.db import dg_fixture_snapshots, engine, init_db, list_bets
from app.xgot_metrics import financial_stats, fixture_cluster_note, outcome_stats
from app.xgot_research import LOG_TYPES, XGOT_FW_VERSION, XGOT_RESEARCH_SYNC_ENABLED
from app.xgot_strat import BASELINE_STRATEGY_VERSION, enrich_xgot_entries, xgot_dashboard

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_REPORT_PATH = REPO_ROOT / "analysis" / "xgot_forensic_audit" / "REPORT.md"

VARIANT_META: dict[str, dict[str, str]] = {
    "A": {
        "label": "A · Baseline",
        "log_type": "xgot",
        "rule": "All eligible × markets (unchanged)",
        "href": "/xgot-bet-log",
    },
    "B": {
        "label": "B · O2.5 xGOT[3.0,3.5)",
        "log_type": "xgot_fw_b",
        "rule": "O2.5 only when 3.0 ≤ total < 3.5",
        "href": "/xgot-fw-b-bet-log",
    },
    "C": {
        "label": "C · BTTS minHA[1.2,1.5)",
        "log_type": "xgot_fw_c",
        "rule": "BTTS only when 1.2 ≤ min(H,A) < 1.5",
        "href": "/xgot-fw-c-bet-log",
    },
    "D": {
        "label": "D · No O3.5",
        "log_type": "xgot_fw_d",
        "rule": "Baseline markets minus O3.5",
        "href": "/xgot-fw-d-bet-log",
    },
    "E": {
        "label": "E · SOT 7.5/8.5/9.5",
        "log_type": "xgot_fw_e",
        "rule": "SOT lines ∈ {7.5,8.5,9.5}; ROI needs real odds",
        "href": "/xgot-fw-e-bet-log",
    },
}


def _summarize_log(log_type: str) -> dict[str, Any]:
    entries = list_bets(log_type)
    out = outcome_stats(entries)
    fin = financial_stats(entries)
    cluster = fixture_cluster_note(entries)
    return {**out, **fin, **cluster, "log_type": log_type}


def snapshot_stats() -> dict[str, Any]:
    init_db()
    with engine.connect() as conn:
        count = conn.execute(select(func.count()).select_from(dg_fixture_snapshots)).scalar() or 0
        latest = (
            conn.execute(
                select(dg_fixture_snapshots.c.scraped_at, dg_fixture_snapshots.c.fixture_count)
                .order_by(dg_fixture_snapshots.c.scraped_at.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
    return {
        "count": int(count),
        "latest_scraped_at": (latest or {}).get("scraped_at"),
        "latest_fixture_count": (latest or {}).get("fixture_count"),
    }


def build_forward_hub() -> dict[str, Any]:
    variants: dict[str, Any] = {}
    for vid, meta in VARIANT_META.items():
        stats = _summarize_log(meta["log_type"])
        variants[vid] = {**meta, **stats}
    return {
        "xgot_fw_version": XGOT_FW_VERSION,
        "baseline_version": BASELINE_STRATEGY_VERSION,
        "research_sync_enabled": XGOT_RESEARCH_SYNC_ENABLED,
        "snapshots": snapshot_stats(),
        "variants": variants,
        "audit_href": "/xgot-audit",
        "strat_href": "/xgot-strat",
    }


def load_audit_markdown() -> str:
    if not AUDIT_REPORT_PATH.is_file():
        return "# Audit report missing\n\nExpected file not found on server."
    return AUDIT_REPORT_PATH.read_text(encoding="utf-8")


def _inline_md(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def markdown_to_simple_html(md: str) -> str:
    """Small GFM-ish renderer (headings, lists, tables, hr, paragraphs) — no extra deps."""
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_list = False
    in_code = False
    code_buf: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
                code_buf = []
                in_code = False
            else:
                close_list()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # GFM table: header | --- | rows
        if (
            "|" in line
            and i + 1 < len(lines)
            and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1].replace("|", " | "))
        ):
            close_list()
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append('<div class="table-wrap"><table class="audit-table">')
            out.append("<thead><tr>" + "".join(f"<th>{_inline_md(c)}</th>" for c in header) + "</tr></thead>")
            out.append("<tbody>")
            for row in rows:
                # pad/trunc to header width
                while len(row) < len(header):
                    row.append("")
                out.append("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in row[: len(header)]) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        if re.match(r"^-{3,}\s*$", line.strip()):
            close_list()
            out.append("<hr />")
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            close_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline_md(m.group(2))}</h{level}>")
            i += 1
            continue

        if re.match(r"^[-*]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^[-*]\s+", "", line)
            out.append(f"<li>{_inline_md(item)}</li>")
            i += 1
            continue

        if not line.strip():
            close_list()
            i += 1
            continue

        close_list()
        out.append(f"<p>{_inline_md(line)}</p>")
        i += 1

    close_list()
    if in_code:
        out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
    return "\n".join(out)


def load_audit_html() -> dict[str, Any]:
    md = load_audit_markdown()
    return {
        "markdown": md,
        "html": markdown_to_simple_html(md),
        "source_path": "analysis/xgot_forensic_audit/REPORT.md",
    }


def fw_variant_key(slug: str) -> str | None:
    key = str(slug or "").strip().upper()
    return key if key in LOG_TYPES else None


def load_fw_log_payload(variant_id: str, *, season_payload_fn) -> dict[str, Any]:
    """Build strat-log payload for a research variant."""
    key = fw_variant_key(variant_id)
    if key is None:
        raise ValueError(f"Unknown variant {variant_id!r}")
    log_type = LOG_TYPES[key]
    entries = enrich_xgot_entries(list_bets(log_type))
    return season_payload_fn(entries, xgot_dashboard)
