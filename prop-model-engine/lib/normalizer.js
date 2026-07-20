const fs = require("fs");
const path = require("path");
const config = require("../config");
const db = require("../db/client");
const { resolvePlayerName, slugifyPlayerId } = require("./name-alias-resolver");

/**
 * Common normalized row shape:
 * { player_id, player_name, team, sport, stat_type, value, source, scraped_at }
 */

function readRawFiles(sport, dateStr) {
  const dir = path.join(config.rawDir, sport, dateStr);
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => ({
      file: f,
      path: path.join(dir, f),
      data: JSON.parse(fs.readFileSync(path.join(dir, f), "utf8")),
    }));
}

function todayStamp() {
  return new Date().toISOString().slice(0, 10);
}

function listDateDirs(sport) {
  const base = path.join(config.rawDir, sport);
  if (!fs.existsSync(base)) return [];
  return fs
    .readdirSync(base)
    .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d))
    .sort();
}

function flattenNba(rawFiles) {
  const rows = [];
  for (const file of rawFiles) {
    const { data, file: fileName } = file;
    const scrapedAt = data.scraped_at || new Date().toISOString();
    const source = data.source || fileName.replace(/\.json$/, "");

    if (source.includes("per36") || source === "nba-per36") {
      for (const p of data.players || []) {
        const name = resolvePlayerName(p.name, { addAlias: true });
        const playerId = slugifyPlayerId("nba", name, p.team);
        const stats = {
          pts_per36: p.pts_per36,
          reb_per36: p.reb_per36,
          ast_per36: p.ast_per36,
          fg3_per36: p.fg3_per36,
          mp: p.mp,
          games: p.games,
        };
        for (const [stat_type, value] of Object.entries(stats)) {
          if (value == null || Number.isNaN(Number(value))) continue;
          rows.push({
            player_id: playerId,
            player_name: name,
            team: p.team || null,
            sport: "nba",
            position: p.position || null,
            stat_type,
            value: Number(value),
            source,
            scraped_at: scrapedAt,
            extra: p,
          });
        }
      }
    }

    if (source.includes("gamelog") || source === "nba-gamelogs") {
      for (const p of data.players || []) {
        const name = resolvePlayerName(p.name, { addAlias: true });
        const playerId = slugifyPlayerId("nba", name, p.team);
        rows.push({
          player_id: playerId,
          player_name: name,
          team: p.team || null,
          sport: "nba",
          position: p.position || null,
          stat_type: "l10_gamelog",
          value: null,
          source,
          scraped_at: scrapedAt,
          extra: { last10: p.last10 || [], games: p.games || [] },
        });
      }
    }

    if (source.includes("pace") || source === "nba-team-pace") {
      for (const t of data.teams || []) {
        rows.push({
          player_id: null,
          player_name: null,
          team: t.team,
          sport: "nba",
          position: null,
          stat_type: "team_pace",
          value: t.pace != null ? Number(t.pace) : null,
          source,
          scraped_at: scrapedAt,
          extra: t,
        });
      }
    }

    if (source.includes("dvp") || source === "nba-dvp") {
      for (const row of data.ranks || data.rows || []) {
        rows.push({
          player_id: null,
          player_name: null,
          team: row.team || null,
          sport: "nba",
          position: row.position || null,
          stat_type: "dvp",
          value: row.rank != null ? Number(row.rank) : null,
          source,
          scraped_at: scrapedAt,
          extra: row,
        });
      }
    }

    if (source.includes("injur") || source === "nba-injuries") {
      for (const inj of data.injuries || []) {
        const name = resolvePlayerName(inj.player || inj.name, { addAlias: true });
        const playerId = name ? slugifyPlayerId("nba", name, inj.team) : null;
        rows.push({
          player_id: playerId,
          player_name: name,
          team: inj.team || null,
          sport: "nba",
          position: inj.position || null,
          stat_type: "injury_status",
          value: null,
          source,
          scraped_at: scrapedAt,
          extra: inj,
        });
      }
    }
  }
  return rows;
}

function flattenMlb(rawFiles) {
  const rows = [];
  for (const file of rawFiles) {
    const { data, file: fileName } = file;
    const scrapedAt = data.scraped_at || new Date().toISOString();
    const source = data.source || fileName.replace(/\.json$/, "");

    if (source.includes("xstats") || source.includes("batting") || source === "mlb-batters") {
      for (const p of data.players || data.batters || []) {
        const name = resolvePlayerName(p.name, { addAlias: true });
        const playerId = slugifyPlayerId("mlb", name, p.team);
        const stats = {
          xba: p.xba ?? p.xBA,
          xslg: p.xslg ?? p.xSLG,
          avg: p.avg,
          slg: p.slg,
          vs_lhp_avg: p.vs_lhp_avg,
          vs_rhp_avg: p.vs_rhp_avg,
          vs_lhp_ops: p.vs_lhp_ops,
          vs_rhp_ops: p.vs_rhp_ops,
        };
        for (const [stat_type, value] of Object.entries(stats)) {
          if (value == null || Number.isNaN(Number(value))) continue;
          rows.push({
            player_id: playerId,
            player_name: name,
            team: p.team || null,
            sport: "mlb",
            position: p.position || null,
            stat_type,
            value: Number(value),
            source,
            scraped_at: scrapedAt,
            extra: p,
          });
        }
      }
    }

    if (source.includes("pitch") || source === "mlb-pitchers") {
      for (const p of data.players || data.pitchers || []) {
        const name = resolvePlayerName(p.name, { addAlias: true });
        const playerId = slugifyPlayerId("mlb", name, p.team);
        const stats = {
          k9: p.k9 ?? p["so9"] ?? p.SO9,
          ip: p.ip ?? p.IP,
          days_rest: p.days_rest,
          pitches: p.pitches,
        };
        for (const [stat_type, value] of Object.entries(stats)) {
          if (value == null || Number.isNaN(Number(value))) continue;
          rows.push({
            player_id: playerId,
            player_name: name,
            team: p.team || null,
            sport: "mlb",
            position: "P",
            stat_type,
            value: Number(value),
            source,
            scraped_at: scrapedAt,
            extra: p,
          });
        }
      }
    }

    if (source.includes("park") || source === "mlb-park-factors") {
      for (const pf of data.parks || data.factors || []) {
        rows.push({
          player_id: null,
          player_name: null,
          team: pf.team || pf.park || null,
          sport: "mlb",
          position: null,
          stat_type: "park_factor",
          value: pf.factor != null ? Number(pf.factor) : pf.batting_factor != null ? Number(pf.batting_factor) : null,
          source,
          scraped_at: scrapedAt,
          extra: pf,
        });
      }
    }
  }
  return rows;
}

function writeNormalizedRows(rows) {
  let playersUpserted = 0;
  let statsInserted = 0;

  async function run() {
    for (const row of rows) {
      if (row.player_id && row.player_name) {
        await db.upsertPlayer({
          id: row.player_id,
          name: row.player_name,
          team: row.team,
          sport: row.sport,
          position: row.position,
        });
        playersUpserted += 1;
      }

      await db.insertPlayerStatRaw({
        player_id: row.player_id,
        source: row.source,
        scraped_at: row.scraped_at,
        stat_json: {
          player_id: row.player_id,
          player_name: row.player_name,
          team: row.team,
          sport: row.sport,
          stat_type: row.stat_type,
          value: row.value,
          source: row.source,
          scraped_at: row.scraped_at,
          extra: row.extra || null,
        },
      });
      statsInserted += 1;
    }
    return { playersUpserted, statsInserted, rowCount: rows.length };
  }

  return run();
}

/**
 * Normalize raw JSON for a sport/date into the shared DB (Postgres via DATABASE_URL, else SQLite).
 * @param {{ sport: 'nba'|'mlb', date?: string }} opts
 */
async function normalizeSport({ sport, date } = {}) {
  if (!sport || !["nba", "mlb"].includes(sport)) {
    throw new Error("sport must be 'nba' or 'mlb'");
  }
  const dateStr = date || todayStamp();
  const files = readRawFiles(sport, dateStr);
  if (!files.length) {
    return {
      sport,
      date: dateStr,
      files: 0,
      playersUpserted: 0,
      statsInserted: 0,
      rowCount: 0,
      message: `No raw files in data/raw/${sport}/${dateStr}`,
    };
  }

  const rows = sport === "nba" ? flattenNba(files) : flattenMlb(files);
  const result = await writeNormalizedRows(rows);
  return { sport, date: dateStr, files: files.length, ...result };
}

async function normalizeLatest(sport) {
  const dates = listDateDirs(sport);
  if (!dates.length) {
    return { sport, message: "No raw date folders found", files: 0, rowCount: 0 };
  }
  return normalizeSport({ sport, date: dates[dates.length - 1] });
}

module.exports = {
  readRawFiles,
  flattenNba,
  flattenMlb,
  writeNormalizedRows,
  normalizeSport,
  normalizeLatest,
  listDateDirs,
  todayStamp,
};
