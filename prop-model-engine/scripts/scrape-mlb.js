#!/usr/bin/env node
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });
require("dotenv").config({ path: require("path").join(__dirname, "..", "..", ".env") });

const { runMlbStatsScrape } = require("../scrapers/mlb-stats-scraper");
const { normalizeSport, todayStamp } = require("../lib/normalizer");
const db = require("../db/client");

async function main() {
  await db.initSchema();
  const date = process.env.SCRAPE_DATE || todayStamp();
  const result = await runMlbStatsScrape({ date });
  console.log("[mlb] Normalizing raw files...");
  const norm = await normalizeSport({ sport: "mlb", date });
  console.log("[mlb] Normalize result:", norm);
  await db.close();
  const hardFail = (result.failed || []).some((f) =>
    ["mlb-batters", "mlb-pitchers"].includes(f.source)
  );
  process.exit(hardFail ? 1 : 0);
}

main().catch(async (err) => {
  console.error(err);
  try {
    await db.insertScrapeLog({
      source: "mlb-stats-scraper",
      status: "failure",
      error_message: err.message || String(err),
    });
  } catch {
    /* ignore */
  }
  await db.close().catch(() => {});
  process.exit(1);
});
