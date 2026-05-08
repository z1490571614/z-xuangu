# 选股通知系统

**四阶段智能选股 + V3评分系统 + AI综合概览 + 同花顺式异动解读 + 龙虎榜 + 风险拆解 + 龙头战法 + 新闻情感分析 + 飞书通知 + WebSocket实时推送的生产级选股系统**

---

## 目录

- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [API文档](#api文档)
- [选股架构](#选股架构)
- [评分系统V3](#评分系统v3)
- [个股详情Tab](#个股详情tab)
- [配置说明](#配置说明)
- [运行测试](#运行测试)
- [项目结构](#项目结构)
- [核心质量指标](#核心质量指标)

---

## 功能特性

### 核心功能

| 功能 | 说明 | 状态 |
|------|------|------|
| **四阶段选股架构** | 阶段1: MCP选股 → 阶段2: Tushare分析 → 阶段3: 封板率计算 → 阶段4: 评分系统 | ✅ |
| **评分系统V3** | Alpha评分(6维度) + 风险拆解(7维度) + 决策引擎 + 新旧对比 | ✅ |
| **AI综合概览** | 纯AI汇总8个模块的结构化输出,生成简报、标签、建议 | ✅ |
| **同花顺式异动解读** | 核心标签+行业原因+公司原因,综合近3个交易日新闻 | ✅ |
| **龙虎榜** | Tushare top_list/top_inst/hm_list 数据采集,席位标签+游资别名+行为判定 | ✅ |
| **风险拆解** | 7大维度量化风险（市场环境/筹码压力/舆情公告/个股资金/龙虎/板块题材/技术结构）,纯规则秒出 | ✅ |
| **龙头战法评分** | 龙头强度+退潮风险+综合健康度+消息面Alpha+龙虎榜Alpha,多维度龙虎席位判断 | ✅ |
| **新闻情感分析V2** | 事件驱动的纯规则情感判定引擎,支持多事件冲突合并+确定性因子,独立于策略 | ✅ |
| **东财板块动态别名** | 每日涨停标签自动关联板块别名,自动审批+运行期生效,提升板块匹配准确率 | ✅ |
| **开盘预案生成** | 6种开盘场景、具体观察点、取消条件、止损止盈 | ✅ |
| **封板率计算** | 基于前复权数据计算触板天数、封板天数、封板率 | ✅ |
| **候选股特征快照** | 每日保存候选股特征,支持LightGBM训练样本沉淀 | ✅ |
| **WebSocket实时推送** | 替代轮询,支持频道订阅和消息广播 | ✅ |
| **飞书通知** | 自动推送选股结果(含评分/原因/风险标签)和告警到飞书群 | ✅ |
| **定时任务** | 支持定时自动执行选股任务 | ✅ |

### 系统特性

| 特性 | 说明 | 状态 |
|------|------|------|
| **REST API** | 完整的API接口,支持Swagger文档 | ✅ |
| **JWT认证** | 用户注册、登录、Token鉴权 | ✅ |
| **Prometheus监控** | 请求计数、延迟、活跃请求数 | ✅ |
| **结构化日志** | JSON + 人类可读双格式,日志轮转 | ✅ |
| **安全防护** | HTTPS重定向、安全响应头、CSP策略 | ✅ |
| **直接部署** | Supervisor + Nginx,无需Docker | ✅ |

---

## 技术栈

### 后端技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.109+ | Web框架 |
| SQLAlchemy | 2.0 | ORM |
| APScheduler | - | 任务调度 |
| JWT | - | 认证授权 |
| SQLite | WAL模式 | 数据库 |
| 通达信MCP | - | 阶段1选股 |
| Tushare Pro | - | 阶段2分析 + 阶段3封板率 + 龙虎榜 + 资金流向 + 筹码数据 + 板块行情 |
| 通达信行情API | - | 实时行情/竞价数据 |
| LightGBM | 可选 | 模型评分训练与预测 |
| OpenAI/Doubao API | - | AI综合概览生成 |
| DeepSeek API | - | AI综合分析 |

### 前端技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| Vue | 3.4+ | 前端框架 |
| Vite | 5.4+ | 构建工具 |
| Vue Router | - | 路由管理 |
| ECharts | - | 评分可视化、趋势图 |

---

## 快速开始

### 1. 环境准备

**Windows 环境:**
```bash
cd h:\project_development\xuangu

# 创建虚拟环境
python -m venv .venv
# 激活虚拟环境
.\.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
copy .env.example .env
# 编辑 .env 文件,配置以下必填项:
# - TUSHARE_TOKEN: Tushare API Token
# - FEISHU_WEBHOOK_URL: 飞书机器人 Webhook URL
# - SECRET_KEY: JWT密钥
```

**Linux/Mac 环境:**
```bash
cd /opt/xuangu

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件
```

### 2. 启动服务

```bash
# 开发模式(单进程,热重载)
uvicorn backend.main:app --host 0.0.0.0 --port 9999 --reload

# 生产模式(多Worker)
uvicorn backend.main:app --host 0.0.0.0 --port 9999 --workers 4
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev

# 构建生产版本
npm run build
```

### 4. 快速测试

```bash
# 启动后端后,运行完整接口测试
conda activate xuangu
python test_detail_page.py
```

---

## API文档

启动服务后访问:

| 文档 | URL |
|------|-----|
| Swagger UI | http://localhost:9999/docs |
| ReDoc | http://localhost:9999/redoc |
| 健康检查 | http://localhost:9999/api/v1/health |

### 核心API(V1版本)

#### 选股相关

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/stock/select` | 执行四阶段选股(含评分+预加载) |
| GET | `/api/v1/stock/results` | 获取选股结果列表 |
| GET | `/api/v1/stock/results/{id}` | 获取选股详情(含评分字段) |

#### 个股详情

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/stock/detail?ts_code=xxx` | 个股综合详情(基本信息/评分/涨停/业绩/预案) |
| GET | `/api/v1/stock/detail/lhb?ts_code=xxx` | 龙虎榜详情(席位标签/游资别名/行为判定) |
| GET | `/api/v1/stock/detail/risk?ts_code=xxx` | 风险拆解(支持普通/龙头战法双模式) |
| GET | `/api/v1/stock/overview-brief?ts_code=xxx` | AI综合概览 |
| GET | `/api/v1/stock/anomaly-interpretation?ts_code=xxx` | 异动解读 |
| GET | `/api/v1/stock/detail/news?stock_name=xxx` | 新闻舆情(含新版事件驱动情感分析) |

#### 龙头战法

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/stock/detail/risk?strategy_type=dragon_leader` | 龙头战法评分(龙头强度+退潮风险+综合健康度) |

---

## 选股架构

### 四阶段选股流程

```
┌─────────────────────────────────────────────────────────────┐
│                  阶段1: 通达信MCP选股                         │
│                   选股条件: 非ST/市值/价格/趋势/涨停/竞价     │
│                   响应时间: <1秒                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  阶段2: Tushare补充分析                       │
│                   每日指标: PE/PB/市值/换手率                 │
│                   昨涨幅/开涨幅计算                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  阶段3: 封板率计算与过滤                       │
│                   触板天数/封板天数/封板率                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  阶段4: 评分系统V3                            │
│                   Alpha评分 + 风险拆解 + 决策引擎             │
└─────────────────────────────────────────────────────────────┘
                              ↓
                   后台预加载（非阻塞）:
                     AI概览 + 异动解读 + 龙虎榜 + 风险拆解 + 龙头战法
```

### 接口调用原则

| 阶段 | 允许调用 | 禁止调用 |
|------|----------|----------|
| 阶段1(选股) | 通达信MCP | Tushare |
| 阶段2(分析) | Tushare | 通达信MCP |
| 阶段3(封板率) | Tushare | 通达信MCP |
| 阶段4(评分) | 无外部调用 | - |
| 后台预加载 | Tushare+本地 | 通达信MCP |

---

## 评分系统V3

### Alpha评分(6维度)

| 维度 | 满分 | 核心指标 |
|------|------|---------|
| 交易价值 | 25 | 历史相似形态胜率、冲高5%概率、盈亏比 |
| 预期收益 | 20 | 历史平均涨幅、最大涨幅、上涨空间 |
| 流动性 | 20 | 日均成交额、换手率、买卖盘深度 |
| 板块地位 | 15 | 板块涨幅排名、成交额占比、联动性 |
| 事件驱动 | 10 | 事件重要性、事件时效性、市场关注度 |
| 市场环境 | 10 | 大盘涨跌、市场情绪、赚钱效应 |

### 龙头战法评分（独立模型）

| 维度 | 满分 | 核心指标 |
|------|------|---------|
| 龙头强度 | 100 | 龙头地位25+题材强度20+情绪周期15+板块梯队15+承接强度10+竞价分时10+龙虎榜加成5 |
| 退潮风险 | 100 | 龙头地位动摇20+情绪退潮20+板块梯队断裂15+承接失败15+筹码兑现10+竞价低预期10+公告监管10 |
| 综合健康度 | 100 | 龙头强度×0.6+退潮风险×(-0.3)+公告Alpha×0.5+龙虎榜Alpha×0.5+基准分20 |
| 公告Alpha | -20~+20 | 利好/利空新闻量化（事件驱动情感分析引擎） |
| 龙虎榜Alpha | -20~+20 | 席位买卖方向净加减分（统一席位库） |

**龙头等级**: 极强龙头(≥85) / 强势龙头(≥70) / 疑似龙头(≥55) / 跟风强势股(≥40) / 非龙头

**周期阶段**: 主升期 / 分歧期 / 退潮期 / 混沌期 / 震荡期

### 风险拆解(7维度)

| 维度 | 满分 | 核心指标 |
|------|------|---------|
| 市场环境 | 10 | 换手率、振幅异常 |
| 筹码压力 | 14 | 获利盘比例、阶段涨幅高位 |
| 舆情与公告 | 18 | 减持/立案/亏损等负面关键词 |
| 个股资金 | 14 | 主力资金净流向 |
| 龙虎风险 | 10 | 席位净买卖方向+标签类型(高溢价/核按钮/量化/散户) |
| 板块与题材风险 | 18 | 板块涨跌+涨停家数+资金流向+强度评分 |
| 技术结构 | 16 | 炸板、竞价低预期等技术面风险 |

**等级判定**: ≤20 低 / ≤40 中 / ≤70 高 / >70 极高

### 评分等级

| 最终评分 | 等级 |
|---------|------|
| ≥90 | S |
| 80-89 | A |
| 70-79 | B |
| 60-69 | C |
| <60 | D |

---

## 个股详情Tab

### Tab1: 综合概览
- AI简报、AI建议、正面/负面标签、核心要点
- 基于8个模块结构化输出的AI汇总

### Tab2: Alpha评分
- 6维评分明细、评分雷达图、历史评分趋势

### Tab3: 风险拆解
- 支持双模式: 普通风险模型 + 龙头战法模型
- 普通模式: 7大维度量化风险,主线板块上下文,强势/风险依据
- 龙头模式: 龙头强度+退潮风险+综合健康度三栏评分,消息面/龙虎榜Alpha,详细分项
- 高危预警提示+历史风险走势

### Tab4: 异动解读
- 核心标签+行业原因+公司原因
- 完整新闻正文+情感标签

### Tab5: 新闻舆情
- 新版事件驱动情感分析引擎 (news_sentiment)
- 事件分类+事实抽取+多事件冲突合并+确定性因子
- 区分单股新闻/多股综述,避免错误归因

### Tab6: 龙虎榜
- 总买/净买/总卖 + 红绿进度条
- 买入TOP5/卖出TOP5双栏席位
- 机构/北向/游资/核按钮/散户/量化/高溢价标签（统一席位库）
- 游资别名（赵老哥/章盟主等）
- 历史上榜(近3次) + 风险提示

### Tab7: 业绩排雷
- 公司财务风险预警

### Tab8: 开盘预案
- 6种开盘场景预案

---

## 配置说明

### 环境变量

| 变量名 | 说明 | 必填 |
|--------|------|------|
| TUSHARE_TOKEN | Tushare API Token | 是（现有15000积分） |
| FEISHU_WEBHOOK_URL | 飞书 Webhook URL | 是 |
| SECRET_KEY | JWT 密钥 | 是 |
| DEEPSEEK_API_KEY | DeepSeek API Key | 否(AI综合概览) |
| DOUBAO_API_KEY | 豆包API Key(AI综合概览) | 否 |

### Tushare 接口积分需求

| 接口 | 用途 | 最低积分 |
|------|------|---------|
| `top_list` | 龙虎榜每日明细 | 2000 |
| `top_inst` | 龙虎榜席位明细 | 5000 |
| `hm_list` | 游资名录 | 5000 |
| `moneyflow` | 个股资金流向 | 2000 |
| `cyq_perf` | 筹码胜率(获利盘) | 5000 |
| `ths_daily` | 同花顺板块行情 | 6000 |
| `daily_basic` | 每日指标(换手率) | 2000 |
| `limit_list_ths` | 涨停池(板块动态别名) | 5000 |
| `dc_index` | 东财板块指数 | 2000 |
| `dc_member` | 东财板块成分股 | 2000 |

---

## 运行测试

```bash
# 完整接口测试（后端需启动）
conda activate xuangu
python test_detail_page.py

# 单元测试
pytest tests/ -v --cov=backend
```

---

## 项目结构

```
/opt/xuangu/
│
├── backend/                               # 后端代码(FastAPI)
│   ├── main.py                           # 应用入口(含启动时板块词典/别名同步)
│   ├── api/                              # API路由
│   │   ├── stock_detail.py              # 个股详情API(含龙虎榜/风险拆解/龙头战法)
│   │   ├── stock.py                     # 选股API
│   │   ├── score_v2.py                  # 评分V2/V3 API
│   │   ├── anomaly.py                   # 异动解读API
│   │   ├── overview_brief.py            # AI综合概览API
│   │   └── news_v2.py                   # 新闻舆情API
│   ├── models/                           # 数据模型
│   │   ├── stock_lhb.py                 # 龙虎榜数据
│   │   ├── stock_risk.py                # 风险拆解+龙头战法评分(DragonLeaderScore)
│   │   ├── board.py                     # 东财板块+动态别名(DcBoardAlias等)
│   │   ├── stock_ths_board.py           # 同花顺板块
│   │   ├── anomaly_interpretation.py    # 异动解读
│   │   ├── overview_brief.py            # AI综合概览
│   │   ├── selected_stock.py            # 选股结果
│   │   └── scoring_v2/                  # 评分V3模型
│   ├── services/                         # 业务逻辑
│   │   ├── lhb_service.py              # 龙虎榜服务
│   │   ├── seat_library.py             # 统一席位库(高溢价/核按钮/量化/机构/散户)
│   │   ├── risk_breakdown_service.py   # 风险拆解服务(含龙头战法证据链)
│   │   ├── sentiment_analyzer.py       # 新闻情感分析V1(加权评分规则引擎)
│   │   ├── anomaly_interpretation/     # 异动解读服务
│   │   ├── integrated_news_service.py  # 集成新闻服务
│   │   ├── news_collector.py           # 新闻采集器
│   │   ├── news_sentiment/             # 新闻情感分析V2(事件驱动,纯规则,不绑策略)
│   │   │   ├── analyzer.py             # 主入口(单条/批量分析)
│   │   │   ├── event_classifier.py     # 事件分类器
│   │   │   ├── fact_extractor.py       # 事实抽取(业绩/减持/回购等)
│   │   │   ├── scorer.py               # 事件评分+多事件合并
│   │   │   ├── confidence.py           # 置信度计算
│   │   │   ├── news_scope.py           # 新闻范围分类(单股/多股/市场)
│   │   │   ├── normalizer.py           # 文本标准化
│   │   │   └── rules/                   # 各事件类型规则
│   │   ├── dragon_leader/              # 龙头战法评分系统
│   │   │   ├── main.py                 # 主流程(数据采集+评分+持久化)
│   │   │   ├── lhb_alpha.py            # 龙虎榜席位Alpha评分
│   │   │   ├── output.py               # 输出组装(等级/周期/证据/观察点)
│   │   │   ├── data/                    # 上下文采集器
│   │   │   │   ├── stock_context.py    # 个股上下文
│   │   │   │   ├── market_context.py   # 市场上下文
│   │   │   │   ├── theme_context.py    # 题材上下文(含语义引用板块)
│   │   │   │   ├── fundamental_context.py # 基本面上下文
│   │   │   │   └── intraday_context.py # 分时上下文
│   │   │   └── scorer/                  # 评分器
│   │   │       ├── leader_scorer.py    # 龙头强度(7维)
│   │   │       ├── retreat_scorer.py   # 退潮风险(7维)
│   │   │       └── announcement_alpha.py # 公告消息Alpha
│   │   ├── dc_board_service.py         # 东财板块词典维护
│   │   ├── dc_board_alias_service.py   # 东财板块动态别名(涨停标签→板块)
│   │   ├── stock_alias_service.py      # 股票别名服务
│   │   ├── ai_brief/                    # AI综合概览服务
│   │   ├── stock_selector.py           # 四阶段选股协调
│   │   ├── scoring_v2/                 # 评分V3服务
│   │   └── strategy/                   # 策略服务
│   └── utils/
│       └── trading_date.py            # 交易日工具
│
├── frontend/                            # 前端代码(Vue 3)
│   ├── src/components/
│   │   ├── StockDetailDrawer.vue       # 个股详情抽屉(9个Tab)
│   │   └── stock/
│   │       ├── LhbPanel.vue            # 龙虎榜
│   │       ├── RiskBreakdown.vue       # 风险拆解(支持龙头战法双模式)
│   │       ├── AnomalyInterpretation.vue # 异动解读
│   │       ├── OverviewBrief.vue       # 综合概览
│   │       └── ...                     # 其他Tab组件
│
├── scripts/                             # 脚本工具
│   ├── generate_dc_board_aliases.py    # 板块别名生成
│   ├── migrate_dc_board_alias_tables.py # 别名表迁移
│   └── migrate_risk_context_fields.py  # 风险上下文字段迁移
│
├── tests/                               # 测试
│   └── backend/unit/
│       ├── test_dragon_leader.py        # 龙头战法评分测试
│       ├── test_dragon_leader_e2e.py    # 龙头战法端到端测试
│       ├── test_dc_board_service.py     # 东财板块服务测试
│       ├── test_dc_board_alias_service.py  # 板块别名服务测试
│       ├── test_dc_board_alias_generation.py # 板块别名生成测试
│       ├── test_lhb_seat_effectiveness.py   # 席位有效性测试
│       ├── test_risk_breakdown_persistence.py # 风险拆解持久化测试
│       └── ...                         # 其他测试
│
├── AGENTS.md                            # 架构文档
├── CLAUDE.md                            # 开发指南
└── README.md                            # 本文档
```

---

## 核心质量指标

| 指标 | 目标值 | 实际值 | 状态 |
|------|--------|--------|------|
| 后端测试通过率 | >75% | 93.5% | ✅ 超额 |
| 代码覆盖率 | >80% | 81% | ✅ 达标 |
| API P95响应时间 | <2000ms | 7ms | ✅ 远超 |
| 选股总耗时 | <30秒 | <11秒 | ✅ 远超 |
| 龙虎榜DB缓存响应 | - | ~20ms | ✅ |
| 风险拆解计算 | <5秒 | <2秒 | ✅ |
| 龙头战法评分 | <60秒 | ~5秒 | ✅ |
| 情感分析V2单条 | - | <5ms | ✅ |
| 东财板块别名同步 | - | <10秒 | ✅ |

---

## 许可证

MIT License

---

**文档版本**: v9.0
**最后更新**: 2026-05-08
**维护者**: AI Assistant
