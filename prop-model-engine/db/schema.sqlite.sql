-- Prop Model Engine — SQLite schema (local fallback when DATABASE_URL is unset)

CREATE TABLE IF NOT EXISTS pm_players (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  team TEXT,
  sport TEXT NOT NULL CHECK (sport IN ('nba', 'mlb')),
  position TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pm_player_stats_raw (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT,
  source TEXT NOT NULL,
  stat_json TEXT NOT NULL,
  scraped_at TEXT NOT NULL,
  FOREIGN KEY (player_id) REFERENCES pm_players(id)
);

CREATE INDEX IF NOT EXISTS idx_pm_player_stats_raw_player
  ON pm_player_stats_raw(player_id);
CREATE INDEX IF NOT EXISTS idx_pm_player_stats_raw_source
  ON pm_player_stats_raw(source);
CREATE INDEX IF NOT EXISTS idx_pm_player_stats_raw_scraped
  ON pm_player_stats_raw(scraped_at);

CREATE TABLE IF NOT EXISTS pm_scrape_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('success', 'failure', 'partial')),
  error_message TEXT,
  detail_json TEXT,
  scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pm_scrape_log_source ON pm_scrape_log(source);
CREATE INDEX IF NOT EXISTS idx_pm_scrape_log_scraped ON pm_scrape_log(scraped_at);

CREATE TABLE IF NOT EXISTS pm_prop_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT,
  stat_type TEXT NOT NULL,
  game_id TEXT,
  book TEXT NOT NULL,
  line REAL NOT NULL,
  over_odds REAL,
  under_odds REAL,
  scraped_at TEXT NOT NULL,
  FOREIGN KEY (player_id) REFERENCES pm_players(id)
);

CREATE TABLE IF NOT EXISTS pm_player_projections (
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
  FOREIGN KEY (player_id) REFERENCES pm_players(id)
);

CREATE TABLE IF NOT EXISTS pm_edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id TEXT,
  stat_type TEXT NOT NULL,
  game_id TEXT,
  book TEXT,
  edge_pct REAL NOT NULL,
  confidence_tier TEXT,
  flagged_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (player_id) REFERENCES pm_players(id)
);

CREATE TABLE IF NOT EXISTS pm_bets (
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
  FOREIGN KEY (player_id) REFERENCES pm_players(id)
);
