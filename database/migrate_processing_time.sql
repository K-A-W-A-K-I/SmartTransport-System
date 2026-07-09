-- Add processing_time_seconds to sessions table
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS processing_time_seconds NUMERIC(8,2);

SELECT 'processing_time_seconds added' AS status;
