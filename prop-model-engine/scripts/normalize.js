#!/usr/bin/env node
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });

const { normalizeSport, normalizeLatest, todayStamp } = require("../lib/normalizer");
const db = require("../db/client");

function main() {
  db.initSchema();
  const sport = (process.argv[2] || "all").toLowerCase();
  const date = process.env.SCRAPE_DATE || process.argv[3] || null;

  const sports = sport === "all" ? ["nba", "mlb"] : [sport];
  for (const s of sports) {
    if (!["nba", "mlb"].includes(s)) {
      console.error(`Unknown sport: ${s}`);
      process.exit(1);
    }
    const result = date
      ? normalizeSport({ sport: s, date })
      : normalizeLatest(s) || normalizeSport({ sport: s, date: todayStamp() });
    console.log(result);
  }
  db.close();
}

main();
