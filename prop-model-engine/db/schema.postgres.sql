-- Prop Model Engine — Postgres schema (shared DATABASE_URL with DG app)

CREATE TABLE IF NOT EXISTS pm_players (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  team TEXT,
  sport TEXT NOT NULL CHECK (sport IN ('nba', 'mlb')),
  position TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pm_player_stats_raw (
  id BIGSERIAL PRIMARY KEY,
  player_id TEXT REFERENCES pm_players(id),
  source TEXT NOT NULL,
  stat_json JSONB NOT NULL,
  scraped_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pm_player_stats_raw_player
  ON pm_player_stats_raw(player_id);
CREATE INDEX IF NOT EXISTS idx_pm_player_stats_raw_source
  ON pm_player_stats_raw(source);
CREATE INDEX IF NOT EXISTS idx_pm_player_stats_raw_scraped
  ON pm_player_stats_raw(scraped_at);

CREATE TABLE IF NOT EXISTS pm_scrape_log (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('success', 'failure', 'partial')),
  error_message TEXT,
  detail_json JSONB,
  scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pm_scrape_log_source ON pm_scrape_log(source);
CREATE INDEX IF NOT EXISTS idx_pm_scrape_log_scraped ON pm_scrape_log(scraped_at);

CREATE TABLE IF NOT EXISTS pm_prop_lines (
  id BIGSERIAL PRIMARY KEY,
  player_id TEXT REFERENCES pm_players(id),
  stat_type TEXT NOT NULL,
  game_id TEXT,
  book TEXT NOT NULL,
  line DOUBLE PRECISION NOT NULL,
  over_odds DOUBLE PRECISION,
  under_odds DOUBLE PRECISION,
  scraped_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS pm_player_projections (
  id BIGSERIAL PRIMARY KEY,
  player_id TEXT REFERENCES pm_players(id),
  stat_type TEXT NOT NULL,
  game_id TEXT,
  projected_mean DOUBLE PRECISION NOT NULL,
  projected_stdev DOUBLE PRECISION,
  model_version TEXT,
  confidence_tier TEXT,
  actual_value DOUBLE PRECISION,
  error DOUBLE PRECISION,
  abs_error DOUBLE PRECISION,
  over_under_hit INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pm_edges (
  id BIGSERIAL PRIMARY KEY,
  player_id TEXT REFERENCES pm_players(id),
  stat_type TEXT NOT NULL,
  game_id TEXT,
  book TEXT,
  edge_pct DOUBLE PRECISION NOT NULL,
  confidence_tier TEXT,
  flagged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pm_bets (
  id BIGSERIAL PRIMARY KEY,
  player_id TEXT REFERENCES pm_players(id),
  stat_type TEXT NOT NULL,
  line DOUBLE PRECISION,
  side TEXT,
  stake DOUBLE PRECISION,
  odds DOUBLE PRECISION,
  result TEXT,
  clv_pct DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
