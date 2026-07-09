-- station_daily_statistics
-- Run with: psql -U postgres -d smart_transport -f database/migrate_station_daily.sql

CREATE TABLE IF NOT EXISTS station_daily_statistics (
    id                  SERIAL PRIMARY KEY,
    date                DATE    NOT NULL,
    station_id          INTEGER NOT NULL REFERENCES stations(station_id),
    line_id             INTEGER          REFERENCES lines(line_id),
    total_boardings     INTEGER NOT NULL DEFAULT 0,
    total_alightings    INTEGER NOT NULL DEFAULT 0,
    avg_occupancy_rate  NUMERIC(5,2),
    peak_hour           SMALLINT CHECK (peak_hour BETWEEN 0 AND 23),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_station_daily UNIQUE (date, station_id, line_id)
);

CREATE INDEX IF NOT EXISTS ix_sds_date       ON station_daily_statistics(date);
CREATE INDEX IF NOT EXISTS ix_sds_station_id ON station_daily_statistics(station_id);
CREATE INDEX IF NOT EXISTS ix_sds_line_id    ON station_daily_statistics(line_id);

SELECT 'station_daily_statistics created' AS status;
