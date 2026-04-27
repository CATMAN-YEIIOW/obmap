from sqlalchemy import Column, String, Numeric, DateTime, Enum, Boolean, ForeignKey, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base
import enum


class BuoyStatus(str, enum.Enum):
    inactive = "inactive"      # 未激活，等待MQTT激活指令
    online = "online"           # 正常在线
    offline = "offline"        # 平台主动下线
    disconnected = "disconnected"  # 失联（故障/电量耗尽/手动断开）
    low_battery = "low_battery"    # 低电量模式
    no_power = "no_power"      # 无电状态（电量耗尽）
    drift_alert = "drift_alert"    # 漂移告警


class AlertSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(str, enum.Enum):
    triggered = "triggered"
    acknowledged = "acknowledged"
    resolved = "resolved"


class UserRole(str, enum.Enum):
    admin = "admin"
    researcher = "researcher"
    viewer = "viewer"


class Buoy(Base):
    __tablename__ = "buoys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    latitude = Column(Numeric(10, 7), nullable=False)
    longitude = Column(Numeric(10, 7), nullable=False)
    depth = Column(Numeric(6, 2), default=0)
    status = Column(Enum(BuoyStatus), default=BuoyStatus.inactive)
    sea_area = Column(String(50))
    is_activated = Column(Boolean, default=False)  # 持久化激活状态，后端重启后恢复
    # MQTT通信标识
    mqtt_client_id = Column(UUID(as_uuid=True), default=uuid.uuid4)
    activation_key = Column(String(64))
    # 电量相关
    battery_level = Column(Integer, default=100)  # 0-100
    last_battery_level = Column(Integer, default=100)  # 失联前的电量
    # 漂移检测相关
    base_latitude = Column(Numeric(10, 7))
    base_longitude = Column(Numeric(10, 7))
    drift_radius = Column(Numeric(8, 5), default=0.5)  # 允许偏移半径（公里）
    drift_alert_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    data = relationship("BuoyData", back_populates="buoy", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="buoy", cascade="all, delete-orphan")
    status_logs = relationship("BuoyStatusLog", back_populates="buoy", cascade="all, delete-orphan")


class BuoyStatusLog(Base):
    """浮标状态变更日志"""
    __tablename__ = "buoy_status_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buoy_id = Column(UUID(as_uuid=True), ForeignKey("buoys.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(BuoyStatus), nullable=False)  # 变更后的状态
    previous_status = Column(Enum(BuoyStatus))  # 变更前的状态
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # 变更时间
    reason = Column(String(50))  # 变更原因: low_battery, drift_detected, manual, timeout, recovered
    latitude = Column(Numeric(10, 7))  # 变更时位置
    longitude = Column(Numeric(10, 7))
    battery_level = Column(Integer)  # 变更时电量

    buoy = relationship("Buoy", back_populates="status_logs")


class BuoyData(Base):
    __tablename__ = "buoy_data"

    time = Column(DateTime(timezone=True), primary_key=True)
    buoy_id = Column(UUID(as_uuid=True), ForeignKey("buoys.id", ondelete="CASCADE"), primary_key=True)
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    temperature = Column(Numeric(5, 2))
    salinity = Column(Numeric(5, 2))
    ph = Column(Numeric(4, 2))
    dissolved_oxygen = Column(Numeric(5, 2))
    turbidity = Column(Numeric(6, 2))
    chlorophyll = Column(Numeric(5, 2))
    wave_height = Column(Numeric(5, 2))
    battery_level = Column(Integer)  # 电量
    drift_flagged = Column(Boolean, default=False)  # 漂移期间标记

    buoy = relationship("Buoy", back_populates="data")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buoy_id = Column(UUID(as_uuid=True), ForeignKey("buoys.id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    param_name = Column(String(50), nullable=False)
    threshold_value = Column(Numeric)
    actual_value = Column(Numeric, nullable=False)
    severity = Column(Enum(AlertSeverity), default=AlertSeverity.warning)
    status = Column(Enum(AlertStatus), default=AlertStatus.triggered)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(100))
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(String(100))
    remarks = Column(String(500))  # 处理备注

    buoy = relationship("Buoy", back_populates="alerts")


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buoy_id = Column(UUID(as_uuid=True), ForeignKey("buoys.id", ondelete="CASCADE"), nullable=True)
    param_name = Column(String(50), nullable=False)
    min_threshold = Column(Numeric)
    max_threshold = Column(Numeric)
    severity = Column(Enum(AlertSeverity), default=AlertSeverity.warning)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    buoy = relationship("Buoy", foreign_keys=[buoy_id])


class CombinedAlertRule(Base):
    __tablename__ = "combined_alert_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    buoy_id = Column(UUID(as_uuid=True), ForeignKey("buoys.id", ondelete="CASCADE"), nullable=True)
    conditions = Column(JSON, nullable=False)
    severity = Column(Enum(AlertSeverity), default=AlertSeverity.warning)
    enabled = Column(Boolean, default=True)
    created_by = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    buoy = relationship("Buoy", foreign_keys=[buoy_id])


# Import User from user.py to avoid circular imports
from app.models.user import User