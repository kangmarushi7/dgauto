const config = require("../config");
const db = require("../db/client");
const { withPage, gotoSafe, randomDelay } = require("../lib/browser");
const { writeRawJson, printRunSummary, todayStamp } = require("../lib/io");

function parseNum(text) {
  if (text == null) return null;
  const cleaned = String(text).replace(/,/g, "").trim();
  if (!cleaned || cleaned === "" || cleaned === "-") return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

async function scrapePer36(page, year) {
  const url = config.sources.nba.per36(year);
  await gotoSafe(page, url);
  // Basketball-Reference often comments out tables for bots; uncomment if needed
  await page.evaluate(() => {
    document.querySelectorAll("comment, noscript").forEach(() => {});
    const comments = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
    let node;
    while ((node = walker.nextNode())) comments.push(node);
    for (const c of comments) {
      const wrap = document.createElement("div");
      wrap.innerHTML = c.nodeValue || "";
      c.parentNode?.insertBefore(wrap, c);
    }
  });

  const players = await page.evaluate(() => {
    const table =
      document.querySelector("#per_minute_stats") ||
      document.querySelector("table#per_minute") ||
      document.querySelector("table.stats_table");
    if (!table) return [];
    const rows = Array.from(table.querySelectorAll("tbody tr")).filter(
      (tr) => !tr.classList.contains("thead")
    );
    return rows
      .map((tr) => {
        const nameEl = tr.querySelector('[data-stat="player"] a, td[data-stat="player"] a');
        const name = nameEl?.textContent?.trim();
        const href = nameEl?.getAttribute("href") || "";
        if (!name) return null;
        const get = (stat) => tr.querySelector(`[data-stat="${stat}"]`)?.textContent?.trim() || null;
        return {
          name,
          player_path: href.replace(/\/gamelog.*$/, "").replace(/\.html$/, ""),
          team: get("team_id") || get("team"),
          position: get("pos"),
          games: get("g"),
          mp: get("mp"),
          pts_per36: get("pts"),
          reb_per36: get("trb"),
          ast_per36: get("ast"),
          fg3_per36: get("fg3"),
        };
      })
      .filter(Boolean);
  });

  return players.map((p) => ({
    ...p,
    games: parseNum(p.games),
    mp: parseNum(p.mp),
    pts_per36: parseNum(p.pts_per36),
    reb_per36: parseNum(p.reb_per36),
    ast_per36: parseNum(p.ast_per36),
    fg3_per36: parseNum(p.fg3_per36),
  }));
}

async function scrapeTeamPace(page, year) {
  const url = config.sources.nba.teamStats(year);
  await gotoSafe(page, url);
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
    let node;
    while ((node = walker.nextNode())) {
      const wrap = document.createElement("div");
      wrap.innerHTML = node.nodeValue || "";
      node.parentNode?.insertBefore(wrap, node);
    }
  });

  const teams = await page.evaluate(() => {
    const table =
      document.querySelector("#advanced-team") ||
      document.querySelector("table#advanced_team") ||
      document.querySelector("#team_misc") ||
      document.querySelector("table.stats_table");
    if (!table) return [];
    return Array.from(table.querySelectorAll("tbody tr"))
      .filter((tr) => !tr.classList.contains("thead"))
      .map((tr) => {
        const team =
          tr.querySelector('[data-stat="team"] a, [data-stat="team_name"] a, td[data-stat="team"]')
            ?.textContent?.trim() || null;
        const pace = tr.querySelector('[data-stat="pace"]')?.textContent?.trim() || null;
        if (!team) return null;
        return { team, pace };
      })
      .filter(Boolean);
  });

  return teams.map((t) => ({ team: t.team, pace: parseNum(t.pace) }));
}

async function scrapeGameLog(page, player, year) {
  if (!player.player_path) return { name: player.name, team: player.team, last10: [], games: [] };
  const url = config.sources.nba.gameLog(player.player_path, year);
  await gotoSafe(page, url);
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
    let node;
    while ((node = walker.nextNode())) {
      const wrap = document.createElement("div");
      wrap.innerHTML = node.nodeValue || "";
      node.parentNode?.insertBefore(wrap, node);
    }
  });

  const games = await page.evaluate(() => {
    const table =
      document.querySelector("#pgl_basic") ||
      document.querySelector("table#pgl_basic_playoffs") ||
      document.querySelector("table.stats_table");
    if (!table) return [];
    return Array.from(table.querySelectorAll("tbody tr"))
      .filter((tr) => !tr.classList.contains("thead") && !tr.querySelector('[data-stat="reason"]'))
      .map((tr) => {
        const get = (stat) => tr.querySelector(`[data-stat="${stat}"]`)?.textContent?.trim() || null;
        const date = get("date_game") || get("date");
        if (!date) return null;
        return {
          date,
          opp: get("opp_id") || get("opp"),
          mp: get("mp"),
          pts: get("pts"),
          trb: get("trb"),
          ast: get("ast"),
          fg3: get("fg3"),
        };
      })
      .filter(Boolean);
  });

  const parsed = games.map((g) => ({
    ...g,
    pts: parseNum(g.pts),
    trb: parseNum(g.trb),
    ast: parseNum(g.ast),
    fg3: parseNum(g.fg3),
  }));
  const last10 = parsed.slice(-10);
  return {
    name: player.name,
    team: player.team,
    position: player.position,
    player_path: player.player_path,
    games: parsed,
    last10,
  };
}

async function scrapeDvp(page) {
  const url = config.sources.nba.dvp;
  await gotoSafe(page, url, { waitUntil: "networkidle" });
  const ranks = await page.evaluate(() => {
    const table = document.querySelector("table") || document.querySelector(".table");
    if (!table) return [];
    const headers = Array.from(table.querySelectorAll("thead th, tr:first-child th, tr:first-child td")).map(
      (el) => el.textContent.trim().toLowerCase()
    );
    return Array.from(table.querySelectorAll("tbody tr, tr"))
      .slice(1)
      .map((tr) => {
        const cells = Array.from(tr.querySelectorAll("td")).map((td) => td.textContent.trim());
        if (cells.length < 2) return null;
        return {
          team: cells[0],
          position: headers.includes("pos") || headers.includes("position") ? cells[1] : null,
          pts_rank: cells.find((_, i) => (headers[i] || "").includes("pts")) || cells[2] || null,
          reb_rank: cells.find((_, i) => (headers[i] || "").includes("reb")) || null,
          ast_rank: cells.find((_, i) => (headers[i] || "").includes("ast")) || null,
          raw: cells,
        };
      })
      .filter(Boolean);
  });
  return ranks;
}

async function scrapeInjuries(page) {
  const url = config.sources.nba.injuries;
  await gotoSafe(page, url, { waitUntil: "networkidle" });
  const injuries = await page.evaluate(() => {
    const rows = Array.from(
      document.querySelectorAll("table tbody tr, .injury-report tr, .is-table tbody tr")
    );
    return rows
      .map((tr) => {
        const cells = Array.from(tr.querySelectorAll("td")).map((td) => td.textContent.trim());
        if (cells.length < 2) return null;
        // Rotowire columns often: Team, Pos, Player, Injury, Status, ...
        const player =
          tr.querySelector("a")?.textContent?.trim() ||
          cells.find((c) => c.length > 2 && /[A-Za-z]/.test(c)) ||
          null;
        return {
          team: cells[0] || null,
          position: cells[1] || null,
          player,
          injury: cells[3] || cells[2] || null,
          status: cells[4] || cells[cells.length - 1] || null,
          raw: cells,
        };
      })
      .filter((r) => r && r.player);
  });
  return injuries;
}

/**
 * Full NBA stats scrape run. Never throws for per-player failures.
 */
async function runNbaStatsScrape({ date = todayStamp(), playerLimit = config.nbaPlayerLimit } = {}) {
  const year = config.nbaSeasonYear;
  const succeeded = [];
  const failed = [];
  const summary = { date, year, files: [] };

  console.log(`[nba] Starting stats scrape for season ${year} (${date})`);

  await withPage(async (page) => {
    // --- Per-36 ---
    try {
      console.log("[nba] Scraping per-36 rates...");
      const players = await scrapePer36(page, year);
      const file = writeRawJson("nba", "nba-per36", { season_year: year, players }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "nba-per36",
        status: players.length ? "success" : "partial",
        detail_json: { count: players.length, file },
      });
      succeeded.push({ source: "nba-per36", count: players.length });
      console.log(`[nba] per-36: ${players.length} players`);

      // --- Game logs (sample / limited for politeness) ---
      let list = players.filter((p) => p.player_path);
      if (playerLimit > 0) list = list.slice(0, playerLimit);
      else list = list.slice(0, 40); // default soft cap to avoid IP bans on first runs

      const gamelogs = [];
      for (const player of list) {
        try {
          await randomDelay();
          console.log(`[nba] game log: ${player.name}`);
          const log = await scrapeGameLog(page, player, year);
          gamelogs.push(log);
          succeeded.push({ source: `nba-gamelog:${player.name}` });
        } catch (err) {
          const msg = err.message || String(err);
          console.warn(`[nba] game log failed for ${player.name}: ${msg}`);
          failed.push({ source: `nba-gamelog:${player.name}`, error: msg });
          db.insertScrapeLog({
            source: `nba-gamelog:${player.name}`,
            status: "failure",
            error_message: msg,
          });
        }
      }
      const glFile = writeRawJson("nba", "nba-gamelogs", { season_year: year, players: gamelogs }, date);
      summary.files.push(glFile);
      db.insertScrapeLog({
        source: "nba-gamelogs",
        status: gamelogs.length ? "success" : "partial",
        detail_json: { count: gamelogs.length, file: glFile },
      });
    } catch (err) {
      const msg = err.message || String(err);
      console.error(`[nba] per-36 failed: ${msg}`);
      failed.push({ source: "nba-per36", error: msg });
      db.insertScrapeLog({ source: "nba-per36", status: "failure", error_message: msg });
    }

    // --- Team pace ---
    try {
      await randomDelay();
      console.log("[nba] Scraping team pace...");
      const teams = await scrapeTeamPace(page, year);
      const file = writeRawJson("nba", "nba-team-pace", { season_year: year, teams }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "nba-team-pace",
        status: teams.length ? "success" : "partial",
        detail_json: { count: teams.length, file },
      });
      succeeded.push({ source: "nba-team-pace", count: teams.length });
    } catch (err) {
      const msg = err.message || String(err);
      failed.push({ source: "nba-team-pace", error: msg });
      db.insertScrapeLog({ source: "nba-team-pace", status: "failure", error_message: msg });
    }

    // --- DvP ---
    try {
      await randomDelay();
      console.log("[nba] Scraping DvP ranks...");
      const ranks = await scrapeDvp(page);
      const file = writeRawJson("nba", "nba-dvp", { ranks }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "nba-dvp",
        status: ranks.length ? "success" : "partial",
        detail_json: { count: ranks.length, file },
      });
      succeeded.push({ source: "nba-dvp", count: ranks.length });
    } catch (err) {
      const msg = err.message || String(err);
      failed.push({ source: "nba-dvp", error: msg });
      db.insertScrapeLog({ source: "nba-dvp", status: "failure", error_message: msg });
    }

    // --- Injuries ---
    try {
      await randomDelay();
      console.log("[nba] Scraping injury report...");
      const injuries = await scrapeInjuries(page);
      const file = writeRawJson("nba", "nba-injuries", { injuries }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "nba-injuries",
        status: injuries.length ? "success" : "partial",
        detail_json: { count: injuries.length, file },
      });
      succeeded.push({ source: "nba-injuries", count: injuries.length });
    } catch (err) {
      const msg = err.message || String(err);
      failed.push({ source: "nba-injuries", error: msg });
      db.insertScrapeLog({ source: "nba-injuries", status: "failure", error_message: msg });
    }
  });

  printRunSummary("NBA scrape", { succeeded, failed });
  return { succeeded, failed, summary };
}

module.exports = {
  runNbaStatsScrape,
  scrapePer36,
  scrapeTeamPace,
  scrapeGameLog,
  scrapeDvp,
  scrapeInjuries,
};
