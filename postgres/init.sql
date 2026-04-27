-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create enum types
CREATE TYPE buoy_status AS ENUM ('online', 'offline', 'warning', 'inactive');
CREATE TYPE alert_severity AS ENUM ('info', 'warning', 'critical');
CREATE TYPE alert_status AS ENUM ('triggered', 'acknowledged', 'resolved');

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'viewer' NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Create buoy table
CREATE TABLE IF NOT EXISTS buoys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    depth DECIMAL(6, 2) DEFAULT 0,
    status buoy_status DEFAULT 'offline',
    sea_area VARCHAR(50),
    is_activated BOOLEAN DEFAULT FALSE,
    mqtt_client_id UUID DEFAULT gen_random_uuid(),
    activation_key VARCHAR(64),
    battery_level INTEGER DEFAULT 100,
    last_battery_level INTEGER DEFAULT 100,
    base_latitude DECIMAL(10, 7),
    base_longitude DECIMAL(10, 7),
    drift_radius DECIMAL(8, 5) DEFAULT 0.01000,
    drift_alert_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create buoy_data table (hypertable for TimescaleDB)
CREATE TABLE IF NOT EXISTS buoy_data (
    time TIMESTAMPTZ NOT NULL,
    buoy_id UUID NOT NULL REFERENCES buoys(id) ON DELETE CASCADE,
    latitude DECIMAL(10, 7),
    longitude DECIMAL(10, 7),
    temperature DECIMAL(5, 2),
    salinity DECIMAL(5, 2),
    ph DECIMAL(4, 2),
    dissolved_oxygen DECIMAL(5, 2),
    turbidity DECIMAL(6, 2),
    chlorophyll DECIMAL(5, 2),
    wave_height DECIMAL(5, 2),
    battery_level INTEGER,
    drift_flagged BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (time, buoy_id)
);

-- Convert to hypertable
SELECT create_hypertable('buoy_data', 'time', if_not_exists => TRUE);

-- Create alert table
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buoy_id UUID NOT NULL REFERENCES buoys(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    param_name VARCHAR(50) NOT NULL,
    threshold_value DECIMAL,
    actual_value DECIMAL NOT NULL,
    severity alert_severity DEFAULT 'warning',
    status alert_status DEFAULT 'triggered',
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100),
    remarks VARCHAR(500)
);

-- Create alert_config table (buoy_id NULL = global default)
CREATE TABLE IF NOT EXISTS alert_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buoy_id UUID REFERENCES buoys(id) ON DELETE CASCADE,
    param_name VARCHAR(50) NOT NULL,
    min_threshold DECIMAL,
    max_threshold DECIMAL,
    severity alert_severity DEFAULT 'warning',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(buoy_id, param_name)
);

-- Create combined_alert_rules table
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

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_buoys_status ON buoys(status);
CREATE INDEX IF NOT EXISTS idx_buoys_sea_area ON buoys(sea_area);
CREATE INDEX IF NOT EXISTS idx_buoy_data_buoy_id ON buoy_data(buoy_id);
CREATE INDEX IF NOT EXISTS idx_alerts_buoy_id ON alerts(buoy_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at);

-- Insert default alert configs (global, buoy_id = NULL)
INSERT INTO alert_configs (buoy_id, param_name, min_threshold, max_threshold, severity, enabled) VALUES
    (NULL, 'temperature', 5.0, 30.0, 'warning', true),
    (NULL, 'salinity', 30.0, 36.0, 'warning', true),
    (NULL, 'ph', 7.5, 8.5, 'warning', true),
    (NULL, 'dissolved_oxygen', 5.0, NULL, 'warning', true),
    (NULL, 'turbidity', NULL, 50.0, 'warning', true),
    (NULL, 'chlorophyll', NULL, 20.0, 'warning', true),
    (NULL, 'wave_height', NULL, 5.0, 'warning', true)
ON CONFLICT (buoy_id, param_name) DO NOTHING;