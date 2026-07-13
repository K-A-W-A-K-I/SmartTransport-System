-- M5 — add status to buses, phone + status to drivers
ALTER TABLE buses
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active';

ALTER TABLE drivers
    ADD COLUMN IF NOT EXISTS phone  VARCHAR(30),
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'available';

SELECT 'buses.status and drivers.phone/status added' AS result;
