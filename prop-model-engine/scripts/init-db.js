#!/usr/bin/env node
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });
require("dotenv").config({ path: require("path").join(__dirname, "..", "..", ".env") });

const db = require("../db/client");
const config = require("../config");

async function main() {
  const info = await db.initSchema();
  console.log("Prop Model DB initialized");
  console.log(`  dialect: ${info.dialect}`);
  console.log(`  target:  ${info.target}`);
  if (info.dialect === "postgres") {
    console.log("  using shared DATABASE_URL (same Postgres as DG app)");
  } else {
    console.log(`  DATABASE_URL unset — local SQLite at ${config.dbPath}`);
  }
  await db.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
