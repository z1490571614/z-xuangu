# AGENTS.md - 选股通知系统架构文档

## 项目概述

| 属性 | 值 |
|------|-----|
| **项目名称** | 选股通知系统 (Stock Selector Notification System) |
| **版本** | v3.0 |
| **状态** | 三阶段选股架构已完成 ✅ |
| **最后更新** | 2026-04-27 |

---

## 目录

- [系统架构](#系统架构)
- [核心模块说明](#核心模块说明)
- [数据流](#数据流)
- [配置管理](#配置管理)
- [部署架构](#部署架构)
- [开发进度](#开发进度)
- [关键技术决策](#关键技术决策)
- [接口说明](#接口说明)
- [注意事项](#注意事项)
- [性能基准](#性能基准)
- [开发规范](#开发规范)

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      用户浏览器                              │
│              Vue 3 + Vue Router + WebSocket                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS (Nginx 反向代理)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Nginx 反向代理                            │
│  / → 前端静态文件    /api/ → 后端服务   /ws → WebSocket     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI 后端服务 (Port: 9999)                 │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │  API路由  │ │ 选股引擎 │ │ 任务调度  │ │ 实时通信  │       │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
│       │            │            │            │              │
│  ┌────▼────────────▼────────────▼────────────▼──────────┐   │
│  │                   业务逻辑层                           │   │
│  │  - TdxSelectorService (阶段1: MCP选股)               │   │
│  │  - StockSelectorService (三阶段协调)                  │   │
│  │  - TushareDataCollector (阶段2: 分析)                │   │
│  │  - SealRateCalculator (阶段3: 封板率计算)            │   │
│  │  - ConnectionManager (WebSocket连接管理)             │   │
│  │  - TaskScheduler (任务调度)                           │   │
│  │  - FeishuNotifier (飞书通知)                          │   │
│  │  - AlertService (告警服务)                            │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │                    数据访问层                          │   │
│  │  - SQLAlchemy ORM (连接池优化)                        │   │
│  │  - SQLite WAL 模式                                   │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┬───────────────┐
          ▼               ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ SQLite   │   │ 通达信   │   │ Tushare  │   │  飞书     │
    │  数据库  │   │ MCP接口  │   │   API    │   │ Webhook  │
    │ (WAL模式)│   │ (选股)   │   │ (分析)   │   │ (通知)   │
    └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

---

## 核心模块说明

### 1. 三阶段选股引擎 (Three-Phase Selection Engine)

#### 阶段1: 通达信MCP选股服务

**位置**: `backend/services/tdx_selector.py`

**核心优势**:
- ✅ 支持8个条件的复杂查询
- ✅ 服务端筛选，效率极高 (<1秒响应)
- ✅ 模块化条件架构，支持灵活组合
- ✅ 一次查询完成所有筛选条件

**选股条件配置**:
```
基本筛选: 非ST、非停牌、非北交所
市值条件: 流通市值 < 2000亿
价格条件: 收盘价 < 500元
趋势条件: 近10日股价上涨
涨停条件: 近100日涨停 ≥3次
竞价条件: 竞昨比 4%-30%, 换手率 0.5%-10%
```

**⚠️ 重要：MCP接口格式要求**:
- ✅ 推荐使用整数格式: `4%到30%`
- ❌ 避免使用小数格式: `4.0%到30.0%`
- 📝 数值格式错误会导致返回0条记录

**核心类**:

| 类名 | 说明 | 关键方法 |
|------|------|----------|
| `SelectionCondition` | 选股条件抽象基类 | `build_query_part()`, `validate()` |
| `BasicFilterCondition` | 基本筛选条件 | 非ST/非停牌/非北交所 |
| `MarketCapCondition` | 市值条件 | 流通市值过滤 |
| `PriceCondition` | 价格条件 | 收盘价过滤 |
| `TrendCondition` | 趋势条件 | 近N日股价上涨 |
| `LimitUpCondition` | 涨停条件 | 涨停次数 |
| `CallAuctionCondition` | 竞价条件 | 竞价活跃度过滤 |
| `SelectionTask` | 独立选股任务 | `build_query()`, `add_condition()` |
| `TdxSelectorService` | 选股服务 | `select()`, `add_task()` |

#### 阶段2: Tushare分析服务

**位置**: `backend/services/data_collector.py`

**功能**: 对选出的股票获取补充分析数据

**核心方法**:

| 方法 | 功能 | 用途 |
|------|------|------|
| `get_daily_data()` | 获取日线行情 | K线分析、昨涨幅、开涨幅计算 |
| `get_daily_basic()` | 获取每日指标 | PE/PB/市值 |
| `get_limit_list()` | 获取涨跌停数据 | 涨停详情 |
| `is_trading_day()` | 判断交易日 | 调度判断 |
| `get_latest_trade_date()` | 获取最新交易日 | 自动日期获取 |

**补充数据项**:
- 每日指标: PE、PE_TTM、PB、换手率、量比、总市值、流通市值
- 昨涨幅: 前一交易日涨跌幅
- 开涨幅: 当日开盘价相对昨日收盘价的涨跌幅

#### 阶段3: 封板率计算服务

**位置**: `backend/services/seal_rate_calculator.py`

**功能**: 基于前复权数据计算封板率指标

**计算公式**:
```
区间触板天数 = 100个交易日内最高价≥涨停价的天数
区间涨停天数 = 100个交易日内收盘价≥涨停价的天数
封板率 = 区间涨停天数 / 区间触板天数 × 100%
```

**核心方法**:

| 方法 | 功能 | 说明 |
|------|------|------|
| `get_trading_dates()` | 获取交易日列表 | 指定周期内的交易日 |
| `fetch_and_save_daily_data()` | 获取并保存日线数据 | 前复权处理 |
| `calculate_seal_rate_from_cache()` | 从缓存计算封板率 | 基于数据库数据 |
| `get_cached_result()` | 获取缓存结果 | 避免重复计算 |
| `save_cached_result()` | 保存计算结果 | 缓存到数据库 |
| `calculate_seal_rate()` | 计算封板率 | 主入口方法 |
| `batch_calculate_seal_rate()` | 批量计算封板率 | 支持过滤 |

**数据缓存机制**:
- 日线数据缓存: `stock_daily_data` 表
- 计算结果缓存: `seal_rate_cache` 表
- 支持强制刷新和增量更新

#### 三阶段协调器

**位置**: `backend/services/stock_selector.py`

**核心类**: `StockSelectorService`

**关键流程**:
```
select_stocks()
    ↓
_execute_phase1()  → TdxSelectorService.select()
    ↓ (成功)
_execute_phase2()  → TushareDataCollector (补充数据 + 昨涨幅/开涨幅)
    ↓
_execute_phase3()  → SealRateCalculator (封板率计算与过滤)
    ↓
_merge_results()   → 合并三阶段数据
    ↓
_build_final_result() → 返回最终结果
```

**策略模板**:

| 模板名称 | 创建函数 | 封板率阈值 | 适用场景 |
|---------|---------|-----------|---------|
| default | `create_default_task()` | ≥90% | 日常选股 |
| conservative | `create_conservative_task()` | ≥95% | 稳健投资 |
| aggressive | `create_aggressive_task()` | ≥80% | 激进交易 |

### 2. WebSocket 实时通信 (Real-time Communication)

**位置**: `backend/services/websocket_service.py`

**核心类**: `ConnectionManager`

**功能特性**:
- 多频道支持 (tasks, stocks, default)
- 订阅/取消订阅机制
- 心跳检测 (ping/pong)
- 消息广播到指定频道
- 断线自动清理

**WebSocket 端点**:
- `WS /ws` - 主端点
- `GET /api/v1/ws/stats` - 连接统计

### 3. 监控系统 (Monitoring)

**Prometheus 中间件**: `backend/middleware/prometheus_middleware.py`

**指标**:

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `http_requests_total` | Counter | 请求总数 |
| `http_request_duration_seconds` | Histogram | 请求延迟 |
| `http_requests_in_progress` | Gauge | 活跃请求数 |

### 4. 安全中间件 (Security)

**位置**: `backend/middleware/security_middleware.py`

**安全响应头**:

| 头部 | 值 | 说明 |
|------|------|------|
| X-Content-Type-Options | nosniff | 防止MIME嗅探 |
| X-Frame-Options | DENY | 防止点击劫持 |
| X-XSS-Protection | 1; mode=block | XSS防护 |
| Content-Security-Policy | default-src 'self' | CSP策略 |
| Strict-Transport-Security | max-age=31536000 | HSTS (HTTPS时) |

### 5. 日志系统 (Logging)

**位置**: `backend/core/logging_config.py`

**双格式输出**:
- `logs/xuangu.json` - JSON格式 (适合日志聚合工具)
- `logs/xuangu.log` - 人类可读格式
- **选股专用日志** - 结构化选股任务日志

**日志轮转**: 10MB/文件, 5个备份

### 6. 告警服务 (Alert)

**位置**: `backend/services/alert_service.py`

**告警规则**:

| 规则 | 阈值 | 冷却时间 |
|------|------|---------|
| 高错误率 | > 5% | 5分钟 |
| 高响应时间 | P95 > 2000ms | 5分钟 |
| API不可用 | 健康检查失败 | 1分钟 |

**通知渠道**: 飞书 Webhook

### 7. 认证系统 (Auth)

**位置**: `backend/auth/`

**技术**: JWT (python-jose + passlib)

**功能**: 注册、登录、Token验证

### 8. 数据持久化 (Data Persistence)

**位置**: `backend/models/`

**数据库表**:

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| `selection_record` | 选股记录 | id, trade_date, total_count, status, execution_time |
| `selected_stock` | 股票详情 | id, record_id, ts_code, name, close_price, change_pct, pre_change_pct, open_change_pct, touch_days, limit_up_days, seal_rate |
| `stock_daily_data` | 日线数据 | id, ts_code, trade_date, open, high, low, close, up_limit, adj_factor |
| `seal_rate_cache` | 封板率缓存 | id, ts_code, trade_date, period_days, touch_days, limit_up_days, seal_rate |
| `task_log` | 任务日志 | id, task_type, status, error_message |
| `system_config` | 系统配置 | key, value, value_type |
| `scheduled_task` | 定时任务 | id, name, cron_expression, enabled |

**数据库优化**:
- SQLite: WAL模式, 64MB缓存, 外键约束
- PostgreSQL: QueuePool连接池 (pool_size=5, max_overflow=10)

---

## 数据流

### 三阶段选股流程

```
用户触发选股 (API / WebSocket)
    ↓
API: POST /api/v1/stock/select
    ↓
┌─────────────────── 阶段1: 选股 ───────────────────┐
│ SelectionTask.build_query()                        │
│ → 组合多个 SelectionCondition                      │
│ → 构建自然语言查询语句                               │
│                                                     │
│ TdxSelectorService.select()                         │
│ → 调用通达信MCP接口 (JSON-RPC协议)                  │
│ → 解析返回数据 (parse_tdx_response)                │
│ → 返回 TdxStockResult 列表                          │
│                                                     │
│ ⚠️ 注意：数值格式必须使用整数 (4%而非4.0%)         │
│ ⚠️ 严禁调用Tushare接口                              │
└────────────────────────────────────────────────────┘
    ↓
┌─────────────────── 阶段2: 分析 ───────────────────┐
│ TushareDataCollector                               │
│ → 仅对阶段1选出的股票查询                            │
│ → get_daily_basic(): PE/PB/市值/换手率             │
│ → get_daily_data(): 计算昨涨幅、开涨幅              │
│ → 构建 analysis_data 字典                          │
│                                                     │
│ ⚠️ 严禁调用通达信MCP接口                            │
└────────────────────────────────────────────────────┘
    ↓
┌─────────────────── 阶段3: 封板率 ──────────────────┐
│ SealRateCalculator                                 │
│ → 获取交易日列表                                    │
│ → 获取并缓存前复权日线数据                          │
│ → 计算触板天数、封板天数、封板率                     │
│ → 可选：按封板率阈值过滤                            │
│ → 缓存计算结果到数据库                              │
│                                                     │
│ ⚠️ 严禁调用通达信MCP接口                            │
└────────────────────────────────────────────────────┘
    ↓
_merge_results(): 合并三阶段数据
    ↓
┌─────────────────── 结果处理 ────────────────────┐
│ save_selection_result(): 保存到数据库              │
│ FeishuNotifier: 发送飞书通知                      │
│ push_stock_selection_update(): WebSocket实时推送   │
└────────────────────────────────────────────────────┘
    ↓
API Response: 返回完整结果
{
  trade_date,
  total_count,
  passed_count,
  stocks [...],
  phase1: { phase, source, success, execution_time },
  phase2: { phase, source, success, execution_time },
  phase3: { phase, source, success, execution_time },
  execution_time
}
```

---

## 配置管理

### 环境变量 (.env)

```bash
# Tushare API Token (阶段2、3使用)
TUSHARE_TOKEN=your_token_here

# 通达信MCP配置
TDX_MCP_ENABLED=true
TDX_MCP_URL=https://mcp.tdx.com.cn:3001/mcp
TDX_MCP_API_KEY=your_api_key_here

# 飞书 Webhook URL (通知+告警)
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 数据库路径
DATABASE_URL=sqlite:///./data/xuangu.db

# JWT 密钥
SECRET_KEY=your_secret_key_here

# 服务配置
HOST=0.0.0.0
PORT=9999
LOG_LEVEL=INFO
LOG_DIR=logs

# CORS 配置
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:8081,http://localhost:3000
```

### 选股策略配置

| Key | 默认值 | 说明 |
|-----|--------|------|
| `max_circ_mv` | 2000 | 最大流通市值 (亿) |
| `max_close_price` | 500 | 最大收盘价 (元) |
| `min_limit_count` | 3 | 最小涨停次数 |
| `min_seal_rate` | 90 | 最小封板率 (%) |
| `period_days` | 100 | 封板率计算周期 (交易日) |
| `call_auction_ratio_min` | 4 | 竞昨比最小值 (%) |
| `call_auction_ratio_max` | 30 | 竞昨比最大值 (%) |
| `turnover_rate_min` | 0.5 | 竞价换手率最小值 (%) |
| `turnover_rate_max` | 10 | 竞价换手率最大值 (%) |
| `notification_enabled` | true | 是否启用通知 |

---

## 部署架构

### 直接部署 (Supervisor + Nginx)

**后端进程管理**: Supervisor

```ini
[program:xuangu-backend]
command=/opt/xuangu/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 9999 --workers 4
directory=/opt/xuangu
user=www-data
autostart=true
autorestart=true
stdout_logfile=/opt/xuangu/logs/supervisor.log
```

**反向代理**: Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        root /opt/xuangu/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:9999;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /ws {
        proxy_pass http://127.0.0.1:9999;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    location /metrics {
        allow 127.0.0.1;
        deny all;
        proxy_pass http://127.0.0.1:9999;
    }
}
```

---

## 开发进度

### ✅ Phase 1: MVP版本 - 已完成
### ✅ Phase 2: 测试体系建设 - 已完成
### ✅ Phase 3: 质量提升 - 已完成
### ✅ Phase 4: 生产就绪 - 已完成
- [x] JWT 认证系统
- [x] Prometheus + Grafana 监控
- [x] 日志聚合系统 + 告警服务
- [x] HTTPS 安全连接 + 安全头
- [x] 数据库连接池优化
- [x] 性能基准测试 (50用户, P95=7ms)
- [x] Docker 移除 → Supervisor + Nginx 直接部署

### ✅ Phase 5: 选股流程重构 - 已完成
- [x] 通达信MCP选股服务实现 (模块化条件 + 多任务)
- [x] MCP接口格式要求验证 (整数格式)
- [x] Tushare分析服务重构 (仅补充数据)
- [x] 两阶段流程集成 (严格分离)
- [x] WebSocket实时推送服务
- [x] 选股专用日志系统
- [x] 完整测试验证 (选出14只股票)

### ✅ Phase 6: 封板率计算 - 已完成
- [x] 封板率计算模块实现 (SealRateCalculator)
- [x] 前复权日线数据获取与缓存
- [x] 触板天数、封板天数、封板率计算
- [x] 三阶段选股流程集成
- [x] 昨涨幅、开涨幅计算
- [x] 前端界面更新 (Dashboard, StockResults, StrategyManage)
- [x] 数据库模型更新 (touch_days, limit_up_days, seal_rate)
- [x] 策略配置更新 (封板率阈值)

### 📋 Phase 7: 功能增强 - 规划中
- [ ] 提升测试覆盖率至 85%+
- [ ] 用户权限管理 (RBAC)
- [ ] 数据导出功能 (Excel/PDF)
- [ ] PostgreSQL 迁移
- [ ] Redis 缓存层
- [ ] 回测系统

### 后续阶段
- Phase 8: 量化模拟交易
- Phase 9: 智能分析增强 (AI辅助)

---

## 关键技术决策

### 为什么选择三阶段选股架构?

| 阶段 | 数据源 | 优势 |
|------|--------|------|
| 阶段1 | 通达信MCP | 服务端筛选，一次查询完成，效率极高 |
| 阶段2 | Tushare | 仅对选出的少量股票获取补充数据，减少API调用 |
| 阶段3 | Tushare | 基于前复权数据精确计算封板率，支持缓存 |

**严格分离原则**:
- 选股阶段不调用Tushare
- 分析阶段不调用通达信MCP
- 各阶段职责清晰，易于维护

### 为什么选择 WebSocket?
- **实时性**: 替代轮询，降低服务器压力
- **频道订阅**: 支持按类型分发消息
- **双向通信**: 支持心跳检测和状态同步
- **原生支持**: FastAPI 原生 WebSocket 支持

### 为什么选择 FastAPI?
- 高性能异步框架
- 自动生成 API 文档
- 类型提示支持
- 易于测试
- 原生 WebSocket 支持

---

## 接口说明

### RESTful API

#### 选股接口

**请求**:
```
POST /api/v1/stock/select
Content-Type: application/json

{
  "trade_date": "20260427",           // 可选，默认最新交易日
  "task_template": "default",         // default/conservative/aggressive
  "min_seal_rate": 90,                // 可选，封板率阈值(%)
  "period_days": 100,                 // 可选，封板率计算周期
  "notify": false                     // 是否发送通知
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "trade_date": "20260427",
    "total_count": 12,
    "passed_count": 10,
    "stocks": [
      {
        "ts_code": "002429.SZ",
        "name": "兆驰股份",
        "close": 11.79,
        "change_pct": -10.0,
        "pre_change_pct": 9.99,
        "open_change_pct": -10.0,
        "auction_ratio": 4.14,
        "auction_turnover_rate": 0.74,
        "limit_up_count": 7,
        "touch_days": 10,
        "limit_up_days": 7,
        "seal_rate": 70.0,
        "rise_10d_pct": 15.36
      }
    ],
    "phase1": {
      "phase": "选股",
      "source": "tdx_mcp",
      "success": true,
      "execution_time": 0.85
    },
    "phase2": {
      "phase": "分析",
      "source": "tushare",
      "success": true,
      "execution_time": 2.3
    },
    "phase3": {
      "phase": "封板率计算",
      "source": "tushare",
      "success": true,
      "execution_time": 3.5
    },
    "execution_time": 6.65,
    "record_id": 42
  }
}
```

#### WebSocket 接口

**连接**: `ws://localhost:9999/ws`

**消息格式 (客户端→服务端)**:
```json
{
  "type": "subscribe",      // subscribe/unsubscribe/ping
  "channel": "stocks"       // tasks/stocks/default
}
```

**消息格式 (服务端→客户端)**:
```json
{
  "type": "selection_completed",
  "record_id": 42,
  "trade_date": "20260427",
  "total_count": 10,
  "timestamp": "2026-04-27T09:30:00",
  "source": "stock_selector"
}
```

---

## 注意事项

### 通达信MCP接口使用
- 通过问小达MCP服务进行选股
- 使用JSON-RPC协议格式
- **数值格式要求**: 使用整数格式 (4%而非4.0%)
- 支持8个条件的复杂查询
- 响应时间 < 1秒
- 仅在阶段1使用

### 接口分离原则

| 阶段 | 允许调用 | 禁止调用 |
|------|----------|----------|
| 阶段1 (选股) | 通达信MCP | Tushare |
| 阶段2 (分析) | Tushare | 通达信MCP |
| 阶段3 (封板率) | Tushare | 通达信MCP |
| 准备阶段 | Tushare | - |

### Tushare API 使用
- 需要注册获取 Token
- 部分接口需要积分
- 有调用频率限制 (200 次/分钟)
- 仅在阶段2、3使用 (对少量股票补充数据)

### 飞书 Webhook
- 用于选股结果通知 + 告警通知
- 需要创建自定义机器人
- 支持富文本卡片消息

### WebSocket 连接管理
- 支持多频道订阅
- 自动断线清理
- 心跳检测保持活跃
- 广播消息到指定频道

---

## 性能基准

| 场景 | 指标 | 结果 | 状态 |
|------|------|------|------|
| API 响应时间 (P95) | < 2000ms | 7ms | ✅ 远超目标 |
| 并发用户数 | >= 50 用户 | 50+ 用户 | ✅ 达标 |
| 压力测试错误率 | < 1% | 0% | ✅ 完美 |
| 选股阶段1耗时 | < 2秒 | < 1秒 | ✅ 达标 |
| 选股阶段2耗时 | < 5秒 | < 3秒 | ✅ 达标 |
| 选股阶段3耗时 | < 10秒 | < 5秒 | ✅ 达标 |
| 选股总耗时 | < 30秒 | < 10秒 | ✅ 远超目标 |
| 测试通过率 | > 75% | 93.5% | ✅ 超额 |
| 代码覆盖率 | > 80% | 81% | ✅ 达标 |

---

## 开发规范

### 代码规范

**Python 代码规范**
- **Style Guide**: PEP 8
- **Formatter**: Black (line-length=100)
- **Type Hints**: 必须添加类型注解
- **Docstring**: Google Style

**JavaScript/Vue 代码规范**
- **Style Guide**: Vue Official Style Guide
- **Formatter**: Prettier
- **Naming**: camelCase for variables, PascalCase for components

**数据库规范**
- **Table Naming**: snake_case (如: `selection_record`)
- **Column Naming**: snake_case (如: `trade_date`)
- **Timestamps**: `created_at`, `updated_at` (DATETIME)

**API 规范**
- **URL Naming**: kebab-case (如: `/api/v1/stock-results`)
- **HTTP Methods**: GET (查询), POST (创建), PUT (更新), DELETE (删除)
- **Response Format**: 统一 JSON 格式

### 提交规范
遵循 Conventional Commits:

```
<type>(<scope>): <subject>

类型: feat(新功能) | fix(修复) | docs(文档) | refactor(重构) | test(测试)
```

**示例**:
```
feat(strategy): 实现涨停强度策略
fix(mcp): 修复数值格式问题
```

### 开发流程

**1. 环境准备**
- 后端: `pip install -r requirements.txt`
- 前端: `cd frontend && npm install`

**2. 开发服务器**
- 后端: `uvicorn backend.main:app --reload --host 0.0.0.0 --port 9999`
- 前端: `npm run dev`

**3. 测试**
- 运行所有测试: `pytest tests/ -v --cov=backend`
- 代码格式化: `black backend/ tests/`
- 类型检查: `mypy backend/`

---

**Last Updated**: 2026-04-27  
**Maintainer**: AI Assistant  
**Version**: 3.0
