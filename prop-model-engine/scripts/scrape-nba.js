#!/usr/bin/env node
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });
require("dotenv").config({ path: require("path").join(__dirname, "..", "..", ".env") });

const { runNbaStatsScrape } = require("../scrapers/nba-stats-scraper");
const { normalizeSport, todayStamp } = require("../lib/normalizer");
const db = require("../db/client");

async function main() {
  await db.initSchema();
  const date = process.env.SCRAPE_DATE || todayStamp();
  const result = await runNbaStatsScrape({ date });
  console.log("[nba] Normalizing raw files...");
  const norm = await normalizeSport({ sport: "nba", date });
  console.log("[nba] Normalize result:", norm);
  await db.close();
  const hardFail = (result.failed || []).some((f) => f.source === "nba-per36");
  process.exit(hardFail ? 1 : 0);
}

main().catch(async (err) => {
  console.error(err);
  try {
    await db.insertScrapeLog({
      source: "nba-stats-scraper",
      status: "failure",
      error_message: err.message || String(err),
    });
  } catch {
    /* ignore */
  }
  await db.close().catch(() => {});
  process.exit(1);
});
