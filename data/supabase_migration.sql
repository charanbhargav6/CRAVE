-- CRAVE — Supabase migration
-- Run this in your Supabase SQL editor before first backtest run
-- Dashboard: Settings → SQL Editor → New query → paste → Run

CREATE TABLE IF NOT EXISTS ml_backtest_results (
  id           BIGSERIAL PRIMARY KEY,
  run_id       TEXT NOT NULL,
  symbol       TEXT NOT NULL,
  dataset      TEXT,
  rows         INTEGER,
  mean_acc     REAL,
  std_acc      REAL,
  min_acc      REAL,
  max_acc      REAL,
  degradation  REAL,
  details      JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast dashboard queries
CREATE INDEX IF NOT EXISTS idx_backtest_run_id    ON ml_backtest_results (run_id);
CREATE INDEX IF NOT EXISTS idx_backtest_symbol    ON ml_backtest_results (symbol);
CREATE INDEX IF NOT EXISTS idx_backtest_created   ON ml_backtest_results (created_at DESC);

-- Enable realtime (dashboard auto-updates without polling)
ALTER TABLE ml_backtest_results REPLICA IDENTITY FULL;
ALTER PUBLICATION supabase_realtime ADD TABLE ml_backtest_results;

-- Row Level Security (optional but recommended)
ALTER TABLE ml_backtest_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read" ON ml_backtest_results FOR SELECT USING (true);
CREATE POLICY "service_write" ON ml_backtest_results FOR INSERT
  WITH CHECK (auth.role() = 'service_role' OR auth.role() = 'anon');
