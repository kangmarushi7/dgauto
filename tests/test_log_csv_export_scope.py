"""Regression checks for Logs-tab CSV export scope."""
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

    def test_arahus_logs_remain_unchanged(self):
        for name in ARAHUS_TEMPLATES:
            with self.subTest(template=name):
                html = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
                self.assertNotIn('data-csv-export="1"', html)

    def test_table_tools_has_csv_export_menu_support(self):
        script = (STATIC_DIR / "table_tools.js").read_text(encoding="utf-8")
        self.assertIn('btn.textContent = "Export CSV"', script)
        self.assertIn("exportTableCsv(table);", script)
        self.assertIn("table?.dataset.csvExport === \"1\"", script)
        self.assertIn("attachCsvExportToolbar(table)", script)


if __name__ == "__main__":
    unittest.main()
