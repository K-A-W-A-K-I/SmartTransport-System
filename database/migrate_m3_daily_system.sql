-- Milestone 3 — daily_system_statistics (Executive Dashboard table)
-- Run with: psql -U postgres -d smart_transport -f database/migrate_m3_daily_system.sql

CREATE TABLE IF NOT EXISTS daily_system_statistics (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL UNIQUE,
    total_passengers    INTEGER      NOT NULL DEFAULT 0,
    avg_occupancy_rate  NUMERIC(5,2),
    peak_hour           SMALLINT     CHECK (peak_hour BETWEEN 0 AND 23),
    busiest_line_id     INTEGER      REFERENCES lines(line_id),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_dss_date ON daily_system_statistics(date);

SELECT 'daily_system_statistics created' AS status;
