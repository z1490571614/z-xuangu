# AGENTS.md - 选股通知系统架构文档

## 项目概述

| 属性 | 值 |
|------|-----|
| **项目名称** | 选股通知系统(Stock Selector Notification System) |
| **版本** | v6.0 |
| **状态** | 评分系统V3 + AI综合概览 + 异动解读 + 龙虎榜 + 风险拆解 + 龙头战法 + 板块动态别名 + 事件驱动情感分析 + 默认竞价接力三目标 + 模型中心已完成 ✅ |
| **最后更新** | 2026-05-17 |

---

## 本项目专属开发规则

### 1. 优选复用、次选改造、末选新建

**每新增一个功能模块前，必须优先检查现有系统是否已有可复用的数据源或服务。**

```python
# ✅ 正确做法（优先复用）
from backend.services.integrated_news_service import get_integrated_news_service
from backend.services.lhb_service import analyze_lhb
from backend.services.seat_library import is_premium_seat, is_knock_seat, is_scatter_seat
from backend.services.sentiment_analyzer import SentimentAnalyzer
from backend.services.news_sentiment.analyzer import analyze_news_event

# ❌ 错误做法（自建新数据源）
自行调用 Tushare API 获取新闻     # 新闻已有 integrated_news_service
自行判断席位类型                  # 席位已有 seat_library
自行分析情感                      # 情感已有 sentiment_analyzer/analyze_news_event
自行拉取龙虎榜席位数据             # 龙虎榜已有 lhb_service
```

**复用检查清单**（新增模块前逐一核对）:
- [ ] 行情数据 → `selected_stock` 表已有（change_pct, limit_up_days, rise_10d_pct 等）
- [ ] 新闻数据 → `integrated_news_service` 已有（从新闻数据库读取）
- [ ] 情感分析 → `SentimentAnalyzer`(V1) / `analyze_news_event`(V2) 已有
- [ ] 龙虎榜数据 → `lhb_service` 已有（top_list + top_inst + hm_list）
- [ ] 席位判断 → `seat_library` 已有（premium/knock/scatter/quant/inst）
- [ ] 实时行情 → `data_collector.get_realtime_quotes()` 已有（通达信行情API）
- [ ] 交易日 → `trading_date` 工具已有
- [ ] 数据库会话 → `SessionLocal` 已有
- [ ] 板块数据 → `dc_board_service` 已有（东财板块词典+动态别名）
- [ ] 龙头战法 → `dragon_leader` 已有（数据采集+评分+持久化）
- [ ] LightGBM模型 → `lightgbm_service` 已有（训练+预测+版本管理）

### 2. 数据源复用维度 > API直连维度

**后端模块优先通过现有 Service 获取数据，而非直接调用 Tushare/外部 API。**

```
外层模块
  ↓ 调用 Service 方法（复用）
内部 Service
  ↓ 调用 Tushare/外部 API（直连）
```

**正向示例（龙头战法模块）**:
- 龙虎榜数据 → 复用 `lhb_service.analyze_lhb()`
- 席位判断 → 复用 `seat_library`（is_premium_seat/is_knock_seat等）
- 新闻数据 → 复用 `integrated_news_service`
- 情感分析 → 复用 `news_sentiment.analyzer.analyze_news_event`(V2)
- 板块数据 → 复用 `dc_board_service` + `dc_board_alias_service`

**正向示例（风险拆解模块）**:
- 公告风险 → 复用 `integrated_news_service`（新闻查询接口）
- 舆情风险 → 复用 `SentimentAnalyzer`（情感分析引擎V1）
- 龙虎风险 → 复用 `lhb_service.analyze_lhb()` + `seat_library` 统一席位判断

**反向示例（绝不这样做）**:
- 在风险拆解中重新调 Tushare 接口拉新闻 → ❌ 应复用新闻服务
- 在龙虎榜Alpha中自己分类席位 → ❌ 应复用 `seat_library`
- 在异动解读中自己分析情感 → ❌ 应复用情感分析引擎

### 3. 查询时实时计算 > 入库时预计算

**情感分析、标签匹配、板块别名匹配等纯规则计算，优先在查询时或启动时实时执行。**

| 方案 | 优点 | 缺点 |
|------|------|------|
| 入库时预计算 | 查询时无需计算 | 规则更新需回填，DB 存冗余字段 |
| **查询时实时计算** ✅ | **规则更新立即生效，无回填成本** | 查询增加毫秒级耗时 |
| **启动时同步** ✅ | **启动后即生效，日常零延迟** | 仅启动时一次性开销 |

**适用范围**:
- ✅ 情感分析V1 → 查询时实时计算（`integrated_news_service` 中调用 `SentimentAnalyzer`）
- ✅ 情感分析V2 → 查询时实时计算（调用 `analyze_news_event`）
- ✅ 游资别名匹配 → 查询时实时匹配（`hm_list` 缓存 + 子串匹配）
- ✅ 板块动态别名 → 启动时同步+运行期读取内存（`dc_board_alias` 表 → `DcBoardService` 缓存）
- ❌ 龙虎榜原始数据 → 入库永久存储（`stock_lhb` 表），避免重复调用 Tushare
- ❌ 风险拆解结果 → 入库永久存储（`stock_risk_breakdown` 表），避免重复采集
- ❌ 龙头战法评分 → 入库永久存储（`dragon_leader_score` 表），避免重复计算

### 4. 纯规则 > AI > 硬编码

**决策类逻辑优先使用可解释的纯规则，其次使用 AI，最后才用硬编码常量。**

| 方案 | 可解释性 | 维护成本 | 适用场景 |
|------|---------|---------|---------|
| 纯规则 ✅ | 高 | 低 | 情感分析、席位标签、行为判定、风险评分、板块别名匹配 |
| AI ⚠️ | 中 | 中 | 综合概览、异动解读（语言组织类） |
| 硬编码 ❌ | 低 | 高 | 极少使用，仅用于固定映射 |

### 5. 预加载不阻塞主流程

**选股完成后，AI 概览、龙虎榜、风险拆解、龙头战法等耗时操作在后台线程池中预热，不阻塞选股响应。**

```python
# ✅ ThreadPoolExecutor 非阻塞预热
pool = ThreadPoolExecutor(max_workers=5)
pool.submit(_warm_one, stock)
pool.shutdown(wait=False)

# ❌ 严禁在主线程同步调用
analyze_lhb(ts_code)           # 堵塞选股返回
calculate_dragon_leader_score(ts_code) # 堵塞选股返回
```

**预加载的三类数据及其状态管理**:

| 模块 | 预热时机 | 预热失败影响 |
|------|---------|------------|
| AI概览 + 异动解读 | 选股后后台 | 用户点 Tab 时实时生成（降级） |
| 龙虎榜 | 选股后后台 | 用户点 Tab 时首次调 API |
| 风险拆解 | 选股后后台 | 用户点 Tab 时首次计算 |
| 龙头战法 | 选股后后台 | 用户点 Tab 时首次计算 |

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

### 8. 新增模块的席位判断必须经 seat_library

**所有需要判断席位类型（高溢价/核按钮/量化/机构/散户）的模块，必须通过 `backend/services/seat_library.py` 统一接口，禁止各模块自行维护席位关键词列表。**

```python
# ✅ 正确
from backend.services.seat_library import is_premium_seat, is_knock_seat, match_seat_tag

# ❌ 错误
SEAT_PREMIUM = ["相城大道", ...]  # 各模块自行维护列表
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
│  │  • SentimentAnalyzer (新闻情感分析V1)                   │  │
│  │  • news_sentiment模块 (事件驱动情感分析V2)              │  │
│  │  • LhbService (龙虎榜数据采集+分析)                     │  │
│  │  • seat_library (统一席位库 — 共用底层)                 │  │
│  │  • RiskBreakdownService (风险拆解)                     │  │
│  │  • DragonLeader (龙头战法评分)                          │  │
│  │  • DcBoardService (东财板块词典维护)                    │  │
│  │  • DcBoardAliasService (板块动态别名)                   │  │
│  │  • StockAliasService (股票别名服务)                     │  │
│  │  • ThsBoardService (同花顺板块词典)                     │  │
│  │  • StrategyService (策略服务)                          │  │
│  │  • LightGBMService (竞价模型训练+预测+版本管理)         │  │
│  │  • LeaderMainT0FeatureBuilder (特征工程+候选过滤)       │  │
│  │  • LeaderMainT0LabelBuilder (T+0标签生成)               │  │
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
│  (WAL模式)    │  │  (阶段1选股)  │  │  (阶段2+3+龙  │  │  (AI综合概览)    │
│               │  │               │  │   虎榜+板块)   │  │                  │
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

### 1. 四阶段选股引擎

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

#### 阶段4: 评分系统V3服务

**位置**: `backend/services/scoring_v2/` 目录

**模块架构**:
```
scoring_v2/
├── __init__.py
├── scoring_service.py        # 评分主服务
├── alpha_score_service.py    # Alpha评分(6维度)
├── risk_score_service.py     # 风险拆解(旧)
├── final_score_service.py    # 最终评分融合
├── decision_engine.py        # 决策引擎(AI建议生成)
└── opening_plan.py           # 开盘预案生成
```

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
  _trigger_dragon_leader_preheat() → 龙头战法评分
```

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
- 风险拆解(普通/龙头战法)
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

### 3. 异动解读服务(同花顺1:1复刻)

**位置**: `backend/services/anomaly_interpretation/interpreter_service.py`

**数据源**: 复用 `integrated_news_service`（从新闻数据库读取），非 Tushare API 直连

**解析范围**: 近3个交易日的个股新闻 + 行业新闻

**输出结构(完全对标同花顺)**:
1. 核心标签行(最多3个,用+连接,如"算力租赁+业绩暴增+高送转")
2. 行业原因(板块宏观驱动)
3. 公司原因(分点,最多4条,每条包含日期、事件、核心数据)
4. 行情背景(竞价价格、涨跌幅)
5. 免责声明

### 4. 新闻情感分析服务（双引擎）

#### 4.1 SentimentAnalyzer V1（加权评分规则引擎）

**位置**: `backend/services/sentiment_analyzer.py`

**算法**: 加权评分制规则引擎

**调用时机**: 在 `integrated_news_service.get_stock_news_from_db()` 中实时分析，不入库

#### 4.2 News Sentiment V2（事件驱动情感分析）

**位置**: `backend/services/news_sentiment/`

**定位**: 独立的纯规则事件驱动情感判定底层模块，不调用AI大模型，不绑定任何策略

**模块架构**:
```
news_sentiment/
├── __init__.py                # 公开接口
├── analyzer.py                # 主入口(analyze_news_event/analyze_news_batch)
├── normalizer.py              # 文本标准化
├── news_scope.py              # 新闻范围分类(单股/多股/市场综述)
├── event_classifier.py        # 事件分类器(9种事件类型)
├── fact_extractor.py          # 事实抽取(业绩/减持/增持/回购/合同/解禁)
├── scorer.py                  # 事件评分+多事件冲突合并
├── confidence.py              # 置信度计算
├── constants.py               # 常量定义(情感/事件类型/确定性因子)
├── aggregator.py              # 聚合器
└── rules/                     # 各事件类型专项规则
    ├── performance.py         # 业绩类
    ├── holding_change.py      # 股东变动(减持/增持)
    ├── buyback.py             # 回购
    ├── order_contract.py      # 合同中标
    ├── regulatory.py          # 监管处罚
    ├── restructure.py         # 重组
    └── process.py             # 诉讼/立案/停产
```

**核心流程**:
```
news_item → normalize_text → classify_news_scope
  ├── multi_stock/market_overview → 局部上下文判断（不归因给单股）
  └── single_stock → classify_event_candidates → select_primary_event
       → extract_facts → score_event（多事件评分）
       → merge_event_scores（冲突合并）
       → apply CERTAINTY_FACTOR（确定性因子 ×0.5~1.0）
       → 最终分数 [-5, +5]
       → sentiment + impact_level + confidence + risk_flags
```

**关键安全机制 — 新闻范围分类**: 多股盘面综述/大盘综述不归因为单股利好/利空。避免"板块内X只个股涨停"被误判为特定个股的重大利好。

**调用者**: `dragon_leader/main.py::collect_news()`, `stock_detail.py::get_stock_news()`

### 5. 统一席位库 (seat_library)

**位置**: `backend/services/seat_library.py`

**定位**: `lhb_service`、`risk_breakdown_service`、`dragon_leader/lhb_alpha` 的共用席位判断底层。禁止各模块自行维护席位关键词列表。

**席位标签体系**:

| 函数 | 标签 | 含义 | 代表席位 | 影响方向 |
|------|------|------|---------|---------|
| `is_premium_seat()` | 高溢价游资 | 顶级游资买入信号 | 相城大道、大连黄河路 | 利好(风险减分) |
| `is_institutional_seat()` | 机构/北向 | 机构资金参与 | 机构专用、沪股通 | 利好(风险减分) |
| `is_knock_seat()` | 核按钮 | 砸盘卖出信号 | 长城仙桃钱沟路 | 利空(风险加分) |
| `is_scatter_seat()` | 散户 | 散户集中营 | 东方财富拉萨系列 | 利空(风险加分) |
| `is_quant_seat()` | 量化 | 量化短线席位 | 华鑫上海分公司 | 利空(风险加分) |
| `match_seat_tag()` | 一线游资 | 知名游资席位(不含高溢价) | 华泰深圳益田路 | 中性偏多 |

**新增风险拆解方向判定** (v5.2): 席位判断不再只看"买榜/卖榜位置"，同时考虑净买卖方向：
- 高溢价席位净买入 → 风险抵扣（强势依据）
- 高溢价席位净卖出 → 风险增加
- 核按钮席位净买入 → 风险抵扣（强势依据）
- 核按钮席位净卖出 → 风险增加

### 6. 龙虎榜服务(LhbService)

**位置**: `backend/services/lhb_service.py`

**数据模型**: `backend/models/stock_lhb.py`

**前端组件**: `frontend/src/components/stock/LhbPanel.vue`

**席位标签依赖**: `backend/services/seat_library.py` 统一席位库

**数据接口**（Tushare）:
| 接口 | 用途 | 最低积分 |
|------|------|---------|
| `top_list` | 龙虎榜每日明细（上榜日、涨幅、成交额、净买入） | 2000 |
| `top_inst` | 席位买卖明细（营业部、买入额、卖出额、净买额） | 5000 |
| `hm_list` | 游资名录（营业部→游资别名匹配） | 5000 |

**行为判定**:
```
| 条件 | 标签 |
|------|------|
| 净买入>0 且 买入/卖出 > 1.8 | 一致抢筹 |
| 净买入>0 且 买入/卖出 > 1.2 | 温和抢筹 |
| |净买入| < 500万 | 主力分歧 |
| 净买入<0 且 卖出/买入 > 1.5 | 一致砸盘 |
```

### 7. 风险拆解服务(RiskBreakdownService)

**位置**: `backend/services/risk_breakdown_service.py`

**数据模型**: `backend/models/stock_risk.py` (StockRiskBreakdown + DragonLeaderScore)

**前端组件**: `frontend/src/components/stock/RiskBreakdown.vue` (支持普通/龙头战法双模式)

**7大维度风险计算**（总分100分，纯规则，无AI）:

| 维度 | 满分 | 得分条件 | 数据源 |
|------|------|---------|--------|
| 市场环境 | 10 | 昨日换手率>30% / 振幅>15% | `daily_basic` + `daily` |
| 筹码压力 | 14 | 获利盘>80%(+10)、>60%(+5)；10日涨幅>30%(+5) | `cyq_perf` + `rise_10d_pct` |
| 舆情与公告 | 18 | 减持(+10)、立案(+10)、亏损(+5)、问询(+5) | `integrated_news_service` |
| 个股资金 | 14 | 净流出>5000万(+15)、>2000万(+8)；流入>5000万(-3) | `moneyflow` |
| 龙虎风险 | 10 | 核按钮净卖出(+5)、高溢价净卖出(+3)、砸盘(+3) | `lhb_service` + `seat_library` |
| 板块与题材风险 | 18 | 板块跌>3%(+10)、>1%(+5)；涨>3%(-3)；主线板块上下文 | `ths_daily` + 东财板块 |
| 技术结构 | 16 | 炸板、竞价低预期等技术面风险 | 技术指标 |

**新增输出字段** (v5.2):
- `sector_context`: 主线板块上下文(板块名/涨跌/资金/涨停家数/强度)
- `strength_evidence`: 用户可见强势依据列表
- `risk_evidence`: 用户可见风险依据列表
- `lhb_strength_evidence`: 龙虎榜强势席位证据(内部)
- `lhb_risk_evidence`: 龙虎榜风险席位证据(内部)

**等级判定**: ≤20低 / ≤40中 / ≤70高 / >70极高

### 8. 龙头战法评分(DragonLeader)

**位置**: `backend/services/dragon_leader/`

**数据模型**: `backend/models/stock_risk.py::DragonLeaderScore`

**API接入**: `GET /api/v1/stock/detail/risk?strategy_type=dragon_leader`

**模块架构**:
```
dragon_leader/
├── __init__.py                 # 公开 calculate_dragon_leader_score
├── main.py                    # 主流程(数据采集+评分+持久化+缓存)
├── lhb_alpha.py               # 龙虎榜席位Alpha评分(复用seat_library)
├── output.py                  # 输出组装(等级/周期/证据/观察点)
├── config.yaml                # 权重配置
├── data/                      # 上下文采集器
│   ├── __init__.py
│   ├── stock_context.py       # 个股上下文(行情/筹码/资金/技术)
│   ├── market_context.py      # 市场上下文(大盘涨跌/市场情绪)
│   ├── theme_context.py       # 题材上下文(热点板块+语义引用)
│   ├── fundamental_context.py # 基本面上下文(财务/估值)
│   └── intraday_context.py    # 分时上下文(竞价/分时)
└── scorer/                     # 评分器
    ├── __init__.py
    ├── leader_scorer.py       # 龙头强度(7维×满分100)
    ├── retreat_scorer.py      # 退潮风险(7维×满分100)
    └── announcement_alpha.py  # 公告消息Alpha(使用news_sentiment V2)
```

**三核心分数**:

| 分数 | 满分 | 计算公式 |
|------|------|---------|
| 龙头强度 | 100 | 龙头地位25+题材强度20+情绪周期15+板块梯队15+承接强度10+竞价分时10+龙虎榜加成5 |
| 退潮风险 | 100 | 龙头地位动摇20+情绪退潮20+板块梯队断裂15+承接失败15+筹码兑现10+竞价低预期10+公告监管10 |
| 综合健康度 | 100 | 龙头强度×0.6 + 退潮风险×(-0.3) + 公告Alpha×0.5 + 龙虎榜Alpha×0.5 + 基准分20 |

**Alpha调整**:
- 公告Alpha: [-20, +20] — 复用 `news_sentiment` V2引擎
- 龙虎榜Alpha: [-20, +20] — 复用 `seat_library` 统一席位库

**等级体系**:
- 龙头等级: 极强龙头(≥85) / 强势龙头(≥70) / 疑似龙头(≥55) / 跟风强势股(≥40) / 非龙头
- 周期阶段: 主升期 / 分歧期 / 退潮期 / 混沌期 / 震荡期
- 健康等级: 龙头健康(≥80) / 强势可观察(≥65) / 分歧加大(≥50) / 退潮预警(≥35) / 回避

### 9. 东财板块词典与动态别名

#### 9.1 东财板块词典(DcBoardService)

**位置**: `backend/services/dc_board_service.py`

**数据模型**: `backend/models/board.py` (BoardIndex/StockBoardMember/BoardDailySnapshot/BoardStrengthSnapshot)

**功能**: 维护东财概念/行业/地域板块词典，个股-板块成分关系，板块强度快照

**别名合并**: 启动时从 `DcBoardAliasService.get_active_aliases()` 加载动态别名，与手写别名(`MANUAL_BOARD_ALIASES`)合并供全系统板块匹配使用

#### 9.2 东财板块动态别名(DcBoardAliasService)

**位置**: `backend/services/dc_board_alias_service.py`

**数据模型**: `backend/models/board.py` (DcBoardAlias/DcBoardAliasObservation/DcBoardAliasSyncState)

**定位**: 每个交易日从涨停池 `limit_list_ths` 抓取涨停标签(`lu_desc`)，匹配东财板块词典，自动建立板块别名映射

**核心流程**:
```
1. fetch_dc_boards → 获取东财板块词典（内存）
2. limit_list_ths(trade_date, limit_type="涨停池") → 获取涨停标签
3. split_lu_desc_tags → 按+号拆分标签
4. score_tag_board_match → 模糊匹配+语义相似度评分
5. 写入 dc_board_alias_observation（unique_key去重）
6. 汇总 dc_board_alias（更新hit_count/stock_count/confidence）
7. auto_approved(≥AUTO_SCORE_THRESHOLD) / pending_review(<阈值)
8. 清除 DcBoardService 共享缓存 → 下次读取生效
```

**别名审核状态**: auto_approved / pending_review / manual / reviewed / rejected

**启动同步**: `main.py::lifespan` 启动时同步最新交易日，盘后(15:30后)标记 finalized

#### 9.3 同花顺板块词典(ThsBoardService)

**位置**: `backend/services/ths_board_service.py`

**数据模型**: `backend/models/stock_ths_board.py` (ThsBoardIndex/StockThsBoardMember)

**定位**: 同花顺板块作为灰度兼容层，涨停标签仍由 `limit_list_ths` 提供

### 10. LightGBM竞价模型引擎

**位置**: `backend/services/model_engine/lightgbm_service.py`

**数据模型**: `backend/models/stock_feature_snapshot.py` (StockFeatureSnapshot + ModelVersion) + `backend/models/auction_backtest.py` (StockAuctionOpen + LeaderMainT0TrainingSample)

**模型文件**: `backend/models/*.pkl`

**前端展示**: `Dashboard.vue` (模型状态卡片) + `StockResults.vue` (T+0封板概率列)

**定位**: 基于LightGBM的竞价选股模型，提供T+0封板概率预测，集成至四阶段选股管线。

**双模型架构**:

| 属性 | `active_auction_lgbm` | `leader_main_t0_lgbm` |
|------|----------------------|----------------------|
| 用途 | 竞价活跃度综合评分 | 龙头股T+0封板概率 |
| 特征数 | 8维(limit_up_count_100d, seal_rate_100d, rise_10d_pct, pre_change_pct, open_change_pct, auction_turnover_rate, auction_ratio, circ_mv) | 9维(limit_up_streak, limit_up_count_100d, seal_rate_100d, rise_10d_pct, pre_change_pct, open_change_pct, auction_ratio, auction_turnover_rate, circ_mv) |
| 数据源 | StockFeatureSnapshot | LeaderMainT0TrainingSample |
| 影响final_score | ✅ 权重35% | ✅ 权重10% |
| 预测字段 | `model_score` | `t0_limit_success_prob` |
| 版本管理 | 文件名覆盖 | ModelVersion表(is_active标记) |

**训练管线**（`backtest.py` API + `lightgbm_service.py`）:
```
1. POST /backtest/auction/sync-range      → 同步集合竞价原始数据(stk_auction)
2. POST /backtest/tdx-local-daily/sync    → 同步通达信本地日线(.day文件→stock_daily_data)
3. POST /backtest/auction/recalculate-ratios → 从日线缓存重算auction_ratio
4. POST /backtest/leader-main-t0/build    → 特征构建(9维+规则过滤→LeaderMainT0TrainingSample)
5. POST /backtest/leader-main-t0/labels   → T+0标签生成(label_t0_limit_success)
6. POST /backtest/leader-main-t0/train    → 训练LGBMClassifier(70/20/10分割)
      或 POST /backtest/leader-main-t0/run → 一键执行全管线
```

**候选股过滤**（`leader_main_t0_feature_builder.py::DEFAULT_CONFIG`）:
| 条件 | 阈值 | 条件 | 阈值 |
|------|------|------|------|
| circ_mv | < 2000亿 | open_change_pct | >= -3% |
| prev_close | < 500元 | auction_ratio | 0.04~0.30 |
| rise_10d_pct | > 0 | auction_turnover_rate | 0.5%~10% |
| limit_up_count_100d | >= 3 | seal_rate_100d | >= 80% |
| 非ST/非停牌/非北交所 | 必须 | | |

**T+0标签定义**（`leader_main_t0_label_builder.py`）:
```
一字板: open>=limit*0.997 AND high>=limit*0.997 AND low>=limit*0.997 AND close>=limit*0.997
  → label = NULL (排除出训练集)
非一字板 + high>=limit*0.997 + close>=limit*0.997 → label = 1 (封板成功)
其他 → label = 0 (失败)
涨停价: 300/301/688/689开头 → 20%, 其他 → 10%
```

**预测集成**（`stock_selector.py::_merge_and_score_candidates`）:
```
Phase A: 规则评分 → rule_score
Phase B: 按rule_score降序排序
Phase C: batch_predict_before_selection() → model_score
         final_score = rule_score * 0.6 + model_score * 0.4
Phase D: batch_predict_leader_main_t0() → t0_limit_success_prob
Phase E: final_score = rule_score*0.55 + model_score*0.35 + t0_prob*0.10
Phase E: 等级分配 + 持久化至SelectedStock
```

**模型版本管理**:
- 每次训练生成 `leader_main_t0_lgbm_{YYYYMMDD_HHMMSS}.pkl`
- `model_version` 表记录: model_name, version, feature_cols(JSON), model_path, metrics(JSON), train_start_date, train_end_date, is_active
- `batch_predict_model()` 从 `ModelVersion` 读取活跃模型的特征列（不硬编码）
- 旧版本自动 `is_active=0`，支持回溯

**降级策略**: `joblib` 缺失或模型文件不存在 → 所有预测返回 `None` → 不影响核心选股流程

**关键数据单位**:
- `.day` 成交量需 `/100`(手)，成交额需 `/1000`
- `auction_ratio` = 竞价量(股) / T-1日成交量(手) — 自然产生百分比级数值
- 训练样本少时（<200）AUC虚高属正常现象，阈值保守使用

### 11. 默认竞价接力V2（三目标模型）

**位置**: `backend/services/model_engine/`

**模块架构**:
```
model_engine/
├── lightgbm_service.py                  # 竞价通用+龙头T+0双模型（已有）
├── model_management_service.py          # 模型中心(训练任务+版本激活+预测刷新)
├── default_auction_relay_job_service.py  # 三目标训练编排(创建/运行/诊断)
├── default_auction_model_trainer.py      # 单目标LightGBM训练器
├── default_auction_model_evaluator.py    # TopK评估+验收闸门
├── default_auction_attribution_service.py # 特征质量+分桶归因+训练归因
├── default_auction_sample_builder.py     # 训练样本构建(从选股记录)
├── default_auction_label_builder.py      # 三目标标签辅助(T0/T1溢价/T1连板)
├── default_auction_replay_service.py     # 历史回放入口
└── replay_validation_service.py          # 回放验收(召回率/Jaccard/数量误差)
```

**数据模型**: `backend/models/default_auction_training_sample.py` (DefaultAuctionTrainingSample) + `backend/models/model_training_job.py` (ModelTrainingJob)

**API接入**: `backend/api/model_management.py`

**定位**: 基于LightGBM的默认竞价接力三目标预测系统，三模型分别预测T+0封板、T+1溢价、T+1连板，支持多参数配置轮训、自动验收闸门、原子激活。

**三目标模型**:

| 子模型 | 模型名 | 标签列 | 验收闸门 |
|--------|--------|--------|---------|
| T+0封板 | `default_auction_t0_limit_lgbm` | `label_t0_limit_success` | Top3 Lift≥0.08, Top5 Lift≥0.05, TopK正例≥20, AUC≥0.55 |
| T+1溢价 | `default_auction_t1_premium_lgbm` | `label_t1_premium_success` | Top3 Lift≥0.10, Top5 Lift≥0.06, TopK正例≥25, AUC≥0.55 |
| T+1连板 | `default_auction_t1_continue_lgbm` | `label_t1_continue_limit` | Top3 Lift≥0.06, Top5 Lift≥0.04, TopK正例≥10, AUC≥0.53 |

**14维特征** (`DEFAULT_AUCTION_FEATURES`):
`auction_ratio`(竞昨比), `auction_turnover_rate`(竞价换手率), `open_change_pct`(开盘涨幅), `pre_change_pct`(昨涨幅), `limit_up_count`(涨停次数), `touch_days`(触板天数), `limit_up_days`(涨停天数), `seal_rate`(封板率), `rise_10d_pct`(近10日涨幅), `circ_mv`(流通市值), `prev_turnover_rate`(昨日换手率), `rule_score`(规则评分), `final_score`(最终评分), `risk_tags_count`(风险标签数)

**数据来源**: 纯结构化字段(来自 `SelectedStock`)，不引入新闻/公告/舆情/AI文本特征，避免标签和文本信息反哺模型。

**三目标标签定义**:

| 标签 | 成功条件 | 未知返回 None |
|------|---------|--------------|
| `label_t0_limit_success` | T日最高价触板(≥涨停价×0.997) + 收盘封板 | 涨跌停价/high/close 任一缺失 |
| `label_t1_premium_success` | T+1开盘≥3%或最高≥5%或收盘≥3% | open/high/close 回报率全部缺失 |
| `label_t1_continue_limit` | T+1最高价触板 + 收盘封板(连板) | 涨跌停价/high/close 任一缺失 |

**一字板审计**: `is_t0_one_line_limit_up` / `is_t1_one_line_limit_up` — 开/高/低/收全部接近涨停价→一字板标记。一字板样本标签为NULL(排除出训练集)。

**训练编排** (`default_auction_relay_job_service.py`):

```
create_job → run_job:
  对每个目标模型(model_name, label_column):
    → 样本查询(query samples with non-null label)
    → 特征质量报告(build_feature_quality_report → usable_features)
    → 时间顺序切分(70/15/15 train/val/test)
    → 按参数配置轮训(max_attempts ≤ profile数):
        → 训练LGBMClassifier
        → TopK评估(evaluate_topk → 按交易日分桶取top1/3/5)
        → 验收闸门(judge_target_acceptance)
        → 通过则 break，否则尝试下一个配置
    → 三目标全部通过验收:
        → auto_activate? → 原子激活最新通过版本
        → 否则 → status=passed
    → 任一目标失败 → status=rejected
```

**5种参数配置** (`DEFAULT_PARAM_PROFILES`):

| 配置名 | learning_rate | num_leaves | max_depth | reg_alpha | reg_lambda | subsample | n_estimators |
|--------|--------------|------------|-----------|-----------|------------|-----------|-------------|
| balanced_default | 0.05 | 31 | -1 | 0 | 0 | 0.8 | 500 |
| conservative_regularized | 0.03 | 15 | 4 | 0.1 | 1.0 | 0.75 | 500 |
| shallow_stable | 0.04 | 7 | 3 | 0.2 | 2.0 | 0.9 | 500 |
| wider_ranker | 0.02 | 63 | 6 | 0.05 | 0.5 | 0.8 | 700 |
| seed_retry | 0.03 | 15 | 4 | 0.1 | 1.0 | 0.75 | 500 |

**TopK评估** (`evaluate_topk`):
- 按交易日分组，按预测概率降序取每日 top1/top3/top5
- 计算 top1_rate/top3_rate/top5_rate 相对 baseline_rate 的 lift
- label 为 None/空字符串/非法数字的样本属于未知标签，不进入基准、胜率和 TopK 排名
- `topk_positive_count` = 每日 top5 正例数量总和

**验收闸门** (`TARGET_GATES`):
- top3_lift / top5_lift / min_topk_positive_count / min_auc
- 任一指标不达标 → reject_reasons 包含具体失败原因
- 三目标全部通过验收后方可原子激活

**特征质量报告** (`build_feature_quality_report`):
- 自动检测 numeric/categorical 特征
- 分类特征(score_level, lu_tag, lu_status) → ignored
- 数值特征缺失率≥60% / 唯一值≤1 → dropped
- 输出 usable_features 列表供训练使用

**分桶归因** (`build_bucket_report`):
- 对关键特征(auction_ratio/auction_turnover_rate/open_change_pct/seal_rate/rise_10d_pct)预定义分桶
- 每桶计算正例率(bucket_positive_rate)相对基准的 lift
- 每桶内取概率 top5 计算 top5_positive_rate
- 输出结论(高于/不高于基准)

**训练归因** (`build_training_attribution`):
- Top8正贡献特征(按feature_importance排序)
- 噪声特征(importance=0)
- Best/Worst分桶(按lift排序)
- 失败原因中文摘要 + 下次尝试建议

**回放验收** (`replay_validation_service.py`):
```
validate_replay_against_real:
  对最近N个交易日:
    → 取真实选股列表(real_codes)
    → 取回放模拟选股列表(replay_codes)
    → 计算 recall/jaccard/count_error
    → 检测重复代码
  汇总: avg_recall≥0.80 + avg_jaccard≥0.60 + max_count_error≤0.30
       + 无重复代码 → accepted
```

**模型版本管理**:
- 每次训练生成 `{model_name}_{version}.pkl` (version = YYYYMMDD_HHMMSS_ffffff)
- `model_version` 表: model_name, version, feature_cols(JSON), model_metrics(JSON), model_path, params(JSON), is_active
- 激活新版本时原子更新——先 deactivate 同模型名下所有旧版本，再激活新版本
- `is_active=1` 只允许每个模型名下一行

**预测集成至SelectedStock**:
| SelectedStock 字段 | 来源模型 | 说明 |
|--------------------|---------|------|
| `default_t0_limit_prob` | `default_auction_t0_limit_lgbm` | T+0封板概率 |
| `default_t1_premium_prob` | `default_auction_t1_premium_lgbm` | T+1溢价概率 |
| `default_t1_continue_prob` | `default_auction_t1_continue_lgbm` | T+1连板概率 |
| `default_relay_score` | 综合计算 | 默认竞价接力综合评分 |
| `default_relay_model_version` | 版本标识 | 活跃模型版本号 |

**ModelTrainingJob 表**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `model_name` | VARCHAR(100) | 模型名(如 `default_auction_relay_v2`) |
| `status` | VARCHAR(30) | pending/running/passed/rejected/failed |
| `phase` | VARCHAR(50) | prepare/train:{model_name}/activate/accepted/rejected/failed |
| `progress` | INTEGER | 0-100 |
| `mode` | VARCHAR(20) | test/production |
| `auto_activate` | INTEGER | 训练通过后是否自动激活(0/1) |
| `params_json` | TEXT | 训练参数(profiles等) |
| `acceptance_json` | TEXT | 验收结果(targets/all_accepted/activation) |
| `attempts_json` | TEXT | 每次训练尝试的详情(metrics/acceptance) |
| `logs_json` | TEXT | 时间线日志 |
| `best_model_version` | VARCHAR(255) | 通过验收的最佳版本号 |
| `best_model_path` | VARCHAR(500) | 最佳模型文件路径 |

**降级策略**: 模型文件缺失或 `joblib`/`lightgbm` 不可用时，`default_t0_limit_prob` 等4个预测字段返回 `None`，不影响核心选股流程。

### 12. 股票别名服务(StockAliasService)

**位置**: `backend/services/stock_alias_service.py`

**功能**: 股票代码→名称、名称→代码的正向/反向查询

### 13. 评分系统V2/V3 API

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

### 14. WebSocket实时通信服务

**位置**: `backend/services/websocket_service.py`

**核心类**: `ConnectionManager`

**WebSocket端点**: `WS /ws`, `GET /api/v1/ws/stats`

### 15. 其他服务

**策略服务**: `backend/services/strategy/` — 竞价活跃度/涨停/市值/价格/趋势策略（V1已废弃，V2在strategy_service.py）
**任务调度**: `backend/services/scheduler.py` — 定时选股+任务日志
**新闻采集**: `backend/services/news_collector.py` — 财联社+同花顺定时采集
**集成新闻**: `backend/services/integrated_news_service.py` — 统一新闻查询接口
**飞书通知**: `backend/services/notification.py` — 选股结果+告警推送
**告警服务**: `backend/services/alert_service.py` — 高错误率/高延迟/API不可用
**模型引擎**: `backend/services/model_engine/lightgbm_service.py` — LightGBM双模型训练+预测+版本管理
**模型管理**: `backend/services/model_engine/model_management_service.py` — 训练任务/版本激活/预测刷新
**默认接力编排**: `backend/services/model_engine/default_auction_relay_job_service.py` — 三目标训练编排(创建/运行/诊断)
**默认接力训练器**: `backend/services/model_engine/default_auction_model_trainer.py` — 单目标训练(特征质量+时间切分+TopK评估)
**默认接力评估器**: `backend/services/model_engine/default_auction_model_evaluator.py` — TopK评估+验收闸门
**默认接力归因**: `backend/services/model_engine/default_auction_attribution_service.py` — 特征质量+分桶+训练归因
**默认接力样本构建**: `backend/services/model_engine/default_auction_sample_builder.py` — 从选股记录构建训练样本
**默认接力标签辅助**: `backend/services/model_engine/default_auction_label_builder.py` — T0/T1溢价/T1连板标签
**历史回放**: `backend/services/model_engine/default_auction_replay_service.py` — 默认竞价策略历史回放入口
**回放验收**: `backend/services/model_engine/replay_validation_service.py` — 召回率/Jaccard/数量误差
**特征构建**: `backend/services/backtest/leader_main_t0_feature_builder.py` — 候选股9维特征+过滤
**标签生成**: `backend/services/backtest/leader_main_t0_label_builder.py` — T+0涨停标签

### 16. 数据持久化

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
| `stock_lhb` | 龙虎榜数据 | ✅ |
| `stock_risk_breakdown` | 风险拆解(7维度新) | ✅ |
| `dragon_leader_score` | 龙头战法评分 | ✅ 新增 |
| `board_index` | 东财板块词典 | ✅ |
| `stock_board_member` | 东财板块成分股关系 | ✅ |
| `board_daily_snapshot` | 板块每日快照 | ✅ |
| `board_strength_snapshot` | 板块强度快照 | ✅ |
| `dc_board_alias` | 板块别名汇总 | ✅ 新增 |
| `dc_board_alias_observation` | 板块别名单日命中明细 | ✅ 新增 |
| `dc_board_alias_sync_state` | 板块别名同步水位 | ✅ 新增 |
| `ths_board_index` | 同花顺板块词典 | ✅ |
| `stock_ths_board_member` | 同花顺板块成分股 | ✅ |
| `news_data` | 新闻数据库（独立） | ✅ |
| `strategy_template` | 策略模板 | ✅ |
| `scheduled_task` | 定时任务 | ✅ |
| `task_log` | 任务日志 | ✅ |
| `system_config` | 系统配置 | ✅ |
| `stock_feature_snapshot` | 特征快照 | ✅ |
| `model_version` | LightGBM模型版本记录 | ✅ 新增 |
| `stock_auction_open` | 集合竞价原始数据 | ✅ 新增 |
| `leader_main_t0_training_sample` | 龙头T+0训练样本 | ✅ 新增 |
| `model_training_job` | 模型训练任务(状态/阶段/验收/日志) | ✅ 新增 |
| `default_auction_training_sample` | 默认竞价接力训练样本(14维+3标签) | ✅ 新增 |

---

## 数据流

### 选股后后台预加载流程

```
select_stocks() 完成
    ↓
┌─── 非阻塞后台预热 ────────────────────────┐
│ ThreadPoolExecutor(max_workers=5)         │
│                                            │
│ _trigger_ai_preheat()                      │
│   ├── AiBriefService.generate()            │
│   └── AnomalyInterpretationService()       │
│                                            │
│ _trigger_lhb_preheat()                     │
│   └── analyze_lhb() → top_list +           │
│        top_inst + hm_list                  │
│        → 写入 stock_lhb 表                 │
│                                            │
│ _trigger_risk_preheat()                    │
│   └── calculate_risk()                     │
│        → 7维度并行采集                     │
│        → 写入 stock_risk_breakdown 表      │
│                                            │
│ _trigger_dragon_leader_preheat()            │
│   └── calculate_dragon_leader_score()       │
│        → 采集5种上下文+消息面+龙虎榜        │
│        → 龙头强度+退潮风险+综合健康度       │
│        → 写入 dragon_leader_score 表       │
└────────────────────────────────────────────┘
    ↓
用户点个股详情 → 详情页 Tab
    └── 读 DB 缓存 → ~20ms 秒开
```

### 板块动态别名数据流

```
启动时(main.py lifespan):
  1. DcBoardService.sync_board_index_catalog() → 同步东财板块词典
  2. DcBoardAliasService.sync_trade_date() → 同步今日涨停标签别名
     ├── fetch_dc_boards() → 板块词典
     ├── limit_list_ths(trade_date, limit_type="涨停池") → 涨停池
     ├── split_lu_desc_tags → 拆分标签
     ├── score_tag_board_match → 模糊匹配板块
     ├── 写入 dc_board_alias_observation (unique_key去重)
     └── 汇总 dc_board_alias (auto_approved/pending_review)

运行期:
  查询板块 → DcBoardService._get_board_aliases()
    ├── DcBoardAliasService.get_active_aliases() → 动态别名
    ├── MANUAL_BOARD_ALIASES → 手写别名
    └── _merge_board_aliases() → 合并 → 清除缓存 → 全系统生效
```

### 龙头战法数据流

```
用户请求: GET /api/v1/stock/detail/risk?strategy_type=dragon_leader&ts_code=xxx
    ↓
calculate_dragon_leader_score(ts_code, trade_date, force_refresh=False)
    ↓
┌── 优先从 DB 读取 ─────────────┐
│ dragon_leader_score 表有缓存？  │──→ 返回缓存数据
└──────┬─────否──────────────────┘
       ↓
1. 并行采集5种上下文:
   ├── StockContext(行情/筹码/资金/技术)
   ├── MarketContext(大盘涨跌/情绪)
   ├── ThemeContext(热点板块+语义引用)
   ├── FundamentalContext(财务/估值)
   └── IntradayContext(竞价/分时)
       ↓
2. 消息面(并行):
   ├── collect_news → integrated_news_service → analyze_news_event(V2)
   └── announcement_result → announcement_alpha_score
       ↓
3. 龙虎榜(并行):
   ├── collect_lhb → lhb_service.analyze_lhb
   └── lhb_result → lhb_alpha_score(seat_library)
       ↓
4. 评分计算:
   ├── leader_strength_scoring → 龙头强度 + 7维明细
   ├── retreat_risk_scoring → 退潮风险 + 7维明细
   └── health_formula → 综合健康度
       ↓
5. 输出组装: assemble_output(等级/周期/证据/观察点/分项明细)
       ↓
6. 写入 dragon_leader_score 表
       ↓
7. 返回结果
```

### LightGBM T+0训练与预测数据流

```
训练管线(backtest API):
  POST /backtest/leader-main-t0/run
      ↓
  1. 集合竞价同步
     stk_auction → StockAuctionOpen 表
      ↓
  2. 日线数据同步
     .day 文件 → stock_daily_data 表
      ↓
  3. 竞昨比重算
     auction_vol / T-1 daily_vol → auction_ratio
      ↓
  4. 特征构建(LeaderMainT0FeatureBuilder)
     候选股过滤(8条件) → 9维特征 → LeaderMainT0TrainingSample 表
      ↓
  5. 标签生成(LeaderMainT0LabelBuilder)
     排除一字板 → T+0封板判断 → label_t0_limit_success
      ↓
  6. 模型训练(train_leader_main_t0_lgbm)
     LGBMClassifier(500轮, 70/20/10) → leader_main_t0_lgbm_{version}.pkl
     → ModelVersion 表(is_active=1)
     → 评估指标: AUC/Accuracy/Precision/Recall + 9阈值评估

预测管线(stock_selector.py):
  选股完成 → _merge_and_score_candidates()
      ↓
  batch_predict_before_selection()
     → 加载 active_auction_lgbm.pkl
     → 8维特征预测 → model_score (0-100)
     → final_score = rule_score*0.6 + model_score*0.4
      ↓
  batch_predict_leader_main_t0()
     → 加载 leader_main_t0_lgbm_{version}.pkl (通过ModelVersion)
     → 9维特征预测 → t0_limit_success_prob (0-1)
     → 参与 final_score (权重10%)
      ↓
  持久化: model_score, t0_limit_success_prob, t0_limit_success_model_version
      ↓
  前端展示: Dashboard.vue(模型状态卡) + StockResults.vue(T+0概率列)
```

---

## 配置管理

### 环境变量(.env)

```bash
# Tushare API Token
TUSHARE_TOKEN=your_token_here

# 通达信MCP配置
TDX_MCP_ENABLED=true
TDX_MCP_URL=https://mcp.tdx.com.cn:3001/mcp
TDX_MCP_API_KEY=your_api_key_here

# 飞书Webhook URL (通知+告警)
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 数据库路径
DATABASE_URL=sqlite:///./data/xuangu.db

# JWT密钥
SECRET_KEY=your_secret_key_here

# AI配置
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DOUBAO_API_KEY=your_doubao_api_key_here
SCORING_CACHE_DAYS=7
AI_TIMEOUT=30

# 服务配置
HOST=0.0.0.0
PORT=9999
LOG_LEVEL=INFO
LOG_DIR=logs
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:8081,http://localhost:3000
```

### 龙头战法权重配置

`backend/services/dragon_leader/config.yaml`:
```yaml
dragon_leader:
  health_formula:
    leader_strength_weight: 0.60
    retreat_risk_weight: -0.30
    announcement_alpha_weight: 0.50
    lhb_alpha_weight: 0.50
    base_score: 20
  leader_strength:
    leader_status: 25
    theme_strength: 20
    emotion_cycle: 15
    sector_ladder: 15
    acceptance_strength: 10
    auction_intraday: 10
    lhb_bonus: 5
  retreat_risk:
    leader_position_loss: 20
    emotion_retreat: 20
    ladder_break: 15
    acceptance_failure: 15
    chip_cashout: 10
    auction_miss: 10
    announcement_regulatory: 10
  alpha_limits:
    announcement_alpha_min: -20
    announcement_alpha_max: 20
    lhb_alpha_min: -20
    lhb_alpha_max: 20
```

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

---

## 开发进度

### ✅ Phase 1-4: 基础版本 - 已完成
### ✅ Phase 5: 选股流程重构 - 已完成
### ✅ Phase 6: 封板率计算 - 已完成
### ✅ Phase 7: 评分系统V3 - 已完成
### ✅ Phase 8: AI综合概览 - 已完成
### ✅ Phase 9: 异动解读 - 已完成
### ✅ Phase 10: 新闻情感分析 - 已完成
### ✅ Phase 11: 龙虎榜模块 - 已完成
### ✅ Phase 12: 风险拆解模块 - 已完成

### ✅ Phase 13: 龙头战法+板块别名+情感V2 - 已完成
- [x] 龙头战法评分系统(DragonLeader) — 龙头强度+退潮风险+综合健康度
- [x] 统一席位库(seat_library) — 高溢价/核按钮/量化/机构/散户统一分类
- [x] 东财板块动态别名(DcBoardAliasService) — 涨停标签→板块自动映射
- [x] 事件驱动情感分析V2(news_sentiment) — 事件识别+多事件合并+确定性因子
- [x] 风险拆解增强 — 主线板块上下文+强势/风险依据+席位净买卖方向判定
- [x] 前端RiskBreakdown双模式 — 普通7维度+龙头战法三栏评分

### ✅ Phase 14: LightGBM竞价模型 - 已完成
- [x] 双模型架构 — active_auction_lgbm(8维)+leader_main_t0_lgbm(9维精简版)
- [x] 模型引擎(lightgbm_service) — 训练+批量预测+版本管理
- [x] T+0特征构建(LeaderMainT0FeatureBuilder) — 9维+8条件过滤
- [x] T+0标签生成(LeaderMainT0LabelBuilder) — 一字板排除+封板判定
- [x] 回测管线API(backtest.py) — 竞价同步→特征→标签→训练一键执行
- [x] 选股管线集成(stock_selector.py) — model_score影响final_score(40%)
- [x] 模型状态API(/api/v1/model/status) — 活跃版本+特征+指标查询
- [x] 前端展示 — Dashboard模型状态卡+StockResults T+0概率列
- [x] 测试覆盖 — 6个测试文件47个用例

### ✅ Phase 15: 默认竞价接力V2 + 模型中心 - 已完成
- [x] 默认竞价接力三目标模型(T0封板+T1溢价+T1连板)
- [x] 14维纯结构化特征(不引入新闻/AI文本)
- [x] 5种参数配置轮训+自动验收闸门+TopK评估
- [x] 训练归因(特征质量+分桶+SHAP)
- [x] 模型训练任务编排(ModelTrainingJob全程追踪)
- [x] 原子激活(三目标全部通过验收后同步切换)
- [x] 回放验收(recall≥0.80+jaccard≥0.60)
- [x] 模型中心API(训练/激活/诊断/回放验收/预测刷新)
- [x] 模型中心前端(ModelCenter.vue)
- [x] SelectedStock新增5个预测字段(default_t0/t1_premium/t1_continue/relay_score)
- [x] 测试覆盖(6个新测试文件)

### 📋 Phase 16: 功能优化 - 进行中
- [ ] 提升测试覆盖率至85%+
- [ ] 用户权限管理(RBAC)
- [ ] 数据导出功能(Excel/PDF)
- [ ] PostgreSQL迁移
- [ ] Redis缓存层
- [ ] 回测系统
- [ ] 更多AI模型支持(通义千问)

### 后续阶段
- Phase 16: 量化模拟交易
- Phase 17: 智能分析增强(更多AI能力)

---

## 关键技术决策

### 架构决策汇总

| 决策 | 原因 |
|------|------|
| 四阶段选股架构 | 选股/分析/封板率/评分严格分离，各阶段只调允许的数据源 |
| 新闻数据库+实时情感分析 | 独立DB隔离，情感标签不入库，规则更新即生效 |
| 龙虎榜DB缓存+预加载 | 永久存储可回溯，预加载后~20ms秒开 |
| 7维度风险拆解 | 纯规则秒出，权重聚焦公告/资金/筹码/板块，行情仅10分提示 |
| 龙头战法独立模型 | 与普通风险模型互补，三核心分数+双Alpha调整+5种等级 |
| 统一席位库 | lhb/risk/dragon_leader 共用，避免各模块维护独立关键词列表 |
| 板块动态别名 | 每日涨停标签自动关联板块，auto_approved自动生效，pending_review人工审核 |
| 情感分析双引擎 | V1(加权评分)继续用于旧路径，V2(事件驱动)用于龙头战法+新版API |
| WebSocket实时推送 | 替代轮询，频道订阅+心跳检测+自动断线清理 |
| LightGBM双模型 | 竞价通用(权重35%)+龙头T+0(权重10%)，互补不冲突 |
| 默认竞价接力三目标 | T0封板+T1溢价+T1连板，14维纯结构特征，5参数配置轮训+原子激活 |
| 模型版本管理 | 每次训练生成带时间戳的.pkl，DB记录特征列+指标，回溯可查 |
| T+0标签定义 | 排除一字板(无交易机会)，只评估非一字板封板概率 |
| 训练任务编排 | ModelTrainingJob表全程追踪，多配置重试+自动验收+原子激活 |
| 回放验收 | 真实选股vs回放模拟比较，recall≥0.80+jaccard≥0.60无重复代码 |
| FastAPI异步框架 | 高性能+自动API文档+原生WebSocket+类型安全 |

---

## 接口说明

### 个股详情(V1)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/stock/detail?ts_code=xxx` | 个股综合详情(基本信息+评分+新闻+涨停+龙虎榜+业绩+预案) |
| GET | `/api/v1/stock/detail/lhb?ts_code=xxx` | 龙虎榜详情(含seat_library席位标签) |
| GET | `/api/v1/stock/detail/risk?ts_code=xxx` | 风险拆解(普通模型/龙头战法) |
| GET | `/api/v1/stock/detail/news?stock_name=xxx` | 新闻舆情(含V2事件驱动情感分析) |
| GET | `/api/v1/stock/anomaly-interpretation?ts_code=xxx` | 异动解读 |
| GET | `/api/v1/stock/overview-brief?ts_code=xxx` | AI综合概览 |

### 模型与回测

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/model/status` | 活跃模型版本/特征列/评估指标 |
| POST | `/api/v1/backtest/leader-main-t0/run` | 一键T+0全管线 |
| POST | `/api/v1/backtest/leader-main-t0/build` | 构建训练样本 |
| POST | `/api/v1/backtest/leader-main-t0/labels` | 生成T+0标签 |
| POST | `/api/v1/backtest/leader-main-t0/train` | 训练模型 |
| GET | `/api/v1/backtest/leader-main-t0/samples` | 分页查询样本 |
| POST | `/api/v1/backtest/auction/sync` | 单日竞价同步 |
| POST | `/api/v1/backtest/auction/sync-range` | 区间竞价同步 |
| POST | `/api/v1/backtest/auction/recalculate-ratios` | 重算竞昨比 |
| POST | `/api/v1/backtest/tdx-local-daily/sync` | 本地日线同步 |
	
### 模型中心
	
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/model/models` | 所有活跃模型版本/特征列/评估指标 |
| POST | `/api/v1/model/models/default-auction-replay/validate` | 回放验收(最近N日 recall/jaccard/count_error) |
| POST | `/api/v1/model/models/default-auction-samples/build` | 从选股记录构建训练样本 |
| POST | `/api/v1/model/models/default-auction-relay/train` | 一键训练默认竞价接力三目标模型 |
| GET | `/api/v1/model/models/default-auction-relay/diagnostics/{job_id}` | 接力模型训练诊断(状态/进度/验收/日志) |
| POST | `/api/v1/model/models/{model_name}/versions/{version}/activate` | 激活指定版本(原子更新) |
| POST | `/api/v1/model/models/{model_name}/training-jobs` | 创建通用模型训练任务 |
| GET | `/api/v1/model/models/training-jobs/{job_id}` | 获取训练任务状态 |
| POST | `/api/v1/model/models/{model_name}/refresh-predictions` | 刷新选股记录预测值 |

### 龙头战法接口

```
GET /api/v1/stock/detail/risk?ts_code=600539.SH&strategy_type=dragon_leader&stock_name=狮头股份
```

响应示例:
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "data_status": "available",
    "strategy_type": "dragon_leader",
    "ts_code": "600539.SH",
    "trade_date": "20260508",
    "leader_strength_score": 72,
    "retreat_risk_score": 35,
    "health_score": 65,
    "leader_level": "强势龙头",
    "risk_level": "中等风险",
    "health_level": "强势可观察",
    "cycle_stage": "主升期",
    "announcement_alpha_score": 8,
    "lhb_alpha_score": 5,
    "simplified_summary": "该股为【强势龙头】(强度72分)，当前处于主升期。题材优势：题材强度突出。主要风险：龙虎榜砸盘席位净卖出。消息面偏正面(净分+8)。综合健康度65分(退潮风险35分)。",
    "positive_tips": ["题材强度突出", "板块梯队完整", "机构净买入+5"],
    "negative_tips": ["龙虎榜砸盘席位净卖出"],
    "watch_tips": ["竞价是否转强（弱转强）", "龙头地位是否稳固"],
    "score_detail": {
      "leader_strength": {
        "leader_status": {"score": 18, "tips": ["身位优势明显"]},
        "theme_strength": {"score": 16, "tips": ["题材强度突出"]},
        "emotion_cycle": {"score": 10, "tips": []},
        "sector_ladder": {"score": 12, "tips": ["板块梯队完整"]},
        "acceptance_strength": {"score": 7, "tips": []},
        "auction_intraday": {"score": 6, "tips": []},
        "lhb_bonus": {"score": 3, "tips": ["机构净买入"]}
      },
      "retreat_risk": {
        "leader_position_loss": {"score": 5, "tips": ["龙头地位无明显动摇"]},
        "emotion_retreat": {"score": 5, "tips": ["情绪无退潮信号"]},
        "ladder_break": {"score": 8, "tips": ["板块梯队无明显撕裂"]},
        "acceptance_failure": {"score": 8, "tips": ["无明显炸板"]},
        "chip_cashout": {"score": 4, "tips": []},
        "auction_miss": {"score": 3, "tips": []},
        "announcement_regulatory": {"score": 2, "tips": ["无减持、无ST退市风险"]}
      },
      "alpha_adjustment": {
        "good_news_score": 8,
        "bad_news_score": 0,
        "announcement_alpha_score": 8,
        "lhb_bonus_score": 8,
        "lhb_penalty_score": -3,
        "lhb_alpha_score": 5,
        "announcement_tips": ["业绩预增", "公告利好"],
        "lhb_tips": ["机构买入", "买榜明显强于卖榜"]
      }
    }
  }
}
```

### 风险拆解接口（普通模式）

```
GET /api/v1/stock/detail/risk?ts_code=600539.SH&trade_date=20260508
```

响应示例(新增字段):
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "data_status": "available",
    "ts_code": "600539.SH",
    "trade_date": "20260508",
    "total_score": 45,
    "risk_level": "中",
    "risk_summary": "中等风险，注意龙虎榜席位动向",
    "warning_tip": "注意砸盘席位卖出风险",
    "market_score": 2,
    "chip_score": 8,
    "news_score": 5,
    "capital_score": 8,
    "lhb_score": 6,
    "sector_score": 10,
    "technical_score": 6,
    "sector_context": {
      "primary_board": {"name": "算力租赁", "rank": 3},
      "board_pct_chg": 2.3,
      "money_net_amount_yi": 1.5,
      "limit_up_count": 5,
      "strength_score": 72
    },
    "strength_evidence": [
      "高溢价席位净买入（相城大道）",
      "所属算力租赁板块涨幅前3",
      "板块内5只涨停，梯队完整"
    ],
    "risk_evidence": [
      "核按钮席位净卖出（长城仙桃钱沟路）",
      "近10日涨幅32%，处于阶段高位"
    ],
    "history": [
      {"trade_date": "20260507", "total_score": 38, "risk_level": "中"},
      {"trade_date": "20260506", "total_score": 52, "risk_level": "高"}
    ]
  }
}
```

---

## 注意事项

### 接口分离原则

| 阶段 | 允许调用 | 禁止调用 |
|------|----------|----------|
| 阶段1(选股) | 通达信MCP | Tushare |
| 阶段2(分析) | Tushare | 通达信MCP |
| 阶段3(封板率) | Tushare | 通达信MCP |
| 阶段4(评分) | 无外部调用,AI可选 | - |
| 龙头战法 | Tushare + news_sentiment(V2) + seat_library | 通达信MCP |

### 模块间复用关系

| 上层模块 | 依赖底层 | 关系 |
|---------|---------|------|
| `lhb_service` | `seat_library` | 席位标签匹配 |
| `risk_breakdown_service` | `lhb_service` + `seat_library` | 龙虎风险评分 |
| `dragon_leader/lhb_alpha` | `lhb_service` + `seat_library` | 龙虎榜Alpha评分 |
| `dragon_leader/main` | `news_sentiment`(V2) | 消息面Alpha |
| `dragon_leader/main` | `lhb_service` + `seat_library` | 龙虎榜Alpha |
| `dc_board_service` | `dc_board_alias_service` | 板块别名合并 |
| `stock_detail API` | `news_sentiment`(V2) | 新闻情感分析 |
| `integrated_news_service` | `sentiment_analyzer`(V1) | 旧版新闻情感 |
| `default_auction_relay_job_service` | `default_auction_model_trainer` + `default_auction_model_evaluator` | 训练编排+验收 |
| `default_auction_model_trainer` | `default_auction_attribution_service` + `lightgbm_service` | 训练归因+joblib |
| `model_management API` | `default_auction_relay_job_service` + `replay_validation_service` | 训练+回放 |
| `default_auction_sample_builder` | `SelectedStock` + `SelectionRecord` | 结构化特征提取 |

### 情感分析双引擎使用场景

| 场景 | 使用引擎 | 说明 |
|------|---------|------|
| 龙头战法消息面 | `news_sentiment` V2 | 事件驱动，区分单股/多股新闻 |
| `stock_detail.py` 新闻API | `news_sentiment` V2 | 新版API使用V2 |
| `integrated_news_service` 旧查询路径 | `SentimentAnalyzer` V1 | 保持向后兼容 |
| 风险拆解舆情维度 | `SentimentAnalyzer` V1 | 利空新闻计数 |

### Tushare API积分需求

| 接口 | 用途 | 最低积分 |
|------|------|---------|
| `top_list` | 龙虎榜每日明细 | 2000 |
| `top_inst` | 龙虎榜席位明细 | 5000 |
| `hm_list` | 游资名录 | 5000 |
| `moneyflow` | 个股资金流向 | 2000 |
| `cyq_perf` | 筹码胜率(获利盘) | 5000 |
| `ths_daily` | 同花顺板块行情 | 6000 |
| `daily_basic` | 每日指标(换手率) | 2000 |
| `limit_list_ths` | 涨停池(板块别名+龙头战法) | 5000 |
| `dc_index` | 东财板块指数 | 2000 |
| `dc_member` | 东财板块成分股 | 2000 |

### 各模块注意事项

**龙虎榜**: 席位类型交给 `seat_library` 统一判断，不要在各模块中自行维护关键词列表。

**情感分析**: V1(旧)继续用于 `integrated_news_service` 旧路径；V2(新)用于龙头战法和新版API。两者规则独立，分别维护。

**板块匹配**: 运行期板块别名来自两处合并 — 手写别名(`MANUAL_BOARD_ALIASES`) + 动态别名(`DcBoardAliasService.get_active_aliases()`)。

**龙头战法**: 权重从 `config.yaml` 加载，降级到代码默认值。DB缓存优先，`force_refresh=true` 强制重算。数据不可用时部分维度为0分，不阻断整体评分。

**风险拆解**: 龙虎风险中席位判定已从简单"买榜/卖榜"升级为"净买卖方向+标签类型"判定。行情风险使用**昨日**换手率和振幅（非今日实时）。

**板块别名**: 每日启动时同步最新交易日，盘后(15:30后)标记 finalized。`auto_approved` 别名立即生效，`pending_review` 不生效需人工审核。

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
| 风险拆解计算 | <5秒 | <2秒 | ✅ |
| 龙头战法评分 | <60秒 | ~5秒 | ✅ |
| 情感分析V1单条 | - | <1ms | ✅ |
| 情感分析V2单条 | - | <5ms | ✅ |
| 板块别名同步 | - | <10秒 | ✅ |
| 默认接力单目标训练 | <10秒 | ~3秒 | ✅ |
| 默认接力三目标全管线 | <120秒 | ~20秒 | ✅ |
| 回放验收(5日) | <30秒 | ~5秒 | ✅ |

---

## 开发规范

### Python代码规范
- **Style Guide**: PEP 8
- **Formatter**: Black (line-length=100)
- **Type Hints**: 必须添加类型注解
- **Docstring**: Google Style

### JavaScript/Vue代码规范
- **Style Guide**: Vue Official Style Guide
- **Formatter**: Prettier
- **Naming**: camelCase for variables, PascalCase for components

### 数据库规范
- **Table Naming**: snake_case(如`selection_record`)
- **Column Naming**: snake_case(如`trade_date`)
- **Timestamps**: `created_at`, `updated_at` (DATETIME)

### API规范
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
feat(dragon): 实现龙头战法评分系统
feat(board): 实现东财板块动态别名
feat(sentiment): 实现事件驱动情感分析V2
feat(seat): 实现统一席位库
fix(risk): 修复龙虎风险席位方向判定
```

---

## 相关文档

- `README.md`: 项目主文档
- `CLAUDE.md`: 开发指南
- `DEVELOP.md`: 开发文档
- `WINDOWS_DEPLOYMENT_GUIDE.md`: Windows部署指南

---

**Last Updated**: 2026-05-17
**Maintainer**: AI Assistant
**Version**: 7.0
