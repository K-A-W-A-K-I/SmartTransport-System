-- Milestone 3 — Analytics Tables
-- Run with: psql -U postgres -d smart_transport -f database/migrate_m3_analytics.sql

-- -----------------------------------------------------------------------
-- 1. hourly_station_statistics
--    How busy is each station every hour?
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hourly_station_statistics (
    id                  SERIAL PRIMARY KEY,
    hour_start          TIMESTAMP WITH TIME ZONE NOT NULL,
    station_id          INTEGER NOT NULL REFERENCES stations(station_id),
    line_id             INTEGER REFERENCES lines(line_id),
    total_boardings     INTEGER NOT NULL DEFAULT 0,
    total_alightings    INTEGER NOT NULL DEFAULT 0,
    avg_occupancy_rate  NUMERIC(5,2),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_hourly_station UNIQUE (hour_start, station_id, line_id)
);

CREATE INDEX IF NOT EXISTS ix_hss_hour_start  ON hourly_station_statistics(hour_start);
CREATE INDEX IF NOT EXISTS ix_hss_station_id  ON hourly_station_statistics(station_id);
CREATE INDEX IF NOT EXISTS ix_hss_line_id     ON hourly_station_statistics(line_id);

-- -----------------------------------------------------------------------
-- 2. line_statistics
--    Compare transport lines.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS line_statistics (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    line_id             INTEGER NOT NULL REFERENCES lines(line_id),
    total_passengers    INTEGER NOT NULL DEFAULT 0,
    avg_occupancy_rate  NUMERIC(5,2),
    peak_hour           SMALLINT CHECK (peak_hour BETWEEN 0 AND 23),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_line_statistics UNIQUE (date, line_id)
);

CREATE INDEX IF NOT EXISTS ix_ls_date     ON line_statistics(date);
CREATE INDEX IF NOT EXISTS ix_ls_line_id  ON line_statistics(line_id);

-- -----------------------------------------------------------------------
-- 3. bus_statistics
--    Monitor every bus.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bus_statistics (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    bus_id              INTEGER NOT NULL REFERENCES buses(bus_id),
    total_passengers    INTEGER NOT NULL DEFAULT 0,
    max_occupancy_rate  NUMERIC(5,2),
    avg_occupancy_rate  NUMERIC(5,2),
    peak_hour           SMALLINT CHECK (peak_hour BETWEEN 0 AND 23),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_bus_statistics UNIQUE (date, bus_id)
);

CREATE INDEX IF NOT EXISTS ix_bs_date    ON bus_statistics(date);
CREATE INDEX IF NOT EXISTS ix_bs_bus_id  ON bus_statistics(bus_id);

-- -----------------------------------------------------------------------
-- 4. ETL watermark — tracks last successful pipeline run
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name  VARCHAR(100) PRIMARY KEY,
    last_run_at    TIMESTAMP WITH TIME ZONE NOT NULL
);

SELECT 'Milestone 3 analytics tables created' AS status;
