/**
 * Smoke test for table CSV export helpers (mirrors static/table_tools.js).
 * Run: node tests/test_table_csv_export.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = readFileSync(join(root, "static/table_tools.js"), "utf8");

assert.match(src, /function tableToCsv\(/);
assert.match(src, /function mountCsvExportButton\(/);
assert.match(src, /data-csv-export/);
assert.match(src, /Export CSV/);
assert.match(src, /exportCsv:/);

function csvEscape(value) {
  const s = String(value ?? "");
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

assert.equal(csvEscape("plain"), "plain");
assert.equal(csvEscape('a,b'), '"a,b"');
assert.equal(csvEscape('say "hi"'), '"say ""hi"""');
assert.equal(csvEscape("line\nbreak"), '"line\nbreak"');

const templates = [
  "templates/lm_bet_log.html",
  "templates/no_bet_log.html",
  "templates/h2h_bet_log.html",
  "templates/plus_ev_bet_log.html",
  "templates/cs_bet_log.html",
  "templates/prop_model_bet_log.html",
];
for (const t of templates) {
  const html = readFileSync(join(root, t), "utf8");
  assert.match(html, /data-csv-export="/, `${t} missing data-csv-export`);
}

for (const t of ["templates/arahus_bet_log.html", "templates/arahus_v2_bet_log.html"]) {
  const html = readFileSync(join(root, t), "utf8");
  assert.doesNotMatch(html, /data-csv-export=/, `${t} should not have csv export attr`);
}

console.log("test_table_csv_export.mjs: ok");
