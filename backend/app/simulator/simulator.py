import random
import math
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models import Buoy, BuoyData, BuoyStatus, Alert, AlertConfig, AlertSeverity, AlertStatus
from app.database import SessionLocal

# Global simulator registry
simulator_registry: Dict[str, "DataSimulator"] = {}


class ScenarioType:
    """Simulation scenario types"""
    NORMAL = "normal"
    TEMPERATURE_SPIKE = "temperature_spike"
    TEMPERATURE_DROP = "temperature_drop"
    SALINITY_ANOMALY = "salinity_anomaly"
    PH_DROPS = "ph_drops"
    STORM = "storm"
    SENSOR_FAULT = "sensor_fault"


class DataSimulator:
    """海洋浮标数据模拟器 - 支持多场景和故障注入"""

    BUOY_CONFIGS = [
        {"name": "渤海浮标01号", "code": "BH-001", "lat": 38.7654321, "lon": 120.1234567, "depth": 10.5, "sea_area": "渤海"},
        {"name": "黄海浮标01号", "code": "HH-001", "lat": 35.5678901, "lon": 123.4567890, "depth": 15.0, "sea_area": "黄海"},
        {"name": "东海浮标01号", "code": "DH-001", "lat": 28.2345678, "lon": 122.8765432, "depth": 20.0, "sea_area": "东海"},
        {"name": "南海浮标01号", "code": "NH-001", "lat": 18.3456789, "lon": 110.9876543, "depth": 25.0, "sea_area": "南海"},
        {"name": "南海浮标02号", "code": "NH-002", "lat": 16.4567890, "lon": 112.8765432, "depth": 30.0, "sea_area": "南海"},
    ]

    PARAM_CONFIG = {
        "temperature": {"base": 22.0, "range": (5, 35), "amplitude": 3.0, "period": 24, "unit": "°C"},
        "salinity": {"base": 34.0, "range": (28, 38), "variation": 0.5, "unit": "PSU"},
        "ph": {"base": 8.1, "range": (7.0, 8.8), "variation": 0.05, "unit": ""},
        "dissolved_oxygen": {"base": 7.5, "range": (4, 12), "amplitude": 0.8, "period": 24, "unit": "mg/L"},
        "turbidity": {"base": 10.0, "range": (0, 60), "variation": 5.0, "unit": "NTU"},
        "chlorophyll": {"base": 5.0, "range": (0, 25), "variation": 1.0, "unit": "μg/L"},
        "wave_height": {"base": 1.5, "range": (0, 6), "variation": 0.5, "unit": "m"},
    }

    def __init__(self, mqtt_service=None):
        self.buoys: List[str] = []  # Store buoy_id (str) instead of Buoy objects
        self.current_values: Dict[str, Dict] = {}
        self.mqtt_service = mqtt_service
        self.sampling_interval = 10

        # Scenario settings
        self._current_scenario: str = ScenarioType.NORMAL
        self._scenario_start_time: Optional[datetime] = None
        self._scenario_duration: int = 60  # seconds
        self._buoy_scenarios: Dict[str, str] = {}  # buoy_id -> scenario

        # Fault injection
        self._buoy_faults: Dict[str, Dict] = {}  # buoy_id -> fault config
        self._offline_buoys: Dict[str, float] = {}  # buoy_id -> offline_until timestamp

        # Battery management
        self._buoy_battery: Dict[str, int] = {}  # buoy_id -> battery level (0-100)
        self._battery_decay_rate: float = 0.02  # 每秒衰减0.02%（大约1小时从100%降到28%左右）

        # Drift management
        self._buoy_drift_offset: Dict[str, Dict] = {}  # buoy_id -> {"lat_offset": float, "lon_offset": float}
        self._drift_scenarios: Dict[str, str] = {}  # buoy_id -> "drifting" or None

    def initialize(self, db: Session):
        """Initialize buoys - load defaults and all activated buoys from DB"""
        # First, ensure default buoys exist in DB and mark them as activated
        for config in self.BUOY_CONFIGS:
            existing = db.query(Buoy).filter(Buoy.code == config["code"]).first()
            if existing:
                # Mark default buoys as activated if not already
                if not existing.is_activated:
                    existing.is_activated = True
                    db.commit()
                self.buoys.append(str(existing.id))
                self.current_values[str(existing.id)] = self._generate_initial_values()
                # 从数据库读取当前电量，而不是重置为100%
                if existing.battery_level is not None:
                    self._buoy_battery[str(existing.id)] = existing.battery_level
                else:
                    self._buoy_battery[str(existing.id)] = 100
                simulator_registry[str(existing.id)] = self
            else:
                buoy = Buoy(
                    name=config["name"],
                    code=config["code"],
                    latitude=config["lat"],
                    longitude=config["lon"],
                    depth=config["depth"],
                    sea_area=config["sea_area"],
                    status=BuoyStatus.online,
                    is_activated=True
                )
                db.add(buoy)
                db.commit()
                db.refresh(buoy)
                self.buoys.append(str(buoy.id))
                self.current_values[str(buoy.id)] = self._generate_initial_values()
                simulator_registry[str(buoy.id)] = self

        # Then, load all other activated buoys from DB (user-added buoys that were activated)
        all_activated_buoys = db.query(Buoy).filter(
            Buoy.is_activated == True
        ).all()

        for buoy in all_activated_buoys:
            # Skip if already added from BUOY_CONFIGS
            if str(buoy.id) in self.buoys:
                continue
            self.buoys.append(str(buoy.id))
            self.current_values[str(buoy.id)] = self._generate_initial_values()
            # 从数据库读取当前电量，而不是重置为100%
            if buoy.battery_level is not None:
                self._buoy_battery[str(buoy.id)] = buoy.battery_level
            else:
                self._buoy_battery[str(buoy.id)] = 100
            simulator_registry[str(buoy.id)] = self
            print(f"[Simulator] Restored activated buoy: {buoy.name} ({buoy.code})")

    def _generate_initial_values(self) -> Dict[str, float]:
        """Generate initial values"""
        values = {}
        for param, config in self.PARAM_CONFIG.items():
            values[param] = random.uniform(
                config["range"][0] + (config["range"][1] - config["range"][0]) * 0.3,
                config["range"][0] + (config["range"][1] - config["range"][0]) * 0.7
            )
        # 初始电量100%
        values["battery_level"] = 100
        return values

    def generate_data(self, db: Session) -> List[BuoyData]:
        """Generate data for all buoys"""
        now = datetime.utcnow()
        data_list = []
        buoy_data_for_mqtt = []

        # Check if scenario should end
        self._check_scenario_end()

        for buoy_id in self.buoys:
            # Reload buoy from database to avoid detached instance errors
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                # Buoy was deleted, remove from list
                self.buoys.remove(buoy_id)
                if buoy_id in self.current_values:
                    del self.current_values[buoy_id]
                if buoy_id in simulator_registry:
                    del simulator_registry[buoy_id]
                print(f"[Simulator] Removed deleted buoy {buoy_id} from simulator")
                continue

            # Handle temporary offline (timer-based)
            if buoy_id in self._offline_buoys:
                if time.time() < self._offline_buoys[buoy_id]:
                    # Buoy is temporarily offline (timer), generate empty data row
                    data = BuoyData(
                        time=now,
                        buoy_id=buoy.id,
                        latitude=float(buoy.latitude) if buoy.latitude else float(buoy.base_latitude),
                        longitude=float(buoy.longitude) if buoy.longitude else float(buoy.base_longitude),
                        drift_flagged=True,
                        battery_level=None
                    )
                    data_list.append(data)
                    mqtt_data = {
                        "buoy_id": buoy_id,
                        "buoy_name": buoy.name,
                        "status": "offline",
                        "timestamp": now.isoformat(),
                        "latitude": float(buoy.latitude) if buoy.latitude else float(buoy.base_latitude),
                        "longitude": float(buoy.longitude) if buoy.longitude else float(buoy.base_longitude),
                        "drift_flagged": True,
                        "data": {}
                    }
                    buoy_data_for_mqtt.append(mqtt_data)
                    continue
                else:
                    # Bring buoy back online
                    del self._offline_buoys[buoy_id]
                    buoy.status = BuoyStatus.online
                    db.commit()
                    # Publish status change to MQTT when buoy comes back online
                    if self.mqtt_service and self.mqtt_service.is_connected():
                        self.mqtt_service.publish_status_change(buoy_id, "online")

            # Skip disconnected buoys (失联状态：生成空数据行)
            if buoy.status == BuoyStatus.disconnected:
                # 生成空数据行（保留时间戳，传感器数据为空）
                data = BuoyData(
                    time=now,
                    buoy_id=buoy.id,
                    latitude=float(buoy.latitude) if buoy.latitude else float(buoy.base_latitude),
                    longitude=float(buoy.longitude) if buoy.longitude else float(buoy.base_longitude),
                    drift_flagged=True,
                    battery_level=None
                )
                data_list.append(data)
                mqtt_data = {
                    "buoy_id": buoy_id,
                    "buoy_name": buoy.name,
                    "status": "disconnected",
                    "timestamp": now.isoformat(),
                    "latitude": float(buoy.latitude) if buoy.latitude else float(buoy.base_latitude),
                    "longitude": float(buoy.longitude) if buoy.longitude else float(buoy.base_longitude),
                    "drift_flagged": True,
                    "data": {}
                }
                buoy_data_for_mqtt.append(mqtt_data)
                continue

            # 离线状态：生成空数据行（保留时间戳，传感器数据为空）
            if buoy.status == BuoyStatus.offline:
                data = BuoyData(
                    time=now,
                    buoy_id=buoy.id,
                    latitude=float(buoy.latitude) if buoy.latitude else float(buoy.base_latitude),
                    longitude=float(buoy.longitude) if buoy.longitude else float(buoy.base_longitude),
                    drift_flagged=True,
                    battery_level=None
                )
                data_list.append(data)
                mqtt_data = {
                    "buoy_id": buoy_id,
                    "buoy_name": buoy.name,
                    "status": "offline",
                    "timestamp": now.isoformat(),
                    "latitude": float(buoy.latitude) if buoy.latitude else float(buoy.base_latitude),
                    "longitude": float(buoy.longitude) if buoy.longitude else float(buoy.base_longitude),
                    "drift_flagged": True,
                    "data": {}
                }
                buoy_data_for_mqtt.append(mqtt_data)
                continue

            # Check buoy-specific scenario
            buoy_scenario = self._buoy_scenarios.get(buoy_id, self._current_scenario)
            values = self._apply_scenario(
                buoy_id,
                self.current_values[buoy_id],
                buoy_scenario,
                now
            )

            # Apply fault injection if active
            if buoy_id in self._buoy_faults:
                values = self._apply_fault(buoy_id, values)

            # Update parameter values
            for param, config in self.PARAM_CONFIG.items():
                if param in values:
                    # Limit within range
                    min_val, max_val = config["range"]
                    values[param] = max(min_val, min(max_val, values[param]))

            # 电量衰减
            if buoy_id not in self._buoy_battery:
                self._buoy_battery[buoy_id] = 100
            # 每10秒采样一次，衰减0.2%
            self._buoy_battery[buoy_id] = max(0, self._buoy_battery[buoy_id] - self._battery_decay_rate * self.sampling_interval)
            values["battery_level"] = int(self._buoy_battery[buoy_id])

            # 更新浮标电量到数据库
            buoy.battery_level = int(self._buoy_battery[buoy_id])
            db.commit()

            # 计算位置（带漂移）
            lat_offset = 0.0
            lon_offset = 0.0

            # 验证浮标坐标有效性，跳过无效坐标的浮标
            try:
                test_lat = float(buoy.latitude)
                test_lon = float(buoy.longitude)
                if math.isnan(test_lat) or math.isnan(test_lon) or math.isinf(test_lat) or math.isinf(test_lon):
                    print(f"[Simulator] Skipping buoy {buoy_id} with invalid coordinates: lat={buoy.latitude}, lon={buoy.longitude}")
                    continue
            except (TypeError, ValueError):
                print(f"[Simulator] Skipping buoy {buoy_id} with non-numeric coordinates: lat={buoy.latitude}, lon={buoy.longitude}")
                continue

            # 获取漂移半径，默认0.01度（约1km）
            drift_radius = float(buoy.drift_radius) if hasattr(buoy, 'drift_radius') and buoy.drift_radius else 0.01

            # 初始化当前位置记录
            if buoy_id not in self._buoy_drift_offset:
                self._buoy_drift_offset[buoy_id] = {
                    "lat": 0.0,
                    "lon": 0.0,
                    "velocity_lat": 0.0,
                    "velocity_lon": 0.0,
                    "is_drift_alert": False
                }

            drift_state = self._buoy_drift_offset[buoy_id]

            # 根据状态计算漂移
            if drift_state["is_drift_alert"]:
                # 漂移告警状态：随洋流漂移，速度逐渐减小但方向可能改变
                drift_state["velocity_lat"] += random.uniform(-0.0005, 0.0005)
                drift_state["velocity_lon"] += random.uniform(-0.0005, 0.0005)
                # 限制最大速度
                max_speed = 0.005
                drift_state["velocity_lat"] = max(-max_speed, min(max_speed, drift_state["velocity_lat"]))
                drift_state["velocity_lon"] = max(-max_speed, min(max_speed, drift_state["velocity_lon"]))

                drift_state["lat"] += drift_state["velocity_lat"]
                drift_state["lon"] += drift_state["velocity_lon"]
                lat_offset = drift_state["lat"]
                lon_offset = drift_state["lon"]
            else:
                # 正常状态：在漂移圈内随机运动
                # 使用随机游走算法
                drift_state["velocity_lat"] += random.uniform(-0.0002, 0.0002)
                drift_state["velocity_lon"] += random.uniform(-0.0002, 0.0002)
                # 阻尼效应，防止速度过大
                drift_state["velocity_lat"] *= 0.95
                drift_state["velocity_lon"] *= 0.95

                drift_state["lat"] += drift_state["velocity_lat"]
                drift_state["lon"] += drift_state["velocity_lon"]

                # 检查是否超出漂移圈，如果超出则反弹回来
                distance = math.sqrt(drift_state["lat"]**2 + drift_state["lon"]**2)
                if distance > drift_radius:
                    # 计算角度并反向
                    angle = math.atan2(drift_state["lat"], drift_state["lon"])
                    drift_state["lat"] = drift_radius * math.cos(angle) * random.uniform(0.8, 0.95)
                    drift_state["lon"] = drift_radius * math.sin(angle) * random.uniform(0.8, 0.95)
                    drift_state["velocity_lat"] *= -0.5
                    drift_state["velocity_lon"] *= -0.5

                lat_offset = drift_state["lat"]
                lon_offset = drift_state["lon"]

            # 使用base位置作为漂移计算的基准，而不是累积偏移的buoy.latitude
            base_lat = float(buoy.base_latitude) if buoy.base_latitude else float(buoy.latitude)
            base_lon = float(buoy.base_longitude) if buoy.base_longitude else float(buoy.longitude)

            current_lat = base_lat + lat_offset
            current_lon = base_lon + lon_offset

            # 如果在漂移状态，持续更新浮标的实时位置到数据库（用于持久化）
            if drift_state["is_drift_alert"]:
                buoy.latitude = current_lat
                buoy.longitude = current_lon
                db.commit()  # 立即提交位置更新

            self.current_values[buoy_id] = values

            # 检查低电量模式（<=10%但>0）
            low_battery = self._buoy_battery[buoy_id] <= 10 and self._buoy_battery[buoy_id] > 0
            # 检查无电状态（电量=0）
            no_power = self._buoy_battery[buoy_id] <= 0

            # 检查漂移告警（使用内部状态）
            drift_alert = drift_state["is_drift_alert"]

            # 无电状态：浮标回到base位置
            if no_power:
                # 如果之前是漂移告警状态或当前状态是drift_alert，保留drift_alert以便前端显示组合状态
                was_drift_alert = drift_state["is_drift_alert"] or buoy.status.value == BuoyStatus.drift_alert.value
                if buoy.status.value != BuoyStatus.no_power.value:
                    # 进入无电状态，浮标回到锚定位置（base位置）
                    # 如果base_latitude为null，使用当前latitude作为新的base
                    if buoy.base_latitude is None or buoy.base_longitude is None:
                        buoy.base_latitude = buoy.latitude
                        buoy.base_longitude = buoy.longitude
                        print(f"[Simulator] Buoy {buoy_id} base position not set, using current position as base")
                    buoy.latitude = buoy.base_latitude
                    buoy.longitude = buoy.base_longitude
                    buoy.status = BuoyStatus.no_power
                    db.commit()
                    print(f"[Simulator] Buoy {buoy_id} entered no power mode (battery exhausted), returned to base position")
                # 发送无电状态消息（带漂移标志以便前端显示组合状态）
                # 位置使用base位置（因为进入无电时已经设置为base）
                mqtt_data = {
                    "buoy_id": buoy_id,
                    "buoy_name": buoy.name,
                    "status": "drift_alert" if was_drift_alert else "no_power",
                    "timestamp": now.isoformat(),
                    "latitude": float(buoy.latitude) if buoy.latitude else float(buoy.base_latitude),
                    "longitude": float(buoy.longitude) if buoy.longitude else float(buoy.base_longitude),
                    "drift_flagged": was_drift_alert,
                    "low_battery": False,
                    "no_power": True,  # 无电状态标志
                    "data": {}
                }
                buoy_data_for_mqtt.append(mqtt_data)
                continue

            # 低电量或漂移告警时只发送定位和电量
            restricted = low_battery or drift_alert

            # 当电量低于10%时，自动更新状态为low_battery（如果当前是online）
            if low_battery and not drift_alert and buoy.status == BuoyStatus.online:
                buoy.status = BuoyStatus.low_battery
                db.commit()
                print(f"[Simulator] Buoy {buoy_id} entered low battery mode ({self._buoy_battery[buoy_id]}%)")

            # 只在电量大于0时保存电量数据
            current_battery = int(self._buoy_battery[buoy_id])
            data = BuoyData(
                time=now,
                buoy_id=buoy.id,
                latitude=current_lat,
                longitude=current_lon,
                drift_flagged=drift_alert or restricted,  # low_battery也标记，排除在统计外
                battery_level=current_battery if current_battery > 0 else None
            )

            if not restricted:
                data.temperature = round(values["temperature"], 2)
                data.salinity = round(values["salinity"], 2)
                data.ph = round(values["ph"], 2)
                data.dissolved_oxygen = round(values["dissolved_oxygen"], 2)
                data.turbidity = round(values["turbidity"], 2)
                data.chlorophyll = round(values["chlorophyll"], 2)
                data.wave_height = round(values["wave_height"], 2)

            data_list.append(data)

            # 只在电量大于0时发送电量数据，避免电量为0时覆盖数据库中的恢复电量
            current_battery = int(self._buoy_battery[buoy_id])
            mqtt_data = {
                "buoy_id": buoy_id,
                "buoy_name": buoy.name,
                "status": buoy.status.value if hasattr(buoy.status, 'value') else buoy.status,
                "timestamp": now.isoformat(),
                "latitude": current_lat,
                "longitude": current_lon,
                "drift_flagged": drift_alert,
                "low_battery": low_battery,  # 低电量标志，用于前端显示
                "data": {}
            }
            # 只有电量大于0时才发送电量
            if current_battery > 0:
                mqtt_data["battery_level"] = current_battery

            if not restricted:
                mqtt_data["data"] = {
                    "temperature": round(values["temperature"], 2),
                    "salinity": round(values["salinity"], 2),
                    "ph": round(values["ph"], 2),
                    "dissolved_oxygen": round(values["dissolved_oxygen"], 2),
                    "turbidity": round(values["turbidity"], 2),
                    "chlorophyll": round(values["chlorophyll"], 2),
                    "wave_height": round(values["wave_height"], 2)
                }

            buoy_data_for_mqtt.append(mqtt_data)

        # Publish to MQTT - data will be saved to DB by MQTT handler
        if self.mqtt_service and self.mqtt_service.is_connected():
            self.mqtt_service.publish_all_buoys_data(buoy_data_for_mqtt)
            print(f"[Simulator] Published {len(buoy_data_for_mqtt)} buoy records to MQTT")
        else:
            # Fallback: save directly to DB if MQTT not connected
            for data in data_list:
                db.add(data)
            db.commit()
            print(f"[Simulator] Saved {len(data_list)} records directly to DB (MQTT not connected)")

        return data_list

    def _apply_scenario(self, buoy_id: str, base_values: Dict, scenario: str, now: datetime) -> Dict[str, float]:
        """Apply scenario effects to values"""
        values = base_values.copy()

        if scenario == ScenarioType.TEMPERATURE_SPIKE:
            # Sudden temperature rise - for simulating heat wave
            values["temperature"] = values.get("temperature", 22) + random.uniform(5, 10)
            values["dissolved_oxygen"] = values.get("dissolved_oxygen", 7) - random.uniform(1, 2)

        elif scenario == ScenarioType.TEMPERATURE_DROP:
            # Sudden temperature drop - for simulating cold current
            values["temperature"] = values.get("temperature", 22) - random.uniform(5, 10)
            values["dissolved_oxygen"] = values.get("dissolved_oxygen", 7) + random.uniform(0.5, 1.5)

        elif scenario == ScenarioType.SALINITY_ANOMALY:
            # Salinity sudden change - freshwater intrusion
            values["salinity"] = values.get("salinity", 34) - random.uniform(4, 8)
            values["ph"] = values.get("ph", 8.1) - random.uniform(0.2, 0.5)

        elif scenario == ScenarioType.PH_DROPS:
            # pH drops (acidification)
            values["ph"] = values.get("ph", 8.1) - random.uniform(0.3, 0.8)
            values["chlorophyll"] = values.get("chlorophyll", 5) + random.uniform(2, 5)

        elif scenario == ScenarioType.STORM:
            # Storm conditions
            values["wave_height"] = values.get("wave_height", 1.5) + random.uniform(3, 5)
            values["turbidity"] = values.get("turbidity", 10) + random.uniform(20, 40)
            values["temperature"] = values.get("temperature", 22) - random.uniform(1, 3)

        elif scenario == ScenarioType.SENSOR_FAULT:
            # Sensor fault - return extreme or null values
            values["temperature"] = random.choice([random.uniform(0, 2), random.uniform(45, 50)])
            values["salinity"] = random.uniform(5, 10)

        # Normal case with slight variations
        for param, config in self.PARAM_CONFIG.items():
            if param not in values:
                values[param] = config["base"]

            if scenario == ScenarioType.NORMAL:
                if "amplitude" in config:
                    hour = now.hour + now.minute / 60.0
                    phase = 2 * math.pi * hour / config["period"]
                    base_val = config["base"]
                    variation = config["amplitude"] * math.sin(phase)
                    values[param] = base_val + variation + random.uniform(-0.1, 0.1)
                elif "variation" in config:
                    values[param] += random.uniform(-config["variation"], config["variation"])

        return values

    def _apply_fault(self, buoy_id: str, values: Dict[str, float]) -> Dict[str, float]:
        """Apply fault injection effects"""
        fault = self._buoy_faults.get(buoy_id)
        if not fault:
            return values

        fault_type = fault.get("type")
        fault_start = fault.get("start_time", 0)
        elapsed = time.time() - fault_start

        if fault_type == "offline":
            # Buoy goes offline
            return values
        elif fault_type == "temperature_spike":
            values["temperature"] = random.uniform(38, 45)
        elif fault_type == "salinity_drop":
            values["salinity"] = random.uniform(20, 25)
        elif fault_type == "ph_spike":
            values["ph"] = random.uniform(9.0, 9.5)

        return values

    def _check_scenario_end(self):
        """Check if current scenario should end"""
        if self._scenario_start_time is None:
            return

        elapsed = (datetime.utcnow() - self._scenario_start_time).total_seconds()
        if elapsed >= self._scenario_duration:
            self._current_scenario = ScenarioType.NORMAL
            self._scenario_start_time = None
            print("[Simulator] Scenario ended, returning to normal")

    def check_alerts(self, db: Session, data_list: List[BuoyData]) -> List[Alert]:
        """Check alerts triggered by data"""
        alerts = []
        configs = db.query(AlertConfig).filter(AlertConfig.enabled == True).all()
        config_map = {c.param_name: c for c in configs}

        for data in data_list:
            for param in ["temperature", "salinity", "ph", "dissolved_oxygen", "turbidity", "chlorophyll", "wave_height"]:
                value = getattr(data, param)
                if value is None:
                    continue

                config = config_map.get(param)
                if not config:
                    continue

                is_alert = False
                threshold_value = None

                if config.max_threshold and value > config.max_threshold:
                    is_alert = True
                    threshold_value = config.max_threshold
                elif config.min_threshold and value < config.min_threshold:
                    is_alert = True
                    threshold_value = config.min_threshold

                if is_alert:
                    existing = db.query(Alert).filter(
                        Alert.buoy_id == data.buoy_id,
                        Alert.param_name == param,
                        Alert.status != AlertStatus.resolved
                    ).first()

                    if not existing:
                        alert = Alert(
                            buoy_id=data.buoy_id,
                            alert_type="threshold_exceeded",
                            param_name=param,
                            threshold_value=threshold_value,
                            actual_value=value,
                            severity=config.severity,
                            status=AlertStatus.triggered
                        )
                        alerts.append(alert)

        return alerts

    # ========== Public API for scenario and fault control ==========

    def set_global_scenario(self, scenario: str, duration: int = 60):
        """Set global scenario for all buoys"""
        self._current_scenario = scenario
        self._scenario_start_time = datetime.utcnow()
        self._scenario_duration = duration
        print(f"[Simulator] Global scenario set to: {scenario} for {duration}s")

    def set_buoy_scenario(self, buoy_id: str, scenario: str, duration: int = 60):
        """Set scenario for specific buoy"""
        self._buoy_scenarios[buoy_id] = scenario
        if duration > 0:
            threading.Timer(duration, self._clear_buoy_scenario, args=(buoy_id,)).start()
        print(f"[Simulator] Buoy {buoy_id} scenario set to: {scenario}")

    def _clear_buoy_scenario(self, buoy_id: str):
        """Clear buoy-specific scenario"""
        if buoy_id in self._buoy_scenarios:
            del self._buoy_scenarios[buoy_id]
            print(f"[Simulator] Buoy {buoy_id} scenario cleared")

    def inject_fault(self, buoy_id: str, fault_type: str, duration: int = 0):
        """Inject fault into specific buoy (duration=0 means until manually cleared)"""
        self._buoy_faults[buoy_id] = {
            "type": fault_type,
            "start_time": time.time(),
            "duration": duration
        }
        if duration > 0:
            threading.Timer(duration, self._clear_fault, args=(buoy_id,)).start()
        print(f"[Simulator] Fault injected to buoy {buoy_id}: {fault_type}")

    def start_drift(self, buoy_id: str):
        """手动触发漂移告警（锚定断开）"""
        import math
        # 使用较大的初始偏移量（1.5-2倍漂移半径），确保浮标立即出现在圈外
        # 漂移半径默认0.01度，初始偏移设为0.015-0.020度
        angle = random.uniform(0, 2 * math.pi)  # 随机方向
        drift_distance = random.uniform(0.015, 0.020)  # 1.5-2倍默认漂移半径
        initial_lat = drift_distance * math.sin(angle)
        initial_lon = drift_distance * math.cos(angle)

        if buoy_id in self._buoy_drift_offset:
            self._buoy_drift_offset[buoy_id]["is_drift_alert"] = True
            self._buoy_drift_offset[buoy_id]["lat"] = initial_lat
            self._buoy_drift_offset[buoy_id]["lon"] = initial_lon
            self._buoy_drift_offset[buoy_id]["velocity_lat"] = random.uniform(-0.003, 0.003)
            self._buoy_drift_offset[buoy_id]["velocity_lon"] = random.uniform(-0.003, 0.003)
        else:
            self._buoy_drift_offset[buoy_id] = {
                "lat": initial_lat,
                "lon": initial_lon,
                "velocity_lat": random.uniform(-0.003, 0.003),
                "velocity_lon": random.uniform(-0.003, 0.003),
                "is_drift_alert": True
            }
        print(f"[Simulator] Buoy {buoy_id} started drift alert manually, initial offset: lat={initial_lat:.6f}, lon={initial_lon:.6f}")

    def stop_drift(self, buoy_id: str):
        """恢复浮标：重置位置到锚定点，清除漂移告警状态"""
        if buoy_id in self._buoy_drift_offset:
            self._buoy_drift_offset[buoy_id] = {
                "lat": 0.0,
                "lon": 0.0,
                "velocity_lat": 0.0,
                "velocity_lon": 0.0,
                "is_drift_alert": False
            }
        print(f"[Simulator] Buoy {buoy_id} recovered from drift alert")

    def recharge_battery(self, buoy_id: str):
        """恢复浮充电量到100%（模拟工作人员更换电池）"""
        if buoy_id in self._buoy_battery:
            self._buoy_battery[buoy_id] = 100
            print(f"[Simulator] Buoy {buoy_id} battery recharged to 100%")
        else:
            self._buoy_battery[buoy_id] = 100
            print(f"[Simulator] Buoy {buoy_id} battery initialized to 100%")

    def _clear_fault(self, buoy_id: str):
        """Clear fault from buoy"""
        if buoy_id in self._buoy_faults:
            del self._buoy_faults[buoy_id]
            print(f"[Simulator] Fault cleared from buoy {buoy_id}")

    def set_buoy_offline(self, buoy_id: str, duration: int = 60):
        """Simulate buoy going offline"""
        self._offline_buoys[buoy_id] = time.time() + duration
        print(f"[Simulator] Buoy {buoy_id} set offline for {duration}s")

    def set_buoy_online(self, buoy_id: str):
        """Bring buoy back online"""
        if buoy_id in self._offline_buoys:
            del self._offline_buoys[buoy_id]
            print(f"[Simulator] Buoy {buoy_id} brought back online")

    def activate_buoy(self, buoy_id: str, db: Session):
        """Activate a buoy - add it to simulator and start generating data"""
        # Check if already active
        if buoy_id in self.buoys:
            print(f"[Simulator] Buoy {buoy_id} is already active")
            return

        # Load buoy from database
        from app.models import Buoy, BuoyStatus
        buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
        if not buoy:
            print(f"[Simulator] Buoy {buoy_id} not found in database")
            return

        # Add to simulator (store buoy_id string, not Buoy object)
        self.buoys.append(buoy_id)
        self.current_values[buoy_id] = self._generate_initial_values()
        # 从数据库读取当前电量
        if buoy.battery_level is not None:
            self._buoy_battery[buoy_id] = buoy.battery_level
        else:
            self._buoy_battery[buoy_id] = 100
        simulator_registry[buoy_id] = self

        # Update status and set is_activated flag (persisted to DB)
        buoy.status = BuoyStatus.online
        buoy.is_activated = True
        db.commit()

        print(f"[Simulator] Activated buoy {buoy_id} ({buoy.name}) - now generating data")

    def get_status(self) -> Dict:
        """Get simulator status"""
        return {
            "buoys": len(self.buoys),
            "current_scenario": self._current_scenario,
            "buoy_scenarios": self._buoy_scenarios,
            "buoy_faults": list(self._buoy_faults.keys()),
            "offline_buoys": list(self._offline_buoys.keys()),
            "sampling_interval": self.sampling_interval
        }


def run_simulator():
    """Run simulator standalone"""
    from app.config import get_settings
    settings = get_settings()

    if not settings.simulator_enabled:
        print("[Simulator] Disabled")
        return

    print("[Simulator] Starting...")
    db = SessionLocal()
    try:
        simulator = DataSimulator()
        simulator.initialize(db)
        print(f"[Simulator] Initialized {len(simulator.buoys)} buoys")

        while True:
            time.sleep(10)

            data_list = simulator.generate_data(db)
            for data in data_list:
                db.add(data)

            db.commit()
            print(f"[Simulator] Generated {len(data_list)} records at {datetime.utcnow()}")

            alerts = simulator.check_alerts(db, data_list)
            for alert in alerts:
                db.add(alert)
            if alerts:
                db.commit()
                print(f"[Simulator] {len(alerts)} alerts triggered")

    except Exception as e:
        print(f"[Simulator] Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    run_simulator()
