from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel
from app.database import get_db
from app.models import Alert, AlertConfig, CombinedAlertRule, Buoy, AlertStatus, AlertSeverity, User
from app.routers.auth import get_current_user, require_role

router = APIRouter(prefix="/api/v1/alerts", tags=["告警管理"])


# ============ Pydantic Schemas ============

class AlertResponse(BaseModel):
    id: str
    buoy_id: str
    buoy_name: Optional[str] = None
    alert_type: str
    param_name: str
    threshold_value: Optional[float] = None
    actual_value: float
    severity: str
    status: str
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    remarks: Optional[str] = None


class AlertStatistics(BaseModel):
    total: int
    by_severity: dict
    by_status: dict
    recent_24h: int
    recovered_24h: int


class AlertConfigResponse(BaseModel):
    id: str
    buoy_id: Optional[str] = None
    buoy_name: Optional[str] = None
    param_name: str
    min_threshold: Optional[float] = None
    max_threshold: Optional[float] = None
    severity: str
    enabled: bool
    is_global: bool = False

    model_config = {"from_attributes": True}


class AlertConfigCreate(BaseModel):
    buoy_id: Optional[str] = None
    param_name: str
    min_threshold: Optional[float] = None
    max_threshold: Optional[float] = None
    severity: str = "warning"
    enabled: bool = True


class AlertConfigUpdate(BaseModel):
    min_threshold: Optional[float] = None
    max_threshold: Optional[float] = None
    severity: Optional[str] = None
    enabled: Optional[bool] = None


class CombinedRuleCondition(BaseModel):
    param: str
    operator: str  # ">", "<", ">=", "<=", "==", "!="
    value: float
    logic: Optional[str] = None  # "AND", "OR", null for last condition


class CombinedRuleResponse(BaseModel):
    id: str
    name: str
    buoy_id: Optional[str] = None
    buoy_name: Optional[str] = None
    conditions: list
    severity: str
    enabled: bool
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CombinedRuleCreate(BaseModel):
    name: str
    buoy_id: Optional[str] = None
    conditions: list
    severity: str = "warning"
    enabled: bool = True


class CombinedRuleUpdate(BaseModel):
    name: Optional[str] = None
    buoy_id: Optional[str] = None
    conditions: Optional[list] = None
    severity: Optional[str] = None
    enabled: Optional[bool] = None


class AcknowledgeRequest(BaseModel):
    remarks: Optional[str] = None


class ResolveRequest(BaseModel):
    remarks: Optional[str] = None


# ============ Alert List & Statistics ============

@router.get("")
def get_alerts(
    buoy_id: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(Alert)

    if buoy_id:
        query = query.filter(Alert.buoy_id == buoy_id)

    if status:
        try:
            status_enum = AlertStatus(status)
            query = query.filter(Alert.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")

    if severity:
        try:
            severity_enum = AlertSeverity(severity)
            query = query.filter(Alert.severity == severity_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的严重程度: {severity}")

    if start_time:
        query = query.filter(Alert.triggered_at >= start_time)
    if end_time:
        query = query.filter(Alert.triggered_at <= end_time)

    total = query.count()
    items = query.order_by(desc(Alert.triggered_at)).offset((page - 1) * page_size).limit(page_size).all()

    # N+1 query optimization - batch fetch buoys
    buoy_ids = list(set(item.buoy_id for item in items))
    buoys = db.query(Buoy).filter(Buoy.id.in_(buoy_ids)).all() if buoy_ids else []
    buoy_map = {str(b.id): b.name for b in buoys}

    result = []
    for alert in items:
        result.append(AlertResponse(
            id=str(alert.id),
            buoy_id=str(alert.buoy_id),
            buoy_name=buoy_map.get(str(alert.buoy_id)),
            alert_type=alert.alert_type,
            param_name=alert.param_name,
            threshold_value=float(alert.threshold_value) if alert.threshold_value else None,
            actual_value=float(alert.actual_value),
            severity=alert.severity.value,
            status=alert.status.value,
            triggered_at=alert.triggered_at,
            acknowledged_at=alert.acknowledged_at,
            acknowledged_by=alert.acknowledged_by,
            resolved_at=alert.resolved_at,
            resolved_by=alert.resolved_by,
            remarks=alert.remarks
        ))

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [r.model_dump() for r in result],
            "total": total,
            "page": page,
            "page_size": page_size
        }
    }


@router.get("/statistics")
def get_alert_statistics(db: Session = Depends(get_db)):
    total = db.query(Alert).count()

    by_severity = {}
    for sev in AlertSeverity:
        count = db.query(Alert).filter(Alert.severity == sev).count()
        by_severity[sev.value] = count

    by_status = {}
    for st in AlertStatus:
        count = db.query(Alert).filter(Alert.status == st).count()
        by_status[st.value] = count

    recent_24h = db.query(Alert).filter(
        Alert.triggered_at >= datetime.utcnow() - timedelta(hours=24)
    ).count()

    recovered_24h = db.query(Alert).filter(
        Alert.resolved_at >= datetime.utcnow() - timedelta(hours=24),
        Alert.status == AlertStatus.resolved
    ).count()

    return {
        "code": 200,
        "message": "success",
        "data": AlertStatistics(
            total=total,
            by_severity=by_severity,
            by_status=by_status,
            recent_24h=recent_24h,
            recovered_24h=recovered_24h
        ).model_dump()
    }


# ============ Acknowledge & Resolve ============

@router.put("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    body: Optional[AcknowledgeRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """确认告警 - 记录操作人员"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")

    alert.status = AlertStatus.acknowledged
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = current_user.username
    if body and body.remarks:
        alert.remarks = (alert.remarks or "") + f"\n[确认备注] {body.remarks}"

    db.commit()

    return {"code": 200, "message": "告警已确认", "data": {"id": alert_id, "status": alert.status.value, "acknowledged_by": alert.acknowledged_by}}


@router.put("/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    body: Optional[ResolveRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """解决告警 - 记录操作人员"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")

    alert.status = AlertStatus.resolved
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = current_user.username
    if body and body.remarks:
        alert.remarks = (alert.remarks or "") + f"\n[解决备注] {body.remarks}"

    db.commit()

    return {"code": 200, "message": "告警已解决", "data": {"id": alert_id, "status": alert.status.value, "resolved_by": alert.resolved_by}}


# ============ Alert Config (Per-buoy Threshold) ============

@router.get("/config")
def get_alert_configs(
    buoy_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取告警阈值配置，支持过滤浮标"""
    query = db.query(AlertConfig)
    if buoy_id:
        query = query.filter(AlertConfig.buoy_id == buoy_id)
    # buoy_id 为 None 时返回全部配置（全局 + 所有浮标专属）

    configs = query.all()

    # Batch fetch buoys for names
    buoy_ids = list(set(c.buoy_id for c in configs if c.buoy_id))
    buoys = db.query(Buoy).filter(Buoy.id.in_(buoy_ids)).all() if buoy_ids else []
    buoy_map = {str(b.id): b.name for b in buoys}

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [
                AlertConfigResponse(
                    id=str(c.id),
                    buoy_id=str(c.buoy_id) if c.buoy_id else None,
                    buoy_name=buoy_map.get(str(c.buoy_id)),
                    param_name=c.param_name,
                    min_threshold=float(c.min_threshold) if c.min_threshold else None,
                    max_threshold=float(c.max_threshold) if c.max_threshold else None,
                    severity=c.severity.value,
                    enabled=c.enabled,
                    is_global=c.buoy_id is None
                ).model_dump() for c in configs
            ]
        }
    }


@router.get("/config/{target_buoy_id}/{param_name}")
def get_buoy_param_config(
    target_buoy_id: str,
    param_name: str,
    db: Session = Depends(get_db)
):
    """获取指定浮标+参数的配置，优先返回浮标专属配置，否则返回全局配置"""
    # 先查浮标专属配置
    config = db.query(AlertConfig).filter(
        AlertConfig.buoy_id == target_buoy_id,
        AlertConfig.param_name == param_name
    ).first()

    is_global = False
    if not config:
        # 查全局配置
        config = db.query(AlertConfig).filter(
            AlertConfig.buoy_id == None,
            AlertConfig.param_name == param_name
        ).first()
        is_global = True

    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    buoy = db.query(Buoy).filter(Buoy.id == target_buoy_id).first()

    return {
        "code": 200,
        "message": "success",
        "data": AlertConfigResponse(
            id=str(config.id),
            buoy_id=target_buoy_id if not is_global else None,
            buoy_name=buoy.name if buoy else None,
            param_name=config.param_name,
            min_threshold=float(config.min_threshold) if config.min_threshold else None,
            max_threshold=float(config.max_threshold) if config.max_threshold else None,
            severity=config.severity.value,
            enabled=config.enabled,
            is_global=is_global
        ).model_dump()
    }


@router.post("/config")
def create_alert_config(
    config: AlertConfigCreate,
    current_user: User = Depends(require_role("researcher", "admin")),
    db: Session = Depends(get_db)
):
    """创建告警阈值配置（全局或浮标专属）"""
    # 校验浮标存在
    if config.buoy_id:
        buoy = db.query(Buoy).filter(Buoy.id == config.buoy_id).first()
        if not buoy:
            raise HTTPException(status_code=404, detail="浮标不存在")

    # 检查是否已存在
    existing = db.query(AlertConfig).filter(
        AlertConfig.buoy_id == (config.buoy_id if config.buoy_id else None),
        AlertConfig.param_name == config.param_name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该配置已存在，请使用更新接口")

    db_config = AlertConfig(
        buoy_id=config.buoy_id if config.buoy_id else None,
        param_name=config.param_name,
        min_threshold=config.min_threshold,
        max_threshold=config.max_threshold,
        severity=AlertSeverity(config.severity),
        enabled=config.enabled
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    buoy = db.query(Buoy).filter(Buoy.id == config.buoy_id).first() if config.buoy_id else None

    return {
        "code": 201,
        "message": "配置创建成功",
        "data": AlertConfigResponse(
            id=str(db_config.id),
            buoy_id=config.buoy_id if config.buoy_id else None,
            buoy_name=buoy.name if buoy else None,
            param_name=db_config.param_name,
            min_threshold=float(db_config.min_threshold) if db_config.min_threshold else None,
            max_threshold=float(db_config.max_threshold) if db_config.max_threshold else None,
            severity=db_config.severity.value,
            enabled=db_config.enabled,
            is_global=db_config.buoy_id is None
        ).model_dump()
    }


@router.put("/config/{config_id}")
def update_alert_config(
    config_id: str,
    update: AlertConfigUpdate,
    current_user: User = Depends(require_role("researcher", "admin")),
    db: Session = Depends(get_db)
):
    """更新告警阈值配置"""
    config = db.query(AlertConfig).filter(AlertConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    if update.min_threshold is not None:
        config.min_threshold = update.min_threshold
    if update.max_threshold is not None:
        config.max_threshold = update.max_threshold
    if update.severity:
        config.severity = AlertSeverity(update.severity)
    if update.enabled is not None:
        config.enabled = update.enabled

    config.updated_at = datetime.utcnow()
    db.commit()

    buoy = db.query(Buoy).filter(Buoy.id == config.buoy_id).first() if config.buoy_id else None

    return {
        "code": 200,
        "message": "配置更新成功",
        "data": AlertConfigResponse(
            id=str(config.id),
            buoy_id=str(config.buoy_id) if config.buoy_id else None,
            buoy_name=buoy.name if buoy else None,
            param_name=config.param_name,
            min_threshold=float(config.min_threshold) if config.min_threshold else None,
            max_threshold=float(config.max_threshold) if config.max_threshold else None,
            severity=config.severity.value,
            enabled=config.enabled,
            is_global=config.buoy_id is None
        ).model_dump()
    }


@router.delete("/config/{config_id}")
def delete_alert_config(
    config_id: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """删除告警阈值配置（仅admin，且仅限浮标专属配置）"""
    config = db.query(AlertConfig).filter(AlertConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    db.delete(config)
    db.commit()

    return {"code": 200, "message": "配置删除成功", "data": None}


# ============ Combined Alert Rules ============

@router.get("/rules")
def get_combined_rules(
    buoy_id: Optional[str] = None,
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """获取组合告警规则"""
    query = db.query(CombinedAlertRule)

    if buoy_id:
        query = query.filter(CombinedAlertRule.buoy_id == buoy_id)
    if enabled is not None:
        query = query.filter(CombinedAlertRule.enabled == enabled)

    rules = query.order_by(desc(CombinedAlertRule.created_at)).all()

    # Batch fetch buoys
    rule_buoy_ids = list(set(r.buoy_id for r in rules if r.buoy_id))
    buoys = db.query(Buoy).filter(Buoy.id.in_(rule_buoy_ids)).all() if rule_buoy_ids else []
    buoy_map = {str(b.id): b.name for b in buoys}

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [
                CombinedRuleResponse(
                    id=str(r.id),
                    name=r.name,
                    buoy_id=str(r.buoy_id) if r.buoy_id else None,
                    buoy_name=buoy_map.get(str(r.buoy_id)),
                    conditions=r.conditions,
                    severity=r.severity.value,
                    enabled=r.enabled,
                    created_by=r.created_by,
                    created_at=r.created_at,
                    updated_at=r.updated_at
                ).model_dump() for r in rules
            ]
        }
    }


@router.post("/rules")
def create_combined_rule(
    rule: CombinedRuleCreate,
    current_user: User = Depends(require_role("researcher", "admin")),
    db: Session = Depends(get_db)
):
    """创建组合告警规则"""
    # 校验浮标存在
    if rule.buoy_id:
        buoy = db.query(Buoy).filter(Buoy.id == rule.buoy_id).first()
        if not buoy:
            raise HTTPException(status_code=404, detail="浮标不存在")

    db_rule = CombinedAlertRule(
        name=rule.name,
        buoy_id=rule.buoy_id if rule.buoy_id else None,
        conditions=rule.conditions,
        severity=AlertSeverity(rule.severity),
        enabled=rule.enabled,
        created_by=current_user.username
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)

    buoy = db.query(Buoy).filter(Buoy.id == rule.buoy_id).first() if rule.buoy_id else None

    return {
        "code": 201,
        "message": "规则创建成功",
        "data": CombinedRuleResponse(
            id=str(db_rule.id),
            name=db_rule.name,
            buoy_id=str(db_rule.buoy_id) if db_rule.buoy_id else None,
            buoy_name=buoy.name if buoy else None,
            conditions=db_rule.conditions,
            severity=db_rule.severity.value,
            enabled=db_rule.enabled,
            created_by=db_rule.created_by,
            created_at=db_rule.created_at,
            updated_at=db_rule.updated_at
        ).model_dump()
    }


@router.put("/rules/{rule_id}")
def update_combined_rule(
    rule_id: str,
    update: CombinedRuleUpdate,
    current_user: User = Depends(require_role("researcher", "admin")),
    db: Session = Depends(get_db)
):
    """更新组合告警规则"""
    rule = db.query(CombinedAlertRule).filter(CombinedAlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    if update.name is not None:
        rule.name = update.name
    if update.buoy_id is not None:
        buoy = db.query(Buoy).filter(Buoy.id == update.buoy_id).first()
        if not buoy:
            raise HTTPException(status_code=404, detail="浮标不存在")
        rule.buoy_id = update.buoy_id
    if update.conditions is not None:
        rule.conditions = update.conditions
    if update.severity is not None:
        rule.severity = AlertSeverity(update.severity)
    if update.enabled is not None:
        rule.enabled = update.enabled

    rule.updated_at = datetime.utcnow()
    db.commit()

    buoy = db.query(Buoy).filter(Buoy.id == rule.buoy_id).first() if rule.buoy_id else None

    return {
        "code": 200,
        "message": "规则更新成功",
        "data": CombinedRuleResponse(
            id=str(rule.id),
            name=rule.name,
            buoy_id=str(rule.buoy_id) if rule.buoy_id else None,
            buoy_name=buoy.name if buoy else None,
            conditions=rule.conditions,
            severity=rule.severity.value,
            enabled=rule.enabled,
            created_by=rule.created_by,
            created_at=rule.created_at,
            updated_at=rule.updated_at
        ).model_dump()
    }


@router.delete("/rules/{rule_id}")
def delete_combined_rule(
    rule_id: str,
    current_user: User = Depends(require_role("researcher", "admin")),
    db: Session = Depends(get_db)
):
    """删除组合告警规则"""
    rule = db.query(CombinedAlertRule).filter(CombinedAlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    db.delete(rule)
    db.commit()

    return {"code": 200, "message": "规则删除成功", "data": None}


# ============ Recovered Alerts ============

@router.get("/recovery")
def get_recovered_alerts(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db)
):
    """获取已恢复的告警（数据恢复正常后自动解决）"""
    since = datetime.utcnow() - timedelta(days=days)
    alerts = db.query(Alert).filter(
        Alert.status == AlertStatus.resolved,
        Alert.resolved_at >= since
    ).order_by(desc(Alert.resolved_at)).limit(100).all()

    # Batch fetch buoys for names
    buoy_ids = list(set(a.buoy_id for a in alerts))
    buoys = db.query(Buoy).filter(Buoy.id.in_(buoy_ids)).all() if buoy_ids else []
    buoy_map = {str(b.id): b.name for b in buoys}

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": [
                {
                    "id": str(a.id),
                    "buoy_id": str(a.buoy_id),
                    "buoy_name": buoy_map.get(str(a.buoy_id)),
                    "alert_type": a.alert_type,
                    "param_name": a.param_name,
                    "actual_value": float(a.actual_value),
                    "threshold_value": float(a.threshold_value) if a.threshold_value else None,
                    "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
                    "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                    "resolved_by": a.resolved_by,
                    "remarks": a.remarks
                } for a in alerts
            ],
            "total": len(alerts),
            "days": days
        }
    }
