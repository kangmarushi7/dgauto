const config = require("../config");
const db = require("../db/client");
const { withPage, gotoSafe, randomDelay } = require("../lib/browser");
const { writeRawJson, printRunSummary, todayStamp } = require("../lib/io");

function parseNum(text) {
  if (text == null) return null;
  const cleaned = String(text).replace(/,/g, "").replace(/%/g, "").trim();
  if (!cleaned || cleaned === "" || cleaned === "-") return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

async function uncommentTables(page) {
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
    let node;
    while ((node = walker.nextNode())) {
      const wrap = document.createElement("div");
      wrap.innerHTML = node.nodeValue || "";
      node.parentNode?.insertBefore(wrap, node);
    }
  });
}

async function scrapeBatters(page, year) {
  const url = config.sources.mlb.battingStandard(year);
  await gotoSafe(page, url);
  await uncommentTables(page);

  const batters = await page.evaluate(() => {
    const table =
      document.querySelector("#players_standard_batting") ||
      document.querySelector("table#players_standard_batting") ||
      document.querySelector("table.stats_table");
    if (!table) return [];
    return Array.from(table.querySelectorAll("tbody tr"))
      .filter((tr) => !tr.classList.contains("thead"))
      .map((tr) => {
        const nameEl = tr.querySelector('[data-stat="player"] a, td[data-stat="player"] a');
        const name = nameEl?.textContent?.trim();
        if (!name) return null;
        const get = (stat) => tr.querySelector(`[data-stat="${stat}"]`)?.textContent?.trim() || null;
        return {
          name,
          team: get("team_ID") || get("team_id") || get("team"),
          position: get("pos") || get("position"),
          avg: get("batting_avg"),
          slg: get("slugging_perc") || get("slg"),
          obp: get("onbase_perc"),
          ops: get("onbase_plus_slugging"),
          pa: get("PA") || get("pa"),
          ab: get("AB") || get("ab"),
          hr: get("HR") || get("hr"),
          so: get("SO") || get("so"),
        };
      })
      .filter(Boolean);
  });

  return batters.map((b) => ({
    ...b,
    avg: parseNum(b.avg),
    slg: parseNum(b.slg),
    obp: parseNum(b.obp),
    ops: parseNum(b.ops),
    pa: parseNum(b.pa),
    ab: parseNum(b.ab),
    hr: parseNum(b.hr),
    so: parseNum(b.so),
  }));
}

async function scrapePitchers(page, year) {
  const url = config.sources.mlb.pitchingStandard(year);
  await gotoSafe(page, url);
  await uncommentTables(page);

  const pitchers = await page.evaluate(() => {
    const table =
      document.querySelector("#players_standard_pitching") ||
      document.querySelector("table#players_standard_pitching") ||
      document.querySelector("table.stats_table");
    if (!table) return [];
    return Array.from(table.querySelectorAll("tbody tr"))
      .filter((tr) => !tr.classList.contains("thead"))
      .map((tr) => {
        const nameEl = tr.querySelector('[data-stat="player"] a, td[data-stat="player"] a');
        const name = nameEl?.textContent?.trim();
        if (!name) return null;
        const get = (stat) => tr.querySelector(`[data-stat="${stat}"]`)?.textContent?.trim() || null;
        return {
          name,
          team: get("team_ID") || get("team_id") || get("team"),
          ip: get("IP") || get("ip"),
          so: get("SO") || get("so"),
          so9: get("strikeouts_per_nine") || get("SO9") || get("so9"),
          era: get("earned_run_avg") || get("era"),
          gs: get("GS") || get("gs"),
          bf: get("BF") || get("bf"),
        };
      })
      .filter(Boolean);
  });

  return pitchers.map((p) => ({
    ...p,
    ip: parseNum(p.ip),
    so: parseNum(p.so),
    k9: parseNum(p.so9),
    era: parseNum(p.era),
    gs: parseNum(p.gs),
    bf: parseNum(p.bf),
    days_rest: null,
    pitches: null,
  }));
}

async function scrapeParkFactors(page, year) {
  const url = config.sources.mlb.parkFactors(year);
  await gotoSafe(page, url);
  await uncommentTables(page);

  const factors = await page.evaluate(() => {
    const table =
      document.querySelector("#teams_park_factor") ||
      document.querySelector("table.stats_table") ||
      document.querySelector("table");
    if (!table) return [];
    return Array.from(table.querySelectorAll("tbody tr"))
      .filter((tr) => !tr.classList.contains("thead"))
      .map((tr) => {
        const cells = Array.from(tr.querySelectorAll("th, td")).map((c) => c.textContent.trim());
        const team =
          tr.querySelector('[data-stat="team_ID"] a, [data-stat="team_name"] a, th a, td a')
            ?.textContent?.trim() || cells[0] || null;
        if (!team) return null;
        const get = (stat) => tr.querySelector(`[data-stat="${stat}"]`)?.textContent?.trim() || null;
        return {
          team,
          batting_factor: get("factor_bat") || get("batting") || cells[1] || null,
          pitching_factor: get("factor_pitch") || get("pitching") || cells[2] || null,
          hr_factor: get("HR") || get("hr") || null,
          raw: cells,
        };
      })
      .filter(Boolean);
  });

  return factors.map((f) => ({
    ...f,
    batting_factor: parseNum(f.batting_factor),
    pitching_factor: parseNum(f.pitching_factor),
    hr_factor: parseNum(f.hr_factor),
    factor: parseNum(f.batting_factor),
  }));
}

async function scrapeSavantXstats(page) {
  const url = config.sources.mlb.savantXstats;
  await gotoSafe(page, url, { waitUntil: "networkidle", timeout: 90000 });
  // Savant is JS-rendered; wait for table rows
  try {
    await page.waitForSelector("table tbody tr, .table-body tr, [class*='leaderboard'] tr", {
      timeout: 20000,
    });
  } catch {
    // continue; may still parse something
  }

  const players = await page.evaluate(() => {
    const table = document.querySelector("table") || document.querySelector(".table");
    if (!table) return [];
    const headers = Array.from(table.querySelectorAll("thead th")).map((th) =>
      th.textContent.trim().toLowerCase()
    );
    const idx = (nameParts) =>
      headers.findIndex((h) => nameParts.every((p) => h.includes(p)));

    const iPlayer = idx(["player"]) >= 0 ? idx(["player"]) : 0;
    const iTeam = idx(["team"]);
    const iXba = idx(["xba"]);
    const iXslg = idx(["xslg"]);
    const iXwoba = idx(["xwoba"]);

    return Array.from(table.querySelectorAll("tbody tr"))
      .map((tr) => {
        const cells = Array.from(tr.querySelectorAll("td, th")).map((td) => td.textContent.trim());
        if (!cells.length) return null;
        const name = cells[iPlayer] || null;
        if (!name || name.toLowerCase() === "player") return null;
        return {
          name,
          team: iTeam >= 0 ? cells[iTeam] : null,
          xba: iXba >= 0 ? cells[iXba] : null,
          xslg: iXslg >= 0 ? cells[iXslg] : null,
          xwoba: iXwoba >= 0 ? cells[iXwoba] : null,
          raw: cells,
        };
      })
      .filter(Boolean);
  });

  return players.map((p) => ({
    ...p,
    xba: parseNum(p.xba),
    xslg: parseNum(p.xslg),
    xwoba: parseNum(p.xwoba),
  }));
}

async function scrapePlatoonProxy(page, year) {
  // FanGraphs leaders page as a lightweight platoon-adjacent source.
  // Full vs LHP/RHP splits can be expanded later; we store whatever table we get.
  const url = config.sources.mlb.batterSplits(year);
  await gotoSafe(page, url, { waitUntil: "networkidle", timeout: 90000 });
  try {
    await page.waitForSelector("table tbody tr", { timeout: 15000 });
  } catch {
    /* ignore */
  }

  const rows = await page.evaluate(() => {
    const table = document.querySelector("table");
    if (!table) return [];
    const headers = Array.from(table.querySelectorAll("thead th")).map((th) =>
      th.textContent.trim().toLowerCase()
    );
    return Array.from(table.querySelectorAll("tbody tr"))
      .map((tr) => {
        const cells = Array.from(tr.querySelectorAll("td")).map((td) => td.textContent.trim());
        if (cells.length < 3) return null;
        const nameIdx = headers.findIndex((h) => h.includes("name"));
        const teamIdx = headers.findIndex((h) => h === "team" || h.includes("team"));
        return {
          name: nameIdx >= 0 ? cells[nameIdx] : cells[1] || cells[0],
          team: teamIdx >= 0 ? cells[teamIdx] : null,
          headers,
          cells,
        };
      })
      .filter((r) => r && r.name);
  });

  return rows.slice(0, 300).map((r) => {
    const find = (keys) => {
      const i = r.headers.findIndex((h) => keys.some((k) => h.includes(k)));
      return i >= 0 ? parseNum(r.cells[i]) : null;
    };
    return {
      name: r.name,
      team: r.team,
      avg: find(["avg"]),
      obp: find(["obp"]),
      slg: find(["slg"]),
      ops: find(["ops"]),
      vs_lhp_avg: find(["vsl", "vs l"]),
      vs_rhp_avg: find(["vsr", "vs r"]),
      vs_lhp_ops: null,
      vs_rhp_ops: null,
    };
  });
}

async function runMlbStatsScrape({ date = todayStamp(), playerLimit = config.mlbPlayerLimit } = {}) {
  const year = config.mlbSeasonYear;
  const succeeded = [];
  const failed = [];
  const summary = { date, year, files: [] };

  console.log(`[mlb] Starting stats scrape for season ${year} (${date})`);

  await withPage(async (page) => {
    try {
      console.log("[mlb] Scraping batting standard...");
      let batters = await scrapeBatters(page, year);
      if (playerLimit > 0) batters = batters.slice(0, playerLimit);
      const file = writeRawJson("mlb", "mlb-batters", { season_year: year, players: batters }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "mlb-batters",
        status: batters.length ? "success" : "partial",
        detail_json: { count: batters.length, file },
      });
      succeeded.push({ source: "mlb-batters", count: batters.length });
    } catch (err) {
      const msg = err.message || String(err);
      failed.push({ source: "mlb-batters", error: msg });
      db.insertScrapeLog({ source: "mlb-batters", status: "failure", error_message: msg });
    }

    try {
      await randomDelay();
      console.log("[mlb] Scraping pitching standard (K/9, IP)...");
      let pitchers = await scrapePitchers(page, year);
      if (playerLimit > 0) pitchers = pitchers.slice(0, playerLimit);
      const file = writeRawJson("mlb", "mlb-pitchers", { season_year: year, players: pitchers }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "mlb-pitchers",
        status: pitchers.length ? "success" : "partial",
        detail_json: { count: pitchers.length, file },
      });
      succeeded.push({ source: "mlb-pitchers", count: pitchers.length });
    } catch (err) {
      const msg = err.message || String(err);
      failed.push({ source: "mlb-pitchers", error: msg });
      db.insertScrapeLog({ source: "mlb-pitchers", status: "failure", error_message: msg });
    }

    try {
      await randomDelay();
      console.log("[mlb] Scraping park factors...");
      const parks = await scrapeParkFactors(page, year);
      const file = writeRawJson("mlb", "mlb-park-factors", { season_year: year, parks, factors: parks }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "mlb-park-factors",
        status: parks.length ? "success" : "partial",
        detail_json: { count: parks.length, file },
      });
      succeeded.push({ source: "mlb-park-factors", count: parks.length });
    } catch (err) {
      const msg = err.message || String(err);
      failed.push({ source: "mlb-park-factors", error: msg });
      db.insertScrapeLog({ source: "mlb-park-factors", status: "failure", error_message: msg });
    }

    try {
      await randomDelay();
      console.log("[mlb] Scraping Baseball Savant xStats...");
      const xstats = await scrapeSavantXstats(page);
      const file = writeRawJson("mlb", "mlb-xstats", { players: xstats }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "mlb-xstats",
        status: xstats.length ? "success" : "partial",
        detail_json: { count: xstats.length, file },
      });
      succeeded.push({ source: "mlb-xstats", count: xstats.length });
    } catch (err) {
      const msg = err.message || String(err);
      failed.push({ source: "mlb-xstats", error: msg });
      db.insertScrapeLog({ source: "mlb-xstats", status: "failure", error_message: msg });
    }

    try {
      await randomDelay();
      console.log("[mlb] Scraping platoon / split proxy...");
      const splits = await scrapePlatoonProxy(page, year);
      const file = writeRawJson("mlb", "mlb-platoon-splits", { players: splits }, date);
      summary.files.push(file);
      db.insertScrapeLog({
        source: "mlb-platoon-splits",
        status: splits.length ? "success" : "partial",
        detail_json: { count: splits.length, file },
      });
      succeeded.push({ source: "mlb-platoon-splits", count: splits.length });
    } catch (err) {
      const msg = err.message || String(err);
      failed.push({ source: "mlb-platoon-splits", error: msg });
      db.insertScrapeLog({ source: "mlb-platoon-splits", status: "failure", error_message: msg });
    }
  });

  printRunSummary("MLB scrape", { succeeded, failed });
  return { succeeded, failed, summary };
}

module.exports = {
  runMlbStatsScrape,
  scrapeBatters,
  scrapePitchers,
  scrapeParkFactors,
  scrapeSavantXstats,
  scrapePlatoonProxy,
};
