# 海洋浮标监测信息管理与分析平台

Ocean Buoy Monitoring Information Management and Analysis Platform (OBMAP)

## 项目简介

本科毕业设计项目，用于海洋环境监测数据的实时采集、存储、分析和可视化展示。

## 技术栈

- **前端**: React 18 + TypeScript + Vite + Ant Design 5 + ECharts
- **后端**: Python 3.11 + FastAPI + SQLAlchemy
- **数据库**: PostgreSQL 15 + TimescaleDB (时序数据)
- **缓存**: Redis 7
- **实时通信**: Socket.IO
- **容器化**: Docker + Docker Compose

## 快速开始

### 前置条件

- Docker Desktop (Windows/Mac) 或 Docker Engine (Linux)
- 16GB+ RAM 推荐
- 20GB+ 可用磁盘空间

### 启动服务

```bash
# 克隆项目后，在项目根目录执行
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f backend
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端应用 | http://localhost |
| 后端API | http://localhost:8000 |
| API文档 | http://localhost:8000/docs |
| WebSocket | ws://localhost:8000/ws/realtime |

### 停止服务

```bash
docker-compose down
```

## 目录结构

```
obmap/
├── docs/                    # 开发文档
│   ├── SPEC.md            # 项目规格说明
│   ├── API.md             # API接口文档
│   └── README.md          # 本文件
├── backend/               # 后端服务
│   ├── app/
│   │   ├── main.py       # FastAPI入口
│   │   ├── config.py     # 配置管理
│   │   ├── database.py   # 数据库连接
│   │   ├── models/       # 数据模型
│   │   ├── routers/      # API路由
│   │   ├── services/     # 业务逻辑
│   │   └── simulator/    # 数据模拟服务
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/              # 前端应用
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/        # 页面组件
│   │   ├── components/   # 公共组件
│   │   ├── hooks/        # 自定义Hooks
│   │   ├── services/     # API调用
│   │   └── stores/       # 状态管理
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── .env
```

## 数据模拟说明

系统启动后会自动生成模拟数据：

- **浮标数量**: 5个
- **分布海域**: 渤海、黄海、东海（各1个）、南海（2个）
- **数据频率**: 每10秒生成一条数据/浮标
- **模拟参数**: 水温、盐度、pH、溶解氧、浊度、叶绿素、波高

## 主要功能

1. **实时监测大屏** - 地图展示浮标位置，实时数据刷新
2. **设备管理** - 浮标设备CRUD操作
3. **数据查询** - 历史数据时间范围查询
4. **统计分析** - 多维度数据统计分析
5. **告警管理** - 阈值告警触发和记录

## 开发者

- 开发环境：Windows 11 + VS Code
- 毕业设计：2026届

## 许可

MIT License