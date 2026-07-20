#!/usr/bin/env node
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });

const { runMlbStatsScrape } = require("../scrapers/mlb-stats-scraper");
const { normalizeSport, todayStamp } = require("../lib/normalizer");
const db = require("../db/client");

async function main() {
  db.initSchema();
  const date = process.env.SCRAPE_DATE || todayStamp();
  const result = await runMlbStatsScrape({ date });
  console.log("[mlb] Normalizing raw files...");
  const norm = normalizeSport({ sport: "mlb", date });
  console.log("[mlb] Normalize result:", norm);
  db.close();
  const hardFail = (result.failed || []).some((f) =>
    ["mlb-batters", "mlb-pitchers"].includes(f.source)
  );
  process.exit(hardFail ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  try {
    db.insertScrapeLog({
      source: "mlb-stats-scraper",
      status: "failure",
      error_message: err.message || String(err),
    });
  } catch {
    /* ignore */
  }
  process.exit(1);
});
