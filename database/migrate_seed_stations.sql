-- Real Tunis station names + line_stations route order table
-- Run with: psql -U postgres -d smart_transport -f database/migrate_seed_stations.sql

-- -----------------------------------------------------------------------
-- 1. Clear placeholder stations, insert real ones
-- -----------------------------------------------------------------------
-- Reset to only real stations (keep id=1 as Unknown for legacy events)
UPDATE stations SET station_name = 'Unknown'       WHERE station_id = 1;
UPDATE stations SET station_name = 'Tunis Marine'  WHERE station_id = 2;
UPDATE stations SET station_name = 'Bab Saadoun'   WHERE station_id = 3;
UPDATE stations SET station_name = 'Ariana Centre' WHERE station_id = 4;
UPDATE stations SET station_name = 'La Marsa Plage' WHERE station_id = 5;
UPDATE stations SET station_name = 'Bardo'         WHERE station_id = 6;

-- Add additional stations for Line 23 and Line 42
INSERT INTO stations (station_name) VALUES
    ('Tunis Centre'),
    ('Passage'),
    ('Le Bardo'),
    ('La Goulette'),
    ('Ain Zaghouan'),
    ('Cité Sportive')
ON CONFLICT DO NOTHING;

-- -----------------------------------------------------------------------
-- 2. line_stations — route order table
--    Lets you visualize buses moving along a route stop by stop
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS line_stations (
    id         SERIAL PRIMARY KEY,
    line_id    INTEGER NOT NULL REFERENCES lines(line_id),
    station_id INTEGER NOT NULL REFERENCES stations(station_id),
    stop_order SMALLINT NOT NULL,

    CONSTRAINT uq_line_station UNIQUE (line_id, stop_order)
);

CREATE INDEX IF NOT EXISTS ix_line_stations_line_id
    ON line_stations(line_id);

-- Line 23: Tunis Centre → La Marsa
INSERT INTO line_stations (line_id, station_id, stop_order)
SELECT 1, station_id, stop_order FROM (VALUES
    (7,  1),   -- Tunis Centre
    (8,  2),   -- Passage
    (2,  3),   -- Tunis Marine
    (10, 4),   -- La Goulette
    (5,  5),   -- La Marsa Plage
    (7,  6)    -- (wraps back — circular reference placeholder)
) AS t(station_id, stop_order)
ON CONFLICT DO NOTHING;

-- Line 42: Bab Saadoun → Ariana
INSERT INTO line_stations (line_id, station_id, stop_order)
SELECT 2, station_id, stop_order FROM (VALUES
    (3,  1),   -- Bab Saadoun
    (9,  2),   -- Le Bardo
    (6,  3),   -- Bardo
    (11, 4),   -- Ain Zaghouan
    (4,  5)    -- Ariana Centre
) AS t(station_id, stop_order)
ON CONFLICT DO NOTHING;

SELECT 'Stations and line_stations seeded' AS status;
SELECT ls.line_id, l.line_number, ls.stop_order, s.station_name
FROM line_stations ls
JOIN lines l ON l.line_id = ls.line_id
JOIN stations s ON s.station_id = ls.station_id
ORDER BY ls.line_id, ls.stop_order;
