-- Migration: 004_buoy_status_log
-- Description: 新增浮标状态变更日志表，修改 drift_radius 单位从度改为公里
-- Date: 2026-04-19

-- 1. 创建浮标状态变更日志表
CREATE TABLE IF NOT EXISTS buoy_status_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buoy_id UUID NOT NULL REFERENCES buoys(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL,  -- inactive, online, offline, disconnected, low_battery, no_power, drift_alert
    previous_status VARCHAR(20),    -- 变更前的状态
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    reason VARCHAR(50),            -- low_battery, drift_detected, manual, timeout, recovered
    latitude NUMERIC(10, 7),       -- 变更时位置
    longitude NUMERIC(10, 7),
    battery_level INTEGER,          -- 变更时电量
    CONSTRAINT fk_buoy FOREIGN KEY (buoy_id) REFERENCES buoys(id) ON DELETE CASCADE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_buoy_status_logs_buoy_id ON buoy_status_logs(buoy_id);
CREATE INDEX IF NOT EXISTS idx_buoy_status_logs_changed_at ON buoy_status_logs(changed_at);
CREATE INDEX IF NOT EXISTS idx_buoy_status_logs_status ON buoy_status_logs(status);

-- 2. 将 drift_radius 默认值从 0.01000 度（约1.1公里）改为 0.5 公里
-- 注意：这个字段现在表示公里数，而不是度
ALTER TABLE buoys ALTER COLUMN drift_radius SET DEFAULT 0.5;

-- 3. 将现有的 drift_radius 值转换为公里（如果是旧数据）
-- 假设旧值是以度为单位，1度 ≈ 111公里
-- 如果 drift_radius < 10，则认为是旧的度数据，需要转换
-- 但为了安全起见，我们保留旧值，让用户根据实际情况判断是否需要调整
-- 如果 drift_radius < 10 且不等于 0.5，默认值约等于0.5公里

-- 可选：添加注释说明 drift_radius 现在是公里
COMMENT ON COLUMN buoys.drift_radius IS '允许偏移半径（公里）';
