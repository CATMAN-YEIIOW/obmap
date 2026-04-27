from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.models import Buoy, BuoyData

router = APIRouter(prefix="/api/v1/data", tags=["监测数据查询"])


class BuoyDataResponse(BaseModel):
    time: datetime
    temperature: Optional[float] = None
    salinity: Optional[float] = None
    ph: Optional[float] = None
    dissolved_oxygen: Optional[float] = None
    turbidity: Optional[float] = None
    chlorophyll: Optional[float] = None
    wave_height: Optional[float] = None


class RealtimeBuoyData(BaseModel):
    buoy_id: str
    buoy_name: str
    data: dict


class RealtimeResponse(BaseModel):
    timestamp: datetime
    buoys: List[RealtimeBuoyData]


class PaginatedDataResponse(BaseModel):
    items: List[BuoyDataResponse]
    total: int
    page: int
    page_size: int


@router.get("/realtime")
def get_realtime_data(
    buoy_ids: Optional[str] = Query(None, description="逗号分隔的浮标ID列表，空表示全部"),
    db: Session = Depends(get_db)
):
    # Get all buoys or filter by IDs
    if buoy_ids:
        id_list = [id.strip() for id in buoy_ids.split(",")]
        buoys = db.query(Buoy).filter(Buoy.id.in_(id_list)).all()
    else:
        buoys = db.query(Buoy).all()

    result = []
    for buoy in buoys:
        latest = db.query(BuoyData).filter(
            BuoyData.buoy_id == buoy.id
        ).order_by(desc(BuoyData.time)).first()

        if latest:
            result.append(RealtimeBuoyData(
                buoy_id=str(buoy.id),
                buoy_name=buoy.name,
                data={
                    "temperature": float(latest.temperature) if latest.temperature else None,
                    "salinity": float(latest.salinity) if latest.salinity else None,
                    "pH": float(latest.ph) if latest.ph else None,
                    "dissolved_oxygen": float(latest.dissolved_oxygen) if latest.dissolved_oxygen else None,
                    "turbidity": float(latest.turbidity) if latest.turbidity else None,
                    "chlorophyll": float(latest.chlorophyll) if latest.chlorophyll else None,
                    "wave_height": float(latest.wave_height) if latest.wave_height else None
                }
            ))

    return {
        "code": 200,
        "message": "success",
        "data": {
            "timestamp": datetime.utcnow(),
            "buoys": [r.model_dump() for r in result]
        }
    }


@router.get("/history")
def get_history_data(
    buoy_id: str = Query(..., description="浮标ID"),
    start_time: datetime = Query(..., description="开始时间"),
    end_time: datetime = Query(..., description="结束时间"),
    param: Optional[str] = Query(None, description="筛选参数名"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    # Validate buoy exists
    buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    query = db.query(BuoyData).filter(
        and_(
            BuoyData.buoy_id == buoy_id,
            BuoyData.time >= start_time,
            BuoyData.time <= end_time
        )
    )

    total = query.count()
    items = query.order_by(desc(BuoyData.time)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [
                BuoyDataResponse(
                    time=item.time,
                    temperature=float(item.temperature) if item.temperature else None,
                    salinity=float(item.salinity) if item.salinity else None,
                    ph=float(item.ph) if item.ph else None,
                    dissolved_oxygen=float(item.dissolved_oxygen) if item.dissolved_oxygen else None,
                    turbidity=float(item.turbidity) if item.turbidity else None,
                    chlorophyll=float(item.chlorophyll) if item.chlorophyll else None,
                    wave_height=float(item.wave_height) if item.wave_height else None
                ).model_dump() for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size
        }
    }


@router.get("/latest/{buoy_id}")
def get_latest_data(buoy_id: str, db: Session = Depends(get_db)):
    buoy = db.query(Buoy).filter(Buoy.id == buoy_id).first()
    if not buoy:
        raise HTTPException(status_code=404, detail="浮标不存在")

    latest = db.query(BuoyData).filter(
        BuoyData.buoy_id == buoy_id
    ).order_by(desc(BuoyData.time)).first()

    if not latest:
        raise HTTPException(status_code=404, detail="暂无数据")

    return {
        "code": 200,
        "message": "success",
        "data": {
            "buoy_id": str(buoy_id),
            "time": latest.time,
            "temperature": float(latest.temperature) if latest.temperature else None,
            "salinity": float(latest.salinity) if latest.salinity else None,
            "ph": float(latest.ph) if latest.ph else None,
            "dissolved_oxygen": float(latest.dissolved_oxygen) if latest.dissolved_oxygen else None,
            "turbidity": float(latest.turbidity) if latest.turbidity else None,
            "chlorophyll": float(latest.chlorophyll) if latest.chlorophyll else None,
            "wave_height": float(latest.wave_height) if latest.wave_height else None
        }
    }