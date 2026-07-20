-- Prop Model Engine — Phase 1 schema (+ stubs for later phases)

CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  team TEXT,
  sport TEXT NOT NULL CHECK (sport IN ('nba', 'mlb')),
  position TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS player_stats_raw (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT,
  source TEXT NOT NULL,
  stat_json TEXT NOT NULL,
  scraped_at TEXT NOT NULL,
  FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE INDEX IF NOT EXISTS idx_player_stats_raw_player
  ON player_stats_raw(player_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_raw_source
  ON player_stats_raw(source);
CREATE INDEX IF NOT EXISTS idx_player_stats_raw_scraped
  ON player_stats_raw(scraped_at);

CREATE TABLE IF NOT EXISTS scrape_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('success', 'failure', 'partial')),
  error_message TEXT,
  detail_json TEXT,
  scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_scrape_log_source ON scrape_log(source);
CREATE INDEX IF NOT EXISTS idx_scrape_log_scraped ON scrape_log(scraped_at);

-- Phase 2+ stubs (created empty so dashboard / later modules can query safely)
CREATE TABLE IF NOT EXISTS prop_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT,
  stat_type TEXT NOT NULL,
  game_id TEXT,
  book TEXT NOT NULL,
  line REAL NOT NULL,
  over_odds REAL,
  under_odds REAL,
  scraped_at TEXT NOT NULL,
  FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS player_projections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT,
  stat_type TEXT NOT NULL,
  game_id TEXT,
  projected_mean REAL NOT NULL,
  projected_stdev REAL,
  model_version TEXT,
  confidence_tier TEXT,
  actual_value REAL,
  error REAL,
  abs_error REAL,
  over_under_hit INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT,
  stat_type TEXT NOT NULL,
  game_id TEXT,
  book TEXT,
  edge_pct REAL NOT NULL,
  confidence_tier TEXT,
  flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS bets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT,
  stat_type TEXT NOT NULL,
  line REAL,
  side TEXT,
  stake REAL,
  odds REAL,
  result TEXT,
  clv_pct REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (player_id) REFERENCES players(id)
);
