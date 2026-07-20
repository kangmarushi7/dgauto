const fs = require("fs");
const path = require("path");
const config = require("../config");

let mode = null; // 'postgres' | 'sqlite'
let sqliteDb = null;
let pgPool = null;

function toPgParams(sql) {
  let i = 0;
  return sql.replace(/\?/g, () => `$${++i}`);
}

function ensureDir(filePath) {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function getMode() {
  if (mode) return mode;
  mode = config.databaseUrl ? "postgres" : "sqlite";
  return mode;
}

async function getPg() {
  if (pgPool) return pgPool;
  const { Pool } = require("pg");
  pgPool = new Pool({
    connectionString: config.databaseUrl,
    ssl: config.databaseUrl.includes("localhost") || config.databaseUrl.includes("127.0.0.1")
      ? false
      : { rejectUnauthorized: false },
  });
  return pgPool;
}

function getSqlite() {
  if (sqliteDb) return sqliteDb;
  const Database = require("better-sqlite3");
  ensureDir(config.dbPath);
  sqliteDb = new Database(config.dbPath);
  sqliteDb.pragma("journal_mode = WAL");
  sqliteDb.pragma("foreign_keys = ON");
  return sqliteDb;
}

async function initSchema() {
  const dialect = getMode();
  if (dialect === "postgres") {
    const pool = await getPg();
    const schemaPath = path.join(__dirname, "schema.postgres.sql");
    const sql = fs.readFileSync(schemaPath, "utf8");
    await pool.query(sql);
    return { dialect: "postgres", target: config.databaseUrl.replace(/:[^:@/]+@/, ":***@") };
  }
  const db = getSqlite();
  const schemaPath = path.join(__dirname, "schema.sqlite.sql");
  db.exec(fs.readFileSync(schemaPath, "utf8"));
  return { dialect: "sqlite", target: config.dbPath };
}

async function run(sql, params = []) {
  if (getMode() === "postgres") {
    const pool = await getPg();
    return pool.query(toPgParams(sql), params);
  }
  const stmt = getSqlite().prepare(sql);
  return stmt.run(...params);
}

async function query(sql, params = []) {
  if (getMode() === "postgres") {
    const pool = await getPg();
    const result = await pool.query(toPgParams(sql), params);
    return result.rows;
  }
  return getSqlite().prepare(sql).all(...params);
}

async function queryOne(sql, params = []) {
  const rows = await query(sql, params);
  return rows[0] || null;
}

async function upsertPlayer({ id, name, team, sport, position }) {
  if (getMode() === "postgres") {
    await run(
      `
      INSERT INTO pm_players (id, name, team, sport, position, updated_at)
      VALUES (?, ?, ?, ?, ?, NOW())
      ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        team = COALESCE(EXCLUDED.team, pm_players.team),
        sport = EXCLUDED.sport,
        position = COALESCE(EXCLUDED.position, pm_players.position),
        updated_at = NOW()
    `,
      [id, name, team || null, sport, position || null]
    );
    return;
  }
  await run(
    `
    INSERT INTO pm_players (id, name, team, sport, position, updated_at)
    VALUES (?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(id) DO UPDATE SET
      name = excluded.name,
      team = COALESCE(excluded.team, pm_players.team),
      sport = excluded.sport,
      position = COALESCE(excluded.position, pm_players.position),
      updated_at = datetime('now')
  `,
    [id, name, team || null, sport, position || null]
  );
}

async function insertPlayerStatRaw({ player_id, source, stat_json, scraped_at }) {
  const payload = typeof stat_json === "string" ? stat_json : JSON.stringify(stat_json);
  if (getMode() === "postgres") {
    await run(
      `
      INSERT INTO pm_player_stats_raw (player_id, source, stat_json, scraped_at)
      VALUES (?, ?, ?::jsonb, ?)
    `,
      [player_id || null, source, payload, scraped_at]
    );
    return;
  }
  await run(
    `
    INSERT INTO pm_player_stats_raw (player_id, source, stat_json, scraped_at)
    VALUES (?, ?, ?, ?)
  `,
    [player_id || null, source, payload, scraped_at]
  );
}

async function insertScrapeLog({ source, status, error_message = null, detail_json = null }) {
  const detail =
    detail_json == null
      ? null
      : typeof detail_json === "string"
        ? detail_json
        : JSON.stringify(detail_json);

  if (getMode() === "postgres") {
    await run(
      `
      INSERT INTO pm_scrape_log (source, status, error_message, detail_json, scraped_at)
      VALUES (?, ?, ?, ?::jsonb, NOW())
    `,
      [source, status, error_message, detail]
    );
    return;
  }
  await run(
    `
    INSERT INTO pm_scrape_log (source, status, error_message, detail_json, scraped_at)
    VALUES (?, ?, ?, ?, datetime('now'))
  `,
    [source, status, error_message, detail]
  );
}

async function getScrapeHealth(limit = 50) {
  return query(
    `
    SELECT id, source, status, error_message, detail_json, scraped_at
    FROM pm_scrape_log
    ORDER BY scraped_at DESC, id DESC
    LIMIT ?
  `,
    [limit]
  );
}

async function getLastScrapeBySource() {
  return query(`
    SELECT source, status, error_message, scraped_at
    FROM pm_scrape_log
    WHERE id IN (
      SELECT MAX(id) FROM pm_scrape_log GROUP BY source
    )
    ORDER BY source
  `);
}

async function getPlayerCounts() {
  return query(`
    SELECT sport, COUNT(*) AS count
    FROM pm_players
    GROUP BY sport
  `);
}

async function getRecentStats(limit = 100) {
  return query(
    `
    SELECT ps.id, ps.player_id, p.name AS player_name, p.team, p.sport,
           ps.source, ps.scraped_at, ps.stat_json
    FROM pm_player_stats_raw ps
    LEFT JOIN pm_players p ON p.id = ps.player_id
    ORDER BY ps.scraped_at DESC, ps.id DESC
    LIMIT ?
  `,
    [limit]
  );
}

async function close() {
  if (pgPool) {
    await pgPool.end();
    pgPool = null;
  }
  if (sqliteDb) {
    sqliteDb.close();
    sqliteDb = null;
  }
  mode = null;
}

module.exports = {
  getMode,
  initSchema,
  upsertPlayer,
  insertPlayerStatRaw,
  insertScrapeLog,
  query,
  queryOne,
  getScrapeHealth,
  getLastScrapeBySource,
  getPlayerCounts,
  getRecentStats,
  close,
};
