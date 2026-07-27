-- M6 — Enrich master data for Power BI redesign
-- Run: psql -U postgres -d smart_transport -f database/migrate_m6_enrichment.sql

-- ── buses ────────────────────────────────────────────────────────────────
ALTER TABLE buses
    ADD COLUMN IF NOT EXISTS manufacturer    VARCHAR(100),
    ADD COLUMN IF NOT EXISTS model           VARCHAR(100),
    ADD COLUMN IF NOT EXISTS year            SMALLINT,
    ADD COLUMN IF NOT EXISTS fuel_type       VARCHAR(30),   -- diesel / electric / hybrid
    ADD COLUMN IF NOT EXISTS maintenance_date DATE;

-- ── drivers ──────────────────────────────────────────────────────────────
ALTER TABLE drivers
    ADD COLUMN IF NOT EXISTS years_experience SMALLINT,
    ADD COLUMN IF NOT EXISTS shift            VARCHAR(20),  -- morning / afternoon / night
    ADD COLUMN IF NOT EXISTS hire_date        DATE,
    ADD COLUMN IF NOT EXISTS depot            VARCHAR(100);

-- ── stations ─────────────────────────────────────────────────────────────
ALTER TABLE stations
    ADD COLUMN IF NOT EXISTS zone            VARCHAR(50),
    ADD COLUMN IF NOT EXISTS municipality    VARCHAR(100),
    ADD COLUMN IF NOT EXISTS latitude        NUMERIC(9,6),
    ADD COLUMN IF NOT EXISTS longitude       NUMERIC(9,6);

-- ── monthly_forecasts — new table for Page 3 ─────────────────────────────
CREATE TABLE IF NOT EXISTS monthly_forecasts (
    id              SERIAL PRIMARY KEY,
    forecast_month  DATE NOT NULL,          -- first day of the month
    line_id         INTEGER REFERENCES lines(line_id),
    station_id      INTEGER REFERENCES stations(station_id),
    predicted_passengers  INTEGER,
    predicted_occupancy   NUMERIC(5,2),
    predicted_tickets     INTEGER,
    predicted_peak_hour   SMALLINT,
    suggested_action      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_monthly_forecast UNIQUE (forecast_month, line_id, station_id)
);

CREATE INDEX IF NOT EXISTS ix_mf_month   ON monthly_forecasts(forecast_month);
CREATE INDEX IF NOT EXISTS ix_mf_line_id ON monthly_forecasts(line_id);

SELECT 'M6 enrichment migration complete' AS status;
