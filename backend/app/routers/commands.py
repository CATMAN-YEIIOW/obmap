from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, Literal
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Buoy
from app.services.mqtt import get_mqtt_service

router = APIRouter(prefix="/api/v1/commands", tags=["指令控制"])


class SetIntervalCommand(BaseModel):
    buoy_id: str
    interval: int


class RebootCommand(BaseModel):
    buoy_id: str


class CalibrateCommand(BaseModel):
    buoy_id: str
    sensor: str


class StatusCommand(BaseModel):
    buoy_id: str
    status: Literal["online", "offline", "warning", "disconnected", "low_battery", "drift_alert"]


class ScenarioCommand(BaseModel):
    scenario: Literal["normal", "temperature_spike", "temperature_drop", "salinity_anomaly", "ph_drops", "storm", "sensor_fault"]
    duration: int = 60  # seconds


class BuoyScenarioCommand(BaseModel):
    buoy_id: str
    scenario: Literal["normal", "temperature_spike", "temperature_drop", "salinity_anomaly", "ph_drops", "storm", "sensor_fault"]
    duration: int = 60


class FaultCommand(BaseModel):
    buoy_id: str
    fault_type: Literal["offline", "temperature_spike", "salinity_drop", "ph_spike"]
    duration: int = 0  # 0 means until manually cleared


class OfflineCommand(BaseModel):
    buoy_id: str
    duration: int = 60  # seconds


@router.post("/set_interval")
def set_sampling_interval(command: SetIntervalCommand, db: Session = Depends(get_db)):
    """设置浮标采样间隔"""
    mqtt_service = get_mqtt_service()
    if not mqtt_service or not mqtt_service.is_connected():
        raise HTTPException(status_code=503, detail="MQTT服务未连接")

    buoy = db.query(Buoy).filter(Buoy.id == command.buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    mqtt_service.publish_command(command.buoy_id, {
        "type": "set_interval",
        "params": {"interval": command.interval}
    })

    return {"code": 200, "message": "采样间隔设置指令已发送", "data": {"buoy_id": command.buoy_id, "interval": command.interval}}


@router.post("/reboot")
def reboot_buoy(command: RebootCommand, db: Session = Depends(get_db)):
    """重启浮标"""
    mqtt_service = get_mqtt_service()
    if not mqtt_service or not mqtt_service.is_connected():
        raise HTTPException(status_code=503, detail="MQTT服务未连接")

    buoy = db.query(Buoy).filter(Buoy.id == command.buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    mqtt_service.publish_command(command.buoy_id, {"type": "reboot", "params": {}})

    return {"code": 200, "message": "重启指令已发送", "data": {"buoy_id": command.buoy_id}}


@router.post("/calibrate")
def calibrate_sensor(command: CalibrateCommand, db: Session = Depends(get_db)):
    """校准传感器"""
    mqtt_service = get_mqtt_service()
    if not mqtt_service or not mqtt_service.is_connected():
        raise HTTPException(status_code=503, detail="MQTT服务未连接")

    buoy = db.query(Buoy).filter(Buoy.id == command.buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    mqtt_service.publish_command(command.buoy_id, {
        "type": "calibrate",
        "params": {"sensor": command.sensor}
    })

    return {"code": 200, "message": "校准指令已发送", "data": {"buoy_id": command.buoy_id, "sensor": command.sensor}}


@router.post("/status")
def change_buoy_status(command: StatusCommand, db: Session = Depends(get_db)):
    """修改浮标状态"""
    mqtt_service = get_mqtt_service()
    if not mqtt_service or not mqtt_service.is_connected():
        raise HTTPException(status_code=503, detail="MQTT服务未连接")

    buoy = db.query(Buoy).filter(Buoy.id == command.buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    mqtt_service.publish_status_change(command.buoy_id, command.status)

    return {"code": 200, "message": "状态变更指令已发送", "data": {"buoy_id": command.buoy_id, "status": command.status}}


@router.post("/simulator/scenario")
def set_global_scenario(command: ScenarioCommand, request: Request):
    """设置全局模拟场景（影响所有浮标）"""
    simulator = getattr(request.app.state, "simulator", None)
    if not simulator:
        raise HTTPException(status_code=503, detail="模拟器未运行")

    simulator.set_global_scenario(command.scenario, command.duration)

    scenario_descriptions = {
        "normal": "正常模式",
        "temperature_spike": "温度骤升（模拟热浪）",
        "temperature_drop": "温度骤降（模拟寒流）",
        "salinity_anomaly": "盐度异常（淡水入侵）",
        "ph_drops": "pH下降（海洋酸化）",
        "storm": "风暴条件（波高、浊度剧增）",
        "sensor_fault": "传感器故障（异常读数）"
    }

    return {
        "code": 200,
        "message": f"全局场景设置为: {scenario_descriptions.get(command.scenario, command.scenario)}，持续 {command.duration} 秒",
        "data": {"scenario": command.scenario, "duration": command.duration}
    }


@router.post("/simulator/buoy_scenario")
def set_buoy_scenario(command: BuoyScenarioCommand, request: Request):
    """设置指定浮标的模拟场景"""
    simulator = getattr(request.app.state, "simulator", None)
    if not simulator:
        raise HTTPException(status_code=503, detail="模拟器未运行")

    buoy_found = False
    for buoy_id in simulator.buoys:
        if buoy_id == command.buoy_id:
            buoy_found = True
            break

    if not buoy_found:
        raise HTTPException(status_code=404, detail="浮标不在模拟器中")

    simulator.set_buoy_scenario(command.buoy_id, command.scenario, command.duration)

    scenario_descriptions = {
        "normal": "正常模式",
        "temperature_spike": "温度骤升",
        "temperature_drop": "温度骤降",
        "salinity_anomaly": "盐度异常",
        "ph_drops": "pH下降",
        "storm": "风暴条件",
        "sensor_fault": "传感器故障"
    }

    return {
        "code": 200,
        "message": f"浮标 {command.buoy_id} 场景设置为: {scenario_descriptions.get(command.scenario, command.scenario)}",
        "data": {"buoy_id": command.buoy_id, "scenario": command.scenario, "duration": command.duration}
    }


@router.post("/simulator/inject_fault")
def inject_fault(command: FaultCommand, request: Request, db: Session = Depends(get_db)):
    """向指定浮标注入故障"""
    simulator = getattr(request.app.state, "simulator", None)
    if not simulator:
        raise HTTPException(status_code=503, detail="模拟器未运行")

    buoy = db.query(Buoy).filter(Buoy.id == command.buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    simulator.inject_fault(command.buoy_id, command.fault_type, command.duration)

    return {
        "code": 200,
        "message": f"故障已注入到浮标 {buoy.name}",
        "data": {"buoy_id": command.buoy_id, "fault_type": command.fault_type, "duration": command.duration if command.duration > 0 else "manual"}
    }


@router.post("/simulator/buoy_offline")
def set_buoy_offline(command: OfflineCommand, request: Request, db: Session = Depends(get_db)):
    """模拟浮标离线"""
    simulator = getattr(request.app.state, "simulator", None)
    if not simulator:
        raise HTTPException(status_code=503, detail="模拟器未运行")

    buoy = db.query(Buoy).filter(Buoy.id == command.buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    # Set offline in simulator (buoys now stores buoy_id strings, not objects)
    simulator.set_buoy_offline(command.buoy_id, command.duration)

    # Update database
    buoy.status = "offline"
    db.commit()

    # Immediately publish status change to MQTT for real-time frontend update
    mqtt_service = get_mqtt_service()
    if mqtt_service and mqtt_service.is_connected():
        mqtt_service.publish_status_change(command.buoy_id, "offline")

    return {
        "code": 200,
        "message": f"浮标 {buoy.name} 已设置为离线，持续 {command.duration} 秒",
        "data": {"buoy_id": command.buoy_id, "duration": command.duration}
    }


class OnlineCommand(BaseModel):
    buoy_id: str


@router.post("/simulator/buoy_online")
def set_buoy_online(command: OnlineCommand, request: Request, db: Session = Depends(get_db)):
    """模拟浮标上线"""
    simulator = getattr(request.app.state, "simulator", None)
    if not simulator:
        raise HTTPException(status_code=503, detail="模拟器未运行")

    buoy = db.query(Buoy).filter(Buoy.id == command.buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    # Bring online in simulator (buoys now stores buoy_id strings, not objects)
    simulator.set_buoy_online(command.buoy_id)

    # Update database
    buoy.status = "online"
    db.commit()

    # Immediately publish status change to MQTT for real-time frontend update
    mqtt_service = get_mqtt_service()
    if mqtt_service and mqtt_service.is_connected():
        mqtt_service.publish_status_change(command.buoy_id, "online")

    return {
        "code": 200,
        "message": f"浮标 {buoy.name} 已上线",
        "data": {"buoy_id": command.buoy_id}
    }


class ActivateCommand(BaseModel):
    buoy_id: str


@router.post("/simulator/buoy_activate")
def activate_buoy(command: ActivateCommand, request: Request, db: Session = Depends(get_db)):
    """激活浮标 - 让模拟器开始为该浮标生成数据"""
    simulator = getattr(request.app.state, "simulator", None)
    if not simulator:
        raise HTTPException(status_code=503, detail="模拟器未运行")

    buoy = db.query(Buoy).filter(Buoy.id == command.buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    # Check if already active (in simulator's buoy list)
    is_already_active = command.buoy_id in simulator.buoys
    if is_already_active:
        raise HTTPException(status_code=400, detail="浮标已经是激活状态")

    # Activate the buoy in simulator
    simulator.activate_buoy(command.buoy_id, db)

    # Update database status
    buoy.status = "online"
    db.commit()

    return {
        "code": 200,
        "message": f"浮标 {buoy.name} 已激活，开始生成数据",
        "data": {"buoy_id": command.buoy_id}
    }


@router.get("/simulator/status")
def get_simulator_status(request: Request):
    """获取模拟器状态"""
    simulator = getattr(request.app.state, "simulator", None)
    if not simulator:
        raise HTTPException(status_code=503, detail="模拟器未运行")

    return {
        "code": 200,
        "message": "success",
        "data": simulator.get_status()
    }
