"""Convert a markdown report to PDF (tables + headings)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD = ROOT / "data" / "strategy_profitability_report.md"
DEFAULT_OUT = ROOT / "data" / "strategy_profitability_report.pdf"


class ReportPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")


def clean(text: str) -> str:
    text = text.replace("**", "")
    text = text.replace("`", "")
    text = text.replace("·", "|")
    repl = {
        "–": "-",
        "—": "-",
        "−": "-",
        "×": "x",
        "≥": ">=",
        "≤": "<=",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
    for a, b in repl.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def parse_table_row(line: str) -> list[str]:
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return [clean(p) for p in parts]


def is_sep(line: str) -> bool:
    return bool(re.match(r"^\|?\s*:?-{3,}", line.strip()))


def render_md_to_pdf(md_path: Path, pdf_path: Path) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    pdf = ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_margins(12, 12, 12)

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue

        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 15)
            pdf.set_text_color(20, 20, 20)
            pdf.multi_cell(0, 7, clean(line[2:]))
            pdf.ln(2)
            i += 1
            continue

        if line.startswith("## "):
            if pdf.get_y() > 250:
                pdf.add_page()
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(30, 30, 30)
            pdf.multi_cell(0, 6, clean(line[3:]))
            pdf.ln(1)
            i += 1
            continue

        if line.startswith("### "):
            pdf.ln(1)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 5, clean(line[4:]))
            pdf.ln(0.5)
            i += 1
            continue

        if line.startswith("#### "):
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 5, clean(line[5:]))
            i += 1
            continue

        if line.strip().startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not is_sep(lines[i]):
                    rows.append(parse_table_row(lines[i]))
                i += 1
            if not rows:
                continue
            cols = max(len(r) for r in rows)
            for r in rows:
                while len(r) < cols:
                    r.append("")
            usable = pdf.w - pdf.l_margin - pdf.r_margin
            if cols >= 5:
                first = usable * 0.28
                rest = (usable - first) / (cols - 1)
                widths = [first] + [rest] * (cols - 1)
            elif cols >= 2:
                first = usable * 0.36
                rest = (usable - first) / (cols - 1)
                widths = [first] + [rest] * (cols - 1)
            else:
                widths = [usable]

            font_size = 7 if cols >= 7 else 8
            for ri, row in enumerate(rows):
                if ri == 0:
                    pdf.set_font("Helvetica", "B", font_size)
                    pdf.set_fill_color(31, 78, 121)
                    pdf.set_text_color(255, 255, 255)
                else:
                    pdf.set_font("Helvetica", "", font_size)
                    pdf.set_text_color(30, 30, 30)
                    if ri % 2 == 0:
                        pdf.set_fill_color(245, 247, 250)
                    else:
                        pdf.set_fill_color(255, 255, 255)
                h = 5
                for j, cell in enumerate(row):
                    cw = widths[j] - 1.5
                    chars = max(1, int(cw / 1.5))
                    h = max(h, 4 + 3.2 * (len(cell) // chars))
                if pdf.get_y() + h > pdf.h - 16:
                    pdf.add_page()
                y0 = pdf.get_y()
                x0 = pdf.l_margin
                for j, cell in enumerate(row):
                    pdf.set_xy(x0 + sum(widths[:j]), y0)
                    align = "C" if ri == 0 else ("L" if j == 0 else "R")
                    pdf.multi_cell(widths[j], 4, cell, border=0, fill=True, align=align)
                pdf.set_y(y0 + h)
                pdf.set_x(pdf.l_margin)
            pdf.ln(1.5)
            pdf.set_x(pdf.l_margin)
            continue

        # bullets / paragraphs
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        text = clean(line)
        if len(text) > 450:
            text = text[:450] + "..."
        pdf.multi_cell(pdf.epw, 4.5, text)
        pdf.ln(0.5)
        i += 1

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    print(f"Wrote {pdf_path} ({pdf_path.stat().st_size} bytes)")


def main() -> None:
    md = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MD
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    if not md.is_absolute():
        md = ROOT / md
    if not out.is_absolute():
        out = ROOT / out
    render_md_to_pdf(md, out)


if __name__ == "__main__":
    main()
