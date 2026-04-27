import json
import time
import threading
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List
from sqlalchemy.orm import Session
import paho.mqtt.client as mqtt
from app.database import SessionLocal
from app.models import Buoy, BuoyData, BuoyStatus, BuoyStatusLog, Alert, AlertConfig, AlertStatus, AlertSeverity, CombinedAlertRule
import uuid


class MQTTService:
    """MQTT服务 - 处理与EMQX broker的连接和消息收发"""

    # MQTT Topics
    TOPIC_BUOY_DATA = "buoy/data/{buoy_id}"
    TOPIC_BUOY_COMMAND = "buoy/command/{buoy_id}"
    TOPIC_BUOY_STATUS = "buoy/status/{buoy_id}"
    TOPIC_BROADCAST_DATA = "buoy/data/all"
    TOPIC_ALERT = "buoy/alert"

    def __init__(self, broker_host: str = "emqx", broker_port: int = 1883,
                 username: str = "admin", password: str = "asdfghjkl66"):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password

        # Use client_id to ensure unique connection to EMQX
        self.client = mqtt.Client(client_id=f"obmap-backend-{uuid.uuid4().hex[:8]}")
        self.client.username_pw_set(username, password)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self._connected = False
        self._subscribers: Dict[str, Callable] = {}
        self._buoy_ids: list = []
        self._reconnect_thread: Optional[threading.Thread] = None
        self._should_reconnect = True
        # Track consecutive normal readings for alert auto-recovery
        # Key: f"{buoy_id}_{param}", Value: consecutive normal count
        self._consecutive_normal: Dict[str, int] = {}
        self._recovery_threshold = 3  # Need 3 consecutive normal readings to auto-recover

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[MQTT] Connected to EMQX at {self.broker_host}:{self.broker_port}")
            self._connected = True
            self._subscribe_topics()
        elif rc == 1:
            print(f"[MQTT] Connection refused: incorrect protocol version")
        elif rc == 2:
            print(f"[MQTT] Connection refused: invalid client identifier")
        elif rc == 3:
            print(f"[MQTT] Connection refused: server unavailable")
        elif rc == 4:
            print(f"[MQTT] Connection refused: bad username or password")
        elif rc == 5:
            print(f"[MQTT] Connection refused: not authorized")
        else:
            print(f"[MQTT] Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        print(f"[MQTT] Disconnected with code {rc}")
        self._connected = False
        if rc != 0 and self._should_reconnect:
            print("[MQTT] Attempting to reconnect...")
            self._start_reconnect_thread()

    def _start_reconnect_thread(self):
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()

    def _reconnect_loop(self):
        """Reconnection loop with exponential backoff"""
        delay = 5
        max_delay = 60
        while self._should_reconnect and not self._connected:
            try:
                print(f"[MQTT] Reconnecting in {delay}s...")
                time.sleep(delay)
                result = self.client.connect(self.broker_host, self.broker_port, 60)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    self.client.loop_start()
                    return
                delay = min(delay * 2, max_delay)
            except Exception as e:
                print(f"[MQTT] Reconnection error: {e}")
                delay = min(delay * 2, max_delay)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic

            print(f"[MQTT] Message on {topic}: {payload}")

            # Handle buoy data broadcast
            if topic == self.TOPIC_BROADCAST_DATA or topic == "buoy/data/all":
                buoys_data = payload.get("buoys", [])
                for item in buoys_data:
                    buoy_id = item.get("buoy_id")
                    if buoy_id:
                        self._handle_buoy_data(buoy_id, item)

            # Handle single buoy data
            elif topic.startswith("buoy/data/"):
                buoy_id = topic.split("/")[-1]
                if buoy_id != "all":
                    self._handle_buoy_data(buoy_id, payload)

            # Handle control commands
            elif topic.startswith("buoy/command/"):
                buoy_id = topic.split("/")[-1]
                self._handle_command(buoy_id, payload)

            # Handle status changes
            elif topic.startswith("buoy/status/"):
                buoy_id = topic.split("/")[-1]
                self._handle_status_change(buoy_id, payload)

        except json.JSONDecodeError as e:
            print(f"[MQTT] Failed to decode message: {e}")
        except Exception as e:
            print(f"[MQTT] Error processing message: {e}")

    def _subscribe_topics(self):
        """Subscribe to all necessary topics"""
        topics = [
            ("buoy/data/all", 0),
            ("buoy/command/#", 0),
            ("buoy/status/#", 0),
        ]
        self.client.subscribe(topics)
        print("[MQTT] Subscribed to: buoy/data/all, buoy/command/#, buoy/status/#")

    def connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            self.client.reconnect_delay_set(min_delay=1, max_delay=60)
            result = self.client.connect(self.broker_host, self.broker_port, 60)
            if result == mqtt.MQTT_ERR_SUCCESS:
                self.client.loop_start()
                print(f"[MQTT] Connecting to {self.broker_host}:{self.broker_port}...")
                # Wait briefly for connection
                for _ in range(10):
                    time.sleep(0.5)
                    if self._connected:
                        return True
                if not self._connected:
                    print("[MQTT] Connection timeout, but loop started - will retry in background")
                    return True
            else:
                print(f"[MQTT] Connection returned error code: {result}")
                return False
        except Exception as e:
            print(f"[MQTT] Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from MQTT broker"""
        self._should_reconnect = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as e:
            print(f"[MQTT] Error disconnecting: {e}")

    def is_connected(self) -> bool:
        return self._connected and self.client.is_connected()

    def publish_buoy_data(self, buoy_id: str, data: Dict[str, Any]):
        """Publish buoy data to MQTT broker"""
        if not self.is_connected():
            return False

        topic = self.TOPIC_BUOY_DATA.format(buoy_id=buoy_id)
        payload = json.dumps(data)
        result = self.client.publish(topic, payload)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Published to {topic}")
            return True
        else:
            print(f"[MQTT] Failed to publish to {topic}: {result.rc}")
            return False

    def publish_all_buoys_data(self, buoys_data: List[Dict[str, Any]]):
        """Publish data for all buoys (broadcast)"""
        if not self.is_connected():
            print("[MQTT] Not connected, skipping MQTT publish")
            return False

        # 只发布到广播topic，不发布到单个浮标topic（避免重复处理）
        topic = self.TOPIC_BROADCAST_DATA
        payload = json.dumps({"buoys": buoys_data, "timestamp": datetime.utcnow().isoformat()})
        result = self.client.publish(topic, payload)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Published broadcast to {topic} ({len(buoys_data)} buoys)")
            return True

        return False

    def publish_alert(self, alert_data: Dict[str, Any]):
        """Publish alert to MQTT for real-time notification"""
        if not self.is_connected():
            return
        topic = self.TOPIC_ALERT
        payload = json.dumps(alert_data)
        result = self.client.publish(topic, payload)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Published alert to {topic}")

    def publish_command(self, buoy_id: str, command: Dict[str, Any]):
        """Publish command to a buoy"""
        topic = self.TOPIC_BUOY_COMMAND.format(buoy_id=buoy_id)
        payload = json.dumps(command)
        result = self.client.publish(topic, payload)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Published command to {topic}: {command}")

    def publish_status_change(self, buoy_id: str, status: str):
        """Publish buoy status change"""
        topic = self.TOPIC_BUOY_STATUS.format(buoy_id=buoy_id)
        payload = json.dumps({
            "buoy_id": buoy_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        })
        result = self.client.publish(topic, payload)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[MQTT] Published status change to {topic}: {status}")

    def _handle_buoy_data(self, buoy_id: str, data: Dict[str, Any]):
        """Handle incoming buoy data - save to database"""
        db = SessionLocal()
        try:
            # battery_level 在顶层，sensor data 在 data 嵌套里
            battery_level = data.get("battery_level")
            drift_flagged = data.get("drift_flagged", False)
            latitude = data.get("latitude")
            longitude = data.get("longitude")
            values = data.get("data", data)

            timestamp = data.get("timestamp")
            if timestamp:
                try:
                    record_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except:
                    record_time = datetime.utcnow()
            else:
                record_time = datetime.utcnow()

            # 获取浮标状态
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                print(f"[MQTT] Buoy {buoy_id} not found")
                return

            # 检查是否处于失联状态 - 记录空数据行（保留时间戳，导出时可见空白行）
            if buoy.status == BuoyStatus.disconnected:
                buoy_data = BuoyData(
                    time=record_time,
                    buoy_id=buoy_id,
                    latitude=latitude,
                    longitude=longitude,
                    battery_level=int(battery_level) if battery_level else None,
                    drift_flagged=True  # 标记为无效数据，排除在统计外
                )
                db.add(buoy_data)
                db.commit()
                print(f"[MQTT] Buoy {buoy_id} is disconnected, saved empty data row")
                return

            # 更新电量
            if battery_level is not None:
                buoy.battery_level = int(battery_level)
                db.commit()

            # 离线、断电状态记录空数据行（保留时间戳，传感器数据为空，导出时可见空白行）
            if buoy.status in (BuoyStatus.offline, BuoyStatus.no_power):
                buoy_data = BuoyData(
                    time=record_time,
                    buoy_id=buoy_id,
                    latitude=latitude,
                    longitude=longitude,
                    battery_level=int(battery_level) if battery_level else None,
                    drift_flagged=True  # 标记为无效数据，排除在统计外
                )
                db.add(buoy_data)
                db.commit()
                print(f"[MQTT] Buoy {buoy_id} is {buoy.status.value}, saved empty data row")
                return

            # 低电量模式只接收定位和电量数据，传感器数据不记录
            restricted = buoy.status == BuoyStatus.low_battery

            # 漂移告警期间标记数据，low_battery也标记（因为传感器数据无效，不应进入统计）
            drift_flagged = buoy.status == BuoyStatus.drift_alert or restricted

            # 检查漂移（只有开启drift_alert_enabled才会检测）
            if latitude is not None and longitude is not None:
                self._check_drift(db, buoy_id, latitude, longitude)
                # 重新检查状态（可能在_check_drift中改变）
                buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
                if buoy.status == BuoyStatus.drift_alert:
                    drift_flagged = True

            # 构建数据记录
            buoy_data = BuoyData(
                time=record_time,
                buoy_id=buoy_id,
                latitude=latitude,
                longitude=longitude,
                battery_level=int(battery_level) if battery_level else None,
                drift_flagged=drift_flagged
            )

            if restricted:
                # 低电量模式：只记录定位和电量，传感器数据为None
                print(f"[MQTT] Buoy {buoy_id} low battery mode - sensor data not recorded")
            else:
                # 正常模式：记录所有数据
                buoy_data.temperature = values.get("temperature")
                buoy_data.salinity = values.get("salinity")
                buoy_data.ph = values.get("ph")
                buoy_data.dissolved_oxygen = values.get("dissolved_oxygen")
                buoy_data.turbidity = values.get("turbidity")
                buoy_data.chlorophyll = values.get("chlorophyll")
                buoy_data.wave_height = values.get("wave_height")

            db.add(buoy_data)
            db.commit()

            print(f"[MQTT] Saved buoy data for {buoy_id} (drift_flagged={drift_flagged}, restricted={restricted})")

            # Check alerts (only if not restricted and not drift flagged)
            if not restricted and not drift_flagged:
                self._check_alerts(db, buoy_id, values)

        except Exception as e:
            print(f"[MQTT] Error saving buoy data: {e}")
            db.rollback()
        finally:
            db.close()

    def _handle_command(self, buoy_id: str, command: Dict[str, Any]):
        """Handle control commands"""
        cmd_type = command.get("type")
        params = command.get("params", {})

        print(f"[MQTT] Command for {buoy_id}: {cmd_type}")

        if cmd_type == "activate":
            # 激活浮标 - 验证activation_key
            self._activate_buoy(buoy_id, params.get("activation_key"))
        elif cmd_type == "set_interval":
            interval = params.get("interval")
            self._update_simulator_interval(buoy_id, interval)
        elif cmd_type == "reboot":
            print(f"[MQTT] Reboot command for {buoy_id}")
        elif cmd_type == "calibrate":
            sensor = params.get("sensor")
            print(f"[MQTT] Calibration for {buoy_id} sensor: {sensor}")
        elif cmd_type == "set_status":
            new_status = params.get("status")
            if new_status in ["online", "offline"]:
                self._update_buoy_status(buoy_id, new_status)
        elif cmd_type == "set_offline":
            # 平台主动下线浮标
            self._update_buoy_status(buoy_id, "offline")
        elif cmd_type == "set_disconnected":
            # 浮标失联（故障/电量耗尽/手动断开）
            self._handle_disconnect(buoy_id, params.get("reason"))
        elif cmd_type == "recover":
            # 恢复指令 - 从失联/低电量/漂移告警恢复
            self._handle_recover(buoy_id, params.get("reason"))
        elif cmd_type == "set_drift_alert":
            # 漂移告警 - 由平台自动触发
            self._handle_drift_alert(buoy_id)
        elif cmd_type == "start_drift":
            # 手动模拟漂移 - 浮标偏离正常位置
            self._handle_start_drift(buoy_id)
        elif cmd_type == "stop_drift":
            # 手动停止漂移 - 浮标回到base位置
            self._handle_stop_drift(buoy_id)
        elif cmd_type == "set_low_battery":
            # 低电量模式
            battery = params.get("battery_level", 10)
            self._handle_low_battery(buoy_id, battery)

    def _update_buoy_status(self, buoy_id: str, new_status: str):
        """Update buoy status in database"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if buoy:
                buoy.status = BuoyStatus(new_status)
                db.commit()
                print(f"[MQTT] Updated buoy {buoy_id} status to {new_status}")
                self._publish_status_change(buoy_id, new_status)
        except Exception as e:
            print(f"[MQTT] Error updating buoy status: {e}")
            db.rollback()
        finally:
            db.close()

    def _update_simulator_interval(self, buoy_id: str, interval: int):
        """Update simulator sampling interval"""
        from app.simulator.simulator import simulator_registry
        if buoy_id in simulator_registry:
            simulator_registry[buoy_id].sampling_interval = interval
            print(f"[MQTT] Updated simulator {buoy_id} interval to {interval}s")

    def _activate_buoy(self, buoy_id: str, activation_key: str = None):
        """激活未激活的浮标"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                print(f"[MQTT] Buoy {buoy_id} not found")
                return

            if buoy.status != BuoyStatus.inactive:
                print(f"[MQTT] Buoy {buoy_id} is not inactive (current: {buoy.status})")
                return

            # 验证activation_key
            if buoy.activation_key and buoy.activation_key != activation_key:
                print(f"[MQTT] Invalid activation key for buoy {buoy_id}")
                return

            # 激活浮标
            buoy.status = BuoyStatus.online
            buoy.is_activated = True
            buoy.battery_level = 100
            # 设置base位置为当前位置
            buoy.base_latitude = buoy.latitude
            buoy.base_longitude = buoy.longitude
            db.commit()

            # 通知simulator开始生成数据
            from app.simulator.simulator import simulator_registry, DataSimulator
            if buoy_id not in simulator_registry:
                # 获取全局simulator实例 (使用 app.state，不是 socket_app.state)
                from app.main import app
                simulator = getattr(app.state, 'simulator', None)
                if simulator:
                    # 添加 buoy_id (str) 而不是 Buoy 对象，避免 detached session 问题
                    simulator.buoys.append(buoy_id)
                    simulator.current_values[buoy_id] = simulator._generate_initial_values()
                    simulator_registry[buoy_id] = simulator
                    print(f"[MQTT] Added buoy {buoy_id} to simulator")

            self.publish_status_change(buoy_id, "online")
            print(f"[MQTT] Buoy {buoy_id} activated successfully")
        except Exception as e:
            print(f"[MQTT] Error activating buoy: {e}")
            db.rollback()
        finally:
            db.close()

    def _write_status_log(self, db: Session, buoy_id: str, new_status: BuoyStatus,
                           previous_status: BuoyStatus, reason: str = None,
                           latitude: float = None, longitude: float = None,
                           battery_level: int = None):
        """写入状态变更日志"""
        try:
            log = BuoyStatusLog(
                buoy_id=buoy_id,
                status=new_status,
                previous_status=previous_status,
                reason=reason,
                latitude=latitude,
                longitude=longitude,
                battery_level=battery_level
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"[MQTT] Error writing status log: {e}")
            db.rollback()

    def _handle_disconnect(self, buoy_id: str, reason: str = None):
        """处理浮标失联"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                return

            previous_status = buoy.status

            # 记录失联前的电量
            buoy.last_battery_level = buoy.battery_level
            # 失联时电量保持不变，只有发送恢复指令时才恢复满电

            buoy.status = BuoyStatus.disconnected
            db.commit()

            # 写入状态日志
            self._write_status_log(
                db, buoy_id, BuoyStatus.disconnected, previous_status,
                reason="manual_disconnect" if reason == "manual" else "disconnected",
                latitude=float(buoy.latitude) if buoy.latitude else None,
                longitude=float(buoy.longitude) if buoy.longitude else None,
                battery_level=buoy.battery_level
            )

            self.publish_status_change(buoy_id, "disconnected")
            print(f"[MQTT] Buoy {buoy_id} disconnected (reason: {reason})")
        except Exception as e:
            print(f"[MQTT] Error handling disconnect: {e}")
            db.rollback()
        finally:
            db.close()

    def _handle_recover(self, buoy_id: str, reason: str = None):
        """处理从失联/低电量/漂移告警恢复"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                return

            previous_status = buoy.status

            # 在simulator中停止漂移场景并恢复电量
            from app.simulator.simulator import simulator_registry
            if buoy_id in simulator_registry:
                simulator = simulator_registry[buoy_id]
                simulator.stop_drift(buoy_id)
                simulator.recharge_battery(buoy_id)

            # 根据原因决定恢复逻辑
            if reason == "low_battery":
                # 只恢复电量
                buoy.battery_level = 100
                if buoy.status == BuoyStatus.low_battery:
                    buoy.status = BuoyStatus.online
            elif reason == "drift":
                # 只恢复漂移告警，位置重置到base
                if buoy.status == BuoyStatus.drift_alert:
                    buoy.latitude = buoy.base_latitude
                    buoy.longitude = buoy.base_longitude
                    buoy.status = BuoyStatus.online
            elif reason == "disconnected":
                # 恢复失联状态：电量满，位置回到base
                buoy.battery_level = 100
                buoy.latitude = buoy.base_latitude
                buoy.longitude = buoy.base_longitude
                buoy.status = BuoyStatus.online
            else:
                # 通用恢复
                buoy.battery_level = 100
                if buoy.status in [BuoyStatus.disconnected, BuoyStatus.drift_alert, BuoyStatus.low_battery, BuoyStatus.no_power]:
                    if buoy.status in [BuoyStatus.drift_alert, BuoyStatus.disconnected]:
                        buoy.latitude = buoy.base_latitude
                        buoy.longitude = buoy.base_longitude
                    buoy.status = BuoyStatus.online

            db.commit()

            # 写入状态日志
            self._write_status_log(
                db, buoy_id, BuoyStatus.online, previous_status, reason="recovered",
                latitude=float(buoy.latitude) if buoy.latitude else None,
                longitude=float(buoy.longitude) if buoy.longitude else None,
                battery_level=buoy.battery_level
            )

            self.publish_status_change(buoy_id, buoy.status.value)
            print(f"[MQTT] Buoy {buoy_id} recovered (reason: {reason}, new status: {buoy.status.value})")
        except Exception as e:
            print(f"[MQTT] Error handling recover: {e}")
            db.rollback()
        finally:
            db.close()

    def _handle_low_battery(self, buoy_id: str, battery_level: int):
        """处理低电量模式"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                return

            previous_status = buoy.status
            buoy.battery_level = battery_level

            if battery_level <= 10:
                buoy.status = BuoyStatus.low_battery
                # 写入状态日志
                self._write_status_log(
                    db, buoy_id, BuoyStatus.low_battery, previous_status, reason="low_battery",
                    latitude=float(buoy.latitude) if buoy.latitude else None,
                    longitude=float(buoy.longitude) if buoy.longitude else None,
                    battery_level=battery_level
                )
            elif battery_level == 0:
                buoy.status = BuoyStatus.no_power
                self._write_status_log(
                    db, buoy_id, BuoyStatus.no_power, previous_status, reason="no_power",
                    latitude=float(buoy.latitude) if buoy.latitude else None,
                    longitude=float(buoy.longitude) if buoy.longitude else None,
                    battery_level=battery_level
                )

            db.commit()
            self.publish_status_change(buoy_id, buoy.status.value)
            print(f"[MQTT] Buoy {buoy_id} low battery: {battery_level}%")
        except Exception as e:
            print(f"[MQTT] Error handling low battery: {e}")
            db.rollback()
        finally:
            db.close()

    def _handle_drift_alert(self, buoy_id: str):
        """处理漂移告警"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                return

            previous_status = buoy.status

            # 在simulator中触发漂移场景
            from app.simulator.simulator import simulator_registry
            if buoy_id in simulator_registry:
                simulator = simulator_registry[buoy_id]
                simulator.start_drift(buoy_id)

            buoy.status = BuoyStatus.drift_alert
            # 若电量低于20%则恢复满电
            if buoy.battery_level < 20:
                buoy.battery_level = 100

            db.commit()

            # 写入状态日志
            self._write_status_log(
                db, buoy_id, BuoyStatus.drift_alert, previous_status, reason="drift_detected",
                latitude=float(buoy.latitude) if buoy.latitude else None,
                longitude=float(buoy.longitude) if buoy.longitude else None,
                battery_level=buoy.battery_level
            )

            self.publish_status_change(buoy_id, "drift_alert")
            print(f"[MQTT] Buoy {buoy_id} entered drift alert")
        except Exception as e:
            print(f"[MQTT] Error handling drift alert: {e}")
            db.rollback()
        finally:
            db.close()

    def _handle_start_drift(self, buoy_id: str):
        """手动模拟漂移 - 浮标偏离正常位置"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                print(f"[MQTT] Buoy {buoy_id} not found for start_drift")
                return

            previous_status = buoy.status

            # 在simulator中触发漂移场景
            from app.simulator.simulator import simulator_registry
            if buoy_id in simulator_registry:
                simulator = simulator_registry[buoy_id]
                simulator.start_drift(buoy_id)
                print(f"[MQTT] Started drift simulation for {buoy_id}")
            else:
                print(f"[MQTT] Buoy {buoy_id} not in simulator registry, cannot start drift")

            # 更新状态为漂移告警
            buoy.status = BuoyStatus.drift_alert
            db.commit()

            # 写入状态日志
            self._write_status_log(
                db, buoy_id, BuoyStatus.drift_alert, previous_status, reason="manual_drift",
                latitude=float(buoy.latitude) if buoy.latitude else None,
                longitude=float(buoy.longitude) if buoy.longitude else None,
                battery_level=buoy.battery_level
            )

            self.publish_status_change(buoy_id, "drift_alert")
            print(f"[MQTT] Buoy {buoy_id} drift alert triggered manually")
        except Exception as e:
            print(f"[MQTT] Error starting drift: {e}")
            db.rollback()
        finally:
            db.close()

    def _handle_stop_drift(self, buoy_id: str):
        """手动停止漂移 - 浮标回到base位置，恢复正常"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if not buoy:
                print(f"[MQTT] Buoy {buoy_id} not found for stop_drift")
                return

            previous_status = buoy.status

            # 在simulator中停止漂移场景并恢复电量
            from app.simulator.simulator import simulator_registry
            if buoy_id in simulator_registry:
                simulator = simulator_registry[buoy_id]
                simulator.stop_drift(buoy_id)
                simulator.recharge_battery(buoy_id)
                print(f"[MQTT] Stopped drift simulation for {buoy_id}")

            # 重置位置到base位置
            buoy.latitude = buoy.base_latitude
            buoy.longitude = buoy.base_longitude
            # 恢复电量
            buoy.battery_level = 100
            # 恢复状态为在线
            buoy.status = BuoyStatus.online
            db.commit()

            # 写入状态日志
            self._write_status_log(
                db, buoy_id, BuoyStatus.online, previous_status, reason="drift_recovered",
                latitude=float(buoy.latitude) if buoy.latitude else None,
                longitude=float(buoy.longitude) if buoy.longitude else None,
                battery_level=buoy.battery_level
            )

            self.publish_status_change(buoy_id, "online")
            print(f"[MQTT] Buoy {buoy_id} recovered from drift alert")
        except Exception as e:
            print(f"[MQTT] Error stopping drift: {e}")
            db.rollback()
        finally:
            db.close()

    def _check_drift(self, db, buoy_id: str, lat: float, lon: float) -> bool:
        """检查是否超出漂移范围，返回True表示触发漂移告警"""
        buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
        if not buoy or not buoy.drift_alert_enabled:
            return False

        # 如果已经是漂移告警状态，不再重复触发
        if buoy.status == BuoyStatus.drift_alert:
            return False

        # 使用 Haversine 公式计算两点之间的距离（公里）
        import math
        R = 6371  # 地球半径（公里）

        lat1 = float(buoy.base_latitude or 0)
        lon1 = float(buoy.base_longitude or 0)
        lat2 = lat
        lon2 = lon

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = math.sin(dlat / 2) ** 2 + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c  # 距离（公里）

        drift_radius = float(buoy.drift_radius or 0.5)  # 默认 0.5 公里
        if distance > drift_radius:
            self._handle_drift_alert(buoy_id)
            return True
        return False

    def _handle_status_change(self, buoy_id: str, data: Dict[str, Any]):
        """Handle buoy status change"""
        db = SessionLocal()
        try:
            buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if buoy:
                new_status = data.get("status")
                if new_status in [s.value for s in BuoyStatus]:
                    buoy.status = BuoyStatus(new_status)
                    db.commit()
                    print(f"[MQTT] Updated buoy {buoy_id} status to {new_status}")
        except Exception as e:
            print(f"[MQTT] Error updating buoy status: {e}")
            db.rollback()
        finally:
            db.close()

    def _get_threshold_config(self, db, buoy_id: str, param_name: str):
        """Get threshold config for a specific buoy+param, fallback to global config"""
        # First try per-buoy config
        config = db.query(AlertConfig).filter(
            AlertConfig.buoy_id == buoy_id,
            AlertConfig.param_name == param_name,
            AlertConfig.enabled == True
        ).first()

        if config:
            return config

        # Fallback to global config
        config = db.query(AlertConfig).filter(
            AlertConfig.buoy_id == None,
            AlertConfig.param_name == param_name,
            AlertConfig.enabled == True
        ).first()

        return config

    def _check_combined_rules(self, db, buoy_id: str, data: Dict[str, Any]):
        """Evaluate combined alert rules for a buoy"""
        from app.services.websocket import sio

        # Get all enabled rules for this buoy or global
        rules = db.query(CombinedAlertRule).filter(
            CombinedAlertRule.enabled == True,
            (CombinedAlertRule.buoy_id == buoy_id) | (CombinedAlertRule.buoy_id == None)
        ).all()

        for rule in rules:
            conditions = rule.conditions
            if not conditions:
                continue

            # Evaluate all conditions with AND logic
            all_conditions_met = True
            first_condition_value = None

            for i, cond in enumerate(conditions):
                param = cond.get("param")
                operator = cond.get("operator")
                threshold = cond.get("value")
                logic = cond.get("logic")  # "AND", "OR", or None (last)

                if param is None or operator is None or threshold is None:
                    continue

                value = data.get(param)
                if value is None:
                    all_conditions_met = False
                    break

                # Evaluate condition
                cond_met = False
                if operator == ">":
                    cond_met = value > threshold
                elif operator == "<":
                    cond_met = value < threshold
                elif operator == ">=":
                    cond_met = value >= threshold
                elif operator == "<=":
                    cond_met = value <= threshold
                elif operator == "==":
                    cond_met = value == threshold
                elif operator == "!=":
                    cond_met = value != threshold

                if i == 0:
                    first_condition_value = value
                    all_conditions_met = cond_met
                elif logic == "AND":
                    all_conditions_met = all_conditions_met and cond_met
                elif logic == "OR":
                    all_conditions_met = all_conditions_met or cond_met
                else:
                    # No logic specified, treat as AND
                    all_conditions_met = all_conditions_met and cond_met

                if not all_conditions_met:
                    break

            if all_conditions_met:
                # Check if there's already an unresolved combined alert for this rule
                existing = db.query(Alert).filter(
                    Alert.buoy_id == buoy_id,
                    Alert.alert_type == "combined_rule",
                    Alert.param_name == rule.name,
                    Alert.status != AlertStatus.resolved
                ).first()

                if not existing:
                    # Trigger combined alert
                    alert = Alert(
                        buoy_id=buoy_id,
                        alert_type="combined_rule",
                        param_name=rule.name,
                        threshold_value=None,
                        actual_value=first_condition_value,
                        severity=rule.severity,
                        status=AlertStatus.triggered
                    )
                    db.add(alert)
                    db.commit()

                    buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
                    alert_info = {
                        "type": "alert_triggered",
                        "alert": {
                            "id": str(alert.id),
                            "buoy_id": str(buoy_id),
                            "buoy_name": buoy.name if buoy else "Unknown",
                            "param_name": rule.name,
                            "actual_value": float(first_condition_value),
                            "threshold_value": None,
                            "direction": None,
                            "severity": rule.severity.value,
                            "status": "triggered",
                            "alert_type": "combined_rule",
                            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else datetime.utcnow().isoformat()
                        }
                    }

                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            loop.create_task(sio.emit("buoy/alert", alert_info))
                        else:
                            asyncio.run(sio.emit("buoy/alert", alert_info))
                    except Exception as ws_err:
                        print(f"[MQTT] Combined rule WebSocket emit error: {ws_err}")

                    print(f"[MQTT] Combined rule triggered: {rule.name} for buoy {buoy_id}")

    def _check_alerts(self, db, buoy_id: str, data: Dict[str, Any]):
        """Check if data triggers any alerts and publish to WebSocket"""
        from app.services.websocket import sio
        try:
            # Check combined rules first
            self._check_combined_rules(db, buoy_id, data)

            # Check individual param thresholds
            for param in ["temperature", "salinity", "ph", "dissolved_oxygen", "turbidity", "chlorophyll", "wave_height"]:
                value = data.get(param)
                if value is None:
                    continue

                config = self._get_threshold_config(db, buoy_id, param)
                if not config:
                    continue

                is_alert = False
                threshold_value = None
                alert_direction = None

                if config.max_threshold and value > config.max_threshold:
                    is_alert = True
                    threshold_value = config.max_threshold
                    alert_direction = "above_max"
                elif config.min_threshold and value < config.min_threshold:
                    is_alert = True
                    threshold_value = config.min_threshold
                    alert_direction = "below_min"

                if is_alert:
                    # Check if there's already an unresolved alert
                    existing = db.query(Alert).filter(
                        Alert.buoy_id == buoy_id,
                        Alert.param_name == param,
                        Alert.status != AlertStatus.resolved
                    ).first()

                    if not existing:
                        alert = Alert(
                            buoy_id=buoy_id,
                            alert_type="threshold_exceeded",
                            param_name=param,
                            threshold_value=threshold_value,
                            actual_value=value,
                            severity=config.severity,
                            status=AlertStatus.triggered
                        )
                        db.add(alert)
                        db.commit()
                        # Reset consecutive normal counter since a new alert was triggered
                        self._consecutive_normal[f"{buoy_id}_{param}"] = 0
                        print(f"[MQTT] Alert triggered: {param} = {value} (threshold: {threshold_value})")

                        # Publish alert to WebSocket for real-time notification
                        buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
                        alert_info = {
                            "type": "alert_triggered",
                            "alert": {
                                "id": str(alert.id),
                                "buoy_id": str(buoy_id),
                                "buoy_name": buoy.name if buoy else "Unknown",
                                "param_name": param,
                                "actual_value": float(value),
                                "threshold_value": float(threshold_value),
                                "direction": alert_direction,
                                "severity": config.severity.value,
                                "status": "triggered",
                                "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else datetime.utcnow().isoformat()
                            }
                        }
                        # Broadcast via Socket.IO
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                loop.create_task(sio.emit("buoy/alert", alert_info))
                            else:
                                asyncio.run(sio.emit("buoy/alert", alert_info))
                        except Exception as ws_err:
                            print(f"[MQTT] WebSocket emit error: {ws_err}")

                # ===== Alert Recovery Detection =====
                # Only check recovery if there's actually an unresolved alert
                else:
                    # Check if value is back to normal (within threshold)
                    is_in_normal_range = True
                    if config.max_threshold and value > config.max_threshold:
                        is_in_normal_range = False
                    if config.min_threshold and value < config.min_threshold:
                        is_in_normal_range = False

                    # Check if there's an unresolved alert for this buoy/param
                    unresolved_alert = db.query(Alert).filter(
                        Alert.buoy_id == buoy_id,
                        Alert.param_name == param,
                        Alert.status != AlertStatus.resolved
                    ).first()

                    counter_key = f"{buoy_id}_{param}"

                    if is_in_normal_range:
                        if unresolved_alert:
                            # Increment consecutive normal counter
                            self._consecutive_normal[counter_key] = self._consecutive_normal.get(counter_key, 0) + 1
                            normal_count = self._consecutive_normal[counter_key]

                            # Only auto-recover after threshold consecutive normal readings
                            if normal_count >= self._recovery_threshold:
                                # Auto-recover the alert
                                old_status = unresolved_alert.status
                                unresolved_alert.status = AlertStatus.resolved
                                unresolved_alert.resolved_at = datetime.utcnow()
                                unresolved_alert.resolved_by = "system"
                                unresolved_alert.remarks = (unresolved_alert.remarks or "") + f"\n[自动恢复] 数据连续{normal_count}次恢复正常: 最终值={value} (阈值: {config.min_threshold}~{config.max_threshold})"
                                db.commit()

                                print(f"[MQTT] Alert auto-recovered after {normal_count} consecutive normal readings: {param}={value}")

                                # Clear the counter after recovery
                                self._consecutive_normal[counter_key] = 0

                                # Publish recovery to WebSocket
                                buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
                                recovery_info = {
                                    "type": "alert_recovered",
                                    "alert": {
                                        "id": str(unresolved_alert.id),
                                        "buoy_id": str(buoy_id),
                                        "buoy_name": buoy.name if buoy else "Unknown",
                                        "param_name": param,
                                        "old_value": float(unresolved_alert.actual_value),
                                        "current_value": float(value),
                                        "threshold_value": float(threshold_value) if threshold_value else None,
                                        "previous_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
                                        "resolved_at": unresolved_alert.resolved_at.isoformat()
                                    }
                                }
                                import asyncio
                                try:
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        loop.create_task(sio.emit("buoy/alert", recovery_info))
                                    else:
                                        asyncio.run(sio.emit("buoy/alert", recovery_info))
                                except Exception as ws_err:
                                    print(f"[MQTT] Recovery WebSocket emit error: {ws_err}")
                    else:
                        # Value is out of range - reset consecutive normal counter
                        if counter_key in self._consecutive_normal:
                            self._consecutive_normal[counter_key] = 0

        except Exception as e:
            print(f"[MQTT] Error checking alerts: {e}")


# Global MQTT service instance
_mqtt_service: Optional[MQTTService] = None


def get_mqtt_service() -> Optional[MQTTService]:
    return _mqtt_service


def init_mqtt_service(broker_host: str = "emqx", broker_port: int = 1883,
                      username: str = "admin", password: str = "asdfghjkl66") -> MQTTService:
    global _mqtt_service
    _mqtt_service = MQTTService(broker_host, broker_port, username, password)
    return _mqtt_service
