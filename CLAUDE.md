# CLAUDE.md - 选股通知系统开发指南

## 项目概述

| 属性 | 值 |
|------|-----|
| **项目名称** | 选股通知系统 (Stock Selector Notification System) |
| **项目类型** | 量化选股 + AI分析 + 通知推送系统 |
| **当前版本** | v6.0 (四阶段选股 + AI分析 + 新闻舆情 + 龙虎榜 + 风险拆解 + 龙头战法 + 默认竞价接力三目标 + 模型中心已完成) |
| **最后更新** | 2026-05-17 |
| **项目成熟度** | ⭐⭐⭐⭐⭐ (5/5 星 - 生产就绪) |

---

## 通用开发指导原则

### 1. 先思考再编码

**不要假设。不要隐藏困惑。把权衡摆上台面。**

在实现之前：
- 明确陈述你的假设。如果不确定，就询问。
- 如果存在多种解读方式，都摆出来 - 不要默默选择。
- 如果有更简单的方法，就说出来。有理由时就反驳。
- 如果有什么不清楚，停下来。说出哪里困惑。然后询问。

### 2. 简单优先

**用最少的代码解决问题。不做投机的事。**

- 不添加超出要求的功能。
- 不为单次使用的代码做抽象。
- 不做未被要求的"灵活性"或"可配置性"。
- 不为不可能发生的场景做错误处理。
- 如果你写了200行而其实50行就能搞定，重写它。

问问自己："一个资深工程师会不会说这太复杂了？"如果是，就简化。

### 3. 精准修改

**只触碰你必须触碰的。只清理你自己造成的混乱。**

修改现有代码时：
- 不要"改进"相邻的代码、注释或格式。
- 不要重构没有坏的东西。
- 遵循现有风格，即使你有不同的做法。
- 如果你发现不相关的死代码，提出来 - 但不要删除它。

当你的修改造成无主资源时：
- 移除你的修改造成的未使用的导入/变量/函数。
- 不要删除原先就存在的死代码，除非被要求。

检验标准：每一行修改都应该能直接追溯到用户的需求。

### 4. 目标驱动执行

**定义成功标准。循环直到验证通过。**

将任务转化为可验证的目标：
- "添加验证" → "为无效输入编写测试，然后让它们通过"
- "修复bug" → "编写能复现问题的测试，然后让它通过"
- "重构X" → "确保测试在重构前后都通过"

对于多步骤任务，陈述简要计划：
```
1. [步骤] → 验证: [检查项]
2. [步骤] → 验证: [检查项]
3. [步骤] → 验证: [检查项]
```

强有力的成功标准让你能独立循环。软弱的标准（"让它跑起来"）需要不断澄清。

---

## 项目特定开发规范

### 5. 四阶段选股架构规范

**严格分离原则**

| 阶段 | 允许调用 | 禁止调用 | 核心职责 |
|------|----------|----------|----------|
| 阶段1 (选股) | 通达信MCP | Tushare | 服务端筛选，一次查询完成 |
| 阶段2 (分析) | Tushare | 通达信MCP | 补充数据 + 昨涨幅/开涨幅计算 |
| 阶段3 (封板率) | Tushare | 通达信MCP | 触板天数/封板天数/封板率计算 |
| 阶段4 (评分) | Tushare/DeepSeek | 通达信MCP | Alpha评分 + 风险拆解 + 决策引擎 |

### 6. MCP接口使用规范

**⚠️ 重要：数值格式要求**

```python
# ✅ 正确：整数格式
"竞价量占昨日成交量比例4%到30%"
"竞价换手率0.5%到10%"

# ❌ 错误：小数格式
"竞价量占昨日成交量比例4.0%到30.0%"
"竞价换手率0.5%到10.0%"
```

**支持的查询复杂度**
- ✅ 支持8个条件的复杂查询
- ✅ 服务端筛选，效率极高 (<1秒)
- ✅ 使用JSON-RPC协议格式

### 7. 评分系统V3开发规范

**模块位置**
- 评分引擎: `backend/services/scoring_v2/`
- 数据模型: `backend/models/scoring_v2/`
- API接口: `backend/api/score_v2.py`

**Alpha评分6维度**
- 趋势强度: 近20日/60日趋势强度
- 动量质量: 涨停质量+量价配合+高开意愿
- 资金热度: 竞价资金+主力流入
- 估值水位: 历史百分位+行业相对
- 基本面锚定: 营收/利润/ROE
- 事件催化: 公告/新闻/研报

**决策引擎**
- 最终评级: A+ / A / A- / B+ / B / B- / C+ / C / C- / D
- 操作建议: 立即介入 / 可考虑介入 / 观望 / 暂不介入 / 坚决回避
- 介入等级: 1-5级

### 8. AI综合概览开发规范

**模块位置**
- 核心服务: `backend/services/ai_brief/`
- 数据模型: `backend/models/overview_brief.py`
- API接口: `backend/api/overview_brief.py`

**输出结构**
- 三句话速览: 一句话标的、一句话走势、一句话策略
- 关键数据卡片: 7项核心数据
- 多维度评分: Alpha评分+风险评级
- 技术面看点: 3点+
- 资金面看点: 3点+
- 消息面看点: 3点+
- 风险提示: 3点+
- 操作建议: 3档+

**降级策略**
- 优先使用AI生成
- AI失败时使用本地模板
- 状态管理: available/partial/fallback_generated/pending/ai_disabled

### 9. 同花顺式异动解读开发规范

**模块位置**
- 核心服务: `backend/services/anomaly_interpretation/`
- 数据模型: `backend/models/anomaly_interpretation.py`
- API接口: `backend/api/anomaly.py`

**数据源**: 复用 `integrated_news_service`（从新闻数据库读取，非Tushare API直连）

**输出结构**
- 核心标签: 最多3个核心标签（用+连接）
- 异动原因: 行业原因+公司原因
- 近期新闻: 近3个交易日新闻筛选

**AI输出验证规则**
- ❌ 禁止编造数据（空值保留空值）
- ❌ 禁止使用保证性词汇（"必将"、"肯定"、"绝对"）
- ✅ 必须包含免责声明
- ✅ 输出必须JSON可解析

### 10. 情感分析模块开发规范

系统有两套情感分析引擎，适用不同场景：

#### 10.1 SentimentAnalyzer V1（加权评分规则引擎）

**模块位置**: `backend/services/sentiment_analyzer.py`

**算法**: 加权评分制规则引擎，非简单关键词计数

**判定维度**:
- 利空模式 40+条（加权权重 0.5~1.0），标题内权重 ×1.5
- 利好模式 35+条（加权权重 0.5~1.0），标题内权重 ×1.5

**核心流程**:
```
text = title + content
  1. 检查否定词（前5字内检测）→ 命中则权重 ×0.2
  2. 匹配利空模式 → 累加负分
  3. 匹配利好模式 → 累加正分
  4. 标题加权 ×1.5
  5. 判断: 负分≥2.0 且 ≥正分×1.5 → negative
          正分≥2.0 且 ≥负分×1.5 → positive
          否则 → neutral
```

**前置过滤**:
- 技术面词汇（涨停/连板/跌停等）→ 直接 neutral
- 大盘/市场新闻（命中≥2个市场词）→ 直接 neutral

**调用时机**: 查询时实时判断（在 `integrated_news_service.get_stock_news_from_db()` 中），不入库，规则更新立即生效

#### 10.2 News Sentiment V2（事件驱动情感分析）

**模块位置**: `backend/services/news_sentiment/`

**定位**: 独立的纯规则事件驱动情感判定底层模块，不调用AI大模型，不绑定任何策略。

**算法**: 事件识别 → 事实抽取 → 单事件评分 → 多事件冲突合并 → 确定性因子调整 → 输出

**核心流程**:
```
news_item → normalize_text → classify_news_scope
  ├── multi_stock/market_overview → 局部上下文判断（不归因给单股）
  └── single_stock → classify_event_candidates → select_primary_event
       → extract_facts → score_event（单事件）
       → merge_event_scores（多事件冲突合并）
       → apply CERTAINTY_FACTOR（确定性因子 ×0.5~1.0）
       → 最终分数 [-5, +5]
       → sentiment + impact_level + confidence + risk_flags
```

**支持的事件类型**:
- performance（业绩预告/快报/年报）
- reduce_holding（减持）
- increase_holding（增持）
- buyback（股份回购）
- order_contract（重大合同/中标）
- unlock（解禁）
- restructure（重组）
- regulatory（监管/处罚）
- process（诉讼/立案/停产）

**新闻范围分类**（关键安全机制）:
- `single_stock`: 单股新闻，正常事件识别
- `multi_stock`: 多股盘面综述，检查目标股票被提及情况，不做利好/利空归因
- `market_overview`: 大盘综述，直接 neutral

**确定性因子**（影响最终分数）:
- `completed`(已完成): ×1.0
- `forecast`(预计): ×0.7
- `planned`(拟): ×0.6
- `preliminary`(筹划): ×0.5
- `framework`(框架协议): ×0.5
- `uncertain`(存在不确定性): ×0.5

**调用者**: `dragon_leader/main.py::collect_news()`, `stock_detail.py::get_stock_news()`

**与V1的关系**: V2 替换 V1 用于龙头战法和新版API；V1 继续用于 integrated_news_service 中的旧版查询路径。两套引擎独立维护。

### 11. 龙虎榜模块开发规范

**模块位置**
- 核心服务: `backend/services/lhb_service.py`
- 统一席位库: `backend/services/seat_library.py`
- 数据模型: `backend/models/stock_lhb.py`
- 前端组件: `frontend/src/components/stock/LhbPanel.vue`

**数据接口**（Tushare，需15000积分全可用）:
| 接口 | 用途 | 最低积分 |
|------|------|---------|
| `top_list` | 龙虎榜每日明细（上榜日、涨幅、成交额、净买入） | 2000 |
| `top_inst` | 席位买卖明细（营业部、买入额、卖出额、净买额） | 5000 |
| `hm_list` | 游资名录（用于营业部→游资别名匹配） | 5000 |

**统一席位库标签体系** (`seat_library.py`):

| 标签类别 | 函数 | 代表席位 |
|---------|------|---------|
| 高溢价游资 | `is_premium_seat()` | 相城大道、大连黄河路、南京汉中路 |
| 机构/北向 | `is_institutional_seat()` | 机构专用、沪股通、深股通 |
| 核按钮 | `is_knock_seat()` | 长城仙桃钱沟路、华泰成都南一环路 |
| 散户 | `is_scatter_seat()` | 东方财富拉萨系列、同花顺分公司 |
| 量化 | `is_quant_seat()` | 华鑫上海分公司、中金上海分公司 |
| 一线游资 | `match_seat_tag()` | 华泰深圳益田路、中信杭州延安路等 |

`seat_library.py` 是 `lhb_service`、`risk_breakdown_service`、`dragon_leader/lhb_alpha` 的共用席位判断底层。

**游资别名匹配**: 调用 `hm_list` 接口建立营业部→游资名称反向映射，精确+子串双匹配

**行为判定规则**:
```
净买入>0 且 买入/卖出 > 1.8 → 一致抢筹
净买入>0 且 买入/卖出 > 1.2 → 温和抢筹
|净买入| < 500万            → 主力分歧
净买入<0 且 卖出/买入 > 1.5 → 一致砸盘
```

**预加载**: 选股完成后后台线程批量预热（5线程池），写入 DB 永久存储

### 12. 风险拆解模块开发规范

**模块位置**
- 核心服务: `backend/services/risk_breakdown_service.py`
- 数据模型: `backend/models/stock_risk.py`
- 前端组件: `frontend/src/components/stock/RiskBreakdown.vue`

**7大维度**（总分100分，纯规则计算，无AI）:

| 维度 | 满分 | 数据源 | 所需积分 |
|------|------|--------|---------|
| 市场环境 | 10 | Tushare `daily_basic(turnover_rate)` + `daily(high/low/pre_close)` — 昨日数据 | 2000 |
| 筹码压力 | 14 | Tushare `cyq_perf(winner_rate)` + `rise_10d_pct` | 5000 |
| 舆情与公告 | 18 | `integrated_news_service` 新闻关键词匹配（减持/立案/亏损等） | 0 |
| 个股资金 | 14 | Tushare `moneyflow(net_mf_amount)` | 2000 |
| 龙虎风险 | 10 | `lhb_service(risk_tips/action_tag)` + 席位净买卖方向判定 | 已有 |
| 板块与题材风险 | 18 | Tushare `ths_daily(板块行情)` + 东财板块上下文 | 6000 |
| 技术结构 | 16 | 炸板/竞价低预期等技术面风险 | 已有 |

**龙虎风险增强**: 席位判定现在考虑净买方向：
- 高溢价席位净买入 → 风险减分（进入强势依据）
- 高溢价席位净卖出 → 风险加分
- 核按钮/量化/散户净买入 → 风险减分（进入强势依据）
- 核按钮/量化/散户净卖出 → 风险加分

**数据库新增字段**（v5.2）:
- `sector_context`: 东财板块上下文(JSON) — 主线板块名+涨跌+资金+涨停家数+强度
- `lhb_strength_evidence`: 龙虎榜强势席位证据(JSON)
- `lhb_risk_evidence`: 龙虎榜风险席位证据(JSON)
- `strength_evidence`: 用户可见强势依据(JSON)
- `risk_evidence`: 用户可见风险依据(JSON)

**等级判定**:
```
≤20 低 / ≤40 中 / ≤70 高 / >70 极高
```

**API支持双模式**:
- `strategy_type=normal`（默认）: 普通7维度风险模型
- `strategy_type=dragon_leader`: 龙头战法评分模型

### 13. 龙头战法评分开发规范

**模块位置**
- 核心服务: `backend/services/dragon_leader/`
- 数据采集: `dragon_leader/data/` (stock/market/theme/fundamental/intraday)
- 评分器: `dragon_leader/scorer/` (leader_scorer/retreat_scorer/announcement_alpha)
- 龙虎榜Alpha: `dragon_leader/lhb_alpha.py`
- 输出组装: `dragon_leader/output.py`
- 数据模型: `backend/models/stock_risk.py::DragonLeaderScore`
- API接入: `backend/api/stock_detail.py::get_stock_risk(strategy_type="dragon_leader")`

**三核心分数**:
| 分数 | 满分 | 构成 |
|------|------|------|
| 龙头强度 | 100 | 龙头地位25+题材强度20+情绪周期15+板块梯队15+承接强度10+竞价分时10+龙虎榜加成5 |
| 退潮风险 | 100 | 龙头地位动摇20+情绪退潮20+板块梯队断裂15+承接失败15+筹码兑现10+竞价低预期10+公告监管10 |
| 综合健康度 | 100 | 龙头强度×0.6 + 退潮风险×(-0.3) + 公告Alpha×0.5 + 龙虎榜Alpha×0.5 + 基准分20 |

**Alpha调整**:
- 公告Alpha: [-20, +20] — 使用 `news_sentiment` V2引擎分析利好/利空
- 龙虎榜Alpha: [-20, +20] — 使用 `seat_library` 统一席位库判断买卖方向

**等级体系**:
- 龙头等级: 极强龙头(≥85) / 强势龙头(≥70) / 疑似龙头(≥55) / 跟风强势股(≥40) / 非龙头
- 周期阶段: 主升期 / 分歧期 / 退潮期 / 混沌期 / 震荡期
- 健康等级: 龙头健康(≥80) / 强势可观察(≥65) / 分歧加大(≥50) / 退潮预警(≥35) / 回避

**权重配置**: `dragon_leader/config.yaml`，不存在时使用 `DRAGON_LEADER_WEIGHTS` 默认值

**缓存策略**: 优先从 `dragon_leader_score` 表读DB缓存，传 `force_refresh=true` 强制重算。非强制刷新时直接返回缓存结果。

### 14. 东财板块动态别名开发规范

**模块位置**
- 核心服务: `backend/services/dc_board_alias_service.py`
- 板块服务: `backend/services/dc_board_service.py`
- 数据模型: `backend/models/board.py` (DcBoardAlias/DcBoardAliasObservation/DcBoardAliasSyncState)
- 生成脚本: `scripts/generate_dc_board_aliases.py`

**定位**: 每个交易日从涨停池 `limit_list_ths` 抓取涨停标签(`lu_desc`)，匹配东财板块词典，自动建立板块别名映射。

**核心流程**:
```
1. fetch_dc_boards → 获取东财板块词典
2. limit_list_ths(trade_date, limit_type="涨停池") → 获取涨停标签
3. split_lu_desc_tags → 拆分标签（按+号切分）
4. score_tag_board_match → 标签与板块名称模糊匹配+语义相似度评分
5. 写入 dc_board_alias_observation（单日命中明细，唯一键去重）
6. 汇总 dc_board_alias → 更新命中次数/股票数/置信度
7. auto_approved(≥阈值) / pending_review(<阈值)
8. 清除 dc_board_service 缓存，下次读取即生效
```

**别名审核状态**:
- `auto_approved`: 自动批准（置信度≥阈值）
- `pending_review`: 待人工审核
- `manual`: 人工确认
- `reviewed`: 已审核
- `rejected`: 已拒绝（is_active=False）

**启动时同步**: `main.py::lifespan` 中，启动时自动同步最新交易日数据，盘后(15:30后)标记 finalized

**运行期生效**: `DcBoardService._get_board_aliases()` 合并手写别名(`MANUAL_BOARD_ALIASES`)和动态别名(`DcBoardAliasService.get_active_aliases()`)

### 15. LightGBM模型模块开发规范

**模块位置**
- 模型引擎: `backend/services/model_engine/lightgbm_service.py`
- 特征构建: `backend/services/backtest/leader_main_t0_feature_builder.py`
- 标签生成: `backend/services/backtest/leader_main_t0_label_builder.py`
- 竞价数据: `backend/services/auction_data_service.py`
- 回测API: `backend/api/backtest.py`
- 选股集成: `backend/services/stock_selector.py`
- 训练脚本: `scripts/train_leader_main_t0_pipeline.py`
- 数据模型: `backend/models/auction_backtest.py` (StockAuctionOpen + LeaderMainT0TrainingSample)
- 版本管理: `backend/models/stock_feature_snapshot.py` (ModelVersion)
- 模型文件目录: `backend/models/` (*.pkl)

**双模型架构**:

| 属性 | `active_auction_lgbm` | `leader_main_t0_lgbm` |
|------|----------------------|----------------------|
| 用途 | 竞价活跃度综合评分 | 龙头股T+0封板概率 |
| 特征数 | 8维 | **9维** (v2026-05精简) |
| 数据源 | StockFeatureSnapshot | LeaderMainT0TrainingSample |
| 影响final_score | ✅ 权重35% | ✅ 权重10% |
| 预测写入字段 | `model_score` | `t0_limit_success_prob` |
| 版本管理 | 文件名+ModelVersion表 | ModelVersion表(is_active标记) |

**龙头T+0模型9维特征**（v2026-05 从13维精简）:
```
limit_up_streak         — 连续涨停天数（龙头核心标识）
limit_up_count_100d     — 近100日涨停次数
seal_rate_100d          — 近100日封板率(%)
rise_10d_pct            — 近10日涨幅(%)
pre_change_pct          — 昨日涨跌幅(%)
open_change_pct         — 今日开盘涨幅(%)
auction_ratio           — 竞昨比（小数，如 0.08 = 8%）
auction_turnover_rate   — 竞价换手率（%，如 1.64 = 1.64%）
circ_mv                 — 流通市值(亿)
```

**已移除的4维及原因**（不能加回来除非数据条件改善）:
- `market_height_rank` — 与 limit_up_streak 高度共线（连板天数直接决定排名）
- `rise_5d_pct` — 与 rise_10d_pct 部分共线（5天包含在10天内）
- `sector_change_pct` — 数据源不稳定，常默认填0，模型无法学到有效信号
- `sector_limit_up_count` — 同上

**核心公式**:

竞昨比 `auction_ratio`:
```
auction_ratio = 竞价成交量(股) / T-1日成交量(股) → 小数，如 0.08 表示 8%
```
- Tushare `stk_auction.vol` → 股；Tushare `daily.vol` → **手**，需 ×100 转股
- `.day` 文件 `vol` 解析时 `/100` → **手** (TDX_VOL_TO_TUSHARE_VOL_SCALE=100)
- `StockDailyData.vol` → **手**（与 Tushare daily.vol 格式一致）
- **两条数据路径都需在调用 `calculate_auction_metrics` 前将分母 ×100 转为股！**
  - Tushare同步路径: `sync_auction_open()` 中 `prev_volume = {k: v*100 ...}`
  - .day重算路径: `recalculate_auction_ratios_from_daily_cache()` 中 `prev_volume = {k: row.vol*100 ...}`

竞价换手率 `auction_turnover_rate`:
```
auction_turnover_rate = 竞价量(股) / (流通股本(万股) × 10000) × 100 → 百分比，如 1.64 表示 1.64%
```
- 优先用 `free_share`，缺失降级 `float_share`（Tushare daily_basic，单位万股）

**DEFAULT_CONFIG 过滤器阈值**（`leader_main_t0_feature_builder.py`）:
- `min_auction_ratio=0.04, max_auction_ratio=0.30` — 适配小数格式（4%~30%）
- `min_auction_turnover_rate=0.5, max_auction_turnover_rate=10` — 百分比格式（0.5%~10%）
- **⚠️ 如果改了竞昨比公式的输出格式，必须同步改 DEFAULT_CONFIG 和 RuleScoreService 阈值**

**RuleScoreService 竞昨比阈值**（`rule_score_service.py::score_auction_momentum`）:
```python
>= 0.20 → 极高(15分); >= 0.10 → 较高(12分); >= 0.05 → 适中(8分)
>= 0.03 → 较低(5分);  < 0.03 → 偏低(2分)
# 显示时需 ×100: f"{auction_ratio * 100:.2f}%"
```

**T+0标签定义**（`leader_main_t0_label_builder.py`）:
```
一字板: open>=limit*0.997 AND high>=limit*0.997 AND low>=limit*0.997 AND close>=limit*0.997
  → label_t0_limit_success = NULL （排除出训练集）

非一字板 + 最高价触板 + 收盘封板:
  high >= limit*0.997 AND close >= limit*0.997
  → label = 1 （T+0封板成功）

其他 → label = 0 （失败）
```
涨停价: 300/301/688/689开头 → 20%；其他 → 10%

**训练管线**（6步，必须按序执行，可用 `scripts/train_leader_main_t0_pipeline.py` 一键运行）:
```
1. 同步集合竞价数据   → AuctionDataService.sync_auction_open_date_range()
2. 同步本地日线数据   → TdxLocalDailySyncService.sync_range()
3. 重算竞昨比         → AuctionDataService.recalculate_auction_ratios_from_daily_cache()
4. 构建候选股特征     → LeaderMainT0FeatureBuilder.build_leader_main_t0_range()
5. 生成T+0标签        → LeaderMainT0LabelBuilder.build_leader_main_t0_labels()
6. 训练模型           → train_leader_main_t0_lgbm()
```
⚠️ Step 3 必须在 Step 1 之后运行——重算路径用 StockDailyData.vol 修正 Tushare 路径的竞昨比。

**候选股过滤规则**（`DEFAULT_CONFIG`）:

| 条件 | 阈值 | 备注 |
|------|------|------|
| 流通市值 | < 2000亿 | |
| 收盘价 | < 500元 | |
| 近10日涨幅 | > 0 | |
| 近100日涨停次数 | >= 3 | |
| 封板率 | >= 80% | |
| 开盘涨幅 | >= -3% | |
| 竞昨比 | 0.04~0.30 (小数) | 对应4%~30%，格式变更于2026-05 |
| 竞价换手率 | 0.5%~10% | 百分比格式 |
| 非ST/非停牌/非北交所 | 必须 | |

**模型超参数**:
```python
LGBMClassifier(
    objective='binary', boosting_type='gbdt',
    learning_rate=0.05, num_leaves=31,
    n_estimators=500, subsample=0.8, colsample_bytree=0.8,
    metric='auc', random_state=42, verbose=-1,
    is_unbalance=True,  # v2026-05: 自动处理正负样本不均衡
)
# early_stopping=50, 数据分割70/20/10(按时间顺序)
# 滚动窗口CV: 3折时间序列, min_train=30, min_test=5
```

**预测集成至选股管线**（`stock_selector.py::_merge_and_score_candidates`）:
```
Phase A: 规则评分 (RuleScoreService) → rule_score
Phase B: 按 rule_score 降序排序
Phase C: batch_predict_before_selection() → model_score
Phase D: batch_predict_leader_main_t0() → t0_limit_success_prob
Phase E: final_score = rule_score*0.55 + model_score*0.35 + t0_prob*0.10
         (任一模型不可用时按权重归一化)
Phase F: 评分等级分配 + 持久化至 SelectedStock
```

**模型版本管理**:
- 每次训练生成 `leader_main_t0_lgbm_{YYYYMMDD_HHMMSS}.pkl`
- DB `model_version` 表: model_name, version, feature_cols(JSON), model_path, metrics(JSON), is_active, params(JSON)
- 新版本激活时旧版本自动 `is_active=0`
- `batch_predict_model()` 从 `ModelVersion` 读取活跃模型的特征列（不硬编码）
- `batch_predict_before_selection()` 硬编码 `FEATURE_COLS`（8列，遗留设计）

**夜间自动训练**: `nightly_train()` 同时训练两个模型，覆盖近2年数据。

**SHAP 可解释性**:
- `_compute_shap_importance(model, X, feature_cols)` — 训练后计算 mean|SHAP| 存入 metrics
- `explain_leader_main_t0_prediction(features)` — 单预测特征贡献解释
- `shap` 为可选依赖，不可用时 SHAP 指标为 None，不影响训练和预测

**当前模型指标**（v20260510_040441, 2026-05-10训练）:
| 指标 | 值 |
|------|-----|
| 训练样本 | 2154 (正687/负1467) |
| AUC | 0.6957 |
| CV AUC (3折) | 0.671 ± 0.038 |
| Precision@0.25 | 0.39 |
| Recall@0.25 | 0.84 |
| Top SHAP特征 | open_change_pct(0.41), auction_turnover_rate(0.28), pre_change_pct(0.11) |

**⚠️ 注意事项**:
- `is_unbalance=True` 会压低概率输出，默认0.5阈值下 Precision/Recall 不理想，需从 `threshold_evaluation` 选最优阈值（推荐 0.25~0.30）
- `batch_predict_before_selection` 硬编码 `FEATURE_COLS`（8列），不从 `ModelVersion` 读取（遗留设计）
- `.day` 文件数据单位: 成交量需 `/100`(转手)，成交额需 `/1000` — `StockDailyData.vol` 是**手**
- `joblib` 为可选依赖，缺失时所有预测返回 `None`，不影响核心选股
- `shap` 为可选依赖，缺失时 SHAP 指标为 None
- T+0免责声明: `"T+0成功率由历史样本模型估算，仅作排序参考，不构成投资建议"`
- 训练管线脚本: `scripts/train_leader_main_t0_pipeline.py --start YYYYMMDD --end YYYYMMDD`

**API端点**:
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/model/status` | GET | 活跃模型版本/特征列/评估指标 |
| `/api/v1/backtest/leader-main-t0/run` | POST | 一键完整管线 |
| `/api/v1/backtest/leader-main-t0/build` | POST | 构建训练样本 |
| `/api/v1/backtest/leader-main-t0/labels` | POST | 生成标签 |
| `/api/v1/backtest/leader-main-t0/train` | POST | 训练模型 |
| `/api/v1/backtest/leader-main-t0/samples` | GET | 分页查询样本 |
| `/api/v1/backtest/auction/sync` | POST | 单日竞价同步 |
| `/api/v1/backtest/auction/sync-range` | POST | 区间竞价同步 |
| `/api/v1/backtest/tdx-local-daily/sync` | POST | 本地日线同步 |

### 16. 默认竞价接力V2与模型中心开发规范

**模块位置**
- 训练编排: `backend/services/model_engine/default_auction_relay_job_service.py`
- 单目标训练器: `backend/services/model_engine/default_auction_model_trainer.py`
- 评估器: `backend/services/model_engine/default_auction_model_evaluator.py`
- 归因服务: `backend/services/model_engine/default_auction_attribution_service.py`
- 样本构建: `backend/services/model_engine/default_auction_sample_builder.py`
- 标签辅助: `backend/services/model_engine/default_auction_label_builder.py`
- 历史回放: `backend/services/model_engine/default_auction_replay_service.py`
- 回放验收: `backend/services/model_engine/replay_validation_service.py`
- 模型管理: `backend/services/model_engine/model_management_service.py`
- 数据模型: `backend/models/default_auction_training_sample.py` + `backend/models/model_training_job.py`
- 模型文件: `backend/models/default_auction_{target}_{version}.pkl`
- API接入: `backend/api/model_management.py`
- 前端: `frontend/src/views/ModelCenter.vue`

**定位**: 基于LightGBM的默认竞价接力三目标预测系统。三模型分别预测T+0封板、T+1溢价、T+1连板，支持多参数配置轮训、自动验收闸门、原子激活。纯结构化特征(来自SelectedStock)，不引入新闻/公告/舆情/AI文本。

**三目标模型**:

| 子模型 | 模型名 | 标签列 | Top3 Lift | Top5 Lift | TopK正例 | AUC |
|--------|--------|--------|-----------|-----------|---------|-----|
| T+0封板 | `default_auction_t0_limit_lgbm` | `label_t0_limit_success` | ≥0.08 | ≥0.05 | ≥20 | ≥0.55 |
| T+1溢价 | `default_auction_t1_premium_lgbm` | `label_t1_premium_success` | ≥0.10 | ≥0.06 | ≥25 | ≥0.55 |
| T+1连板 | `default_auction_t1_continue_lgbm` | `label_t1_continue_limit` | ≥0.06 | ≥0.04 | ≥10 | ≥0.53 |

**14维特征** (`DEFAULT_AUCTION_FEATURES`):
```python
DEFAULT_AUCTION_FEATURES = [
    "auction_ratio",          # 竞昨比
    "auction_turnover_rate",  # 竞价换手率
    "open_change_pct",        # 开盘涨幅
    "pre_change_pct",         # 昨涨幅
    "limit_up_count",         # 涨停次数
    "touch_days",             # 触板天数
    "limit_up_days",          # 涨停天数
    "seal_rate",             # 封板率
    "rise_10d_pct",           # 近10日涨幅
    "circ_mv",               # 流通市值
    "prev_turnover_rate",     # 昨日换手率
    "rule_score",            # 规则评分
    "final_score",           # 最终评分
    "risk_tags_count",       # 风险标签数
]
```

特征提取来源: 只读 `SelectedStock` 的结构化字段(18个 `FEATURE_FIELDS`)，纯结构化，不引入文本特征。

分类特征: `score_level`, `lu_tag`, `lu_status` → 自动 `ignored`，不进训练。

**三目标标签定义**:

T+0封板: 非一字板 + high≥limit×0.997 + close≥limit×0.997 → label=1，数据缺失→None

T+1溢价: T+1开盘≥3% 或 最高≥5% 或 收盘≥3% → label=1，数据全缺→None

T+1连板: T+1 high≥limit×0.997 + close≥limit×0.997 → label=1，数据缺失→None

一字板审计: `is_t0_one_line_limit_up` / `is_t1_one_line_limit_up` → 开/高/低/收全部≥涨停价×0.997

**5种参数配置** (`DEFAULT_PARAM_PROFILES`):

| 配置名 | lr | leaves | max_depth | reg_α | reg_λ | subsample | n_est |
|--------|-----|--------|-----------|-------|-------|-----------|-------|
| balanced_default | 0.05 | 31 | -1 | 0 | 0 | 0.8 | 500 |
| conservative_regularized | 0.03 | 15 | 4 | 0.1 | 1.0 | 0.75 | 500 |
| shallow_stable | 0.04 | 7 | 3 | 0.2 | 2.0 | 0.9 | 500 |
| wider_ranker | 0.02 | 63 | 6 | 0.05 | 0.5 | 0.8 | 700 |
| seed_retry | 0.03 | 15 | 4 | 0.1 | 1.0 | 0.75 | 500 |

全部 `is_unbalance=True`, `early_stopping_rounds=50`。

**训练流程** (6阶段):
```
1. 样本查询 → label_column IS NOT NULL + 日期区间
2. 特征质量 → build_feature_quality_report → usable_features
3. 时间切分 → trade_date 排序 70/15/15
4. 训练模型 → LGBMClassifier(is_unbalance=True)
5. TopK评估 → 按交易日分桶取每日top1/top3/top5
6. 验收闸门 → judge_target_acceptance
```

**TopK评估**: 按交易日分组，取每日概率降序 top1/top3/top5，计算各层正例率相对baseline_rate的lift。未知标签样本不进基准、胜率和TopK排名。

**训练任务编排**: `create_job → run_job → 逐目标轮训参数配置 → 全部通过验收 → (auto_activate?→原子激活 : passed)。任一目标未通过→rejected。异常→failed。

**原子激活**: 三模型最新通过版本预校验(版本存在+文件存在) → deactivate旧版本 → 激活新版本。校验不通过→rejected。

**回放验收**: real_codes vs replay_codes → daily recall/jaccard/count_error → min_avg_recall≥0.80 + min_avg_jaccard≥0.60 + max_count_error≤0.30 + 无重复代码 → accepted

**模型中心API** (基路径 `/api/v1/model`):
| 端点 | 方法 | 说明 |
|------|------|------|
| `/models` | GET | 活跃模型/特征/指标 |
| `/models/default-auction-replay/validate` | POST | 回放验收 |
| `/models/default-auction-samples/build` | POST | 构建训练样本 |
| `/models/default-auction-relay/train` | POST | 训练三目标(后台) |
| `/models/default-auction-relay/diagnostics/{job_id}` | GET | 训练诊断 |
| `/models/{model_name}/versions/{version}/activate` | POST | 激活版本 |
| `/models/{model_name}/training-jobs` | POST | 创建训练任务 |
| `/models/training-jobs/{job_id}` | GET | 任务状态 |
| `/models/{model_name}/refresh-predictions` | POST | 刷新预测 |

**SelectedStock新增预测字段**:
| 字段 | 来源模型 |
|------|---------|
| `default_t0_limit_prob` | T+0封板概率 |
| `default_t1_premium_prob` | T+1溢价概率 |
| `default_t1_continue_prob` | T+1连板概率 |
| `default_relay_score` | 综合评分 |
| `default_relay_model_version` | 版本号 |

**降级策略**: 模型文件或依赖缺失→预测值返回None。预测指标仅作排序参考，不构成投资建议。

**⚠️ 注意事项**:
- 特征提取只读SelectedStock结构化字段，不要引入news/announcement/sentiment/AI文本
- `is_unbalance=True` 压低概率输出，验收看TopK lift而非绝对概率
- 分类特征(score_level/lu_tag/lu_status)自动过滤，不要当数值特征传入
- `build_samples_from_selected_record` 按唯一约束upsert，不要直接merge
- 三目标训练串行执行，每个目标独立记录状态和日志
- 训练前确保标签非空样本≥50
- 回放验收仅比较代码集合，不比较排序
- 模型文件路径: `backend/models/{model_name}_{version}.pkl`

### 17. 代码规范

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

```json
{
  "code": 200,
  "message": "success",
  "data": {...},
  "timestamp": 1704300000
}
```

---

## 常见问题与解决方案

### 18. 故障排查指南

**Q1: MCP接口返回0条记录?**
```bash
# 检查数值格式
# ✅ 正确: "4%到30%"
# ❌ 错误: "4.0%到30.0%"
```

**Q2: pytest 找不到模块?**
```bash
export PYTHONPATH="${PYTHONPATH}$(pwd)"
pytest tests/backend/unit/ -v
```

**Q3: Tushare API 调用失败?**
检查 `.env` 文件中的 `TUSHARE_TOKEN` 是否正确配置。

**Q4: 飞书通知发送失败?**
检查 `FEISHU_WEBHOOK_URL` 是否为有效的飞书机器人 Webhook 地址。

**Q5: 龙虎榜返回500错误?**
检查 Tushare `top_list` / `top_inst` 接口的积分是否充足（至少2000/5000积分）。检查返回值中是否有 `numpy.float64` 等不可JSON序列化的类型（已通过 `_pyfloat()` + `_clean_nan()` 处理，如有问题查看 `_build_seat_tags_list` 中的数据转换）。

**Q6: 新闻情感分析不准?**
- V1: 检查 `sentiment_analyzer.py` 中的关键词库是否覆盖了相关场景。
- V2: 检查 `news_sentiment/event_classifier.py` 事件分类是否正确，以及 `news_scope.py` 是否正确区分单股/多股新闻。
- 两套引擎规则更新后立即生效，无需回填数据。

**Q7: 龙虎榜缓存不生效?**
首次调 Tushare API 取数成功后自动写入 `stock_lhb` 表，后续请求优先读 DB。如需强制刷新，传 `force_refresh=true` 参数。

**Q8: 风险拆解得分异常?**
检查各维度的输入数据是否完整：
- 市场环境：需 `daily_basic` 和 `daily` 接口权限
- 筹码压力：需 `cyq_perf` 接口（5000积分）
- 个股资金：需 `moneyflow` 接口（2000积分）
- 板块与题材风险：需 `ths_daily` 接口（6000积分）+ 东财板块数据
- 公告/龙虎：复用已有模块

**Q9: 龙虎榜买入/卖出金额为0?**
Tushare `top_inst` 接口可能需要5000积分，积分不足时返回空数据。此时系统会降级使用 `top_list` 的汇总数据。

**Q10: 游资别名不显示?**
需要调用 Tushare `hm_list` 接口（5000积分）建立营业部→游资映射。首次调用后缓存，重启服务后重新加载。

**Q11: 板块动态别名不准?**
- 检查 `dc_board_alias` 表 `review_status` 字段，`pending_review` 状态的别名不会在线上生效
- 置信度阈值见 `scripts/generate_dc_board_aliases.py` 中的 `AUTO_SCORE_THRESHOLD`
- 需要手动批准可改为 `manual` 或 `reviewed` 状态

**Q12: 龙头战法评分返回空?**
- 检查 `dragon_leader_score` 表中是否有缓存数据
- 确认个股基本信息（stock context）能正常获取
- 消息面和龙虎榜为可选数据源，缺失时不影响主评分

**Q13: LightGBM模型预测返回None?**
- 检查 `backend/models/` 目录下是否存在 `.pkl` 模型文件（当前: `leader_main_t0_lgbm_{timestamp}.pkl`）
- 检查 `joblib` 是否已安装（`pip install joblib`）
- 检查 `model_version` 表中是否有 `is_active=1` 的版本记录
- 模型不可用时不影响核心选股，`t0_limit_success_prob` 为 `None` 属正常降级
- 如果模型文件存在但预测仍返回 None，检查 `model_version.feature_cols` 是否与当前特征名匹配

**Q14: 竞昨比数值异常（过大或为0）?**
- 确认已运行 Step 3（重算竞昨比）— 两条数据路径(Tushare/.day)的 daily vol 都是**手**，需在 `calculate_auction_metrics` 前 ×100 转股
- 检查 `sync_auction_open` 中 `prev_volume` 是否做了 ×100 转换
- 检查 `recalculate_auction_ratios_from_daily_cache` 中 `prev_volume` 是否做了 ×100 转换
- 过滤器阈值 `DEFAULT_CONFIG.min_auction_ratio=0.04, max_auction_ratio=0.30` 适配小数格式
- `RuleScoreService.score_auction_momentum` 阈值也需同步更新（>=0.20, >=0.10, >=0.05, >=0.03）
- 候选股为0只的常见原因：竞昨比格式与过滤器阈值不匹配

**Q15: 默认竞价接力训练任务创建后状态一直是pending?**
- 检查 `run_default_auction_relay_training_job` 是否被 `BackgroundTasks` 正常调度
- 检查 `default_auction_training_sample` 表中是否有标签非空的训练样本(≥MIN_TRAINING_SAMPLES=50)
- 查看任务日志: `GET /api/v1/model/models/default-auction-relay/diagnostics/{job_id}`

**Q16: 默认竞价接力模型训练后验收未通过?**
- 查看 `acceptance_json` 中的 `reject_reasons` 字段，判断是哪个验收指标不达标
- TopK正例数不足: 检查正负样本比例，正例太少无法产生足够topk正例
- AUC低于阈值: 尝试增加训练样本量或切换参数配置
- TopK Lift不足: 模型排序能力弱，可能需要更多特征工程或更大样本量

**Q17: 回放验收不通过?**
- 检查 `reject_reasons`: avg_recall_below_threshold / avg_jaccard_below_threshold / daily_count_error_above_threshold / duplicate_codes_detected
- 检查回放数据源是否与真实选股使用相同的策略参数
- 检查重复代码: real_codes 或 replay_codes 中有重复的 ts_code

**Q18: 原子激活失败?**
- 检查 `activation.reject_reasons`: missing_version / version_not_found / model_file_missing
- 确认三目标的最新通过版本在 `model_version` 表中存在且 `model_path` 可访问
- 确认文件系统中模型文件未被人为删除或移动

---

## 开发工作流

### 19. 开发流程

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

**4. 提交规范**
遵循 Conventional Commits:

```
<type>(<scope>): <subject>

类型: feat(新功能) | fix(修复) | docs(文档) | refactor(重构) | test(测试)
```

**示例**:
```
feat(scoring): 实现评分系统V3
fix(ai): 修复AI输出验证逻辑
feat(lhb): 实现龙虎榜模块
feat(sentiment): 实现新闻情感分析引擎
feat(risk): 实现风险拆解模块
feat(dragon): 实现龙头战法评分系统
feat(board): 实现东财板块动态别名
```

---

## 性能与安全

### 20. 性能规范

**API 性能**
- **Response Time**: 选股 API < 30 秒
- **Concurrent Requests**: 支持 10+ 并发请求
- **Pagination**: 列表接口必须分页

**数据库性能**
- **Indexing**: 常用查询字段必须添加索引
- **Query Optimization**: 避免 N+1 查询
- **Connection Pool**: 使用连接池

**AI API 性能**
- 缓存策略: 相同股票7天内缓存评分结果
- 降级策略: AI不可用时使用本地模板
- 超时设置: DeepSeek API 30秒超时

**情感分析性能**
- V1 纯规则引擎，关键词匹配 + 正则，单条新闻 < 1ms
- V2 事件驱动引擎，多事件合并+确定性因子，单条新闻 < 5ms
- 均在查询时实时计算，不影响预加载速度

**龙虎榜性能**
- DB缓存优先：首次API拉取后写入 `stock_lhb` 表，后续读DB ~20ms
- 预加载：选股完成后后台批量拉取（5线程），不阻塞选股流程

**风险拆解性能**
- 纯规则计算，无AI耗时
- 7维度并行数据采集，单只股票 < 2秒
- 预加载：选股完成后后台批量计算，不阻塞选股流程

**龙头战法性能**
- 数据采集+评分计算 < 5秒
- DB缓存优先，强制刷新才重新计算
- 消息面和龙虎榜并行采集

**板块别名同步**
- 启动时自动同步最新交易日，< 10秒
- 运行期别名读取为纯内存操作，无额外延迟

**LightGBM训练预测性能**
- 训练(2154样本, 9特征): <5秒
- 批量预测(含DB读取): <50ms
- 全管线(竞价同步→训练, ~500交易日): ~50分钟（瓶颈在Tushare API逐日调用）
- 模型文件加载: <100ms (joblib)
- SHAP解释(单预测): <10ms
- 默认接力单目标训练(2000+样本, 14特征): <5秒
- 默认接力三目标全管线: <30秒
- 回放验收(5日): <5秒

### 21. 安全规范

**敏感信息管理**
- **Environment Variables**: 使用 `.env` 文件 (不提交到 Git)
- **Secrets**: 使用环境变量或密钥管理服务
- **Logging**: 禁止记录敏感信息 (Token, 密码, API Key)

**API 安全**
- **Rate Limiting**: 实现请求限流
- **Input Validation**: Pydantic 严格验证
- **Error Handling**: 不暴露敏感错误信息

**AI输出安全**
- **验证规则**: 禁止编造数据、禁止保证性词汇
- **免责声明**: 所有AI输出必须包含免责声明
- **降级机制**: AI失败时自动降级到本地模板

---

## 监控与维护

### 22. 监控指标

**Prometheus 指标**:
- `http_requests_total` (Counter)
- `http_request_duration_seconds` (Histogram)
- `http_requests_in_progress` (Gauge)

**健康检查**:
- `/api/v1/health` - 系统健康状态

**龙虎榜监控**:
- `stock_lhb` 表数据量
- Tushare `top_list` 调用成功率
- 游资 HM_LIST 缓存命中率

**情感分析监控**:
- V1: 各情感类别分布（positive/negative/neutral 比例）
- V2: 事件类型分布、确定性因子分布、多股新闻占比

**龙头战法监控**:
- `dragon_leader_score` 表数据量
- 龙头等级分布（极强龙头/强势龙头/疑似龙头/非龙头）
- 消息面/龙虎榜Alpha覆盖比例

**板块别名监控**:
- `dc_board_alias` 表别名数
- auto_approved vs pending_review 比例
- `dc_board_alias_observation` 日增长量

**LightGBM模型监控**:
- `model_version` 表活跃模型版本数
- `leader_main_t0_training_sample` 表样本量/正负比例
- 模型AUC/准确率/精确率/召回率趋势
- 预测覆盖率（`t0_limit_success_prob` 非空比例）
- 模型文件大小与加载耗时

**默认竞价接力模型监控**:
- `model_training_job` 表任务状态分布(pending/running/passed/rejected/failed)
- `default_auction_training_sample` 表样本量/正负比例/标签覆盖率
- 三目标模型AUC/TopK Lift趋势
- 默认接力预测字段非空比例
- 回放验收指标趋势(avg_recall/avg_jaccard/daily_count_error)

### 23. 日志规范

**双格式输出**:
- `logs/xuangu.json` - JSON格式 (适合日志聚合工具)
- `logs/xuangu.log` - 人类可读格式

**日志轮转**: 10MB/文件, 5个备份

**AI专用日志**:
- 记录AI调用次数、成功率、响应时间
- 记录降级触发原因
- 记录AI输出验证结果

**龙虎榜日志**:
- 记录Tushare API调用（top_list / top_inst / hm_list）
- 记录数据库读写状态
- 记录席位标签匹配结果
- 记录预加载执行情况

**情感分析日志**:
- V1: 记录匹配的关键词和权重
- V2: 记录事件类型、事实抽取结果、确定性因子
- 记录最终判定结果

**龙头战法日志**:
- 记录数据采集耗时（stock/market/theme/fundamental/intraday）
- 记录评分计算耗时
- 记录DB缓存命中/写入

**板块别名日志**:
- 记录每日同步状态（fetch/save/insert counts）
- 记录自动批准与待审核数量

---

## 部署与运维

### 24. 部署架构

**直接部署 (Supervisor + Nginx)**

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
}
```

**环境变量配置** (.env):
```bash
# 原有配置
TUSHARE_TOKEN=your_token_here
TDX_MCP_ENABLED=true
TDX_MCP_URL=https://mcp.tdx.com.cn:3001/mcp
TDX_MCP_API_KEY=your_api_key_here
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
DATABASE_URL=sqlite:///./data/xuangu.db
SECRET_KEY=your_secret_key_here
HOST=0.0.0.0
PORT=9999
LOG_LEVEL=INFO
LOG_DIR=logs
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:8081,http://localhost:3000

# AI配置
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
SCORING_CACHE_DAYS=7
AI_TIMEOUT=30
```

---

**这些指南有效的标志：** 差异中不必要的修改更少了，因过度复杂而重写的情况更少了，澄清问题出现在实现之前而不是出错之后。

**Last Updated**: 2026-05-17
**Maintainer**: AI Assistant
**Version**: 10.0
