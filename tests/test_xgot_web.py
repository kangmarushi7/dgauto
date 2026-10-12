"""Tests for xGOT forward hub helpers and audit markdown render."""
from __future__ import annotations

import os
import tempfile
import unittest

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from app.db import init_db  # noqa: E402
from app.xgot_web import build_forward_hub, load_audit_html, markdown_to_simple_html  # noqa: E402


class MarkdownRenderTests(unittest.TestCase):
    def test_table_and_heading(self):
        md = "# Title\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        html = markdown_to_simple_html(md)
        self.assertIn("<h1>", html)
        self.assertIn("<table", html)
        self.assertIn("<th>", html)
        self.assertIn("<td>", html)


class HubTests(unittest.TestCase):
    def test_hub_has_variants_a_through_e(self):
        init_db()
        hub = build_forward_hub()
        self.assertEqual(set(hub["variants"]), {"A", "B", "C", "D", "E"})
        self.assertIn("xgot_fw_version", hub)
        self.assertIn("snapshots", hub)

    def test_audit_html_loads(self):
        audit = load_audit_html()
        self.assertTrue(audit["html"])
        self.assertIn("xGOT", audit["html"])


if __name__ == "__main__":
    unittest.main()
