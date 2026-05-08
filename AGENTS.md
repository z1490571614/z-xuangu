# AGENTS.md - 选股通知系统架构文档

## 项目概述

| 属性 | 值 |
|------|-----|
| **项目名称** | 选股通知系统(Stock Selector Notification System) |
| **版本** | v5.0 |
| **状态** | 评分系统V3 + AI综合概览 + 异动解读 + 龙虎榜 + 风险拆解 + 情感分析已完成 ✅ |
| **最后更新** | 2026-04-30 |

---

## 本项目专属开发规则

### 1. 优选复用、次选改造、末选新建

**每新增一个功能模块前，必须优先检查现有系统是否已有可复用的数据源或服务。**

```python
# ✅ 正确做法（优先复用）
from backend.services.integrated_news_service import get_integrated_news_service
from backend.services.lhb_service import analyze_lhb
from backend.services.sentiment_analyzer import SentimentAnalyzer

# ❌ 错误做法（自建新数据源）
自行调用 Tushare API 获取新闻  # 新闻已有 integrated_news_service
自行计算情感                  # 情感已有 SentimentAnalyzer
自行拉取龙虎榜席位数据          # 龙虎榜已有 lhb_service
```

**复用检查清单**（新增模块前逐一核对）:
- [ ] 行情数据 → `selected_stock` 表已有（change_pct, limit_up_days, rise_10d_pct 等）
- [ ] 新闻数据 → `integrated_news_service` 已有（从新闻数据库读取）
- [ ] 情感分析 → `SentimentAnalyzer` 已有（加权评分规则引擎）
- [ ] 龙虎榜数据 → `lhb_service` 已有（top_list + top_inst + hm_list）
- [ ] 实时行情 → `data_collector.get_realtime_quotes()` 已有（通达信行情API）
- [ ] 交易日 → `trading_date` 工具已有
- [ ] 数据库会话 → `SessionLocal` 已有

### 2. 数据源复用维度 > API直连维度

**后端模块优先通过现有 Service 获取数据，而非直接调用 Tushare/外部 API。**

```
外层模块
  ↓ 调用 Service 方法（复用）
内部 Service
  ↓ 调用 Tushare/外部 API（直连）
```

**正向示例（风险拆解模块）**:
- 公告风险 → 复用 `integrated_news_service`（新闻查询接口）
- 舆情风险 → 复用 `SentimentAnalyzer`（情感分析引擎）
- 龙虎风险 → 复用 `lhb_service.analyze_lhb()`（龙虎榜服务）

**反向示例（绝不这样做）**:
- 在风险拆解中重新调 Tushare 接口拉新闻 → ❌ 应复用新闻服务
- 在异动解读中自己分析情感 → ❌ 应复用情感分析引擎

### 3. 查询时实时计算 > 入库时预计算

**情感分析、标签匹配等纯规则计算，优先在查询时实时执行，不在入库时写入。**

| 方案 | 优点 | 缺点 |
|------|------|------|
| 入库时预计算 | 查询时无需计算 | 规则更新需回填，DB 存冗余字段 |
| **查询时实时计算** ✅ | **规则更新立即生效，无回填成本** | 查询增加毫秒级耗时 |

**适用范围**:
- ✅ 情感分析 → 查询时实时计算（`integrated_news_service` 中调用 `SentimentAnalyzer`）
- ✅ 游资别名匹配 → 查询时实时匹配（`hm_list` 缓存 + 子串匹配）
- ❌ 龙虎榜原始数据 → 入库永久存储（`stock_lhb` 表），避免重复调用 Tushare
- ❌ 风险拆解结果 → 入库永久存储（`stock_risk_breakdown` 表），避免重复采集

### 4. 纯规则 > AI > 硬编码

**决策类逻辑优先使用可解释的纯规则，其次使用 AI，最后才用硬编码常量。**

| 方案 | 可解释性 | 维护成本 | 适用场景 |
|------|---------|---------|---------|
| 纯规则 ✅ | 高 | 低 | 情感分析、席位标签、行为判定、风险评分 |
| AI ⚠️ | 中 | 中 | 综合概览、异动解读（语言组织类） |
| 硬编码 ❌ | 低 | 高 | 极少使用，仅用于固定映射 |

### 5. 预加载不阻塞主流程

**选股完成后，AI 概览、龙虎榜、风险拆解等耗时操作在后台线程池中预热，不阻塞选股响应。**

```python
# ✅ ThreadPoolExecutor 非阻塞预热
pool = ThreadPoolExecutor(max_workers=5)
pool.submit(_warm_one, stock)
pool.shutdown(wait=False)

# ❌ 严禁在主线程同步调用
analyze_lhb(ts_code)  # 堵塞选股返回
```

**预加载的三类数据及其状态管理**:

| 模块 | 预热时机 | 预热失败影响 |
|------|---------|------------|
| AI概览 + 异动解读 | 选股后后台 | 用户点 Tab 时实时生成（降级） |
| 龙虎榜 | 选股后后台 | 用户点 Tab 时首次调 API |
| 风险拆解 | 选股后后台 | 用户点 Tab 时首次计算 |

### 6. 数据源缺失时降级而非阻断

**当某个数据源不可用（Tushare 积分不足、接口超时等），该维度降级为 0 分或显示"暂无数据"，不影响其他维度和整体功能。**

```python
# ✅ 降级模式
try:
    df = self.pro.cyq_perf(...)
    if df is not None: ...
except Exception:
    return 0, []  # 降级为0分

# ❌ 严禁抛出异常导致整个模块崩溃
```

### 7. 前端组件三态全覆盖

**每个 Tab 组件必须覆盖 loading / error / empty 三种状态，缺一不可。**

```
loading  → 骨架屏或加载提示
error    → 错误信息 + 重试按钮
empty    → 无数据提示（区分"功能未配置"和"数据为空"）
```

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
│              Vue 3 + Vue Router + WebSocket + ECharts       │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS (Nginx反向代理)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Nginx反向代理                            │
│  / → 前端静态文件    /api/ → 后端服务   /ws → WebSocket     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI后端服务(Port: 9999)                 │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │  API路由  │ │ 选股引擎 │ │ 任务调度 │ │ 实时通信 │       │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
│       │            │            │            │              │
│  ┌────▼───────────────────────────────────────────────────┐  │
│  │                   业务逻辑层                            │  │
│  │  • TdxSelectorService (阶段1: MCP选股)                │  │
│  │  • TdxLocalSelector (阶段1: 本地选股备选)              │  │
│  │  • StockSelectorService (四阶段协调)                   │  │
│  │  • TushareDataCollector (阶段2: 分析)                  │  │
│  │  • SealRateCalculator (阶段3: 封板率计算)               │  │
│  │  • ScoringV2Service (阶段4: 评分系统V3)                │  │
│  │  • AlphaScoreService (Alpha评分)                       │  │
│  │  • DecisionEngine (决策引擎)                           │  │
│  │  • AiBriefService (AI综合概览)                         │  │
│  │  • AnomalyInterpreterService (异动解读)                │  │
│  │  • SentimentAnalyzer (新闻情感分析)                     │  │
│  │  • LhbService (龙虎榜数据采集+分析)                     │  │
│  │  • RiskBreakdownService (风险拆解)                     │  │
│  │  • StrategyService (策略服务)                          │  │
│  │  • ConnectionManager (WebSocket连接管理)               │  │
│  │  • TaskScheduler (任务调度)                            │  │
│  │  • FeishuNotifier (飞书通知)                           │  │
│  │  • AlertService (告警服务)                            │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │                    数据访问层                          │  │
│  │  • SQLAlchemy ORM (连接池优化)                        │  │
│  │  • SQLite WAL模式                                     │  │
│  └──────────────────────┬───────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┬───────────────┐
          ▼               ▼               ▼               ▼
┌────────────────┐  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐
│  SQLite数据库 │  │  通达信MCP    │  │  Tushare Pro  │  │  Doubao/OpenAI   │
│  (WAL模式)    │  │  (阶段1选股)  │  │  (阶段2+3)    │  │  (AI综合概览)    │
└────────────────┘  └──────────────┘  └───────────────┘  └──────────────────┘
          │
          └───────────────────┬────────────────────────────────┐
                              ▼                                ▼
                    ┌─────────────────────┐        ┌──────────────────────┐
                    │      飞书Webhook      │        │    通达信行情API     │
                    │  (通知+告警)           │        │   (实时行情/竞价)   │
                    └─────────────────────┘        └──────────────────────┘
```

---

## 核心模块说明

### 1. 四阶段选股引擎(评分系统V3并入后)

#### 阶段1: 通达信MCP选股服务

**位置**: `backend/services/tdx_selector.py` + `backend/services/tdx_mcp_client.py`

**备选方案**: `backend/services/tdx_local_selector.py` (本地选股备选)

**核心优势**:
- ✅ 支持8个条件的复杂查询
- ✅ 服务端筛选,效率极高(<1秒响应)
- ✅ 模块化条件架构,支持灵活组合
- ✅ 一次查询完成所有筛选条件
- ✅ 本地选股备选方案,提高系统可靠性

**选股条件配置**:
```
基本筛选: 非ST、非停牌、非北交所
市值条件: 流通市值 < 2000亿
价格条件: 收盘价 < 500元
趋势条件: 近10日股价上涨
涨停条件: 近100日涨停 ≥3次
竞价条件: 竞昨比4%-30%,换手率0.5%-10%
```

**⚠️ 重要: MCP接口格式要求**:
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
| `TdxLocalSelector` | 本地选股备选服务 | `select()` |

#### 阶段2: Tushare补充分析服务

**位置**: `backend/services/data_collector.py`

**功能**: 对选出的股票获取补充分析数据

**核心方法**:

| 方法 | 功能 | 用途 |
|------|------|------|
| `get_daily_data()` | 获取日线行情 | K线分析、昨涨幅、开涨幅计算 |
| `get_daily_basic()` | 获取每日指标 | PE/PB/市值 |
| `get_limit_list()` | 获取涨跌停数据 | 涨停详情 |
| `is_trading_day()` | 判断交易日 | 调度判断 |
| `get_latest_trading_date()` | 获取最新交易日 | 自动日期获取 |

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

#### 阶段4: 评分系统V3服务

**位置**: `backend/services/scoring_v2/` 目录

**模块架构**:
```
scoring_v2/
├── __init__.py
├── scoring_service.py        # 评分主服务
├── alpha_score_service.py    # Alpha评分(6维度)
├── risk_score_service.py     # 风险拆解(8维度)
├── final_score_service.py    # 最终评分融合
├── decision_engine.py        # 决策引擎(AI建议生成)
└── opening_plan.py           # 开盘预案生成
```

**Alpha评分维度**:
1. 交易价值: 历史相似形态胜率、冲高5%概率、盈亏比
2. 预期收益: 历史平均涨幅、最大涨幅、上涨空间
3. 流动性: 日均成交额、换手率、买卖盘深度
4. 板块地位: 板块涨幅排名、成交额占比、联动性
5. 事件驱动: 事件重要性、事件时效性、市场关注度
6. 市场环境: 大盘涨跌、市场情绪、赚钱效应

**决策引擎**:
- 生成AI建议(不关注/只观察/开盘确认/小仓试错/不参与)
- 仓位建议
- 止损止盈建议
- 关键观察点
- 取消条件

**数据模型**:
- `backend/models/scoring_v2/stock_score_v2.py`: 评分主表
- `backend/models/scoring_v2/stock_score_breakdown_v2.py`: 评分明细表
- `backend/models/scoring_v2/stock_risk_breakdown_v2.py`: 风险明细表

#### 四阶段协调器

**位置**: `backend/services/stock_selector.py`

**核心类**: `StockSelectorService`

**关键流程**:
```
select_stocks()
    ↓
_execute_phase1()  → TdxSelectorService.select()
    ↓ (成功)
_execute_phase2()  → TushareDataCollector (补充数据+昨涨幅/开涨幅)
    ↓
_execute_phase3()  → SealRateCalculator (封板率计算与过滤)
    ↓
_execute_phase4()  → ScoringV2Service (评分系统V3+AI综合概览+异动解读)
    ↓
_merge_results()   → 合并四阶段数据
    ↓
_build_final_result() → 返回最终结果
    ↓
后台预热（不阻塞主流程）:
  _trigger_ai_preheat()       → AI概览+异动解读
  _trigger_lhb_preheat()      → 龙虎榜数据
  _trigger_risk_preheat()     → 风险拆解
```

**策略模板**:

| 模板名称 | 创建函数 | 封板率阈值 | 适用场景 |
|---------|---------|-----------|---------|
| default | `create_default_task()` | ≥90% | 日常选股 |
| conservative | `create_conservative_task()` | ≥95% | 稳健投资 |
| aggressive | `create_aggressive_task()` | ≥80% | 激进交易 |

### 2. AI综合概览服务

**位置**: `backend/services/ai_brief/` 目录

**模块架构**:
```
ai_brief/
├── __init__.py
├── ai_client.py              # AI客户端接口
├── overview_brief_service.py # 综合概览主服务
├── overview_prompt_builder.py# 提示词构建器
├── output_validator.py       # 输出验证器
└── tag_builder.py            # 标签构建器
```

**定位**: 用户进入详情页的第一决策入口,纯AI汇总8个模块的结构化输出

**输入数据**:
- Alpha评分
- 风险拆解
- 规则评分(历史兼容)
- 异动解读
- 新闻舆情
- 龙虎榜
- 业绩排雷
- 开盘预案

**输出内容**:
1. AI简报(150-300字)
2. AI建议(不关注/只观察/开盘确认/小仓试错/不参与)
3. 建议原因
4. 正面标签(3-8个)
5. 负面标签(3-8个)
6. 核心要点(3-5条)
7. 免责声明

**数据模型**:
- `backend/models/overview_brief.py`: 综合概览数据表

**数据状态**:
- `available`: 正常可用
- `partial`: 部分数据可用
- `fallback_generated`: AI失败,使用本地模板降级
- `pending`: 生成中
- `ai_disabled`: AI功能未启用
- `ai_failed`: AI调用失败
- `invalid_output`: AI输出无效

**降级策略**: 当AI不可用时,使用本地规则生成fallback简报

**⚠️ 重要约束**:
- AI只做简报生成和语言组织,不参与核心评分计算
- 禁止AI编造输入中不存在的公告、财报、新闻
- 涨停、连板只能作为行情背景,不能作为核心原因
- AI输出必须经过验证,包含免责声明
- 禁止出现"必涨"、"确定机会"等保证性词汇

### 3. 异动解读服务(同花顺1:1复刻)

**位置**: `backend/services/anomaly_interpretation/interpreter_service.py`

**数据模型**:
- `backend/models/anomaly_interpretation.py`: 异动解读数据表

**定位**: 回答"市场可能在炒什么?",基于客观事实

**数据源**: 复用 `integrated_news_service`（从新闻数据库读取），非 Tushare API 直连

**解析范围**: 近3个交易日的个股新闻 + 行业新闻

**输出结构(完全对标同花顺)**:
1. 核心标签行(最多3个,用+连接,如"算力租赁+业绩暴增+高送转")
2. 行业原因(板块宏观驱动)
3. 公司原因(分点,最多4条,每条包含日期、事件、核心数据)
4. 行情背景(竞价价格、涨跌幅)
5. 免责声明

**⚠️ 核心规则**:
- 禁止技术面词汇(涨停、连板、竞价抢筹、短期涨幅大)作为核心原因
- 技术面词汇只能作为行情背景
- 核心原因必须来自公告、财报、行业新闻等基本面信息
- 公司原因必须包含日期、事件、核心数据

**数据状态**:
- `available`: 有明确催化
- `generated_from_market_only`: 仅行情生成,无明确催化
- `fetch_failed`: 数据获取失败
- `not_integrated`: 功能未接入

### 4. 新闻情感分析服务(SentimentAnalyzer)

**位置**: `backend/services/sentiment_analyzer.py`

**定位**: 基于规则引擎的股票新闻情感判断，在新闻查询时实时计算

**算法**: 加权评分制规则引擎

**利空/利好关键词库**:
- 业绩类: `净利润亏损`, `预亏`, `由盈转亏`, `业绩大幅下降`, `同比下降` → 利空 2.0
- 监管类: `立案调查`, `退市风险`, `行政处罚`, `监管函` → 利空 1.0~2.0
- 股东类: `大股东减持`, `质押爆仓`, `司法冻结` → 利空 1.0~2.0
- 业绩利好: `净利润大增`, `扭亏为盈`, `业绩超预期` → 利好 2.0
- 经营利好: `亏损收窄`, `减亏`, `中标`, `股份回购` → 利好 2.0
- 同比增长: `同比增长`, `同比大增` → 利好 1.5

**前置过滤规则**:
- 技术面词汇（涨停/连板/跌停）→ 直接 neutral
- 大盘/市场新闻（命中≥2个市场词）→ 直接 neutral
- 否定词检测（"不存在亏损"等）→ 权重 ×0.2

**调用时机**: 在 `integrated_news_service.get_stock_news_from_db()` 中实时分析，不入库

### 5. 龙虎榜服务(LhbService)

**位置**: `backend/services/lhb_service.py`

**数据模型**: `backend/models/stock_lhb.py`

**前端组件**: `frontend/src/components/stock/LhbPanel.vue`

**数据接口**（Tushare）:
| 接口 | 用途 | 最低积分 |
|------|------|---------|
| `top_list` | 龙虎榜每日明细（上榜日、涨幅、成交额、净买入） | 2000 |
| `top_inst` | 席位买卖明细（营业部、买入额、卖出额、净买额） | 5000 |
| `hm_list` | 游资名录（营业部→游资别名匹配） | 5000 |

**席位标签**: 20+条规则匹配，识别机构/北向/一线游资/核按钮/散户

**游资别名**: 调用 `hm_list` 接口建立营业部→游资反向映射，精确+子串双匹配

**行为判定**:
```
| 条件 | 标签 |
|------|------|
| 净买入>0 且 买入/卖出 > 1.8 | 一致抢筹 |
| 净买入>0 且 买入/卖出 > 1.2 | 温和抢筹 |
| \|净买入\| < 500万 | 主力分歧 |
| 净买入<0 且 卖出/买入 > 1.5 | 一致砸盘 |
```

**前端展示**: 总买/净买/总卖 红绿进度条 + 买入TOP5/卖出TOP5双栏席位（含游资别名）

**API接口**: `GET /api/v1/stock/detail/lhb`

### 6. 风险拆解服务(RiskBreakdownService)

**位置**: `backend/services/risk_breakdown_service.py`

**数据模型**: `backend/models/stock_risk.py`

**前端组件**: `frontend/src/components/stock/RiskBreakdown.vue`

**7大维度风险计算**（总分100分，纯规则，无AI）:

| 维度 | 权重 | 得分条件 | 数据源 |
|------|------|---------|--------|
| 行情风险 | 4分 | 昨日换手率>30%(+2)、昨日振幅>15%(+2) | `daily_basic` + `daily` |
| 筹码风险 | 18分 | 获利盘>80%(+10)、>60%(+5)；10日涨幅>30%(+5) | `cyq_perf` + `rise_10d_pct` |
| 公告风险 | 25分 | 减持(+10)、立案(+10)、亏损(+5)、问询(+5) | `integrated_news_service` |
| 资金风险 | 20分 | 净流出>5000万(+15)、>2000万(+8)；流入>5000万(-3) | `moneyflow` |
| 舆情风险 | 10分 | 利空≥3条(+10)、≥2条(+7)、≥1条(+4) | `SentimentAnalyzer` |
| 龙虎风险 | 13分 | 核按钮(+5)、净卖出>5000万(+5)、砸盘(+3) | `lhb_service` |
| 行业风险 | 10分 | 板块跌>3%(+10)、>1%(+5)；涨>3%(-3) | `ths_daily` |

**等级判定**: ≤20低 / ≤40中 / ≤70高 / >70极高

**API接口**: `GET /api/v1/stock/detail/risk`

### 7. 评分系统V2/V3服务(重构)

**位置**: `backend/api/score_v2.py`

**API接口列表**:

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v2/stock/score-v3/detail` | 评分V3详情(9个Tab整合) |
| GET | `/api/v2/stock/score-v3/overview` | 综合概览(Tab1) |
| GET | `/api/v2/stock/score-v3/alpha` | Alpha评分(Tab2) |
| GET | `/api/v2/stock/score-v3/risk` | 风险拆解(Tab3) |
| GET | `/api/v2/stock/score-v3/rule` | 规则评分(Tab4,历史兼容) |
| GET | `/api/v2/stock/score-v3/anomaly` | 异动解读(Tab5) |
| GET | `/api/v2/stock/score-v3/news` | 新闻舆情(Tab6) |
| GET | `/api/v2/stock/score-v3/dragon-tiger` | 龙虎榜(Tab7) |
| GET | `/api/v2/stock/score-v3/financial` | 业绩排雷(Tab8) |
| GET | `/api/v2/stock/score-v3/opening-plan` | 开盘预案(Tab9) |

### 8. WebSocket实时通信服务

**位置**: `backend/services/websocket_service.py`

**核心类**: `ConnectionManager`

**功能特性**:
- 多频道支持(tasks, stocks, default)
- 订阅/取消订阅机制
- 心跳检测(ping/pong)
- 消息广播到指定频道
- 断线自动清理

**WebSocket端点**:
- `WS /ws` - 主端点
- `GET /api/v1/ws/stats` - 连接统计

### 9. 策略服务

**位置**: `backend/services/strategy/` 目录

**模块架构**:
```
strategy/
├── __init__.py
├── base_strategy.py           # 策略基类
├── auction_activity_strategy.py  # 竞价活跃度策略
├── limit_up_strategy.py       # 涨停策略
├── market_cap_strategy.py     # 市值策略
├── price_strategy.py          # 价格策略
└── trend_strategy.py          # 趋势策略
```

**API接口**:
- `GET /api/v1/stock/strategies` - 获取策略列表
- `GET /api/v2/stock/strategy` - 策略API(V2)

### 10. 任务调度服务

**位置**: `backend/services/scheduler.py`

**功能**:
- 定时执行选股任务
- 任务日志记录
- 任务状态管理

**API接口**:
- `POST /api/v1/task/trigger` - 手动触发任务
- `GET /api/v1/task/logs` - 获取任务日志
- `GET /api/v1/task/status` - 获取任务状态

### 11. 新闻服务

**位置**: `backend/services/tushare_news.py` + `backend/services/integrated_news_service.py` + `backend/services/news_collector.py`

**数据架构**:
- `NewsCollector`: 定时采集财联社/cls 和同花顺/10jqka 新闻，写入 `news_data` 表
- `IntegratedNewsService`: 统一查询接口，优先读 DB，数据不足时触发采集
- `SentimentAnalyzer`: 查询时实时情感分析（不入库）

**API接口**:
- `GET /api/v1/stock/news-v2` - 新闻舆情查询
- `GET /api/v1/stock/news-v2/db-stats` - 新闻数据库统计

### 12. 监控系统

**Prometheus中间件**: `backend/middleware/prometheus_middleware.py`

**指标**:

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `http_requests_total` | Counter | 请求总数 |
| `http_request_duration_seconds` | Histogram | 请求延迟 |
| `http_requests_in_progress` | Gauge | 活跃请求数 |

### 13. 安全中间件

**位置**: `backend/middleware/security_middleware.py`

**安全响应头**:

| 头部 | 值 | 说明 |
|------|------|------|
| X-Content-Type-Options | nosniff | 防止MIME嗅探 |
| X-Frame-Options | DENY | 防止点击劫持 |
| X-XSS-Protection | 1; mode=block | XSS防护 |
| Content-Security-Policy | default-src 'self' | CSP策略 |
| Strict-Transport-Security | max-age=31536000 | HSTS(HTTPS时) |

### 14. 日志系统

**位置**: `backend/core/logging_config.py`

**双格式输出**:
- `logs/xuangu.json` - JSON格式(适合日志聚合工具)
- `logs/xuangu.log` - 人类可读格式
- **选股专用日志** - 结构化选股任务日志

**日志轮转**: 10MB/文件,5个备份

### 15. 告警服务

**位置**: `backend/services/alert_service.py`

**告警规则**:

| 规则 | 阈值 | 冷却时间 |
|------|------|---------|
| 高错误率 | >5% | 5分钟 |
| 高响应时间 | P95 >2000ms | 5分钟 |
| API不可用 | 健康检查失败 | 1分钟 |

**通知渠道**: 飞书Webhook

### 16. 认证系统

**位置**: `backend/auth/`

**技术**: JWT (python-jose + passlib)

**功能**: 注册、登录、Token验证

### 17. 配置服务

**位置**: `backend/services/config.py`

**功能**: 系统配置管理

**API接口**:
- `GET /api/v1/config/system` - 获取系统配置
- `PUT /api/v1/config/system` - 更新系统配置

### 18. 数据持久化

**位置**: `backend/models/`

**数据库表**:

| 表名 | 说明 | 状态 |
|------|------|------|
| `selection_record` | 选股记录 | ✅ |
| `selected_stock` | 股票详情 | ✅ |
| `stock_daily_data` | 日线数据缓存 | ✅ |
| `seal_rate_cache` | 封板率缓存 | ✅ |
| `stock_score_v2` | 评分V3主表 | ✅ |
| `stock_score_breakdown_v2` | 评分明细表 | ✅ |
| `stock_risk_breakdown_v2` | 风险明细表(旧评分) | ✅ |
| `overview_brief` | AI综合概览 | ✅ |
| `anomaly_interpretation` | 异动解读 | ✅ |
| `stock_lhb` | 龙虎榜数据 | ✅ 新增 |
| `stock_risk_breakdown` | 风险拆解(7维度新) | ✅ 新增 |
| `news_data` | 新闻数据库（独立） | ✅ |
| `strategy_template` | 策略模板 | ✅ |
| `scheduled_task` | 定时任务 | ✅ |
| `task_log` | 任务日志 | ✅ |
| `system_config` | 系统配置 | ✅ |
| `stock_feature_snapshot` | 特征快照 | ✅ |

**新增表说明**:

| 表名 | 位置 | 核心字段 |
|------|------|----------|
| `stock_lhb` | `backend/models/stock_lhb.py` | ts_code, trade_date, reason, change_pct, buy_amount, sell_amount, net_amount, main_type, action_tag, detail_json |
| `stock_risk_breakdown` | `backend/models/stock_risk.py` | ts_code, trade_date, total_score, risk_level, 7维度score+json, risk_summary, warning_tip |

**数据库优化**:
- SQLite: WAL模式,64MB缓存,外键约束
- PostgreSQL: QueuePool连接池(pool_size=5, max_overflow=10)

---

## 数据流

### 选股后后台预加载流程

```
select_stocks() 完成
    ↓
┌─── 非阻塞后台预热 ─────────────────────┐
│ ThreadPoolExecutor(max_workers=5)      │
│                                         │
│ _trigger_ai_preheat()                   │
│   ├── AiBriefService.generate()         │
│   └── AnomalyInterpretationService()    │
│                                         │
│ _trigger_lhb_preheat()                  │
│   └── analyze_lhb() → top_list +        │
│        top_inst + hm_list               │
│        → 写入 stock_lhb 表              │
│                                         │
│ _trigger_risk_preheat()                 │
│   └── calculate_risk()                  │
│        → 7维度并行采集                  │
│        → 写入 stock_risk_breakdown 表   │
└─────────────────────────────────────────┘
    ↓
用户点个股详情 → 详情页 Tab
    └── 读 DB 缓存 → ~20ms 秒开
```

### 新闻情感分析数据流

```
定时采集: NewsCollector
  ├── 财联社(cls) → NewsData 表（原始数据，无情感标签）
  └── 同花顺(10jqka) → NewsData 表

查询时: IntegratedNewsService.get_stock_news()
  ├── 从 NewsData 表读取原始 title + content
  └── SentimentAnalyzer.analyze(title, content) → 实时情感标签
       ├── 前置过滤（技术面词/大盘新闻）
       ├── 利空关键词匹配 → 累加负分
       ├── 利好关键词匹配 → 累加正分
       └── 加权判定 → positive / negative / neutral
```

### 龙虎榜数据流

```
用户请求: GET /api/v1/stock/detail/lhb?ts_code=xxx
    ↓
analyze_lhb(ts_code, force_refresh=False)
    ↓
┌── 优先从 DB 读取 ─────┐
│ stock_lhb 表有缓存？   │──→ 返回缓存数据（~20ms）
└──────┬─────否──────────┘
       ↓
从 Tushare 拉取:
  1. top_list(trade_date, ts_code) → 上榜基础数据
  2. top_inst(trade_date, ts_code) → 席位明细
  3. hm_list() → 游资别名映射（首次调用后缓存）
       ↓
  席位标签匹配 + 行为判定 + 游资别名匹配
       ↓
  写入 stock_lhb 表（永久存储）
       ↓
  返回结果
```

### 风险拆解数据流

```
用户请求: GET /api/v1/stock/detail/risk?ts_code=xxx&trade_date=yyy
    ↓
calculate_risk(ts_code, trade_date, force_refresh=False)
    ↓
┌── 优先从 DB 读取 ─────────────┐
│ stock_risk_breakdown 表有缓存？ │──→ 返回缓存数据
└──────┬─────否──────────────────┘
       ↓
并行采集7维度数据:
  ├── 行情: daily_basic(turnover_rate) + daily(high/low)
  ├── 筹码: cyq_perf(winner_rate) + selected_stock(rise_10d_pct)
  ├── 公告: integrated_news_service → 关键词匹配
  ├── 资金: moneyflow(net_mf_amount)
  ├── 舆情: SentimentAnalyzer → 利空计数
  ├── 龙虎: lhb_service → risk_tips/action_tag
  └── 行业: ths_daily(板块行情)
       ↓
  加权计算 → total_score + risk_level + risk_summary + warning_tip
       ↓
  写入 stock_risk_breakdown 表
       ↓
  返回结果
```

---

## 配置管理

### 环境变量(.env)

```bash
# Tushare API Token (阶段2、3使用)
TUSHARE_TOKEN=your_token_here

# 通达信MCP配置
TDX_MCP_ENABLED=true
TDX_MCP_URL=https://mcp.tdx.com.cn:3001/mcp
TDX_MCP_API_KEY=your_api_key_here

# 飞书Webhook URL (通知+告警)
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# AI综合概览配置(可选)
DOUBAO_API_KEY=your_doubao_api_key_here
DOUBAO_MODEL=doubao-pro-32k
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
AI_BRIEF_ENABLED=true
AI_BRIEF_TIMEOUT=10

# 数据库路径
DATABASE_URL=sqlite:///./data/xuangu.db

# JWT密钥
SECRET_KEY=your_secret_key_here

# 服务配置
HOST=0.0.0.0
PORT=9999
LOG_LEVEL=INFO
LOG_DIR=logs

# CORS配置
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:8081,http://localhost:3000
```

### 选股策略配置

| Key | 默认值 | 说明 |
|-----|--------|------|
| `max_circ_mv` | 2000 | 最大流通市值(亿) |
| `max_close_price` | 500 | 最大收盘价(元) |
| `min_limit_count` | 3 | 最小涨停次数 |
| `min_seal_rate` | 90 | 最小封板率(%) |
| `period_days` | 100 | 封板率计算周期(交易日) |
| `call_auction_ratio_min` | 4 | 竞昨比最小值(%) |
| `call_auction_ratio_max` | 30 | 竞昨比最大值(%) |
| `turnover_rate_min` | 0.5 | 竞价换手率最小值(%) |
| `turnover_rate_max` | 10 | 竞价换手率最大值(%) |
| `notification_enabled` | true | 是否启用通知 |

---

## 部署架构

### 直接部署(Supervisor + Nginx)

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

### Windows部署

参考文档: `WINDOWS_DEPLOYMENT_GUIDE.md`

快速启动: `python start_project.py`

快速停止: `python stop_project.py`

---

## 开发进度

### ✅ Phase 1: MVP版本 - 已完成
### ✅ Phase 2: 测试体系建设 - 已完成
### ✅ Phase 3: 质量提升 - 已完成
### ✅ Phase 4: 生产就绪 - 已完成
- [x] JWT认证系统
- [x] Prometheus + Grafana监控
- [x] 日志聚合系统 + 告警服务
- [x] HTTPS安全连接 + 安全头
- [x] 数据库连接池优化
- [x] 性能基准测试(50用户, P95=7ms)
- [x] Docker移除 → Supervisor + Nginx直接部署

### ✅ Phase 5: 选股流程重构 - 已完成
- [x] 通达信MCP选股服务实现(模块化条件+多任务)
- [x] MCP接口格式要求验证(整数格式)
- [x] Tushare分析服务重构(仅补充数据)
- [x] 两阶段流程集成(严格分离)
- [x] WebSocket实时推送服务
- [x] 选股专用日志系统
- [x] 完整测试验证(选出14只股票)
- [x] 本地选股备选方案(TdxLocalSelector)

### ✅ Phase 6: 封板率计算 - 已完成
- [x] 封板率计算模块实现(SealRateCalculator)
- [x] 前复权日线数据获取与缓存
- [x] 触板天数、封板天数、封板率计算
- [x] 三阶段选股流程集成
- [x] 昨涨幅、开涨幅计算
- [x] 前端界面更新(Dashboard, StockResults, StrategyManage)
- [x] 数据库模型更新(touch_days, limit_up_days, seal_rate)
- [x] 策略配置更新(封板率阈值)

### ✅ Phase 7: 评分系统V3 - 已完成
- [x] Alpha评分服务(6维度)
- [x] 风险拆解服务(8维度)
- [x] 决策引擎
- [x] 开盘预案生成
- [x] 评分数据模型重构
- [x] 历史评分对比
- [x] 评分可视化(ECharts)
- [x] 新旧评分系统兼容
- [x] 9个Tab模块重构

### ✅ Phase 8: AI综合概览 - 已完成
- [x] AI客户端接口设计
- [x] 豆包API集成
- [x] 提示词构建器
- [x] 输出验证器
- [x] 标签构建器
- [x] 综合概览服务
- [x] 数据模型设计
- [x] 降级策略实现
- [x] 前端界面更新

### ✅ Phase 9: 异动解读 - 已完成
- [x] 异动解读服务实现
- [x] 近3个交易日新闻筛选
- [x] 核心标签生成
- [x] 行业原因生成
- [x] 公司原因生成(分点+数据)
- [x] 数据模型设计
- [x] 前端界面更新(1:1复刻同花顺)
- [x] 数据源切换: Tushare API → 新闻数据库(integrated_news_service)
- [x] 提示词增强: 传完整content+情感标签

### ✅ Phase 10: 新闻情感分析 - 已完成
- [x] 加权评分制规则引擎(SentimentAnalyzer)
- [x] 利空/利好关键词库(80+条)
- [x] 前置过滤规则(技术面/大盘/否定词)
- [x] 关键词去重+分级权重+量化判定
- [x] 查询时实时计算(不入库)
- [x] 情感冲突消解(同一日期统一)
- [x] 同源新闻情感统一(财联社vs同花顺)
- [x] 集成到 integrated_news_service

### ✅ Phase 11: 龙虎榜模块 - 已完成
- [x] Tushare top_list/top_inst/hm_list 数据采集
- [x] 20+条席位标签规则(机构/北向/游资/核按钮/散户)
- [x] 游资别名匹配(hm_list反向映射)
- [x] 行为判定(抢筹/分歧/砸盘)
- [x] 数据库永久存储(stock_lhb)
- [x] 独立API端点(GET /api/v1/stock/detail/lhb)
- [x] 前端同花顺风格展示(总买/净买/总卖+进度条+双栏席位)
- [x] 游资别名席位下方展示
- [x] 历史上榜(近3次)
- [x] 风险提示(核按钮/分歧/散户接盘)
- [x] 选股后预加载

### ✅ Phase 12: 风险拆解模块 - 已完成
- [x] 7大维度量化风险(纯规则)
- [x] Tushare 5个接口数据接入(daily_basic/cyq_perf/moneyflow/ths_daily)
- [x] 复用3个已有模块(新闻/情感/龙虎)
- [x] 数据库永久存储(stock_risk_breakdown)
- [x] 独立API端点(GET /api/v1/stock/detail/risk)
- [x] 前端7维度列表+色条+高危预警
- [x] 选股后预加载
- [x] 权重优化: 行情4分(低权重提示) + 重点分配至公告25/资金20/筹码18

### 📋 Phase 13: 功能优化 - 进行中
- [ ] 提升测试覆盖率至85%+
- [ ] 用户权限管理(RBAC)
- [ ] 数据导出功能(Excel/PDF)
- [ ] PostgreSQL迁移
- [ ] Redis缓存层
- [ ] 回测系统
- [ ] 更多AI模型支持(通义千问、DeepSeek)

### 后续阶段
- Phase 14: 量化模拟交易
- Phase 15: 智能分析增强(更多AI能力)

---

## 关键技术决策

### 为什么选择四阶段选股架构?

| 阶段 | 数据源 | 优势 |
|------|--------|------|
| 阶段1 | 通达信MCP | 服务端筛选,一次查询完成,效率极高 |
| 阶段2 | Tushare | 仅对选出的少量股票获取补充数据,减少API调用 |
| 阶段3 | Tushare | 基于前复权数据精确计算封板率,支持缓存 |
| 阶段4 | 本地算法 + AI | 评分、AI分析在本地完成,可控性强 |

**严格分离原则**:
- 选股阶段不调用Tushare
- 分析阶段不调用通达信MCP
- AI只做简报生成,不参与核心评分
- 各阶段职责清晰,易于维护

### 为什么选择新闻数据库+实时情感分析?

| 决策 | 原因 |
|------|------|
| 独立新闻数据库 | 与主业务DB隔离，定时采集不阻塞选股 |
| 入库时不判断情感 | 保持原始数据纯净，情感规则可随时更新无需回填 |
| 查询时实时判断 | SentimentAnalyzer 纯规则引擎 <1ms/条，规则更新立即生效 |
| 情感冲突消解 | 同一股票同一日期的多条新闻情感统一，避免财联社/同花顺报道矛盾 |

### 为什么选择龙虎榜DB缓存+预加载?

| 决策 | 原因 |
|------|------|
| DB永久存储 | 历史龙虎榜可回溯，不依赖Tushare API |
| 选股后预加载 | 用户点详情页时直接读DB，~20ms秒开 |
| 游资标签纯规则 | 20+条基于席位名称的关键词匹配，准确率高，无API依赖 |
| 行为判定量化 | 净买入/买入卖出比率量化阈值，有明确的可解释性 |

### 为什么选择7维度风险拆解?

| 决策 | 原因 |
|------|------|
| 纯规则计算 | 无AI耗时，选股后预加载秒出 |
| 权重聚焦 | 行情仅4分(低权重提示)，重点分配至公告25/资金20/筹码18 |
| 复用已有模块 | 公告/舆情/龙虎 3个维度直接复用现有服务，零额外成本 |
| 数据源完整 | 15000积分覆盖全部Tushare接口，7个维度全部有真实数据 |

### 为什么选择WebSocket?

- **实时性**: 替代轮询,降低服务器压力
- **频道订阅**: 支持按类型分发消息
- **双向通信**: 支持心跳检测和状态同步
- **原生支持**: FastAPI原生WebSocket支持

### 为什么选择FastAPI?

- 高性能异步框架
- 自动生成API文档
- 类型提示支持
- 易于测试
- 原生WebSocket支持

---

## 接口说明

### RESTful API(V1)

#### 选股接口

**请求**:
```
POST /api/v1/stock/select
Content-Type: application/json

{
  "trade_date": "20260429",           // 可选,默认最新交易日
  "task_template": "default",         // default/conservative/aggressive
  "min_seal_rate": 90,                // 可选,封板率阈值(%)
  "period_days": 100,                 // 可选,封板率计算周期
  "notify": false,                    // 是否发送通知
  "enable_ai_brief": false,           // 是否启用AI综合概览(可选)
  "enable_anomaly": false             // 是否启用异动解读(可选)
}
```

**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "trade_date": "20260429",
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
        "rise_10d_pct": 15.36,
        "alpha_score": 63.5,
        "risk_score": 34.0,
        "final_score": 58.7,
        "score_grade": "C",
        "ai_suggestion": "只观察",
        "position_suggestion": "不参与"
      }
    ],
    "execution_time": 7.85,
    "record_id": 43
  }
}
```

#### 个股详情(V1)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/stock/detail?ts_code=xxx` | 个股综合详情(基本信息+评分+新闻+涨停+龙虎榜+业绩+预案) |
| GET | `/api/v1/stock/detail/lhb?ts_code=xxx` | 龙虎榜详情 |
| GET | `/api/v1/stock/detail/risk?ts_code=xxx` | 风险拆解(7维度) |
| GET | `/api/v1/stock/news-v2?ts_code=xxx` | 新闻舆情(含情感分析) |
| GET | `/api/v1/stock/anomaly-interpretation?ts_code=xxx` | 异动解读 |
| GET | `/api/v1/stock/overview-brief?ts_code=xxx` | AI综合概览 |

#### 龙虎榜接口

```
GET /api/v1/stock/detail/lhb?ts_code=600539.SH&trade_date=20260430&force_refresh=false
```

响应示例:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "data_status": "available",
    "trade_date": "20260430",
    "reason": "当日涨幅偏离值达7%",
    "change_pct": 10.02,
    "amount": 582000000,
    "turnover_rate": 15.32,
    "action_tag": "一致抢筹",
    "main_type": "游资主导",
    "buy_amount": 122000000,
    "sell_amount": 80000000,
    "net_amount": 42000000,
    "buy_top5": [
      {"exalter": "华泰证券深圳益田路", "buy": 122000000, "sell": 0, "net_buy": 122000000, "tag": "一线游资", "trader": "赵老哥"},
      {"exalter": "机构专用", "buy": 86000000, "sell": 12000000, "net_buy": 74000000, "tag": "机构", "trader": "机构专用"},
      {"exalter": "沪股通专用", "buy": 52000000, "sell": 0, "net_buy": 52000000, "tag": "北向", "trader": "深股通专用"}
    ],
    "sell_top5": [
      {"exalter": "长城证券仙桃钱沟路", "buy": 0, "sell": 31000000, "net_buy": -31000000, "tag": "核按钮", "trader": "zhouyu1933"},
      {"exalter": "东方财富证券拉萨团结路", "buy": 5000000, "sell": 26000000, "net_buy": -21000000, "tag": "散户", "trader": "T王"}
    ],
    "tags": ["一线游资抢筹", "机构净买入"],
    "risk_tips": ["核按钮席位卖出：长城证券仙桃钱沟路", "无核按钮砸盘风险"],
    "history": [
      {"trade_date": "20260428", "net_amount": 52000000, "action_tag": "一致抢筹", "change_pct": 10.02}
    ]
  }
}
```

#### 风险拆解接口

```
GET /api/v1/stock/detail/risk?ts_code=600539.SH&trade_date=20260430
```

响应示例:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "data_status": "available",
    "ts_code": "600539.SH",
    "trade_date": "20260430",
    "total_score": 78,
    "risk_level": "极高",
    "risk_summary": "风险极高，接力价值极低",
    "warning_tip": "高危预警：股东减持+核按钮砸盘",
    "market_score": 2,
    "chip_score": 15,
    "announcement_score": 25,
    "capital_score": 15,
    "sentiment_score": 7,
    "lhb_score": 10,
    "sector_score": 4,
    "market_tips": ["昨日换手率45.2%，筹码活跃度偏高"],
    "chip_tips": ["获利盘92.1%，抛压极大", "近10日涨幅35.2%，阶段高位"],
    "announcement_tips": ["股东发布减持计划"],
    "capital_tips": ["主力净流出6800万元"],
    "sentiment_tips": ["3条利空新闻，负面情绪较高"],
    "lhb_tips": ["核按钮席位卖出", "游资出货明显"],
    "sector_tips": ["所属板块下跌3.21%"],
    "history": [
      {"trade_date": "20260429", "total_score": 62, "risk_level": "高"},
      {"trade_date": "20260428", "total_score": 45, "risk_level": "中"}
    ]
  }
}
```

#### WebSocket接口

**连接**: `ws://localhost:9999/ws`

**消息格式(客户端→服务端)**:
```json
{
  "type": "subscribe",
  "channel": "stocks"
}
```

**消息格式(服务端→客户端)**:
```json
{
  "type": "selection_completed",
  "record_id": 43,
  "trade_date": "20260429",
  "total_count": 10,
  "timestamp": "2026-04-29T09:30:00",
  "source": "stock_selector"
}
```

---

## 注意事项

### 通达信MCP接口使用
- 通过问小达MCP服务进行选股
- 使用JSON-RPC协议格式
- **数值格式要求**: 使用整数格式(`4%`而非`4.0%`)
- 支持8个条件的复杂查询
- 响应时间<1秒
- 仅在阶段1使用
- 提供本地选股备选方案(TdxLocalSelector)

### 接口分离原则

| 阶段 | 允许调用 | 禁止调用 |
|------|----------|----------|
| 阶段1(选股) | 通达信MCP | Tushare |
| 阶段2(分析) | Tushare | 通达信MCP |
| 阶段3(封板率) | Tushare | 通达信MCP |
| 阶段4(评分) | 无外部调用,AI可选 | - |

### Tushare API使用
- 需要注册获取Token
- 部分接口需要积分
- 现有15000积分，覆盖所有接口
- top_list(2000) / top_inst(5000) / hm_list(5000) / moneyflow(2000) / daily_basic(2000) / cyq_perf(5000) / ths_daily(6000)
- 仅在阶段2、3使用(对少量股票补充数据)

### 龙虎榜使用注意事项
- 龙虎榜数据不保证当日所有上榜股票都能获取到数据
- `top_inst` 接口需要5000积分，积分不足时仅显示汇总数据
- `hm_list` 接口首次调用后缓存，重启后重新加载
- 游资别名匹配基于营业部名称子串匹配，可能存在少量误匹配
- DB缓存优先，强制刷新传 `force_refresh=true`

### 情感分析使用注意事项
- 纯规则引擎，不保证100%准确
- 规则更新后立刻生效，无需回填
- 大盘新闻和技术面新闻默认中性
- 情感冲突消解仅在同一天内生效

### 风险拆解使用注意事项
- 行情风险使用**昨日**换手率和振幅（非今日实时），低权重（4分）纯提示
- 筹码风险需要 `cyq_perf` 接口（5000积分），积分不足时降级为0分
- 行业风险需要 `ths_daily` 接口（6000积分）和行业→板块代码映射
- 公告风险通过新闻关键词匹配，非直接获取公告数据

### AI综合概览使用
- 需要配置豆包API Key(可选)
- AI只做语言组织,不参与核心评分计算
- 有完善的降级策略,AI不可用时系统仍可用
- AI输出必须经过验证,禁止编造数据
- 必须包含免责声明

### 异动解读使用
- 基于近3个交易日新闻
- 隔夜新闻优先级最高
- 禁止技术面词汇作为核心原因
- 公司原因必须包含日期、事件、核心数据

### 飞书Webhook
- 用于选股结果通知 + 告警通知
- 需要创建自定义机器人
- 支持富文本卡片消息

### WebSocket连接管理
- 支持多频道订阅
- 自动断线清理
- 心跳检测保持活跃
- 广播消息到指定频道

---

## 性能基准

| 场景 | 指标 | 结果 | 状态 |
|------|------|------|------|
| API响应时间(P95) | <2000ms | 7ms | ✅ 远超目标 |
| 并发支持 | ≥50用户 | 50+用户 | ✅ 达标 |
| 压力测试错误率 | <1% | 0% | ✅ 完美 |
| 选股阶段1耗时 | <2秒 | <1秒 | ✅ 达标 |
| 选股阶段2耗时 | <5秒 | <3秒 | ✅ 达标 |
| 选股阶段3耗时 | <10秒 | <5秒 | ✅ 达标 |
| 选股阶段4耗时 | <5秒 | <2秒 | ✅ 达标 |
| 选股总耗时 | <30秒 | <11秒 | ✅ 远超目标 |
| AI综合概览生成 | <10秒 | <3秒 | ✅ 达标 |
| 测试通过率 | >75% | 93.5% | ✅ 超额 |
| 代码覆盖率 | >80% | 81% | ✅ 达标 |
| 龙虎榜API响应(DB缓存) | - | ~20ms | ✅ |
| 龙虎榜API响应(首次拉取) | <30秒 | ~5秒 | ✅ |
| 风险拆解计算 | <5秒 | <2秒 | ✅ |
| 情感分析单条 | - | <1ms | ✅ |

---

## 开发规范

### 代码规范

**Python代码规范**
- **Style Guide**: PEP 8
- **Formatter**: Black (line-length=100)
- **Type Hints**: 必须添加类型注解
- **Docstring**: Google Style

**JavaScript/Vue代码规范**
- **Style Guide**: Vue Official Style Guide
- **Formatter**: Prettier
- **Naming**: camelCase for variables, PascalCase for components

**数据库规范**
- **Table Naming**: snake_case(如`selection_record`)
- **Column Naming**: snake_case(如`trade_date`)
- **Timestamps**: `created_at`, `updated_at` (DATETIME)

**API规范**
- **URL Naming**: kebab-case(如`/api/v1/stock-results`)
- **HTTP Methods**: GET(查询), POST(创建), PUT(更新), DELETE(删除)
- **Response Format**: 统一JSON格式

```json
{
  "code": 200,
  "message": "success",
  "data": {...},
  "timestamp": 1704300000
}
```

### 提交规范
遵循Conventional Commits:

```
<type>(<scope>): <subject>

类型: feat(新功能) | fix(修复) | docs(文档) | refactor(重构) | test(测试)
```

**示例**:
```
feat(lhb): 实现龙虎榜模块
feat(sentiment): 实现新闻情感分析引擎
feat(risk): 实现风险拆解模块
fix(lhb): 修复NaN序列化问题
fix(sentiment): 修复否定词检测逻辑
```

### 开发流程

**1. 环境准备**
- 后端: `pip install -r requirements.txt`
- 前端: `cd frontend && npm install`

**2. 开发服务器**
- 后端: `uvicorn backend.main:app --reload --host 0.0.0.0 --port 9999`
- 或使用快速启动脚本: `python start_project.py`
- 前端: `cd frontend && npm run dev`

**3. 测试**
- 运行所有测试: `pytest tests/backend/unit/ -v --cov=backend`
- 代码格式化: `black backend/ tests/`
- 类型检查: `mypy backend/`

**4. 快速脚本**
- `_test_*.py`: 快速测试各模块功能
- `_debug_*.py`: 调试各模块
- `_clear_cache.py`: 清除缓存数据
- `scripts/`: 各类脚本工具

---

## 相关文档

- `README.md`: 项目主文档
- `CLAUDE.md`: 开发指南
- `DEVELOP.md`: 开发文档
- `WINDOWS_DEPLOYMENT_GUIDE.md`: Windows部署指南
- `docs/DEPLOYMENT.md`: 部署文档
- `docs/评分系统技术文档.md`: 评分系统详细设计
- `docs/综合概览模块.md`: AI综合概览详细设计
- `docs/异动解读模块.md`: 异动解读详细设计
- `docs/评分系统重构.md`: 评分系统重构设计

---

**Last Updated**: 2026-04-30  
**Maintainer**: AI Assistant  
**Version**: 5.0
