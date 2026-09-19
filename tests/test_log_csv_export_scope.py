"""Regression checks for Logs-tab CSV / Excel export scope."""
from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"
STATIC_DIR = REPO_ROOT / "static"

CSV_ENABLED_TEMPLATES = [
    "lm_bet_log.html",
    "no_bet_log.html",
    "h2h_bet_log.html",
    "plus_ev_bet_log.html",
    "cs_bet_log.html",
    "prop_model_bet_log.html",
]

ARAHUS_TEMPLATES = [
    "arahus_bet_log.html",
    "arahus_v2_bet_log.html",
]


class LogCsvExportScopeTests(unittest.TestCase):
    def test_non_arahus_logs_enable_csv_export(self):
        for name in CSV_ENABLED_TEMPLATES:
            with self.subTest(template=name):
                html = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
                self.assertIn('data-csv-export="1"', html)

    def test_arahus_logs_do_not_enable_csv_export(self):
        for name in ARAHUS_TEMPLATES:
            with self.subTest(template=name):
                html = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
                self.assertNotIn('data-csv-export="1"', html)

    def test_arahus_logs_enable_excel_export(self):
        expected = {
            "arahus_bet_log.html": 'data-excel-filename="arahus-log"',
            "arahus_v2_bet_log.html": 'data-excel-filename="arahus-v2-log"',
        }
        for name, filename_attr in expected.items():
            with self.subTest(template=name):
                html = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
                self.assertIn('data-excel-export="1"', html)
                self.assertIn(filename_attr, html)

    def test_table_tools_has_csv_export_menu_support(self):
        script = (STATIC_DIR / "table_tools.js").read_text(encoding="utf-8")
        self.assertIn('btn.textContent = "Export CSV"', script)
        self.assertIn("exportTableCsv(table)", script)
        self.assertIn('table?.dataset.csvExport === "1"', script)
        self.assertIn("attachExportToolbar(table)", script)

    def test_table_tools_has_excel_export_support(self):
        script = (STATIC_DIR / "table_tools.js").read_text(encoding="utf-8")
        self.assertIn('btn.textContent = "Export Excel"', script)
        self.assertIn("exportTableExcel(table)", script)
        self.assertIn('table?.dataset.excelExport === "1"', script)
        self.assertIn("buildXlsxBytes", script)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", script)


if __name__ == "__main__":
    unittest.main()
