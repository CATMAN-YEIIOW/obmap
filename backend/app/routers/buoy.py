from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
import uuid
import secrets
from app.database import get_db
from app.models import Buoy, BuoyStatus

router = APIRouter(prefix="/api/v1/buoys", tags=["浮标设备管理"])


class BuoyBase(BaseModel):
    name: str
    code: str
    latitude: float
    longitude: float
    depth: Optional[float] = 0
    sea_area: Optional[str] = None


class BuoyCreate(BuoyBase):
    pass


class BuoyUpdate(BaseModel):
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    depth: Optional[float] = None
    sea_area: Optional[str] = None


class BuoyResponse(BuoyBase):
    id: str
    status: str
    mqtt_client_id: Optional[str] = None  # MQTT通信ID
    activation_key: Optional[str] = None  # 激活密钥
    battery_level: Optional[int] = None  # 电量
    drift_radius: Optional[float] = None  # 漂移半径
    drift_alert_enabled: Optional[bool] = None  # 漂移检测是否开启
    base_latitude: Optional[float] = None  # 基础位置纬度
    base_longitude: Optional[float] = None  # 基础位置经度
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, buoy):
        return cls(
            id=str(buoy.id),
            name=buoy.name,
            code=buoy.code,
            latitude=float(buoy.latitude),
            longitude=float(buoy.longitude),
            depth=float(buoy.depth) if buoy.depth else 0,
            status=buoy.status.value if hasattr(buoy.status, 'value') else buoy.status,
            sea_area=buoy.sea_area,
            mqtt_client_id=str(buoy.mqtt_client_id) if buoy.mqtt_client_id else None,
            activation_key=buoy.activation_key,
            battery_level=buoy.battery_level,
            drift_radius=float(buoy.drift_radius) if buoy.drift_radius else None,
            drift_alert_enabled=buoy.drift_alert_enabled,
            base_latitude=float(buoy.base_latitude) if buoy.base_latitude else None,
            base_longitude=float(buoy.base_longitude) if buoy.base_longitude else None,
            created_at=buoy.created_at,
            updated_at=buoy.updated_at
        )

    class Config:
        from_attributes = True


class BuoyDetailResponse(BuoyResponse):
    latest_data: Optional[dict] = None


class PaginatedResponse(BaseModel):
    items: List[BuoyResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=PaginatedResponse)
def get_buoys(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    sea_area: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Buoy)

    if status:
        try:
            status_enum = BuoyStatus(status)
            query = query.filter(Buoy.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")

    if sea_area:
        query = query.filter(Buoy.sea_area == sea_area)

    total = query.count()
    items = query.order_by(desc(Buoy.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        items=[BuoyResponse.from_orm(item) for item in items],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{buoy_id}", response_model=BuoyDetailResponse)
def get_buoy(buoy_id: str, db: Session = Depends(get_db)):
    buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    # Get latest data
    from app.models import BuoyData
    latest = db.query(BuoyData).filter(BuoyData.buoy_id == buoy_id).order_by(desc(BuoyData.time)).first()

    latest_data_dict = None
    if latest or buoy:
        latest_data_dict = {
            # 传感器数据
            "temperature": float(latest.temperature) if latest and latest.temperature else None,
            "salinity": float(latest.salinity) if latest and latest.salinity else None,
            "pH": float(latest.ph) if latest and latest.ph else None,
            "dissolved_oxygen": float(latest.dissolved_oxygen) if latest and latest.dissolved_oxygen else None,
            "turbidity": float(latest.turbidity) if latest and latest.turbidity else None,
            "chlorophyll": float(latest.chlorophyll) if latest and latest.chlorophyll else None,
            "wave_height": float(latest.wave_height) if latest and latest.wave_height else None,
            # 位置和状态（优先使用buoy_data表中的， fallback到buoys表）
            "latitude": float(latest.latitude) if latest and latest.latitude else float(buoy.latitude),
            "longitude": float(latest.longitude) if latest and latest.longitude else float(buoy.longitude),
            "battery_level": latest.battery_level if latest and latest.battery_level else buoy.battery_level,
            "status": buoy.status.value,
            "timestamp": latest.time.isoformat() if latest else None
        }

    response = BuoyDetailResponse(
        id=str(buoy.id),
        name=buoy.name,
        code=buoy.code,
        latitude=float(buoy.latitude),
        longitude=float(buoy.longitude),
        depth=float(buoy.depth) if buoy.depth else 0,
        status=buoy.status.value,
        sea_area=buoy.sea_area,
        created_at=buoy.created_at,
        updated_at=buoy.updated_at,
        latest_data=latest_data_dict
    )
    return response


@router.post("", status_code=201)
def create_buoy(buoy: BuoyCreate, db: Session = Depends(get_db)):
    # Check if code exists
    existing = db.query(Buoy).filter(Buoy.code == buoy.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="浮标编码已存在")

    # Generate unique MQTT client ID and activation key
    mqtt_client_id = uuid.uuid4()
    activation_key = secrets.token_hex(16)

    db_buoy = Buoy(
        name=buoy.name,
        code=buoy.code,
        latitude=buoy.latitude,
        longitude=buoy.longitude,
        depth=buoy.depth or 0,
        sea_area=buoy.sea_area,
        status=BuoyStatus.inactive,
        mqtt_client_id=mqtt_client_id,
        activation_key=activation_key,
        battery_level=100,
        base_latitude=buoy.latitude,
        base_longitude=buoy.longitude
    )
    db.add(db_buoy)
    db.commit()
    db.refresh(db_buoy)

    return {
        "code": 201,
        "message": "浮标创建成功，请通过MQTT客户端发送激活指令",
        "data": {
            "id": str(db_buoy.id),
            "name": db_buoy.name,
            "code": db_buoy.code,
            "mqtt_client_id": str(mqtt_client_id),
            "activation_key": activation_key,
            "activate_topic": f"buoy/command/{db_buoy.id}",
            "activate_payload": {
                "type": "activate",
                "params": {
                    "activation_key": activation_key
                }
            }
        }
    }


@router.put("/{buoy_id}")
def update_buoy(buoy_id: str, buoy_update: BuoyUpdate, db: Session = Depends(get_db)):
    db_buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
    if not db_buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    update_data = buoy_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_buoy, key, value)

    db.commit()
    return {"code": 200, "message": "浮标更新成功", "data": None}


@router.delete("/{buoy_id}")
def delete_buoy(buoy_id: str, db: Session = Depends(get_db)):
    db_buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
    if not db_buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    # 从simulator registry中移除
    from app.simulator.simulator import simulator_registry, DataSimulator
    if buoy_id in simulator_registry:
        simulator = simulator_registry[buoy_id]
        # 从simulator的buoys列表中移除（buoys现在是str列表）
        if buoy_id in simulator.buoys:
            simulator.buoys.remove(buoy_id)
        # 删除current_values
        if buoy_id in simulator.current_values:
            del simulator.current_values[buoy_id]
        # 从registry中删除
        del simulator_registry[buoy_id]
        print(f"[Buoy] Removed buoy {buoy_id} from simulator registry")

    db.delete(db_buoy)
    db.commit()
    return {"code": 200, "message": "浮标删除成功", "data": None}