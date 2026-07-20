const fs = require("fs");
const path = require("path");
const config = require("../config");

function todayStamp() {
  return new Date().toISOString().slice(0, 10);
}

function ensureRawDir(sport, dateStr = todayStamp()) {
  const dir = path.join(config.rawDir, sport, dateStr);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function writeRawJson(sport, dataType, payload, dateStr = todayStamp()) {
  const dir = ensureRawDir(sport, dateStr);
  const filePath = path.join(dir, `${dataType}.json`);
  const body = {
    source: dataType,
    scraped_at: new Date().toISOString(),
    ...payload,
  };
  fs.writeFileSync(filePath, JSON.stringify(body, null, 2), "utf8");
  return filePath;
}

function printRunSummary(label, { succeeded = [], failed = [] }) {
  console.log("\n========================================");
  console.log(`${label} summary`);
  console.log(`  succeeded: ${succeeded.length}`);
  console.log(`  failed:    ${failed.length}`);
  if (failed.length) {
    console.log("  failures:");
    for (const f of failed) {
      console.log(`    - ${f.source || f.player || "unknown"}: ${f.error}`);
    }
  }
  console.log("========================================\n");
}

module.exports = {
  todayStamp,
  ensureRawDir,
  writeRawJson,
  printRunSummary,
};
