"""
报表生成服务 - 生成 PDF 格式的统计报表
支持日报、周报、月报、季报
"""
import io
import math
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.widgets.markers import makeMarker
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import SessionLocal
from app.models import Buoy, BuoyData, BuoyStatusLog, BuoyStatus, Alert, AlertConfig

# 中文字体配置
# 容器中使用 Noto Sans CJK
import os
import subprocess

CHINESE_FONT = "Helvetica"

# 尝试查找并注册字体
try:
    # 尝试用 fc-list 查找中文字体文件
    try:
        result = subprocess.run(['fc-list', ':lang=zh', '-f', '%{file}\n'], capture_output=True, text=True)
        if result.stdout:
            font_file = result.stdout.strip().split('\n')[0]
            if font_file and os.path.exists(font_file):
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                # 提取字体族名（去掉路径和扩展名）
                font_basename = os.path.basename(font_file)
                font_name = font_basename.replace('.ttc', '').replace('.ttf', '')
                pdfmetrics.registerFont(TTFont(font_name, font_file))
                CHINESE_FONT = font_name
                print(f"Registered Chinese font: {font_name} from {font_file}")
    except Exception as e:
        print(f"fc-list failed: {e}")

    # 如果还没找到字体，尝试常见路径
    if CHINESE_FONT == "Helvetica":
        font_paths = [
            # 文泉驿字体（已知可用）
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    from reportlab.pdfbase import pdfmetrics
                    from reportlab.pdfbase.ttfonts import TTFont
                    font_name = os.path.basename(fp).replace('.ttc', '').replace('.ttf', '')
                    font = TTFont(font_name, fp)
                    pdfmetrics.registerFont(font)
                    CHINESE_FONT = font_name
                    print(f"Registered Chinese font from path: {font_name}")
                    break
                except Exception as e:
                    print(f"Font registration failed for {fp}: {e}")
                    continue
except Exception as e:
    print(f"Font registration failed: {e}")
    CHINESE_FONT = "Helvetica"

print(f"Using font: {CHINESE_FONT}")

# 采集间隔（秒）
SAMPLING_INTERVAL_SECONDS = 10

# 报表类型
class ReportType:
    DAILY = "daily"      # 日报
    WEEKLY = "weekly"    # 周报
    MONTHLY = "monthly"  # 月报
    QUARTERLY = "quarterly"  # 季报

# 报表类型对应的中文名称
REPORT_TYPE_NAMES = {
    ReportType.DAILY: "日报",
    ReportType.WEEKLY: "周报",
    ReportType.MONTHLY: "月报",
    ReportType.QUARTERLY: "季报"
}

# 参数配置
PARAM_CONFIG = {
    "temperature": {"label": "水温", "unit": "°C"},
    "salinity": {"label": "盐度", "unit": "PSU"},
    "ph": {"label": "pH值", "unit": ""},
    "dissolved_oxygen": {"label": "溶解氧", "unit": "mg/L"},
    "turbidity": {"label": "浊度", "unit": "NTU"},
    "chlorophyll": {"label": "叶绿素", "unit": "μg/L"},
    "wave_height": {"label": "波高", "unit": "m"}
}


@dataclass
class ReportConfig:
    """报表配置"""
    buoy_ids: List[str]
    report_type: str
    start_time: datetime
    end_time: datetime
    include_trends: bool = True
    include_comparison: bool = False


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点之间的Haversine距离（公里）"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_report_time_range(report_type: str, reference_time: datetime = None):
    """根据报表类型计算时间范围"""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    # 确保 reference_time 是有时区的
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    if report_type == ReportType.DAILY:
        start = reference_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)
    elif report_type == ReportType.WEEKLY:
        # 周报：从周一到周日
        days_since_monday = reference_time.weekday()
        start = (reference_time - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7) - timedelta(seconds=1)
    elif report_type == ReportType.MONTHLY:
        start = reference_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # 下个月第一天减一秒
        if reference_time.month == 12:
            end = reference_time.replace(year=reference_time.year + 1, month=1, day=1) - timedelta(seconds=1)
        else:
            end = reference_time.replace(month=reference_time.month + 1, day=1) - timedelta(seconds=1)
    elif report_type == ReportType.QUARTERLY:
        # 季报：Q1=1-3月, Q2=4-6月, Q3=7-9月, Q4=10-12月
        quarter = (reference_time.month - 1) // 3
        start_month = quarter * 3 + 1
        start = reference_time.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_month == 10:
            end = reference_time.replace(year=reference_time.year + 1, month=1, day=1) - timedelta(seconds=1)
        else:
            end = reference_time.replace(month=start_month + 3, day=1) - timedelta(seconds=1)
    else:
        raise ValueError(f"Unknown report type: {report_type}")

    return start, end


class ReportGenerator:
    """报表生成器"""

    def __init__(self, config: ReportConfig):
        self.config = config
        self.db = SessionLocal()
        self.buoys = []
        self.report_data = {}

    def __del__(self):
        if self.db:
            self.db.close()

    def load_buoys(self):
        """加载浮标信息"""
        for buoy_id in self.config.buoy_ids:
            buoy = self.db.query(Buoy).filter(Buoy.id == buoy_id).first()
            if buoy:
                self.buoys.append(buoy)

    def get_buoy_statistics(self, buoy: Buoy):
        """获取浮标统计数据"""
        buoy_id = str(buoy.id)

        # 基础统计
        records = self.db.query(BuoyData).filter(
            BuoyData.buoy_id == buoy_id,
            BuoyData.time >= self.config.start_time,
            BuoyData.time <= self.config.end_time,
            BuoyData.drift_flagged == False
        ).count()

        statistics = {}
        for param, config in PARAM_CONFIG.items():
            column = getattr(BuoyData, param)
            stats = self.db.query(
                func.min(column).label("min"),
                func.max(column).label("max"),
                func.avg(column).label("avg"),
                func.stddev(column).label("std")
            ).filter(
                BuoyData.buoy_id == buoy_id,
                BuoyData.time >= self.config.start_time,
                BuoyData.time <= self.config.end_time,
                column.isnot(None),
                BuoyData.drift_flagged == False
            ).first()

            if stats and stats.min is not None:
                statistics[param] = {
                    "min": float(stats.min),
                    "max": float(stats.max),
                    "avg": round(float(stats.avg), 2),
                    "std": round(float(stats.std), 2) if stats.std else None,
                    "unit": config["unit"]
                }

        # 告警统计
        alerts = self.db.query(Alert).filter(
            Alert.buoy_id == buoy_id,
            Alert.triggered_at >= self.config.start_time,
            Alert.triggered_at <= self.config.end_time
        ).all()

        alert_count = len(alerts)
        alert_by_type = {}
        critical_count = 0
        for alert in alerts:
            alert_type = alert.alert_type
            severity = alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity)
            alert_by_type[alert_type] = alert_by_type.get(alert_type, 0) + 1
            if severity == "critical":
                critical_count += 1

        # 阈值和超标分析
        thresholds = self.db.query(AlertConfig).filter(
            AlertConfig.enabled == True,
            (AlertConfig.buoy_id == buoy_id) | (AlertConfig.buoy_id == None)
        ).all()

        threshold_map = {}
        for cfg in thresholds:
            if cfg.param_name:
                threshold_map[cfg.param_name] = {
                    "min": float(cfg.min_threshold) if cfg.min_threshold else None,
                    "max": float(cfg.max_threshold) if cfg.max_threshold else None,
                    "severity": cfg.severity.value if cfg.severity else "warning"
                }

        # 计算超标
        over_limit_count = 0
        over_limit_data = []
        raw_data_query = self.db.query(BuoyData).filter(
            BuoyData.buoy_id == buoy_id,
            BuoyData.time >= self.config.start_time,
            BuoyData.time <= self.config.end_time,
            BuoyData.drift_flagged == False
        ).order_by(BuoyData.time).all()

        for row in raw_data_query:
            for param, threshold in threshold_map.items():
                value = getattr(row, param)
                if value is not None:
                    if threshold["max"] and value > threshold["max"]:
                        over_limit_count += 1
                        over_limit_data.append({
                            "time": row.time,
                            "param": param,
                            "value": float(value),
                            "threshold": threshold["max"],
                            "type": "over_max"
                        })
                    elif threshold["min"] and value < threshold["min"]:
                        over_limit_count += 1
                        over_limit_data.append({
                            "time": row.time,
                            "param": param,
                            "value": float(value),
                            "threshold": threshold["min"],
                            "type": "under_min"
                        })

        # 状态统计
        status_logs = self.db.query(BuoyStatusLog).filter(
            BuoyStatusLog.buoy_id == buoy_id,
            BuoyStatusLog.changed_at >= self.config.start_time,
            BuoyStatusLog.changed_at <= self.config.end_time
        ).order_by(BuoyStatusLog.changed_at).all()

        total_seconds = (self.config.end_time - self.config.start_time).total_seconds()
        total_hours = total_seconds / 3600

        status_hours = {
            "online": 0.0, "offline": 0.0, "disconnected": 0.0,
            "low_battery": 0.0, "no_power": 0.0, "drift_alert": 0.0, "inactive": 0.0
        }

        # 确保时间比较时有时区信息
        def ensure_tz(dt):
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        start_time = ensure_tz(self.config.start_time)
        end_time = ensure_tz(self.config.end_time)

        if not status_logs:
            current_status = buoy.status.value if hasattr(buoy.status, 'value') else buoy.status
            if current_status in status_hours:
                status_hours[current_status] = total_hours
        else:
            prev_log = None
            for log in status_logs:
                if prev_log is None:
                    if log.changed_at > start_time:
                        duration = (log.changed_at - start_time).total_seconds() / 3600
                        prev_status = log.previous_status.value if hasattr(log.previous_status, 'value') else log.previous_status
                        if prev_status in status_hours:
                            status_hours[prev_status] += duration
                else:
                    duration = (log.changed_at - prev_log.changed_at).total_seconds() / 3600
                    prev_status = log.previous_status.value if hasattr(log.previous_status, 'value') else log.previous_status
                    if prev_status in status_hours:
                        status_hours[prev_status] += duration
                prev_log = log

            last_status = status_logs[-1].status.value if hasattr(status_logs[-1].status, 'value') else status_logs[-1].status
            if status_logs[-1].changed_at < end_time:
                duration = (end_time - status_logs[-1].changed_at).total_seconds() / 3600
                if last_status in status_hours:
                    status_hours[last_status] += duration

        # 漂移事件
        drift_events = []
        current_drift = None
        for log in status_logs:
            curr_status = log.status.value if hasattr(log.status, 'value') else log.status
            if curr_status == "drift_alert":
                if current_drift is None:
                    current_drift = {
                        "start": log.changed_at,
                        "start_lat": float(log.latitude) if log.latitude else None,
                        "start_lon": float(log.longitude) if log.longitude else None,
                        "max_offset_km": 0.0
                    }
                else:
                    if log.latitude and log.longitude and current_drift["start_lat"]:
                        offset = haversine_distance(
                            current_drift["start_lat"], current_drift["start_lon"],
                            float(log.latitude), float(log.longitude)
                        )
                        if offset > current_drift["max_offset_km"]:
                            current_drift["max_offset_km"] = offset
            else:
                if current_drift is not None:
                    current_drift["end"] = log.changed_at
                    current_drift["end_lat"] = float(log.latitude) if log.latitude else None
                    current_drift["end_lon"] = float(log.longitude) if log.longitude else None
                    current_drift["max_offset_km"] = round(current_drift["max_offset_km"], 4)
                    drift_events.append(current_drift)
                    current_drift = None

        if current_drift is not None:
            current_drift["end"] = self.config.end_time
            current_drift["max_offset_km"] = round(current_drift["max_offset_km"], 4)
            drift_events.append(current_drift)

        # 数据完整率
        expected_points = int(total_seconds / SAMPLING_INTERVAL_SECONDS)
        actual_points = self.db.query(BuoyData).filter(
            BuoyData.buoy_id == buoy_id,
            BuoyData.time >= self.config.start_time,
            BuoyData.time <= self.config.end_time
        ).count()

        completeness_rate = round((actual_points / expected_points * 100), 2) if expected_points > 0 else 0

        return {
            "buoy": buoy,
            "records": records,
            "statistics": statistics,
            "alerts": {
                "count": alert_count,
                "by_type": alert_by_type,
                "critical_count": critical_count,
                "critical_rate": round(critical_count / alert_count * 100, 2) if alert_count > 0 else 0
            },
            "over_limit": {
                "count": over_limit_count,
                "rate": round(over_limit_count / records * 100, 2) if records > 0 else 0,
                "max_deviation": over_limit_data
            },
            "status": {
                "hours": status_hours,
                "total_hours": total_hours,
                "online_rate": round((status_hours.get("online", 0) / total_hours * 100), 2) if total_hours > 0 else 0
            },
            "drift_events": drift_events,
            "data_completeness": {
                "expected": expected_points,
                "actual": actual_points,
                "rate": completeness_rate,
                "missing": expected_points - actual_points
            }
        }

    def get_timeseries_data(self, buoy_id: str, param: str, bucket: str = "1h"):
        """获取时序数据用于绘图"""
        interval_map = {
            "1h": "1 hour", "6h": "6 hour", "1d": "1 day",
            "30m": "30 min", "12h": "12 hour"
        }
        interval = interval_map.get(bucket, "1 hour")

        bucket_time = func.time_bucket(interval, BuoyData.time).label('bucket_time')
        column = getattr(BuoyData, param)

        result = self.db.query(
            bucket_time,
            func.min(column).label('min_val'),
            func.max(column).label('max_val'),
            func.avg(column).label('avg_val')
        ).filter(
            BuoyData.buoy_id == buoy_id,
            BuoyData.time >= self.config.start_time,
            BuoyData.time <= self.config.end_time,
            column.isnot(None),
            BuoyData.drift_flagged == False
        ).group_by(bucket_time).order_by(bucket_time).all()

        return [
            {
                "time": row.bucket_time.isoformat() if row.bucket_time else str(row[0]),
                "min": float(row.min_val) if row.min_val is not None else None,
                "max": float(row.max_val) if row.max_val is not None else None,
                "avg": round(float(row.avg_val), 2) if row.avg_val is not None else None
            }
            for row in result
        ]

    def generate_pdf(self) -> bytes:
        """生成 PDF 报表"""
        self.load_buoys()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='ChineseTitle',
            fontName=CHINESE_FONT,
            fontSize=18,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=20
        ))
        styles.add(ParagraphStyle(
            name='ChineseHeading',
            fontName=CHINESE_FONT,
            fontSize=14,
            leading=18,
            alignment=TA_LEFT,
            spaceBefore=15,
            spaceAfter=10
        ))
        styles.add(ParagraphStyle(
            name='ChineseBody',
            fontName=CHINESE_FONT,
            fontSize=10,
            leading=14,
            alignment=TA_LEFT
        ))
        styles.add(ParagraphStyle(
            name='ChineseCenter',
            fontName=CHINESE_FONT,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER
        ))
        styles.add(ParagraphStyle(
            name='ChineseSmall',
            fontName=CHINESE_FONT,
            fontSize=8,
            leading=10,
            alignment=TA_LEFT
        ))

        story = []

        # ===== 封面信息 =====
        report_type_name = REPORT_TYPE_NAMES.get(self.config.report_type, "报表")
        title = f"{report_type_name} - 海洋浮标监测统计报告"
        story.append(Paragraph(title, styles['ChineseTitle']))
        story.append(Spacer(1, 10))

        # 报表信息
        info_data = [
            ["报表类型", report_type_name],
            ["生成时间", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")],
            ["统计周期", f"{self.config.start_time.strftime('%Y-%m-%d %H:%M')} ~ {self.config.end_time.strftime('%Y-%m-%d %H:%M')}"],
            ["浮标数量", str(len(self.buoys))],
            ["浮标列表", ", ".join([b.name for b in self.buoys])]
        ]
        info_table = Table(info_data, colWidths=[4*cm, 12*cm])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 20))

        # ===== 遍历每个浮标生成详情 =====
        for buoy in self.buoys:
            buoy_data = self.get_buoy_statistics(buoy)
            self.report_data[str(buoy.id)] = buoy_data

            # 浮标标题
            story.append(Paragraph(
                f"浮标: {buoy.name} ({buoy.code})",
                styles['ChineseHeading']
            ))
            story.append(Paragraph(
                f"位置: {buoy.latitude:.4f}°N, {buoy.longitude:.4f}°E | 海域: {buoy.sea_area or '未设置'}",
                styles['ChineseSmall']
            ))
            story.append(Spacer(1, 10))

            # 1. 数据完整率
            completeness = buoy_data["data_completeness"]
            dc_data = [
                ["数据完整率", f"{completeness['rate']}%"],
                ["理论数据点", str(completeness['expected'])],
                ["实际数据点", str(completeness['actual'])],
                ["缺失数据点", str(completeness['missing'])]
            ]
            dc_table = Table(dc_data, colWidths=[4*cm, 3*cm])
            dc_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(dc_table)
            story.append(Spacer(1, 15))

            # 2. 统计摘要表
            story.append(Paragraph("统计摘要", styles['ChineseHeading']))
            stats = buoy_data["statistics"]
            if stats:
                stats_header = ["参数", "最小值", "最大值", "平均值", "标准差", "单位"]
                stats_rows = [stats_header]
                for param, config in PARAM_CONFIG.items():
                    if param in stats:
                        s = stats[param]
                        stats_rows.append([
                            config["label"],
                            f"{s['min']:.2f}",
                            f"{s['max']:.2f}",
                            f"{s['avg']:.2f}",
                            f"{s.get('std') or '-':.2f}" if isinstance(s.get('std'), (int, float)) else str(s.get('std') or '-'),
                            s['unit']
                        ])
                stats_table = Table(stats_rows, colWidths=[3*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2*cm])
                stats_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#366092')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                ]))
                story.append(stats_table)
            else:
                story.append(Paragraph("该时段内无有效数据", styles['ChineseBody']))
            story.append(Spacer(1, 15))

            # 3. 告警统计
            alerts = buoy_data["alerts"]
            story.append(Paragraph("告警统计", styles['ChineseHeading']))
            alert_data = [
                ["告警次数", str(alerts['count'])],
                ["严重告警", str(alerts['critical_count'])],
                ["严重告警占比", f"{alerts['critical_rate']}%"],
            ]
            if alerts['by_type']:
                for atype, count in alerts['by_type'].items():
                    alert_data.append([f"类型: {atype}", str(count)])
            alert_table = Table(alert_data, colWidths=[4*cm, 3*cm])
            alert_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff2e6')) if alerts['count'] > 0 else ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(alert_table)
            story.append(Spacer(1, 15))

            # 4. 超标分析
            over_limit = buoy_data["over_limit"]
            story.append(Paragraph("超标分析", styles['ChineseHeading']))
            ol_data = [
                ["超标点数", str(over_limit['count'])],
                ["超标比例", f"{over_limit['rate']}%"]
            ]
            ol_table = Table(ol_data, colWidths=[4*cm, 3*cm])
            ol_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff2e6')) if over_limit['count'] > 0 else ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(ol_table)
            story.append(Spacer(1, 15))

            # 5. 状态统计
            status = buoy_data["status"]
            story.append(Paragraph("状态统计", styles['ChineseHeading']))
            status_header = ["状态", "在线", "离线", "失联", "低电量", "无电", "漂移告警"]
            status_values = [
                ["时长(小时)",
                 f"{status['hours'].get('online', 0):.1f}",
                 f"{status['hours'].get('offline', 0):.1f}",
                 f"{status['hours'].get('disconnected', 0):.1f}",
                 f"{status['hours'].get('low_battery', 0):.1f}",
                 f"{status['hours'].get('no_power', 0):.1f}",
                 f"{status['hours'].get('drift_alert', 0):.1f}"]
            ]
            status_rows = [status_header, status_values[0]]
            status_table = Table(status_rows, colWidths=[2.5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2.5*cm])
            status_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5470c6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#52c41a')),  # online 绿色
                ('BACKGROUND', (6, 1), (6, 1), colors.HexColor('#ff4d4f')),  # drift 红色
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(status_table)
            story.append(Spacer(1, 5))
            story.append(Paragraph(f"在线率: {status['online_rate']}%", styles['ChineseSmall']))
            story.append(Spacer(1, 15))

            # 6. 漂移事件详情
            drift_events = buoy_data["drift_events"]
            if drift_events:
                story.append(Paragraph("漂移事件详情", styles['ChineseHeading']))
                drift_header = ["开始时间", "结束时间", "持续时长", "最大偏移(km)", "起始位置", "结束位置"]
                drift_rows = [drift_header]
                for event in drift_events:
                    start = event.get('start')
                    end = event.get('end')
                    duration = ""
                    if start and end:
                        delta = end - start if isinstance(end, datetime) and isinstance(start, datetime) else None
                        if delta:
                            duration = f"{delta.total_seconds() / 3600:.1f}h"
                    drift_rows.append([
                        start.strftime("%m-%d %H:%M") if start else "-",
                        end.strftime("%m-%d %H:%M") if end else "-",
                        duration,
                        f"{event.get('max_offset_km', 0):.3f}",
                        f"{event.get('start_lat', 0):.4f}, {event.get('start_lon', 0):.4f}" if event.get('start_lat') else "-",
                        f"{event.get('end_lat', 0):.4f}, {event.get('end_lon', 0):.4f}" if event.get('end_lat') else "-"
                    ])
                drift_table = Table(drift_rows, colWidths=[2.5*cm, 2.5*cm, 2*cm, 2.5*cm, 3.5*cm, 3.5*cm])
                drift_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), CHINESE_FONT),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ff4d4f')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(drift_table)
            story.append(Spacer(1, 15))

            # 分页
            if buoy != self.buoys[-1]:
                story.append(PageBreak())

        # ===== 页脚 =====
        story.append(Spacer(1, 30))
        footer_text = f"报表生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} | OBMAP 海洋浮标监测平台"
        story.append(Paragraph(footer_text, styles['ChineseSmall']))

        # 生成 PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()


def generate_report(config: ReportConfig) -> bytes:
    """生成报表的入口函数"""
    generator = ReportGenerator(config)
    return generator.generate_pdf()
