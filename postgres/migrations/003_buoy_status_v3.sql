-- Migration: Buoy status v3 - add disconnected, low_battery, drift_alert statuses
-- and new fields for MQTT client ID, activation key, battery, drift detection

-- Step 1: Add new enum values to buoy_status
ALTER TYPE buoy_status ADD VALUE IF NOT EXISTS 'disconnected';
ALTER TYPE buoy_status ADD VALUE IF NOT EXISTS 'low_battery';
ALTER TYPE buoy_status ADD VALUE IF NOT EXISTS 'drift_alert';

-- Step 2: Add new columns to buoys table
ALTER TABLE buoys ADD COLUMN IF NOT EXISTS mqtt_client_id UUID DEFAULT gen_random_uuid();
ALTER TABLE buoys ADD COLUMN IF NOT EXISTS activation_key VARCHAR(64);
ALTER TABLE buoys ADD COLUMN IF NOT EXISTS battery_level INTEGER DEFAULT 100 CHECK (battery_level >= 0 AND battery_level <= 100);
ALTER TABLE buoys ADD COLUMN IF NOT EXISTS base_latitude DECIMAL(10, 7);
ALTER TABLE buoys ADD COLUMN IF NOT EXISTS base_longitude DECIMAL(10, 7);
ALTER TABLE buoys ADD COLUMN IF NOT EXISTS drift_radius DECIMAL(8, 5) DEFAULT 0.01000;  -- ~1km in degrees
ALTER TABLE buoys ADD COLUMN IF NOT EXISTS drift_alert_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE buoys ADD COLUMN IF NOT EXISTS last_battery_level INTEGER DEFAULT 100;  -- battery level before disconnect

-- Step 3: Add new columns to buoy_data
ALTER TABLE buoy_data ADD COLUMN IF NOT EXISTS latitude DECIMAL(10, 7);
ALTER TABLE buoy_data ADD COLUMN IF NOT EXISTS longitude DECIMAL(10, 7);
ALTER TABLE buoy_data ADD COLUMN IF NOT EXISTS battery_level INTEGER;
ALTER TABLE buoy_data ADD COLUMN IF NOT EXISTS drift_flagged BOOLEAN DEFAULT FALSE;

-- Step 4: Set base_latitude/longitude for existing buoys (use current position as base)
UPDATE buoys SET base_latitude = latitude, base_longitude = longitude WHERE base_latitude IS NULL;

-- Step 5: Set mqtt_client_id for existing buoys
UPDATE buoys SET mqtt_client_id = gen_random_uuid() WHERE mqtt_client_id IS NULL;

-- Step 6: Copy current lat/lon to buoy_data for existing records
UPDATE buoy_data SET latitude = (
    SELECT latitude FROM buoys WHERE buoys.id = buoy_data.buoy_id
), longitude = (
    SELECT longitude FROM buoys WHERE buoys.id = buoy_data.buoy_id
) WHERE buoy_data.latitude IS NULL;
