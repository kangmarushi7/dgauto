const fs = require("fs");
const path = require("path");
const Database = require("better-sqlite3");
const config = require("../config");

let db;

function ensureDir(filePath) {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function getDb() {
  if (db) return db;
  ensureDir(config.dbPath);
  db = new Database(config.dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  initSchema(db);
  return db;
}

function initSchema(database = getDb()) {
  const schemaPath = path.join(__dirname, "schema.sql");
  const sql = fs.readFileSync(schemaPath, "utf8");
  database.exec(sql);
}

function upsertPlayer({ id, name, team, sport, position }) {
  const stmt = getDb().prepare(`
    INSERT INTO players (id, name, team, sport, position, updated_at)
    VALUES (@id, @name, @team, @sport, @position, datetime('now'))
    ON CONFLICT(id) DO UPDATE SET
      name = excluded.name,
      team = COALESCE(excluded.team, players.team),
      sport = excluded.sport,
      position = COALESCE(excluded.position, players.position),
      updated_at = datetime('now')
  `);
  return stmt.run({ id, name, team: team || null, sport, position: position || null });
}

function insertPlayerStatRaw({ player_id, source, stat_json, scraped_at }) {
  const stmt = getDb().prepare(`
    INSERT INTO player_stats_raw (player_id, source, stat_json, scraped_at)
    VALUES (?, ?, ?, ?)
  `);
  const payload = typeof stat_json === "string" ? stat_json : JSON.stringify(stat_json);
  return stmt.run(player_id || null, source, payload, scraped_at);
}

function insertScrapeLog({ source, status, error_message = null, detail_json = null }) {
  const stmt = getDb().prepare(`
    INSERT INTO scrape_log (source, status, error_message, detail_json, scraped_at)
    VALUES (?, ?, ?, ?, datetime('now'))
  `);
  const detail =
    detail_json == null
      ? null
      : typeof detail_json === "string"
        ? detail_json
        : JSON.stringify(detail_json);
  return stmt.run(source, status, error_message, detail);
}

function query(sql, params = []) {
  return getDb().prepare(sql).all(...params);
}

function queryOne(sql, params = []) {
  return getDb().prepare(sql).get(...params);
}

function getScrapeHealth(limit = 50) {
  return query(
    `
    SELECT id, source, status, error_message, detail_json, scraped_at
    FROM scrape_log
    ORDER BY scraped_at DESC, id DESC
    LIMIT ?
  `,
    [limit]
  );
}

function getLastScrapeBySource() {
  return query(`
    SELECT source, status, error_message, scraped_at
    FROM scrape_log
    WHERE id IN (
      SELECT MAX(id) FROM scrape_log GROUP BY source
    )
    ORDER BY source
  `);
}

function getPlayerCounts() {
  return query(`
    SELECT sport, COUNT(*) AS count
    FROM players
    GROUP BY sport
  `);
}

function getRecentStats(limit = 100) {
  return query(
    `
    SELECT ps.id, ps.player_id, p.name AS player_name, p.team, p.sport,
           ps.source, ps.scraped_at, ps.stat_json
    FROM player_stats_raw ps
    LEFT JOIN players p ON p.id = ps.player_id
    ORDER BY ps.scraped_at DESC, ps.id DESC
    LIMIT ?
  `,
    [limit]
  );
}

function close() {
  if (db) {
    db.close();
    db = null;
  }
}

module.exports = {
  getDb,
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
