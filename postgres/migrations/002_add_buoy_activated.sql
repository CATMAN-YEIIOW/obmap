-- Migration: Add is_activated to buoys for persistent simulator activation state
-- This allows buoys to be re-activated after backend restart

ALTER TABLE buoys ADD COLUMN IF NOT EXISTS is_activated BOOLEAN NOT NULL DEFAULT FALSE;

-- Initialize is_activated for existing default buoys (those that exist in BUOY_CONFIGS)
-- The default 5 buoys should be considered "activated" by default
UPDATE buoys SET is_activated = TRUE WHERE code IN ('BH-001', 'HH-001', 'DH-001', 'NH-001', 'NH-002');
