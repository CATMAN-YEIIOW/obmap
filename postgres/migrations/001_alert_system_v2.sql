-- Migration: Alert System V2 - Per-buoy configs, combined rules, user tracking
-- Run this on existing databases

DO $$
BEGIN
    -- 1. Add 'inactive' to buoy_status enum (ignore if exists)
    BEGIN
        ALTER TYPE buoy_status ADD VALUE 'inactive';
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END;
END
$$;

-- 2. Add buoy_id column to alert_configs (for per-buoy threshold)
ALTER TABLE alert_configs ADD COLUMN IF NOT EXISTS buoy_id UUID REFERENCES buoys(id) ON DELETE CASCADE;

-- 3. Drop the old unique constraint on param_name only (ignore if doesn't exist)
ALTER TABLE alert_configs DROP CONSTRAINT IF EXISTS alert_configs_param_name_key;

-- 4. Add new unique constraint on (buoy_id, param_name)
ALTER TABLE alert_configs ADD CONSTRAINT alert_configs_buoy_param_unique UNIQUE (buoy_id, param_name);

-- 5. Update existing global configs to have buoy_id = NULL if they're currently NULL
UPDATE alert_configs SET buoy_id = NULL WHERE buoy_id IS NULL;

-- 6. Create combined_alert_rules table
CREATE TABLE IF NOT EXISTS combined_alert_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    buoy_id UUID REFERENCES buoys(id) ON DELETE CASCADE,
    conditions JSONB NOT NULL,
    severity alert_severity DEFAULT 'warning',
    enabled BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_combined_rules_buoy_id ON combined_alert_rules(buoy_id);
CREATE INDEX IF NOT EXISTS idx_combined_rules_enabled ON combined_alert_rules(enabled);