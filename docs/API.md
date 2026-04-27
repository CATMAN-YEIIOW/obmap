# 海洋浮标监测信息管理与分析平台 - API接口文档

## 概述

- **基础URL**: `http://localhost:8000/api/v1`
- **认证方式**: Bearer Token (JWT)
- **数据格式**: JSON
- **字符编码**: UTF-8

---

## 目录

1. [用户认证](#1-用户认证)
2. [浮标设备管理](#2-浮标设备管理)
3. [监测数据查询](#3-监测数据查询)
4. [实时数据订阅](#4-实时数据订阅)
5. [告警管理](#5-告警管理)
6. [统计分析](#6-统计分析)

---

## 1. 用户认证

### 1.1 用户注册

**请求**
```
POST /auth/register
Content-Type: application/json
```

**请求体**
```json
{
  "username": "string",
  "email": "string",
  "password": "string",
  "full_name": "string (可选)"
}
```

**响应 (201)**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "bd950917-21f2-499c-a7aa-e45424c312b8",
    "username": "admin",
    "email": "admin@obmap.com",
    "full_name": "管理员",
    "role": "viewer",
    "is_active": true
  }
}
```

**错误响应 (400)**
```json
{
  "detail": "用户名已存在"
}
```

---

### 1.2 用户登录

**请求**
```
POST /auth/login
Content-Type: application/x-www-form-urlencoded
```

**请求体**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| password | string | 是 | 密码 |

**响应 (200)**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "bd950917-21f2-499c-a7aa-e45424c312b8",
    "username": "admin",
    "email": "admin@obmap.com",
    "full_name": "管理员",
    "role": "viewer",
    "is_active": true
  }
}
```

---

### 1.3 获取当前用户

**请求**
```
GET /auth/me
Authorization: Bearer <token>
```

**响应 (200)**
```json
{
  "id": "bd950917-21f2-499c-a7aa-e45424c312b8",
  "username": "admin",
  "email": "admin@obmap.com",
  "full_name": "管理员",
  "role": "viewer",
  "is_active": true
}
```

---

### 1.4 修改密码

**请求**
```
POST /auth/change-password
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体**
```json
{
  "old_password": "string",
  "new_password": "string"
}
```

**响应 (200)**
```json
{
  "code": 200,
  "message": "密码修改成功"
}
```

---

### 1.5 用户列表 (管理员)

**请求**
```
GET /auth/users
Authorization: Bearer <token>
```

**响应 (200)**
```json
[
  {
    "id": "bd950917-21f2-499c-a7aa-e45424c312b8",
    "username": "admin",
    "email": "admin@obmap.com",
    "full_name": "管理员",
    "role": "admin",
    "is_active": true
  }
]
```

---

### 1.6 更新用户角色 (管理员)

**请求**
```
PUT /auth/users/{user_id}/role?role=admin
Authorization: Bearer <token>
```

**响应 (200)**
```json
{
  "code": 200,
  "message": "角色更新成功"
}
```

---

### 1.7 删除用户 (管理员)

**请求**
```
DELETE /auth/users/{user_id}
Authorization: Bearer <token>
```

**响应 (200)**
```json
{
  "code": 200,
  "message": "用户删除成功"
}
```

---

## 2. 浮标设备管理

### 1.1 获取浮标列表

**请求**
```
GET /buoys
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码，默认1 |
| page_size | int | 否 | 每页数量，默认20 |
| status | string | 否 | 过滤状态：online/offline/warning |
| sea_area | string | 否 | 海域过滤 |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "渤海浮标01号",
        "code": "BH-001",
        "latitude": 39.1234567,
        "longitude": 121.7654321,
        "depth": 10.5,
        "status": "online",
        "sea_area": "渤海",
        "created_at": "2026-03-01T10:00:00Z",
        "updated_at": "2026-03-30T08:30:00Z"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 20
  }
}
```

### 1.2 获取浮标详情

**请求**
```
GET /buoys/{buoy_id}
```

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| buoy_id | UUID | 浮标ID |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "渤海浮标01号",
    "code": "BH-001",
    "latitude": 39.1234567,
    "longitude": 121.7654321,
    "depth": 10.5,
    "status": "online",
    "sea_area": "渤海",
    "created_at": "2026-03-01T10:00:00Z",
    "updated_at": "2026-03-30T08:30:00Z",
    "latest_data": {
      "temperature": 23.5,
      "salinity": 35.2,
      "pH": 8.12,
      "timestamp": "2026-03-30T10:30:00Z"
    }
  }
}
```

### 1.3 创建浮标

**请求**
```
POST /buoys
```

**请求体**
```json
{
  "name": "东海浮标02号",
  "code": "DH-002",
  "latitude": 30.2345678,
  "longitude": 122.8765432,
  "depth": 15.0,
  "sea_area": "东海"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 浮标名称，最大100字符 |
| code | string | 是 | 浮标编码，最大50字符，唯一 |
| latitude | decimal | 是 | 纬度，范围 -90~90 |
| longitude | decimal | 是 | 经度，范围 -180~180 |
| depth | decimal | 否 | 部署深度，默认0 |
| sea_area | string | 否 | 海域名称 |

**响应**
```json
{
  "code": 201,
  "message": "浮标创建成功",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "东海浮标02号",
    "code": "DH-002"
  }
}
```

### 1.4 更新浮标

**请求**
```
PUT /buoys/{buoy_id}
```

**请求体**
```json
{
  "name": "东海浮标02号(修正)",
  "latitude": 30.2500000,
  "depth": 20.0
}
```

**响应**
```json
{
  "code": 200,
  "message": "浮标更新成功",
  "data": null
}
```

### 1.5 删除浮标

**请求**
```
DELETE /buoys/{buoy_id}
```

**响应**
```json
{
  "code": 200,
  "message": "浮标删除成功",
  "data": null
}
```

---

## 3. 监测数据查询

### 2.1 获取实时数据

**请求**
```
GET /data/realtime
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| buoy_ids | string | 否 | 浮标ID列表，逗号分隔，默认全部 |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "timestamp": "2026-03-30T10:30:00Z",
    "buoys": [
      {
        "buoy_id": "550e8400-e29b-41d4-a716-446655440000",
        "buoy_name": "渤海浮标01号",
        "data": {
          "temperature": 23.5,
          "salinity": 35.2,
          "pH": 8.12,
          "dissolved_oxygen": 7.8,
          "turbidity": 12.5,
          "chlorophyll": 5.3,
          "wave_height": 1.2
        }
      }
    ]
  }
}
```

### 2.2 获取历史数据

**请求**
```
GET /data/history
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| buoy_id | UUID | 是 | 浮标ID |
| start_time | datetime | 是 | 开始时间 ISO8601格式 |
| end_time | datetime | 是 | 结束时间 ISO8601格式 |
| param | string | 否 | 筛选参数名，如 temperature |
| page | int | 否 | 页码，默认1 |
| page_size | int | 否 | 每页数量，默认100，最大1000 |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "time": "2026-03-30T10:00:00Z",
        "temperature": 23.4,
        "salinity": 35.1,
        "pH": 8.11,
        "dissolved_oxygen": 7.9,
        "turbidity": 11.8,
        "chlorophyll": 5.1,
        "wave_height": 1.1
      },
      {
        "time": "2026-03-30T09:50:00Z",
        "temperature": 23.3,
        "salinity": 35.0,
        "pH": 8.10,
        "dissolved_oxygen": 8.0,
        "turbidity": 12.0,
        "chlorophyll": 5.2,
        "wave_height": 1.0
      }
    ],
    "total": 180,
    "page": 1,
    "page_size": 100
  }
}
```

### 2.3 获取最新数据

**请求**
```
GET /data/latest/{buoy_id}
```

**路径参数**
| 参数 | 类型 | 说明 |
|------|------|------|
| buoy_id | UUID | 浮标ID |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "buoy_id": "550e8400-e29b-41d4-a716-446655440000",
    "time": "2026-03-30T10:30:00Z",
    "temperature": 23.5,
    "salinity": 35.2,
    "pH": 8.12,
    "dissolved_oxygen": 7.8,
    "turbidity": 12.5,
    "chlorophyll": 5.3,
    "wave_height": 1.2
  }
}
```

---

## 4. 实时数据订阅

### 3.1 WebSocket连接

**连接地址**
```
ws://localhost:8000/ws/realtime
```

**客户端订阅消息**
```json
{
  "type": "subscribe",
  "buoy_ids": ["all"]  // 或指定 ["id1", "id2"]
}
```

**服务端推送消息格式**
```json
{
  "type": "data_update",
  "timestamp": "2026-03-30T10:30:00Z",
  "data": [
    {
      "buoy_id": "550e8400-e29b-41d4-a716-446655440000",
      "buoy_name": "渤海浮标01号",
      "status": "online",
      "temperature": 23.5,
      "salinity": 35.2,
      "pH": 8.12,
      "dissolved_oxygen": 7.8,
      "turbidity": 12.5,
      "chlorophyll": 5.3,
      "wave_height": 1.2
    }
  ]
}
```

**告警推送消息格式**
```json
{
  "type": "alert",
  "timestamp": "2026-03-30T10:30:00Z",
  "data": {
    "id": "alert-001",
    "buoy_id": "550e8400-e29b-41d4-a716-446655440000",
    "buoy_name": "渤海浮标01号",
    "alert_type": "threshold_exceeded",
    "param_name": "temperature",
    "actual_value": 32.5,
    "threshold_value": 30.0,
    "severity": "warning",
    "message": "水温超过阈值: 32.5°C > 30.0°C"
  }
}
```

**心跳消息**
```json
{
  "type": "ping"
}
```

---

## 5. 告警管理

### 4.1 获取告警列表

**请求**
```
GET /alerts
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| buoy_id | UUID | 否 | 浮标ID |
| status | string | 否 | 状态：triggered/acknowledged/resolved |
| severity | string | 否 | 严重程度：info/warning/critical |
| start_time | datetime | 否 | 开始时间 |
| end_time | datetime | 否 | 结束时间 |
| page | int | 否 | 页码，默认1 |
| page_size | int | 否 | 每页数量，默认20 |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "alert-001",
        "buoy_id": "550e8400-e29b-41d4-a716-446655440000",
        "buoy_name": "渤海浮标01号",
        "alert_type": "threshold_exceeded",
        "param_name": "temperature",
        "threshold_value": 30.0,
        "actual_value": 32.5,
        "severity": "warning",
        "status": "triggered",
        "triggered_at": "2026-03-30T10:30:00Z",
        "resolved_at": null
      }
    ],
    "total": 15,
    "page": 1,
    "page_size": 20
  }
}
```

### 4.2 获取告警统计

**请求**
```
GET /alerts/statistics
```

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 150,
    "by_severity": {
      "info": 80,
      "warning": 50,
      "critical": 20
    },
    "by_status": {
      "triggered": 5,
      "acknowledged": 10,
      "resolved": 135
    },
    "recent_24h": 12
  }
}
```

### 4.3 确认告警

**请求**
```
PUT /alerts/{alert_id}/acknowledge
```

**响应**
```json
{
  "code": 200,
  "message": "告警已确认",
  "data": null
}
```

### 4.4 解决告警

**请求**
```
PUT /alerts/{alert_id}/resolve
```

**响应**
```json
{
  "code": 200,
  "message": "告警已解决",
  "data": null
}
```

### 4.5 获取告警配置列表

**请求**
```
GET /alerts/config
```

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "config-001",
        "param_name": "temperature",
        "min_threshold": null,
        "max_threshold": 30.0,
        "severity": "warning",
        "enabled": true
      },
      {
        "id": "config-002",
        "param_name": "pH",
        "min_threshold": 7.0,
        "max_threshold": 8.5,
        "severity": "warning",
        "enabled": true
      }
    ]
  }
}
```

### 4.6 更新告警配置

**请求**
```
PUT /alerts/config/{config_id}
```

**请求体**
```json
{
  "max_threshold": 32.0,
  "enabled": true
}
```

**响应**
```json
{
  "code": 200,
  "message": "配置更新成功",
  "data": null
}
```

---

## 6. 统计分析

### 5.1 获取统计摘要

**请求**
```
GET /statistics/summary
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| buoy_id | UUID | 是 | 浮标ID |
| start_time | datetime | 是 | 开始时间 |
| end_time | datetime | 是 | 结束时间 |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "buoy_id": "550e8400-e29b-41d4-a716-446655440000",
    "period": {
      "start": "2026-03-01T00:00:00Z",
      "end": "2026-03-30T23:59:59Z"
    },
    "records": 259200,
    "statistics": {
      "temperature": {
        "min": 18.5,
        "max": 28.3,
        "avg": 23.4,
        "unit": "°C"
      },
      "salinity": {
        "min": 32.1,
        "max": 36.5,
        "avg": 34.8,
        "unit": "PSU"
      },
      "pH": {
        "min": 7.8,
        "max": 8.4,
        "avg": 8.1,
        "unit": ""
      },
      "dissolved_oxygen": {
        "min": 6.5,
        "max": 9.2,
        "avg": 7.8,
        "unit": "mg/L"
      }
    }
  }
}
```

### 5.2 获取时序统计数据

**请求**
```
GET /statistics/timeseries
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| buoy_id | UUID | 是 | 浮标ID |
| param | string | 是 | 参数名 |
| start_time | datetime | 是 | 开始时间 |
| end_time | datetime | 是 | 结束时间 |
| bucket | string | 否 | 聚合间隔：1h/6h/1d，默认1h |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "param": "temperature",
    "unit": "°C",
    "bucket": "1h",
    "items": [
      {
        "time": "2026-03-30T00:00:00Z",
        "min": 22.1,
        "max": 24.5,
        "avg": 23.3,
        "count": 360
      },
      {
        "time": "2026-03-30T01:00:00Z",
        "min": 22.3,
        "max": 24.8,
        "avg": 23.5,
        "count": 360
      }
    ]
  }
}
```

### 5.3 获取多浮标对比数据

**请求**
```
GET /statistics/compare
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| buoy_ids | string | 是 | 浮标ID列表，逗号分隔，最多5个 |
| param | string | 是 | 参数名 |
| start_time | datetime | 是 | 开始时间 |
| end_time | datetime | 是 | 结束时间 |

**响应**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "param": "temperature",
    "unit": "°C",
    "buoys": [
      {
        "buoy_id": "550e8400-e29b-41d4-a716-446655440000",
        "buoy_name": "渤海浮标01号",
        "avg": 23.4,
        "min": 18.5,
        "max": 28.3
      },
      {
        "buoy_id": "550e8400-e29b-41d4-a716-446655440001",
        "buoy_name": "黄海浮标01号",
        "avg": 21.2,
        "min": 16.8,
        "max": 26.5
      }
    ]
  }
}
```

### 5.4 导出数据

**请求**
```
GET /export/data
```

**查询参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| buoy_id | UUID | 是 | 浮标ID |
| start_time | datetime | 是 | 开始时间 |
| end_time | datetime | 是 | 结束时间 |
| format | string | 否 | 导出格式：csv/xlsx，默认csv |

**响应**
- Content-Type: text/csv 或 application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
- Content-Disposition: attachment; filename="buoy_data_20260301_20260330.csv"

---

## 错误响应格式

```json
{
  "code": 400,
  "message": "请求参数错误",
  "detail": {
    "field": "latitude",
    "reason": "纬度值超出范围 (-90 ~ 90)"
  }
}
```

### 错误码说明
| code | 说明 |
|------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 附录：数据字典

### 监测参数说明
| 参数名 | 中文名 | 单位 | 正常范围 |
|--------|--------|------|---------|
| temperature | 水温 | °C | 5-30 |
| salinity | 盐度 | PSU | 30-36 |
| pH | pH值 | - | 7.5-8.5 |
| dissolved_oxygen | 溶解氧 | mg/L | 5-10 |
| turbidity | 浊度 | NTU | 0-50 |
| chlorophyll | 叶绿素 | μg/L | 0-20 |
| wave_height | 波高 | m | 0-5 |

### 浮标状态说明
| 状态 | 说明 |
|------|------|
| online | 在线 |
| offline | 离线 |
| warning | 告警中 |

### 海域说明
| 海域 | 说明 |
|------|------|
| 渤海 | 中国渤海海域 |
| 黄海 | 中国黄海海域 |
| 东海 | 中国东海海域 |
| 南海 | 中国南海海域 |