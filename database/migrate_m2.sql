-- Milestone 2 — Transport Master Data
-- Run with: psql -U postgres -d smart_transport -f database/migrate_m2.sql

-- 1. lines table
CREATE TABLE IF NOT EXISTS lines (
    line_id     SERIAL PRIMARY KEY,
    line_name   VARCHAR(100) NOT NULL,
    line_number VARCHAR(20)  NOT NULL
);

-- 2. drivers table
CREATE TABLE IF NOT EXISTS drivers (
    driver_id      SERIAL PRIMARY KEY,
    name           VARCHAR(255) NOT NULL,
    license_number VARCHAR(50)  NOT NULL UNIQUE
);

-- 3. buses — add license_plate, driver_id FK
ALTER TABLE buses ADD COLUMN IF NOT EXISTS license_plate VARCHAR(20);
ALTER TABLE buses ADD COLUMN IF NOT EXISTS driver_id     INTEGER REFERENCES drivers(driver_id);

-- 4. buses — wire line_id as a real FK now that lines table exists
ALTER TABLE buses DROP CONSTRAINT IF EXISTS buses_line_id_fkey;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_buses_line'
          AND table_name = 'buses'
    ) THEN
        ALTER TABLE buses
            ADD CONSTRAINT fk_buses_line
            FOREIGN KEY (line_id) REFERENCES lines(line_id);
    END IF;
END$$;

-- 5. sessions — add bus_id FK
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS bus_id INTEGER;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sessions_bus'
          AND table_name = 'sessions'
    ) THEN
        ALTER TABLE sessions
            ADD CONSTRAINT fk_sessions_bus
            FOREIGN KEY (bus_id) REFERENCES buses(bus_id);
    END IF;
END$$;

-- 6. passenger_events — add occupancy_rate, promote bus_id to proper FK
ALTER TABLE passenger_events ADD COLUMN IF NOT EXISTS occupancy_rate NUMERIC(5,2);
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_events_bus'
          AND table_name = 'passenger_events'
    ) THEN
        ALTER TABLE passenger_events
            ADD CONSTRAINT fk_events_bus
            FOREIGN KEY (bus_id) REFERENCES buses(bus_id);
    END IF;
END$$;

-- 7. indexes
CREATE INDEX IF NOT EXISTS ix_sessions_bus_id       ON sessions(bus_id);
CREATE INDEX IF NOT EXISTS ix_events_occupancy_rate ON passenger_events(occupancy_rate);

SELECT 'Milestone 2 schema migration complete' AS status;
