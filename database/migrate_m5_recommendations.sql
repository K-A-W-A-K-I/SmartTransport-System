-- M5 — add timestamp columns to recommendations for the Operations Portal
ALTER TABLE recommendations
    ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS resolved_at     TIMESTAMP WITH TIME ZONE;

SELECT 'recommendations timestamps added' AS status;
