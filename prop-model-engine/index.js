#!/usr/bin/env node
/**
 * Prop Model Engine — scheduler entrypoint (Phase 1).
 * Uses DATABASE_URL Postgres when set (same DB as DG app); otherwise local SQLite.
 */
require("dotenv").config({ path: require("path").join(__dirname, ".env") });
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });

const cron = require("node-cron");
const config = require("./config");
const db = require("./db/client");
const { runNbaStatsScrape } = require("./scrapers/nba-stats-scraper");
const { runMlbStatsScrape } = require("./scrapers/mlb-stats-scraper");
const { normalizeSport, todayStamp } = require("./lib/normalizer");

async function runNbaJob() {
  const date = todayStamp();
  console.log(`[cron] NBA job ${date}`);
  try {
    await runNbaStatsScrape({ date });
    console.log("[cron] NBA normalize:", await normalizeSport({ sport: "nba", date }));
  } catch (err) {
    console.error("[cron] NBA job failed:", err.message || err);
    await db.insertScrapeLog({
      source: "nba-cron",
      status: "failure",
      error_message: err.message || String(err),
    });
  }
}

async function runMlbJob() {
  const date = todayStamp();
  console.log(`[cron] MLB job ${date}`);
  try {
    await runMlbStatsScrape({ date });
    console.log("[cron] MLB normalize:", await normalizeSport({ sport: "mlb", date }));
  } catch (err) {
    console.error("[cron] MLB job failed:", err.message || err);
    await db.insertScrapeLog({
      source: "mlb-cron",
      status: "failure",
      error_message: err.message || String(err),
    });
  }
}

async function main() {
  const info = await db.initSchema();
  console.log("Prop Model Engine scheduler starting");
  console.log(`  dialect: ${info.dialect}`);
  console.log(`  target:  ${info.target}`);
  console.log(`  NBA cron: ${config.nbaCron}`);
  console.log(`  MLB cron: ${config.mlbCron}`);

  if (!cron.validate(config.nbaCron) || !cron.validate(config.mlbCron)) {
    console.error("Invalid cron expression in config");
    process.exit(1);
  }

  cron.schedule(config.nbaCron, () => {
    runNbaJob();
  });
  cron.schedule(config.mlbCron, () => {
    runMlbJob();
  });

  console.log("Scheduler armed. Use npm run scrape:nba / scrape:mlb for manual runs.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
