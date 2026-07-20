#!/usr/bin/env node
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });

const { runNbaStatsScrape } = require("../scrapers/nba-stats-scraper");
const { normalizeSport, todayStamp } = require("../lib/normalizer");
const db = require("../db/client");

async function main() {
  db.initSchema();
  const date = process.env.SCRAPE_DATE || todayStamp();
  const result = await runNbaStatsScrape({ date });
  console.log("[nba] Normalizing raw files...");
  const norm = normalizeSport({ sport: "nba", date });
  console.log("[nba] Normalize result:", norm);
  db.close();
  const hardFail = (result.failed || []).some((f) => f.source === "nba-per36");
  process.exit(hardFail ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  try {
    db.insertScrapeLog({
      source: "nba-stats-scraper",
      status: "failure",
      error_message: err.message || String(err),
    });
  } catch {
    /* ignore */
  }
  process.exit(1);
});
