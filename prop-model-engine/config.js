require("dotenv").config({ path: require("path").join(__dirname, ".env") });
// Also load parent app .env so DATABASE_URL from Railway / root .env is visible locally
require("dotenv").config({ path: require("path").join(__dirname, "..", ".env") });

const path = require("path");

const root = __dirname;

function normalizeDatabaseUrl(raw) {
  const url = String(raw || "").trim();
  if (!url) return "";
  // Node pg accepts postgres:// and postgresql://
  return url;
}

module.exports = {
  root,
  /** Prefer shared app Postgres (DATABASE_URL). SQLite only when unset. */
  databaseUrl: normalizeDatabaseUrl(process.env.DATABASE_URL),
  dbPath: process.env.DB_PATH
    ? path.isAbsolute(process.env.DB_PATH)
      ? process.env.DB_PATH
      : path.join(root, process.env.DB_PATH)
    : path.join(root, "data", "prop-model.db"),
  rawDir: path.join(root, "data", "raw"),
  aliasesPath: path.join(root, "data", "aliases.json"),

  delayMinMs: Number(process.env.SCRAPE_DELAY_MIN_MS || 2000),
  delayMaxMs: Number(process.env.SCRAPE_DELAY_MAX_MS || 5000),

  nbaSeasonYear: Number(process.env.NBA_SEASON_YEAR || 2026),
  mlbSeasonYear: Number(process.env.MLB_SEASON_YEAR || 2025),

  nbaCron: process.env.NBA_CRON || "30 6 * * *",
  mlbCron: process.env.MLB_CRON || "45 6 * * *",

  headless: String(process.env.PLAYWRIGHT_HEADLESS || "true").toLowerCase() !== "false",
  nbaPlayerLimit: Number(process.env.NBA_PLAYER_LIMIT || 0),
  mlbPlayerLimit: Number(process.env.MLB_PLAYER_LIMIT || 0),

  userAgents: [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
  ],

  sources: {
    nba: {
      per36: (year) =>
        `https://www.basketball-reference.com/leagues/NBA_${year}_per_minute.html`,
      advanced: (year) =>
        `https://www.basketball-reference.com/leagues/NBA_${year}_advanced.html`,
      teamStats: (year) =>
        `https://www.basketball-reference.com/leagues/NBA_${year}.html`,
      gameLog: (playerPath, year) =>
        `https://www.basketball-reference.com${playerPath}/gamelog/${year}`,
      // Hashtag Basketball DvP ranks (position defense)
      dvp: "https://hashtagbasketball.com/nba-defense-vs-position",
      injuries: "https://www.rotowire.com/basketball/injury-report.php",
    },
    mlb: {
      battingStandard: (year) =>
        `https://www.baseball-reference.com/leagues/majors/${year}-standard-batting.html`,
      pitchingStandard: (year) =>
        `https://www.baseball-reference.com/leagues/majors/${year}-standard-pitching.html`,
      parkFactors: (year) =>
        `https://www.baseball-reference.com/leagues/majors/${year}-factor-pitching.shtml`,
      // FanGraphs platoon (public HTML tables; no paid API)
      batterSplits: (year) =>
        `https://www.fangraphs.com/leaders/major-league?pos=all&stats=bat&lg=all&qual=50&season=${year}&season1=${year}&ind=0&type=6&month=0&team=0`,
      pitcherWorkload: (year) =>
        `https://www.baseball-reference.com/leagues/majors/${year}-standard-pitching.html`,
      savantXstats:
        "https://baseballsavant.mlb.com/leaderboard/expected_statistics?type=batter&year=2025&position=&team=&min=q",
    },
  },
};
