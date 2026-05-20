# xuangu 多模型联动开发文档

| 版本 | 日期 | 说明 |
|---|---:|---|
| v1.0 | 2026-05-17 | 初始版本：面向默认竞价选股策略的多模型联动体系 |
| v1.1 | 2026-05-17 | 增加模型中心、规则模型先行、LightGBM 渐进替换、回测与实盘闭环 |
| v2.0 | 2026-05-17 | 合并补充文档：样本偏差检测、训练数据设计、数据源映射、API/DB扩展、训练前检查清单、附录 |

---

## 目录

1. [文档概述](#1-文档概述)
2. [项目背景与当前系统理解](#2-项目背景与当前系统理解)
3. [核心需求分析](#3-核心需求分析)
4. [建设目标与设计原则](#4-建设目标与设计原则)
5. [多模型联动总体架构](#5-多模型联动总体架构)
6. [模型体系设计](#6-模型体系设计)
7. [特征体系设计](#7-特征体系设计)
   - [7.11 数据源与字段来源映射](#711-数据源与字段来源映射)
8. [训练样本与标签设计](#8-训练样本与标签设计)
   - [8.6 训练前样本偏差检测（必须）](#86-训练前样本偏差检测必须)
9. [训练数据总体设计](#8b-训练数据总体设计)
10. [模型中心模块设计](#9-模型中心模块设计)
   - [9.8 训练数据质量模块](#98-训练数据质量模块)
11. [后端服务架构设计](#10-后端服务架构设计)
12. [数据库表结构设计](#11-数据库表结构设计)
   - [11.8 补充数据库表](#118-补充数据库表)
13. [API 设计规范](#12-api-设计规范)
   - [12.11-12.22 训练/偏差/实时API](#1211-构建历史候选池)
14. [前端页面与交互设计](#13-前端页面与交互设计)
15. [选股流程集成方案](#14-选股流程集成方案)
16. [训练、回测与有效性验证](#15-训练回测与有效性验证)
17. [训练前检查清单](#15b-训练前检查清单)
18. [开发实施计划](#16-开发实施计划)
   - [16.1b 第一阶段详细开发顺序](#161b-第一阶段详细开发顺序)
19. [质量保证计划](#17-质量保证计划)
20. [运维监控方案](#18-运维监控方案)
21. [风险评估与应对](#19-风险评估与应对)
22. [验收标准](#20-验收标准)
   - [20.5-20.9 扩展验收标准](#205-数据保存验收)
23. [后续演进规划](#21-后续演进规划)
24. [附录：第一版规则模型评分建议](#22-附录第一版规则模型评分建议)
25. [附录A：第一阶段必需字段总表](#附录-a第一阶段必需字段总表)
26. [附录B：第一阶段建议训练数据集](#附录-b第一阶段建议训练数据集)
27. [附录C：不允许用于早盘模型训练的字段](#附录-c不允许用于早盘模型训练的字段)
28. [附录D：推荐结论](#附录-d推荐结论)

---

## 1. 文档概述

### 1.1 编写目的

本文档用于指导 `xuangu` 项目从当前的“默认竞价选股 + 规则评分 + 单模型分 + T+0 概率 + 最终分”模式，演进为“默认竞价策略驱动的多模型联动体系”。

本方案不重新设计一套全市场选股系统，而是在现有默认竞价选股策略基础上，增加多个专用模型，对默认策略候选股进行多维度评分、排序、过滤、展示、回填、评估和持续训练。

最终系统需要回答以下交易问题：

```text
默认竞价策略已经选出的股票中：
1. 哪些竞价最强？
2. 哪些更可能触板或封板？
3. 哪些有次日溢价？
4. 哪些容易高开低走、炸板或大亏？
5. 哪些适合 T+0 或盘中处理？
6. 综合排序后，Top 1 / Top 3 / Top 5 是否优于默认策略原始排序？
```

### 1.2 适用范围

本文档适用于以下系统模块：

```text
backend/services/stock_selector.py
backend/services/rule_score_service.py
backend/services/model_score_service.py
backend/services/composite_score_service.py
backend/services/model_center_service.py
backend/services/model_evaluation_service.py
backend/api/stock.py
backend/api/model_center.py
backend/models/selected_stock.py
backend/models/model_registry.py
backend/models/stock_model_score.py
frontend/src/views/ModelCenter.vue
frontend/src/views/StockResults.vue
frontend/src/components/model/*
frontend/src/components/stock/*
```

### 1.3 文档定位

本文档兼具以下用途：

```text
1. 产品需求文档：说明为什么要做多模型联动。
2. 架构设计文档：说明如何融入当前 xuangu 系统。
3. 开发实施文档：说明后端、前端、数据库、API 如何落地。
4. 训练规范文档：说明模型如何训练、验证、回测和上线。
5. 迭代规划文档：说明先做什么，后做什么，如何逐渐完善。
```

### 1.4 核心结论

本项目不应以“一个大模型替代默认策略”为目标，而应以“多个专用模型服务默认竞价策略”为目标。

```text
默认竞价策略：负责生成候选池。
多模型体系：负责候选池内部排序、过滤、解释和复盘。
模型中心：负责模型注册、版本、启停、表现和综合分配置。
前端页面：负责多模型分数展示、排序切换、风险提示和个股解释。
```

---

## 2. 项目背景与当前系统理解

### 2.1 当前系统定位

`xuangu` 是一个围绕 A 股短线竞价、涨停、龙头战法构建的选股平台。当前主链路可概括为：

```text
通达信 MCP / 本地行情初筛
  ↓
Tushare 数据增强
  ↓
封板率计算
  ↓
规则评分
  ↓
LightGBM 模型分
  ↓
T+0 成功率模型
  ↓
最终分
  ↓
保存 SelectionRecord / SelectedStock / StockFeatureSnapshot
  ↓
前端展示 / 飞书通知 / WebSocket 推送
  ↓
后台预热 AI 概览、异动解读、龙虎榜、风险拆解、板块关系
```

系统已经不是单纯脚本，而是一个长期运行的 FastAPI + Vue 生产型选股平台。现有系统已具备：

```text
1. 默认竞价策略候选池生成能力
2. 通达信 MCP / 本地 .day 降级能力
3. Tushare 数据补充能力
4. 封板率计算能力
5. 规则评分能力
6. LightGBM 模型预测能力
7. T+0 成功率模型能力
8. 选股结果入库能力
9. 特征快照沉淀能力
10. 模型状态接口基础
11. 前端模型中心页面基础
12. 前端选股结果页面基础
13. 飞书 / WebSocket 通知基础
```

### 2.2 当前默认竞价策略理解

当前默认竞价策略大致筛选思想为：

```text
非 ST
非停牌
非北交所
流通市值不过大
价格不过高
近 10 日趋势向上
近 100 日有多次涨停
竞价量占昨日成交量比例约 4% - 30%
竞价换手率约 0.5% - 10%
```

因此，模型的目标不是全市场预测，而是：

```text
在默认竞价策略已经选出的候选股中，判断谁更强、谁更危险、谁更值得排前。
```

### 2.3 当前模型体系的主要不足

当前系统已有模型分，但仍存在以下问题：

```text
1. 模型目标不够拆分：一个模型分难以解释竞价、封板、风险、溢价等不同问题。
2. 风险与机会混在一起：风险应独立建模，并作为扣分项参与综合排序。
3. 前端展示不够多维：用户只能看到最终分，难以理解强在哪里、危险在哪里。
4. 模型中心管理能力不足：缺少模型注册、版本、启停、观察、综合权重配置。
5. 模型有效性验证不足：缺少 Top N 回测、分层表现、风险过滤效果。
6. 训练闭环不完整：模型分数、特征快照、真实结果回填之间需要统一管理。
```

### 2.4 本次改造方向

本次改造采用渐进路线：

```text
第一步：规则模型先行，先把分数算出来、入库、展示、排序。
第二步：每天回填真实结果，积累默认策略候选样本。
第三步：对每个模型分别训练 LightGBM。
第四步：新模型先进入观察状态，稳定后再参与综合排序。
第五步：模型中心持续展示模型有效性和实盘表现。
```

---

## 3. 核心需求分析

### 3.1 用户真实需求

用户当前真实需求不是“马上训练出完美模型”，而是：

```text
先做出来，融入当前项目，能展示，能排序，能回填，然后逐渐完善。
```

这意味着第一版应以“闭环可运转”为第一目标，而不是以“模型指标最优”为第一目标。

### 3.2 功能性需求

#### 3.2.1 多模型评分需求

系统需要支持多个模型并行对同一只股票打分：

```text
竞价强度分
封板潜力分
风险分
次日溢价分
T+0 成功率分
题材强度分
综合排序分
```

#### 3.2.2 模型中心管理需求

模型中心需要支持：

```text
模型列表展示
模型状态切换
模型版本查看
模型是否参与综合分配置
模型今日打分统计
模型历史表现展示
模型详情查看
模型权重配置
```

#### 3.2.3 选股结果展示需求

选股结果页需要展示：

```text
综合分
竞价强度
封板潜力
风险分
次日溢价
T+0 成功率
题材强度
模型建议
模型解释
```

#### 3.2.4 结果回填需求

系统需要在收盘后和次日回填：

```text
当日最高收益
当日收盘收益
当日最大回撤
是否触板
是否封板
是否炸板
次日开盘收益
次日最高收益
次日收盘收益
是否高开低走
是否出现大面风险
```

#### 3.2.5 有效性验证需求

模型有效性不能只看准确率，需要看：

```text
Top 1 / Top 3 / Top 5 表现
高分组收益是否高于低分组
高分组封板率是否高于低分组
高风险组大亏率是否高于低风险组
过滤风险后最大回撤是否下降
默认策略 + 模型排序 是否优于默认策略原始排序
```

### 3.3 非功能性需求

```text
1. 不影响当前默认选股主流程稳定性。
2. 模型调用失败不能阻塞选股结果返回。
3. 模型结果必须可追溯到版本。
4. 规则模型和 LightGBM 模型应使用统一接口。
5. 新模型必须支持 observe 状态，避免直接影响实盘排序。
6. 前端展示必须简洁，不能把用户淹没在模型细节中。
7. 数据结构必须支持后续扩展模型数量。
```

---

## 4. 建设目标与设计原则

### 4.1 总体建设目标

建设一个围绕默认竞价策略的多模型联动系统：

```text
默认竞价策略候选池
  ↓
多模型并行打分
  ↓
模型中心统一管理
  ↓
前端多维展示
  ↓
综合排序
  ↓
真实结果回填
  ↓
模型表现评估
  ↓
LightGBM 逐步替换规则模型
```

### 4.2 第一阶段目标

第一阶段只做三个模型：

```text
auction_model   竞价强度模型
limitup_model   封板潜力模型
risk_model      大面风险模型
```

第一阶段允许全部使用规则打分。

目标不是模型最优，而是完成：

```text
能算分
能入库
能展示
能排序
能回填
能评估
```

### 4.3 第二阶段目标

第二阶段增加：

```text
premium_model   次日溢价模型
t0_model        T+0 成功率模型
theme_model     题材强度模型
```

### 4.4 第三阶段目标

第三阶段开始训练真实机器学习模型：

```text
auction_model: rule_v1 → lgb_auction_v1
limitup_model: rule_v1 → lgb_limitup_v1
risk_model: rule_v1 → lgb_risk_v1
premium_model: rule_v1 → lgb_premium_v1
t0_model: rule_v1 → lgb_t0_v1
```

### 4.5 核心设计原则

#### 4.5.1 服务默认策略原则

模型服务于默认竞价策略，不替代默认竞价策略。

```text
默认竞价策略负责选出候选股。
多模型负责候选股内部排序、过滤和解释。
```

#### 4.5.2 条件分布建模原则

训练样本只来自默认策略候选池。

```text
建模目标：P(成功 | 已被默认竞价策略选中)
不是：P(成功 | 全市场股票)
```

#### 4.5.3 多模型解耦原则

每个模型只回答一个问题。

```text
竞价强度模型：竞价是否超预期？
封板潜力模型：是否容易触板/封板？
风险模型：是否容易高开低走或炸板大面？
次日溢价模型：明天是否有肉？
T+0 模型：盘中是否适合操作？
题材模型：是否处于主线题材？
```

#### 4.5.4 先展示后参与原则

新模型上线后，先进入 observe 状态。

```text
observe：只打分、只展示、不参与综合排序。
enabled：打分、展示、参与综合排序。
disabled：不打分、不展示、不参与排序。
```

#### 4.5.5 风险独立原则

风险模型必须独立存在，风险分必须作为扣分项参与综合分。

#### 4.5.6 可追溯原则

每个模型分数必须记录：

```text
model_name
model_version
score
probability
rank
explain_json
created_at
```

#### 4.5.7 防未来函数原则

所有特征必须满足：

```text
feature_time <= prediction_time
```

---

## 5. 多模型联动总体架构

### 5.1 总体链路

```text
用户触发默认竞价选股
  ↓
StockSelector 生成候选池
  ↓
Tushare / 通达信 / 本地行情数据增强
  ↓
RuleScoreService 计算规则分
  ↓
ModelScoreService 读取模型中心配置
  ↓
并行调用多个模型
  ├─ auction_model   竞价强度
  ├─ limitup_model   封板潜力
  ├─ risk_model      大面风险
  ├─ premium_model   次日溢价
  ├─ t0_model        T+0 成功率
  └─ theme_model     题材强度
  ↓
保存 stock_model_scores
  ↓
CompositeScoreService 计算综合分
  ↓
保存 SelectedStock
  ↓
前端 StockResults 多模型展示
  ↓
ModelCenter 展示模型状态、版本、表现
  ↓
收盘 / 次日回填真实结果
  ↓
ModelEvaluationService 评估模型有效性
  ↓
训练服务生成新模型版本
```

### 5.2 模块关系

```text
ModelCenter
  ├─ 管理模型注册
  ├─ 管理模型版本
  ├─ 管理模型状态
  ├─ 管理综合分权重
  ├─ 查看模型表现
  └─ 控制是否参与排序

ModelScoreService
  ├─ 查询 enabled / observe 模型
  ├─ 加载规则模型或 LightGBM 模型
  ├─ 执行模型打分
  ├─ 保存模型结果
  └─ 返回多模型分数字典

CompositeScoreService
  ├─ 读取综合分配置
  ├─ 聚合多模型分
  ├─ 风险分扣分
  ├─ 生成最终排序分
  └─ 输出操作建议

ModelEvaluationService
  ├─ 读取历史模型分
  ├─ 读取真实回填结果
  ├─ 计算分层表现
  ├─ 计算 Top N 表现
  ├─ 计算风险过滤效果
  └─ 写入模型表现指标
```

### 5.3 模型状态流转

```text
disabled
  ↓
observe
  ↓
enabled
  ↓
observe / disabled
```

| 状态 | 是否打分 | 是否展示 | 是否参与综合分 | 使用场景 |
|---|---:|---:|---:|---|
| disabled | 否 | 否 | 否 | 未启用或失效 |
| observe | 是 | 是 | 否 | 新模型观察期 |
| enabled | 是 | 是 | 是 | 正式参与排序 |

### 5.4 第一阶段实现边界

第一阶段只实现：

```text
model_registry
model_versions
stock_model_scores
model_daily_metrics
auction_model rule_v1
limitup_model rule_v1
risk_model rule_v1
composite_score_service
ModelCenter 基础展示
StockResults 多列展示
```

暂不实现：

```text
自动训练
自动调参
完整模型漂移检测
自动降级
复杂模型对比实验平台
```

---

## 6. 模型体系设计

### 6.1 模型清单

| 模型名 | 中文名 | 第一阶段 | 类型 | 作用 |
|---|---|---:|---|---|
| auction_model | 竞价强度模型 | 是 | 规则 → LightGBM | 判断竞价是否超预期 |
| limitup_model | 封板潜力模型 | 是 | 规则 → LightGBM | 判断是否有触板/封板潜力 |
| risk_model | 大面风险模型 | 是 | 规则 → LightGBM | 判断是否容易高开低走/炸板/大亏 |
| premium_model | 次日溢价模型 | 否 | LightGBM | 判断 T+1 是否有溢价 |
| t0_model | T+0 成功率模型 | 否 | 规则 → LightGBM | 判断是否适合盘中 T |
| theme_model | 题材强度模型 | 否 | 规则优先 | 判断是否处于主线题材 |
| composite_model | 综合排序模型 | 是 | 规则聚合 | 综合排序与建议 |

### 6.2 竞价强度模型 auction_model

#### 6.2.1 模型目标

判断默认竞价策略选出的股票中，哪些竞价阶段表现更强，开盘后更容易继续冲高。

#### 6.2.2 第一版规则分

```text
auction_score =
  竞价涨幅合理性分     * 30%
+ 竞价量占比分         * 25%
+ 竞价换手分           * 20%
+ 竞价额/流通市值分     * 15%
+ 近期强度分           * 10%
```

#### 6.2.3 输出字段

```text
auction_score
auction_rank
auction_level
auction_explain_json
```

#### 6.2.4 未来 LightGBM 标签

```text
label_auction_strength = 1
如果 9:30-10:00 最高收益 >= 3%
且 9:30-10:00 最大回撤 > -3%

label_auction_strength = 0
如果开盘后无明显冲高或高开低走
```

### 6.3 封板潜力模型 limitup_model

#### 6.3.1 模型目标

判断股票当日是否具备触板、封板、回封、晋级潜力。

#### 6.3.2 第一版规则分

```text
limitup_score =
  涨停基因分   * 30%
+ 封板率分     * 25%
+ 触板活跃分   * 15%
+ 题材强度分   * 15%
+ 市场情绪分   * 15%
```

#### 6.3.3 输出字段

```text
limitup_score
touch_limit_prob
seal_limit_prob
break_limit_risk
limitup_explain_json
```

#### 6.3.4 未来 LightGBM 标签

```text
label_touch_limit = 当日是否触板
label_seal_limit = 当日是否最终封板
```

### 6.4 大面风险模型 risk_model

#### 6.4.1 模型目标

识别虽然满足默认竞价策略，但容易出现以下风险的股票：

```text
高开低走
竞价过热
炸板大面
次日低开
高位加速后回落
板块退潮
市场情绪恶化
```

#### 6.4.2 第一版规则分

风险分越高，代表越危险。

```text
risk_score =
  高位加速风险 * 25%
+ 竞价高开风险 * 20%
+ 长上影风险   * 15%
+ 炸板历史风险 * 20%
+ 市场退潮风险 * 20%
```

#### 6.4.3 风险等级

```text
0 - 30：低风险
30 - 60：中风险
60 - 80：高风险
80 - 100：极高风险
```

#### 6.4.4 输出字段

```text
risk_score
risk_level
risk_tags
risk_explain_json
```

#### 6.4.5 未来 LightGBM 标签

```text
label_big_loss = 1
如果出现任一情况：
1. 当日最大回撤 <= -5%
2. 当日高开低走，收盘较开盘跌幅 <= -4%
3. 当日炸板后明显回落
4. T+1 开盘 <= -3%
5. T+1 收盘 <= -5%
```

### 6.5 次日溢价模型 premium_model

#### 6.5.1 模型目标

判断今日入选股票在 T+1 是否有溢价。

#### 6.5.2 建议拆分版本

```text
premium_model_preopen
  用于早盘预测，只使用竞价前和竞价数据。

premium_model_afterclose
  用于收盘复盘，可以使用当天完整日线、封板结果和收盘结构。
```

#### 6.5.3 标签设计

```text
label_next_day_premium = 1
如果 T+1 开盘收益 >= 1.5%
或 T+1 最高收益 >= 3%

label_next_day_premium = 0
如果 T+1 低开低走
或 T+1 收盘收益 <= -2%
```

#### 6.5.4 输出字段

```text
premium_score
t1_open_premium_prob
t1_high_premium_prob
premium_explain_json
```

### 6.6 T+0 成功率模型 t0_model

#### 6.6.1 模型目标

判断股票是否适合盘中低吸、回封、快进快出或做 T。

#### 6.6.2 标签设计

需要先固定 T+0 交易规则，例如：

```text
买入规则：开盘后回踩 VWAP 或均线区间
卖出规则：冲高 2% - 5% 或尾盘卖出
成功条件：可执行收益 >= 2%，且最大回撤不超过 -3%
```

#### 6.6.3 输出字段

```text
t0_score
t0_success_prob
t0_style
```

`t0_style` 可选：

```text
低吸
回封
追高不适合
只观察
```

### 6.7 题材强度模型 theme_model

#### 6.7.1 模型目标

判断候选股所属题材是否为当前市场主线，是否具备板块联动助攻。

#### 6.7.2 第一版规则分

```text
theme_score =
  板块涨停家数分 * 30%
+ 板块涨幅排名分 * 20%
+ 板块成交额变化 * 15%
+ 是否板块前排   * 20%
+ 新闻/热度分    * 15%
```

#### 6.7.3 输出字段

```text
theme_score
main_theme
is_mainline_theme
sector_rank
theme_explain_json
```

### 6.8 综合排序模型 composite_model

#### 6.8.1 第一版综合分

```text
composite_score =
  auction_score * 0.35
+ limitup_score * 0.35
- risk_score    * 0.30
+ rule_score    * 0.20
```

最终限制：

```text
0 <= composite_score <= 100
```

#### 6.8.2 操作建议

```text
composite_score >= 80 且 risk_score < 40：重点关注
composite_score >= 65 且 risk_score < 60：正常关注
risk_score >= 70：高风险，仅观察
其他：低优先级
```

---

## 7. 特征体系设计

### 7.1 特征设计原则

```text
1. 只使用预测时点之前可见的数据。
2. 所有特征必须保存快照。
3. 特征必须区分 feature_time 和 prediction_time。
4. 特征必须可复现，不能只存在内存中。
5. 训练和线上预测必须使用同一套特征计算逻辑。
6. 缺失特征必须有统一默认值和缺失标记。
```

### 7.2 基础特征

```text
float_mv                  流通市值
total_mv                  总市值
close_price               昨收价
pe                        PE
pb                        PB
turnover_rate             昨日换手率
volume_ratio              量比
industry                  行业
board_type                主板/创业板/科创板
listed_days               上市天数
is_st                     是否 ST
is_suspended              是否停牌
```

### 7.3 走势特征

```text
ret_1d                    昨日涨幅
ret_2d                    近 2 日涨幅
ret_3d                    近 3 日涨幅
ret_5d                    近 5 日涨幅
ret_10d                   近 10 日涨幅
ret_20d                   近 20 日涨幅
amp_1d                    昨日振幅
amp_3d                    近 3 日平均振幅
amp_5d                    近 5 日平均振幅
max_drawdown_5d           近 5 日最大回撤
max_drawdown_10d          近 10 日最大回撤
distance_to_20d_high      距离 20 日高点
distance_to_60d_high      距离 60 日高点
```

### 7.4 涨停结构特征

```text
limitup_count_5d          近 5 日涨停次数
limitup_count_10d         近 10 日涨停次数
limitup_count_20d         近 20 日涨停次数
limitup_count_60d         近 60 日涨停次数
limitup_count_100d        近 100 日涨停次数
touch_limit_count_20d     近 20 日触板次数
seal_limit_count_20d      近 20 日封板次数
break_limit_count_20d     近 20 日炸板次数
seal_rate_20d             近 20 日封板率
seal_rate_60d             近 60 日封板率
days_since_last_limitup   距离上次涨停天数
current_board_height      当前连板高度
is_first_board            是否首板
is_second_board           是否二板
```

### 7.5 竞价特征

```text
auction_open_pct              竞价/开盘涨幅
auction_amount                竞价成交额
auction_volume                竞价成交量
auction_turnover_rate         竞价换手率
auction_volume_ratio          竞价量比
auction_volume_pct            竞价量 / 昨日成交量
auction_amount_pct            竞价成交额 / 昨日成交额
auction_amount_to_float_mv    竞价成交额 / 流通市值
auction_gap_vs_prev_ret       竞价涨幅 - 昨日涨幅
```

### 7.6 成交量与资金特征

```text
amount_1d                 昨日成交额
amount_3d_avg             近 3 日平均成交额
amount_5d_avg             近 5 日平均成交额
amount_10d_avg            近 10 日平均成交额
volume_1d                 昨日成交量
volume_5d_avg             近 5 日平均成交量
volume_spike_1d           昨日放量倍数
volume_spike_3d           近 3 日放量倍数
turnover_1d               昨日换手
turnover_3d_avg           近 3 日平均换手
turnover_5d_avg           近 5 日平均换手
```

### 7.7 K 线结构特征

```text
close_position_1d         昨日收盘位置 = (收盘-最低)/(最高-最低)
upper_shadow_1d           昨日上影线比例
lower_shadow_1d           昨日下影线比例
body_pct_1d               昨日实体涨跌幅
is_long_upper_shadow      是否长上影
is_big_red_candle         是否大阳线
is_big_green_candle       是否大阴线
is_high_open_low_close    是否高开低走
```

### 7.8 市场环境特征

```text
market_index_ret_1d       大盘昨日涨幅
market_index_ret_5d       大盘近 5 日涨幅
market_amount             全市场成交额
market_amount_change      成交额变化
limitup_total             昨日涨停家数
limitdown_total           昨日跌停家数
break_limit_total         昨日炸板家数
seal_rate_market          昨日市场封板率
highest_board_height      昨日最高连板高度
second_board_count        二板数量
third_board_count         三板及以上数量
promotion_rate            晋级率
hot_theme_count           热门题材数量
```

### 7.9 题材与板块特征

```text
theme_count               个股所属题材数量
main_theme_strength       主题材强度
sector_ret_1d             所属板块昨日涨幅
sector_ret_3d             所属板块近 3 日涨幅
sector_limitup_count      所属板块涨停家数
sector_top_stock_ret      板块龙头涨幅
sector_volume_change      板块成交额变化
is_sector_front_runner    是否板块前排
is_mainline_theme         是否主线题材
```

### 7.10 特征快照要求

每次选股时必须保存：

```text
trade_date
ts_code
strategy_name
strategy_version
feature_time
prediction_time
features_json
```

硬性要求：

```text
feature_time <= prediction_time
```

---

### 7.11 数据源与字段来源映射

当前已有数据源：Tushare / 通达信本地日线 / 通达信2年内分钟线 / 5个交易日真实选股结果 / 生产中实时数据。

**Tushare**：stock_basic/trade_cal/daily/daily_basic/adj_factor/stk_limit/limit_list_d/top_list/top_inst/moneyflow/fina_indicator。第一阶段必需字段：ts_code/name/industry/list_date/trade_date/turnover_rate/volume_ratio/pe/pb/total_mv/circ_mv。

**通达信本地日线**：可计算ret_1d~20d, amp, max_drawdown, limitup_count_20d, touch_limit_count_20d, seal_rate_20d, break_limit_count_20d等。

**通达信2年内分钟线**：可计算open_5min/30min_return, intraday_high_return, vwap_position, first_touch_limit_time, break_limit_flag等。

**关键字段映射**：

| 字段 | 历史训练来源 | 生产预测来源 | 说明 |
|---|---|---|---|
| auction_open_pct | 分钟线open代理/live快照 | 实时竞价/开盘 | 真实竞价优先 |
| auction_volume_pct | proxy首分钟/前5分钟量 | 实时竞价量 | 需data_mode区分 |
| auction_amount_to_float_mv | 分钟线+Tushare circ_mv | 实时+Tushare | 核心字段 |
| ret_5d/ret_10d | 通达信日线 | 通达信日线 | 稳定字段 |
| limitup_count_20d | 日线+涨停价 | 日线+涨停价 | 稳定字段 |
| seal_rate_20d | 日线/分钟线 | 日线/分钟线 | 日线可粗算 |
| open_5min_return | 通达信分钟线 | 实时分钟线 | 9:35模型 |
| market_seal_rate | 历史聚合 | 实时/昨日聚合 | 可用昨日值 |
| t1_open_return | 次日日线/分钟线 | 不用于预测 | 标签字段 |


## 8. 训练样本与标签设计

### 8.1 样本范围

训练样本只来自默认竞价策略历史候选股。

```text
样本 = 某交易日 T，某只股票 S，被默认竞价策略选中时的特征快照
```

不得使用全市场样本训练模型。

### 8.2 样本主表

建议使用：

```text
strategy_candidate_snapshot
```

核心字段：

```text
id
trade_date
ts_code
strategy_name
strategy_version
selected_time
feature_time
prediction_time
features_json
created_at
```

### 8.3 结果回填表

建议使用：

```text
strategy_candidate_outcome
```

核心字段：

```text
id
snapshot_id
trade_date
ts_code
actual_intraday_high_return
actual_intraday_close_return
actual_max_drawdown
actual_touch_limit
actual_seal_limit
actual_break_limit
actual_t1_open_return
actual_t1_high_return
actual_t1_close_return
actual_high_open_low_close
actual_big_loss
updated_at
```

### 8.4 各模型标签

| 模型 | 标签 | 正样本定义 |
|---|---|---|
| auction_model | label_auction_strength | 9:30-10:00 最高收益 >= 3%，且最大回撤 > -3% |
| limitup_model | label_seal_limit | 当日最终封住涨停 |
| risk_model | label_big_loss | 当日或次日出现明显大亏风险 |
| premium_model | label_next_day_premium | T+1 开盘 >= 1.5% 或 T+1 最高 >= 3% |
| t0_model | label_t0_success | 固定 T+0 规则下收益 >= 2%，且回撤可控 |

### 8.5 标签版本化

标签定义必须版本化，例如：

```text
auction_label_v1
risk_label_v1
premium_label_v1
```

一旦标签定义变化，模型版本必须变化。

### 8.6 训练前样本偏差检测（必须）

#### 8.6.1 为什么必须检测样本偏差

模型目标是服务默认竞价策略，所以训练集必须近似真实生产候选池。

错误做法：用全市场股票训练模型 / 用收盘后完整数据训练早盘模型 / 用历史代理样本训练后直接正式参与 live 排序。

正确做法：历史回放默认竞价策略生成历史候选股 → 取真实生产候选股作为 live 样本 → 对比数量/重合度/核心特征分布/结果表现 → 偏差可接受后才允许训练。

如果不先解决样本偏差问题，模型很容易出现：离线训练效果好 → 回测指标好 → 但真实生产排序无效甚至反向。

#### 8.6.2 需要比较的两类样本

**A. 历史回放样本 `historical_replay_candidates`**：来源为通达信历史日线 + 历史分钟线 + Tushare + 历史回放默认竞价策略。含义：如果过去某天运行默认竞价策略，理论上会选出哪些股票。

**B. 真实生产样本 `live_selection_candidates`**：来源为真实选股结果 + 实时数据快照 + SelectedStock。含义：真实生产环境中实际选出的股票。

#### 8.6.3 5个交易日真实样本的正确用途

当前只有5个交易日真实样本时，不建议用于正式训练。建议用途：作为 live 验证样本 → 做样本偏差检测 → 检查历史回放能否复现真实选股 → 检查特征偏移 → 模型训练后 observe 观察。

不建议用途：直接混入训练集 / 用来调参 / 用来得出模型有效结论。

#### 8.6.4 五项检测指标

**指标一：每日候选股数量偏差**

统计历史日均/中位数/P10-P90分布，比较live实际数量。live在历史P10-P90内→正常；多次超P95或低于P5→异常；日均与中位数偏差超50%→需排查。

**指标二：候选股重合度**

Jaccard = live ∩ replay / live ∪ replay；Recall_live = live ∩ replay / live。Jaccard≥0.80→很好；0.60-0.80→可接受；<0.60→不建议训练；Recall_live<0.80→必须排查。

重点排查：竞价量占比口径 / 竞价换手率口径 / 流通市值数据日期 / 涨停次数窗口 / 停牌/ST/北交所过滤 / 实时开涨幅与历史代理开涨幅。

**指标三：核心特征分布偏差**

比较 auction_open_pct/auction_volume_pct/auction_turnover_rate/ret_5d/limitup_count_20d/seal_rate_20d/float_mv/market_seal_rate/sector_limitup_count 等特征的历史均值/中位数/P25/P75 vs live对应值。

**指标四：PSI 分布偏移**

PSI = Σ((actual_pct - expected_pct) × ln(actual_pct / expected_pct))。PSI<0.10→接近；0.10-0.25→轻微偏移；≥0.25→明显偏移，不建议直接训练上线。

**指标五：标签结果分布偏差**

比较 intraday_high_return / intraday_max_drawdown / touch_limit_rate / seal_rate / t1_open_return / t1_high_return / big_loss_rate。5天样本只能观察，不能作为长期结论。

#### 8.6.5 样本偏差检测结论分级

**A级（偏差小，可训练）**：live日选股量在历史P10-P90 + Jaccard≥0.80/Recall≥0.80 + 大部分PSI<0.15 + 无关键PSI≥0.25。处理：允许用历史replay样本训练，live样本作为observe验证集。

**B级（轻微偏差，可训练但只观察）**：部分PSI在0.15-0.25 + Jaccard在0.60-0.80。处理：允许训练但模型状态必须为observe，不参与综合排序。

**C级（偏差大，暂不训练）**：多个关键PSI≥0.25 + Jaccard<0.60 + live数量明显偏离。处理：先修数据口径/策略回放/实时快照，不训练正式模型。

---

## 8b. 训练数据总体设计

### 8b.1 核心原则

训练时用历史快照，不是实时接口。但快照必须模拟生产实时预测时的可见数据。

```text
生产中模型在什么时间点使用什么字段，
训练时就必须准备历史上同一时间点能看到的同一批字段。
```

### 8b.2 训练样本结构

每条训练样本由三部分组成：样本身份信息 + 预测时点特征 + 未来结果标签。

### 8b.3 训练数据模式 data_mode

| data_mode | 含义 | 用途 |
|---|---|---|
| proxy | 用历史分钟线模拟生产实时特征 | 历史训练第一版 |
| live | 真实生产实时快照 | live验证、未来正式训练 |
| mixed | proxy与live混合 | 仅观察期使用 |

### 8b.4 预测时点 prediction_time_type

必须固定以下预测时点，不同时点不能混用特征：

| prediction_time_type | 时间 | 可用数据 |
|---|---|---|
| pre_open_925 | 9:25后 | T-1日线、集合竞价快照、市场竞价环境 |
| open_930 | 9:30 | 开盘价、开盘涨幅、实时成交基础数据 |
| open_935 | 9:35 | 开盘5分钟分钟线聚合数据 |
| intraday_1000 | 10:00 | 开盘30分钟走势、VWAP、盘中回撤 |
| post_close | 收盘后 | T日完整日线、触板封板、收盘位置 |

### 8b.5 按模型拆分训练数据要求

**auction_model**：推荐 pre_open_925/open_935。第一版 data_mode=proxy, prediction_time_type=open_935。标签：9:30-10:00最高收益≥3%且回撤>-3%。

**limitup_model**：推荐 pre_open_925/open_930/open_935。第一版优先训练 label_seal_limit。

**risk_model**：推荐 open_935。标签：当日最大回撤≤-5% / 高开低走收盘较开盘跌≤-4% / 炸板后明显回落 / T+1开盘≤-3% / T+1收盘≤-5%。

**premium_model**：拆分为 premium_preopen_model(早盘)和 premium_afterclose_model(收盘后，可用T日完整日线+封板结果)。标签：T+1开盘≥1.5%或T+1最高≥3%。

**t0_model**：推荐 open_935/intraday_1000。标签依赖固定T+0规则（可执行收益≥2%且最大回撤≤-3%）。

### 8b.6 历史训练数据准备流程

```text
历史行情标准化 → 历史默认竞价策略回放 → 生成historical_replay_candidates
→ 生成预测时点特征快照 → 回填未来结果标签 → 执行样本偏差检测
→ 生成模型训练数据集 → 训练模型 → 模型进入observe状态
```

时间切分：训练集取较早历史区间，验证集取中间区间，测试集取最近历史区间，live验证集取最近真实生产日。禁止随机切分。

### 8b.7 生产实时快照保存要求

每次生产选股完成后必须保存实时特征快照。必须字段：trade_date/selection_id/ts_code/strategy_name/strategy_version/prediction_time_type/feature_time/snapshot_time/data_mode=live/features_json/source_status_json。

按预测时点区分的实时数据：
- **9:25竞价后**: auction_price/open_pct/volume/amount/turnover_rate/volume_pct/amount_to_float_mv
- **9:30开盘**: open_price/pct/amount/volume, current_price/pct
- **9:35开盘5分钟**: open_5min_return/high_return/max_drawdown/amount/amount_pct/vwap/vwap_position
- **10:00盘中**: open_30min_return/high_return/max_drawdown/amount_pct, intraday_vwap, pullback_to_vwap
- **实时市场环境**: market_index_ret/amount, limitup/seal/break_total, market_seal_rate, highest_board_height

第一阶段如实时市场环境难以获取，可先用昨日收盘市场环境数据。

### 8b.8 不允许用于早盘模型训练的字段

以下字段不能用于 pre_open_925/open_930/open_935 早盘模型训练：T日收盘价 / T日全天成交额 / T日最终换手率 / T日是否最终封板/炸板 / T日龙虎榜 / T+1开盘价/最高价/收盘价 / T+1新闻/收益。这些只可用于标签/结果回填/收盘后模型/复盘分析。

---

---

## 9. 模型中心模块设计

### 9.1 模型中心定位

模型中心是多模型体系的管理中枢，负责：

```text
模型注册
模型版本管理
模型状态管理
模型启停管理
模型表现展示
综合分权重配置
观察模型管理
模型回测报告查看
```

### 9.2 页面结构

模型中心页面分为五块：

```text
1. 顶部概览卡片
2. 模型列表表格
3. 综合排序配置
4. 模型表现面板
5. 模型详情抽屉
```

### 9.3 顶部概览卡片

展示：

```text
已启用模型数量
观察中模型数量
禁用模型数量
今日参与打分模型数量
今日打分股票数量
最近训练时间
最近回填样本数
```

### 9.4 模型列表字段

```text
模型名称
模型类型
用途
状态
当前版本
是否参与综合分
今日打分数
平均分
最近20日表现
操作
```

### 9.5 模型详情抽屉

点击模型后展示：

```text
模型基础信息
当前版本
评分逻辑
使用特征
标签定义
历史版本
最近打分样例
最近回测表现
启停记录
```

### 9.6 综合排序配置

第一版配置：

```json
{
  "mode": "pre_open",
  "weights": {
    "auction_score": 0.35,
    "limitup_score": 0.35,
    "risk_score": -0.30,
    "rule_score": 0.20
  }
}
```

### 9.7 模型状态管理

支持：

```text
启用
观察
禁用
参与综合分
不参与综合分
切换版本
查看表现
```

### 9.8 训练数据质量模块

模型中心新增"训练样本一致性"卡片，展示：

```text
最新样本偏差等级 (A/B/C)
历史样本数量 vs live样本数量
候选股重合度 (Jaccard/Recall)
异常PSI字段数量
是否允许训练
建议模型状态 (observe/enabled/disabled)
```

**模型详情页增加数据集信息**：当前训练数据集版本 / prediction_time_type / data_mode / 样本数量 / 正负样本数量 / 特征数量 / 标签定义 / 样本偏差等级 / 是否通过训练前检查。

**新模型上线规则**：
```text
样本偏差等级 A：允许训练，训练后进入 observe
样本偏差等级 B：允许训练，但只能 observe
样本偏差等级 C：禁止训练正式模型
```

模型训练完成但样本偏差未通过时，模型中心应显示："数据集未通过样本一致性检查，禁止启用 enabled。"


---

## 10. 后端服务架构设计

### 10.1 新增目录结构

```text
backend/
  models/
    model_registry.py
    model_version.py
    stock_model_score.py
    model_daily_metric.py
    strategy_candidate_snapshot.py
    strategy_candidate_outcome.py

  services/
    model_center_service.py
    model_score_service.py
    composite_score_service.py
    model_evaluation_service.py
    model_training_service.py
    feature_snapshot_service.py
    outcome_fill_service.py

  services/models/
    base_model.py
    auction_rule_model.py
    limitup_rule_model.py
    risk_rule_model.py
    premium_rule_model.py
    t0_rule_model.py
    theme_rule_model.py
    lgb_model_loader.py

  api/
    model_center.py
    model_scores.py
    model_evaluation.py
```

### 10.2 ModelScoreService 职责

```text
读取模型注册表
筛选 enabled / observe 模型
加载模型实现
执行模型打分
保存模型分数
返回分数字典
```

### 10.3 CompositeScoreService 职责

```text
读取综合分配置
只使用参与综合分的模型
风险分按负权重扣分
计算 composite_score
生成操作建议
生成排序字段
```

### 10.4 ModelCenterService 职责

```text
模型列表查询
模型状态更新
模型版本切换
模型详情查询
模型表现汇总
综合分配置管理
```

### 10.5 ModelEvaluationService 职责

```text
按模型统计分层表现
按 Top N 统计收益
评估风险过滤效果
评估模型是否优于默认策略
写入 model_daily_metrics
```

### 10.6 统一模型接口

所有规则模型和 LightGBM 模型都实现统一接口：

```python
class BaseModel:
    model_name: str
    version: str

    def score(self, stock_data: dict) -> dict:
        return {
            "score": 0.0,
            "probability": None,
            "rank": None,
            "level": None,
            "explain": [],
            "extra": {}
        }
```

---

## 11. 数据库表结构设计

### 11.1 model_registry

```sql
CREATE TABLE model_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(128) NOT NULL,
    model_type VARCHAR(32) NOT NULL,
    target_name VARCHAR(128),
    description TEXT,
    status VARCHAR(32) DEFAULT 'observe',
    current_version VARCHAR(64),
    score_field VARCHAR(64),
    sort_order INTEGER DEFAULT 0,
    is_visible BOOLEAN DEFAULT 1,
    is_used_in_composite BOOLEAN DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME
);
```

### 11.2 model_versions

```sql
CREATE TABLE model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name VARCHAR(64) NOT NULL,
    version VARCHAR(64) NOT NULL,
    model_type VARCHAR(32) NOT NULL,
    artifact_path VARCHAR(255),
    config_json TEXT,
    feature_json TEXT,
    label_definition TEXT,
    train_start_date DATE,
    train_end_date DATE,
    sample_count INTEGER,
    metrics_json TEXT,
    is_active BOOLEAN DEFAULT 0,
    created_at DATETIME
);
```

### 11.3 stock_model_scores

```sql
CREATE TABLE stock_model_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selection_id INTEGER,
    trade_date DATE NOT NULL,
    ts_code VARCHAR(16) NOT NULL,
    strategy_name VARCHAR(64),
    strategy_version VARCHAR(64),
    model_name VARCHAR(64) NOT NULL,
    model_version VARCHAR(64),
    score FLOAT,
    probability FLOAT,
    rank INTEGER,
    level VARCHAR(32),
    risk_level VARCHAR(32),
    explain_json TEXT,
    extra_json TEXT,
    created_at DATETIME
);
```

建议索引：

```sql
CREATE INDEX idx_stock_model_scores_trade_date ON stock_model_scores(trade_date);
CREATE INDEX idx_stock_model_scores_ts_code ON stock_model_scores(ts_code);
CREATE INDEX idx_stock_model_scores_model ON stock_model_scores(model_name, model_version);
CREATE INDEX idx_stock_model_scores_selection ON stock_model_scores(selection_id);
```

### 11.4 model_daily_metrics

```sql
CREATE TABLE model_daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL,
    model_name VARCHAR(64) NOT NULL,
    model_version VARCHAR(64),
    sample_count INTEGER,
    avg_score FLOAT,
    top10_avg_return FLOAT,
    top20_avg_return FLOAT,
    bottom30_avg_return FLOAT,
    top10_win_rate FLOAT,
    top20_win_rate FLOAT,
    high_risk_loss_rate FLOAT,
    low_risk_loss_rate FLOAT,
    monotonic_score FLOAT,
    metrics_json TEXT,
    created_at DATETIME
);
```

### 11.5 strategy_candidate_snapshot

```sql
CREATE TABLE strategy_candidate_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selection_id INTEGER,
    trade_date DATE NOT NULL,
    ts_code VARCHAR(16) NOT NULL,
    strategy_name VARCHAR(64),
    strategy_version VARCHAR(64),
    selected_time DATETIME,
    feature_time DATETIME,
    prediction_time DATETIME,
    features_json TEXT,
    created_at DATETIME
);
```

### 11.6 strategy_candidate_outcome

```sql
CREATE TABLE strategy_candidate_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER,
    trade_date DATE NOT NULL,
    ts_code VARCHAR(16) NOT NULL,
    actual_intraday_high_return FLOAT,
    actual_intraday_close_return FLOAT,
    actual_max_drawdown FLOAT,
    actual_touch_limit BOOLEAN,
    actual_seal_limit BOOLEAN,
    actual_break_limit BOOLEAN,
    actual_t1_open_return FLOAT,
    actual_t1_high_return FLOAT,
    actual_t1_close_return FLOAT,
    actual_high_open_low_close BOOLEAN,
    actual_big_loss BOOLEAN,
    updated_at DATETIME
);
```

### 11.7 selected_stock 快捷字段扩展

为了前端查询方便，可在 `SelectedStock` 增加快捷字段：

```text
auction_score
limitup_score
risk_score
premium_score
theme_score
t0_score
composite_score
model_advice
model_tags_json
```

完整模型结果仍以 `stock_model_scores` 为准。

### 11.8 补充数据库表

**strategy_candidate_snapshot**（候选股特征快照，区分proxy/live）：

```sql
CREATE TABLE strategy_candidate_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selection_id INTEGER,
    trade_date DATE NOT NULL,
    ts_code VARCHAR(16) NOT NULL,
    strategy_name VARCHAR(64) NOT NULL,
    strategy_version VARCHAR(64) NOT NULL,
    prediction_time_type VARCHAR(32) NOT NULL,
    feature_time DATETIME,
    snapshot_time DATETIME,
    data_mode VARCHAR(16) NOT NULL,
    features_json TEXT NOT NULL,
    source_status_json TEXT,
    created_at DATETIME
);
```

关键字段：data_mode (proxy/live), prediction_time_type (pre_open_925/open_935/post_close), features_json。

**strategy_candidate_outcome**（真实结果标签回填）：

```sql
CREATE TABLE strategy_candidate_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER,
    selection_id INTEGER,
    trade_date DATE NOT NULL,
    ts_code VARCHAR(16) NOT NULL,
    intraday_high_return FLOAT,
    intraday_close_return FLOAT,
    intraday_max_drawdown FLOAT,
    touch_limit BOOLEAN,
    seal_limit BOOLEAN,
    break_limit BOOLEAN,
    t1_open_return FLOAT,
    t1_high_return FLOAT,
    t1_close_return FLOAT,
    big_loss BOOLEAN,
    outcome_version VARCHAR(32),
    created_at DATETIME,
    updated_at DATETIME
);
```

**model_training_dataset**（训练数据集版本管理）：

```sql
CREATE TABLE model_training_dataset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name VARCHAR(64) NOT NULL,
    dataset_version VARCHAR(64) NOT NULL,
    strategy_name VARCHAR(64) NOT NULL,
    strategy_version VARCHAR(64) NOT NULL,
    prediction_time_type VARCHAR(32) NOT NULL,
    data_mode VARCHAR(16) NOT NULL,
    label_name VARCHAR(64) NOT NULL,
    label_definition TEXT,
    feature_set_version VARCHAR(64),
    feature_list_json TEXT,
    start_date DATE,
    end_date DATE,
    sample_count INTEGER,
    positive_count INTEGER,
    negative_count INTEGER,
    status VARCHAR(32),
    created_at DATETIME
);
```

**sample_bias_report**（样本偏差检测报告）：

```sql
CREATE TABLE sample_bias_report (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name VARCHAR(64) NOT NULL,
    strategy_version VARCHAR(64),
    historical_dataset_id INTEGER,
    live_start_date DATE,
    live_end_date DATE,
    prediction_time_type VARCHAR(32),
    historical_sample_count INTEGER,
    live_sample_count INTEGER,
    avg_jaccard FLOAT,
    avg_live_recall FLOAT,
    daily_count_status VARCHAR(32),
    feature_psi_json TEXT,
    outcome_compare_json TEXT,
    final_level VARCHAR(8),
    final_conclusion TEXT,
    suggestions_json TEXT,
    created_at DATETIME
);
```

**live_realtime_snapshot**（生产实时快照独立表，可选）：

```sql
CREATE TABLE live_realtime_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selection_id INTEGER,
    trade_date DATE NOT NULL,
    ts_code VARCHAR(16) NOT NULL,
    prediction_time_type VARCHAR(32) NOT NULL,
    snapshot_time DATETIME NOT NULL,
    auction_json TEXT,
    open_minute_json TEXT,
    market_env_json TEXT,
    sector_env_json TEXT,
    source_status_json TEXT,
    created_at DATETIME
);
```


---

## 12. API 设计规范

### 12.1 模型中心概览

```http
GET /api/v1/model/center/summary
```

返回：

```json
{
  "enabled_count": 3,
  "observe_count": 2,
  "disabled_count": 1,
  "today_scored_stock_count": 18,
  "latest_train_time": "2026-05-17 09:00:00",
  "latest_outcome_count": 1280
}
```

### 12.2 模型列表

```http
GET /api/v1/model/center/models
```

返回：

```json
[
  {
    "model_name": "auction_model",
    "display_name": "竞价强度模型",
    "model_type": "rule",
    "status": "enabled",
    "current_version": "rule_v1",
    "is_used_in_composite": true,
    "today_score_count": 18,
    "today_avg_score": 72.5,
    "recent_performance": "observe"
  }
]
```

### 12.3 模型详情

```http
GET /api/v1/model/center/models/{model_name}
```

### 12.4 更新模型状态

```http
POST /api/v1/model/center/models/{model_name}/status
```

请求：

```json
{
  "status": "enabled"
}
```

### 12.5 设置是否参与综合分

```http
POST /api/v1/model/center/models/{model_name}/composite
```

请求：

```json
{
  "is_used_in_composite": true
}
```

### 12.6 切换模型版本

```http
POST /api/v1/model/center/models/{model_name}/set-version
```

请求：

```json
{
  "version": "lgb_20260517_v1"
}
```

### 12.7 获取综合分配置

```http
GET /api/v1/model/center/composite-config
```

### 12.8 更新综合分配置

```http
POST /api/v1/model/center/composite-config
```

请求：

```json
{
  "mode": "pre_open",
  "weights": {
    "auction_score": 0.35,
    "limitup_score": 0.35,
    "risk_score": -0.30,
    "rule_score": 0.20
  }
}
```

### 12.9 获取某次选股模型分

```http
GET /api/v1/model/scores?selection_id=123
```

### 12.10 获取模型表现

```http
GET /api/v1/model/center/models/{model_name}/performance?window=60
```


### 12.11 构建历史候选池

```http
POST /api/v1/model/training/build-candidates
```

请求：

```json
{
  "strategy_name": "default_auction",
  "strategy_version": "default_auction_proxy_v1",
  "start_date": "2024-01-01",
  "end_date": "2026-05-10",
  "data_mode": "proxy",
  "prediction_time_type": "open_935",
  "force_rebuild": false
}
```

### 12.12 构建特征快照

```http
POST /api/v1/model/training/build-features
```

请求：`{"candidate_dataset_id": 12, "model_name": "risk_model", "prediction_time_type": "open_935", "feature_set_version": "risk_open_935_v1", "data_mode": "proxy"}`

### 12.13 回填结果标签

```http
POST /api/v1/model/training/fill-outcomes
```

请求：`{"start_date": "2024-01-01", "end_date": "2026-05-10", "outcome_version": "outcome_v1", "use_minute_data": true, "use_t1_data": true}`

### 12.14 生成训练数据集

```http
POST /api/v1/model/training/build-dataset
```

请求：`{"model_name": "risk_model", "dataset_version": "risk_open_935_proxy_v1", "strategy_name": "default_auction", "prediction_time_type": "open_935", "data_mode": "proxy", "label_name": "label_big_loss", "start_date": "2024-01-01", "end_date": "2026-05-10"}`

返回：`{"dataset_id": 21, "model_name": "risk_model", "dataset_version": "...", "sample_count": 12680, "positive_count": 1840, "status": "ready"}`

### 12.15 获取训练数据集详情

```http
GET /api/v1/model/training/datasets/{dataset_id}
```

### 12.16 创建样本偏差检测任务

```http
POST /api/v1/model/training/sample-bias/check
```

请求：`{"strategy_name": "default_auction", "strategy_version": "default_auction_proxy_v1", "historical_dataset_id": 21, "live_start_date": "2026-05-11", "live_end_date": "2026-05-17", "prediction_time_type": "open_935", "features": ["auction_open_pct", "auction_volume_pct", ...], "compare_replay_same_days": true}`

### 12.17 获取样本偏差检测报告

```http
GET /api/v1/model/training/sample-bias/reports/{check_id}
```

返回包含：`daily_count_compare`, `same_day_replay_compare`(avg_jaccard/avg_live_recall), `feature_psi`(各特征PSI值和状态), `final_level`(A/B/C), `final_conclusion`, `suggestions`。

### 12.18 模型中心样本偏差概览

```http
GET /api/v1/model/center/sample-bias/summary
```

返回：`latest_check_id, final_level, final_conclusion, abnormal_feature_count, avg_jaccard, live_sample_count`。

### 12.19 保存实时特征快照

```http
POST /api/v1/model/live/snapshots
```

请求：`{"selection_id": 123, "trade_date": "2026-05-17", "strategy_name": "default_auction", "prediction_time_type": "open_935", "snapshot_time": "2026-05-17 09:35:03", "data_mode": "live", "items": [{"ts_code": "...", "features": {...}, "source_status": {...}}]}`

### 12.20 获取某次选股实时快照

```http
GET /api/v1/model/live/snapshots?selection_id=123&prediction_time_type=open_935
```

### 12.21 实时模型预测

```http
POST /api/v1/model/live/predict
```

请求：`{"selection_id": 123, "prediction_time_type": "open_935", "models": ["auction_model", "limitup_model", "risk_model"], "use_latest_snapshot": true}`

### 12.22 结果回填

```http
POST /api/v1/model/live/outcomes/fill
```

请求：`{"selection_id": 123, "trade_date": "2026-05-17", "items": [{"ts_code": "...", "intraday_high_return": 5.8, "intraday_max_drawdown": -2.3, "touch_limit": true, "seal_limit": false, ...}]}`

---

## 13. 前端页面与交互设计

### 13.1 ModelCenter 页面结构

```text
ModelCenter.vue
  ├─ ModelSummaryCards.vue
  ├─ ModelListTable.vue
  ├─ CompositeConfigPanel.vue
  ├─ ModelPerformancePanel.vue
  └─ ModelDetailDrawer.vue
```

### 13.2 顶部概览卡片

展示：

```text
已启用模型：3
观察中模型：2
禁用模型：1
今日打分股票：18
最近回填样本：1280
最近训练：2026-05-17
```

### 13.3 模型列表表格

字段：

```text
模型
用途
类型
版本
状态
参与综合分
今日打分
平均分
表现
操作
```

状态样式：

```text
enabled：绿色
observe：蓝色
disabled：灰色
```

### 13.4 模型详情抽屉

展示：

```text
基础信息
评分逻辑
特征列表
标签定义
历史版本
最近打分样例
最近 20 / 60 日表现
```

### 13.5 StockResults 页面扩展

表格字段增加：

```text
排名
股票
行业/题材
规则分
综合分
竞价强度
封板潜力
风险分
次日溢价
T+0 成功率
操作建议
```

### 13.6 结果页排序切换

支持：

```text
按综合分排序
按竞价强度排序
按封板潜力排序
按低风险排序
按次日溢价排序
按 T+0 成功率排序
```

### 13.7 个股模型详情展开

点击股票后展示：

```text
竞价强度模型：86
理由：竞价量占比适中、竞价额/流通市值较高

封板潜力模型：78
理由：近 20 日涨停活跃、封板率较高、板块助攻较强

风险模型：34
理由：竞价高开未过度、近期炸板较少、市场情绪尚可
```

---

## 14. 选股流程集成方案

### 14.1 当前选股流程插入点

在当前 `stock_selector.py` 中，建议在规则评分之后、最终分计算之前插入：

```text
ModelScoreService
CompositeScoreService
```

### 14.2 改造后流程

```text
阶段 1：通达信 MCP / 本地数据初筛
阶段 2：Tushare 数据增强
阶段 3：封板率计算
阶段 4：规则评分
阶段 5：多模型打分
阶段 6：综合分计算
阶段 7：保存结果和模型分
阶段 8：后台预热详情
```

### 14.3 伪代码

```python
def process_candidate(stock_data: dict):
    rule_score = rule_score_service.calculate(stock_data)
    stock_data["rule_score"] = rule_score

    model_result = model_score_service.score_candidate(stock_data)
    stock_data.update(model_result["flat_scores"])

    composite_result = composite_score_service.calculate(
        stock_data=stock_data,
        model_scores=model_result["model_scores"]
    )

    stock_data["composite_score"] = composite_result["score"]
    stock_data["model_advice"] = composite_result["advice"]
    stock_data["model_tags"] = composite_result["tags"]

    save_selected_stock(stock_data)
    save_stock_model_scores(model_result)
```

### 14.4 降级策略

模型调用失败时：

```text
1. 不阻塞选股主流程。
2. 记录错误日志。
3. 当前模型分为空。
4. 综合分按已有字段动态归一。
5. 模型中心显示最近错误。
```

---

## 15. 训练、回测与有效性验证

### 15.1 准确率不是唯一目标

对本系统来说，模型有效性不是简单的 accuracy，而是：

```text
默认竞价策略 + 模型排序/过滤 后，是否长期稳定优于默认竞价策略原版。
```

### 15.2 必须使用时间切分

禁止随机切分。

推荐：

```text
训练集：2022-01-01 ~ 2024-12-31
验证集：2025-01-01 ~ 2025-12-31
测试集：2026-01-01 ~ 当前
```

更推荐 walk-forward。

### 15.3 分层验证

按模型分分层：

```text
Top 10%
10% - 30%
30% - 50%
50% - 70%
Bottom 30%
```

观察：

```text
高分组收益是否更高
高分组封板率是否更高
低风险组大亏率是否更低
```

### 15.4 与默认策略对比

至少回测四组：

```text
A：默认策略原始排序
B：默认策略 + auction_score 排序
C：默认策略 + limitup_score 排序
D：默认策略 + auction + limitup - risk 综合排序
```

比较指标：

```text
Top 1 平均收益
Top 3 平均收益
Top 5 平均收益
胜率
最大回撤
大亏次数
连续亏损天数
月度稳定性
```

### 15.5 风险模型单独验收

风险模型重点看：

```text
高风险组大亏率
低风险组大亏率
过滤高风险 20% 后最大回撤是否下降
过滤后收益是否没有明显下降
```

### 15.6 模型中心展示指标

每个模型展示：

```text
最近 20 日 Top 10% 表现
最近 60 日 Top 20% 表现
高分组与低分组差异
分层单调性
风险过滤效果
是否优于默认策略
```

### 15.7 上线标准

```text
1. 离线回测通过。
2. observe 实盘观察至少 20 个交易日。
3. Top N 表现优于默认策略原版。
4. 高分组表现优于低分组。
5. 风险模型能降低最大回撤或大亏次数。
6. 无明显未来函数。
```

---

## 15b. 训练前检查清单

正式训练前必须通过以下检查。

### 策略一致性
- strategy_name 是否一致
- strategy_version 是否一致
- 默认竞价条件是否一致
- 过滤条件是否一致
- 候选股数量是否正常

### 数据时点一致性
- prediction_time_type 是否明确
- feature_time 是否 <= prediction_time
- 是否误用了T日收盘后数据
- 是否误用了T+1数据

### 数据源状态
- Tushare daily_basic 是否完整
- 通达信日线是否完整
- 通达信分钟线是否完整
- 实时快照是否保存
- 缺失率是否可接受

### 样本偏差检测
- 候选股重合度是否达标 (Jaccard≥0.80 或≥0.60)
- 核心字段PSI是否达标 (<0.25)
- live日选股数量是否在历史P10-P90范围内
- proxy与live口径是否偏差过大

### 标签质量
- 标签是否用未来结果生成（正确）
- 标签是否和模型目标一致
- 正负样本比例是否极端失衡
- 大亏标签是否过少
- 封板标签是否计算正确

### 数据集版本
- dataset_version 是否唯一
- feature_set_version 是否记录
- label_definition 是否记录
- data_mode 是否记录 (proxy/live)
- prediction_time_type 是否记录

---


## 16. 开发实施计划

### 16.1 第一阶段：规则模型闭环

目标：先做出来。

任务：

```text
1. 新增 model_registry 表
2. 新增 model_versions 表
3. 新增 stock_model_scores 表
4. 新增 model_daily_metrics 表
5. 实现 auction_rule_model
6. 实现 limitup_rule_model
7. 实现 risk_rule_model
8. 实现 model_score_service
9. 实现 composite_score_service
10. 选股流程接入模型打分
11. SelectedStock 增加快捷字段
12. StockResults 增加多模型列
13. ModelCenter 显示模型列表

### 16.1b 第一阶段详细开发顺序

**第一步：补表** — 新增 strategy_candidate_snapshot / strategy_candidate_outcome / model_training_dataset / sample_bias_report。

**第二步：保存 live 快照** — 在选股完成后保存实时竞价字段、实时开盘/分钟字段、市场环境字段、板块字段、source_status_json。

**第三步：历史回放候选池** — 用通达信日线+分钟线+Tushare回放默认竞价策略。

**第四步：构建 proxy 特征** — 先做 open_935 proxy特征：open_pct_proxy / first_5min_amount_pct / open_5min_return / open_5min_max_drawdown。

**第五步：回填结果** — 回填 intraday_high_return / intraday_max_drawdown / touch_limit / seal_limit / break_limit / t1_open_return / t1_high_return / t1_close_return / big_loss。

**第六步：样本偏差检测** — 用最近5个交易日live样本对比历史replay样本。

**第七步：生成第一版训练集** — 优先生成 auction_open_935_proxy_v1 / limitup_open_935_proxy_v1 / risk_open_935_proxy_v1。

**第八步：模型中心展示** — 新增数据集版本 / 样本偏差等级 / live样本数 / PSI异常字段 / 是否允许启用。

```

### 16.2 第二阶段：回填与评估

任务：

```text
1. 新增 strategy_candidate_snapshot
2. 新增 strategy_candidate_outcome
3. 实现结果回填服务
4. 实现 model_evaluation_service
5. 模型中心展示最近 20 / 60 日表现
6. 支持模型分层表现查看
7. 支持风险过滤效果查看
```

### 16.3 第三阶段：LightGBM 训练接入

任务：

```text
1. 实现训练样本构建脚本
2. 实现 auction_model 训练
3. 实现 limitup_model 训练
4. 实现 risk_model 训练
5. 实现模型版本注册
6. 支持 lgb 模型加载
7. 新模型默认 observe
8. 模型中心支持切换版本
```

### 16.4 第四阶段：扩展模型

任务：

```text
1. 增加 premium_model
2. 增加 t0_model
3. 增加 theme_model
4. 增加综合分模式切换
5. 增加排序模式切换
```

### 16.5 第五阶段：自动化与监控

任务：

```text
1. 自动评估模型表现
2. 自动提示模型失效
3. 自动生成训练报告
4. 自动化 walk-forward 回测
5. 支持模型降级 observe
```

---

## 17. 质量保证计划

### 17.1 单元测试

覆盖：

```text
规则模型评分函数
综合分计算函数
模型状态切换逻辑
模型分保存逻辑
结果回填标签生成逻辑
```

### 17.2 集成测试

覆盖：

```text
选股接口是否正常返回
模型分是否正常入库
SelectedStock 快捷字段是否同步
ModelCenter 是否能读取模型状态
StockResults 是否能展示多模型列
```

### 17.3 数据校验

必须校验：

```text
score 是否在 0-100
risk_score 是否越高越危险
model_version 是否为空
feature_time 是否晚于 prediction_time
模型分是否能与 selection_id 对齐
```

### 17.4 回测校验

每次模型上线前必须输出：

```text
模型分层表现
Top N 表现
风险过滤效果
与默认策略对比
样本数量
训练区间
测试区间
```

---

## 18. 运维监控方案

### 18.1 模型调用监控

监控：

```text
每个模型调用次数
每个模型平均耗时
每个模型失败次数
每个模型平均分
每个模型高分数量
```

### 18.2 数据监控

监控：

```text
每日候选股数量
每日模型分数量
每日回填样本数量
特征缺失率
模型分布漂移
```

### 18.3 表现监控

监控：

```text
最近 20 日 Top 3 收益
最近 20 日风险过滤效果
最近 60 日分层单调性
高风险组大亏率
模型是否优于默认策略
```

### 18.4 告警建议

触发告警：

```text
模型连续调用失败
模型平均分突然大幅偏移
高分组表现低于低分组
风险模型高风险组大亏率不高
回填样本连续缺失
```

---

## 19. 风险评估与应对

### 19.1 未来函数风险

风险：使用了预测时点之后的数据。

应对：

```text
强制保存 feature_time 和 prediction_time。
训练前检查 feature_time <= prediction_time。
早盘模型不得使用当天收盘数据。
```

### 19.2 过拟合风险

风险：样本少、特征多、模型在历史上表现好但实盘失效。

应对：

```text
第一版用规则模型。
LightGBM 限制树深度和叶子数。
使用时间切分和 walk-forward。
新模型 observe 至少 20 个交易日。
```

### 19.3 误杀强势股风险

风险：风险模型过滤掉真正强势股。

应对：

```text
风险模型先 observe。
风险过滤阈值先保守。
评估过滤前后收益和回撤。
只过滤极高风险，不一开始大面积过滤。
```

### 19.4 前端复杂度风险

风险：展示太多模型分，用户难以使用。

应对：

```text
默认只展示核心列：综合分、竞价强度、封板潜力、风险分。
其他模型放到展开详情。
支持用户切换排序模式。
```

### 19.5 主流程稳定性风险

风险：模型服务异常影响选股接口。

应对：

```text
模型打分失败不阻塞主流程。
缺失模型分动态降级综合分。
模型异常写入日志和模型中心状态。
```

---

## 20. 验收标准

### 20.1 第一阶段验收标准

```text
1. 模型中心能看到 auction_model、limitup_model、risk_model。
2. 三个模型均有 rule_v1 版本。
3. 选股时能生成三个模型分。
4. stock_model_scores 有正确入库记录。
5. SelectedStock 能保存快捷分数字段。
6. 选股结果页能展示综合分、竞价强度、封板潜力、风险分。
7. 综合分能正确排序。
8. 模型失败不影响选股接口返回。
```

### 20.2 第二阶段验收标准

```text
1. 能保存候选股特征快照。
2. 能回填真实行情结果。
3. 能计算模型分层表现。
4. 能计算 Top 1 / Top 3 / Top 5 表现。
5. 能在模型中心展示最近 20 / 60 日表现。
```

### 20.3 第三阶段验收标准

```text
1. 能基于默认策略候选样本训练 LightGBM。
2. 能生成模型文件和版本记录。
3. LightGBM 模型能进入 observe 状态。
4. 模型中心能切换版本。
5. observe 模型不影响综合排序。
```

### 20.4 有效性验收标准

```text
1. 高分组收益高于低分组。
2. 高分组封板率高于低分组。
3. 高风险组大亏率高于低风险组。
4. 过滤高风险样本后最大回撤下降。
5. 默认策略 + 综合排序 Top 3 优于默认策略原始 Top 3。
```

### 20.5 数据保存验收

必须满足：
1. 每次真实选股后，所有候选股都有 live 快照
2. live 快照包含 prediction_time_type 和 data_mode
3. features_json 可复现模型输入
4. source_status_json 能说明数据来源是否正常

### 20.6 历史训练数据验收

必须满足：
1. 能生成历史候选池
2. 能生成特征快照
3. 能回填结果标签
4. 每个训练数据集有唯一 dataset_version
5. 每个训练数据集记录特征列表和标签定义

### 20.7 样本偏差检测验收

必须满足：
1. 能输出候选股数量对比
2. 能输出同日replay与live的Jaccard
3. 能输出核心字段PSI
4. 能输出A/B/C评级
5. 模型中心能展示最新样本偏差报告

### 20.8 训练前准入验收

模型训练前必须满足：
1. strategy_version 一致
2. prediction_time_type 明确
3. data_mode 明确
4. 样本偏差报告不是C级
5. 不存在明显未来函数

### 20.9 上线状态验收

新模型训练完成后：
1. 默认进入 observe
2. 不直接参与综合分
3. 需要 live 观察至少20个交易日
4. 样本偏差等级A或B才允许展示
5. 只有回测和observe表现均通过后，才允许 enabled


---

## 21. 后续演进规划

### 21.1 模型层演进

```text
规则模型
  ↓
LightGBM 分类模型
  ↓
LightGBM Ranker
  ↓
分市场环境动态权重
  ↓
模型自动评估与降级
```

### 21.2 特征层演进

```text
基础行情特征
  ↓
竞价特征
  ↓
封板结构特征
  ↓
市场情绪特征
  ↓
题材关系特征
  ↓
分时特征
  ↓
相似样本特征
```

### 21.3 前端层演进

```text
多模型列展示
  ↓
模型详情抽屉
  ↓
排序模式切换
  ↓
模型表现图表
  ↓
个股相似样本解释
  ↓
模型策略复盘报告
```

### 21.4 实盘闭环演进

```text
模型打分
  ↓
用户查看
  ↓
结果回填
  ↓
模型评估
  ↓
模型训练
  ↓
新模型 observe
  ↓
稳定后 enabled
```

---

## 22. 附录：第一版规则模型评分建议

### 22.1 工具函数

```python
def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def range_score(value: float, good_min: float, good_max: float, hard_min: float, hard_max: float) -> float:
    if value is None:
        return 50
    if good_min <= value <= good_max:
        return 100
    if value < hard_min or value > hard_max:
        return 0
    if value < good_min:
        return 100 * (value - hard_min) / max(good_min - hard_min, 1e-6)
    return 100 * (hard_max - value) / max(hard_max - good_max, 1e-6)
```

### 22.2 竞价强度规则模型

```python
def calc_auction_score(stock: dict) -> dict:
    auction_open_pct = stock.get("auction_open_pct", 0)
    auction_volume_pct = stock.get("auction_volume_pct", 0)
    auction_turnover_rate = stock.get("auction_turnover_rate", 0)
    auction_amount_to_float_mv = stock.get("auction_amount_to_float_mv", 0)
    ret_5d = stock.get("ret_5d", 0)

    open_score = range_score(auction_open_pct, 1, 5, -2, 8)
    volume_score = range_score(auction_volume_pct, 4, 15, 0, 35)
    turnover_score = range_score(auction_turnover_rate, 0.5, 5, 0, 12)
    amount_score = range_score(auction_amount_to_float_mv, 0.05, 0.35, 0, 1.0)
    trend_score = range_score(ret_5d, 2, 18, -5, 35)

    score = (
        open_score * 0.30
        + volume_score * 0.25
        + turnover_score * 0.20
        + amount_score * 0.15
        + trend_score * 0.10
    )

    explain = []
    if open_score >= 80:
        explain.append("竞价涨幅处于较合理区间")
    if volume_score >= 80:
        explain.append("竞价量占比表现较强")
    if amount_score >= 80:
        explain.append("竞价成交额相对流通市值较活跃")

    return {
        "score": clamp(score),
        "level": "强" if score >= 80 else "中" if score >= 60 else "弱",
        "explain": explain,
        "version": "rule_v1"
    }
```

### 22.3 封板潜力规则模型

```python
def calc_limitup_score(stock: dict) -> dict:
    limitup_count_20d = stock.get("limitup_count_20d", 0)
    seal_rate_20d = stock.get("seal_rate_20d", 0)
    touch_limit_count_20d = stock.get("touch_limit_count_20d", 0)
    break_limit_count_20d = stock.get("break_limit_count_20d", 0)
    sector_limitup_count = stock.get("sector_limitup_count", 0)
    market_seal_rate = stock.get("seal_rate_market", 0)

    gene_score = clamp(limitup_count_20d * 20)
    seal_score = clamp(seal_rate_20d * 100)
    touch_score = clamp(touch_limit_count_20d * 12)
    break_penalty = clamp(break_limit_count_20d * 10)
    sector_score = clamp(sector_limitup_count * 10)
    market_score = clamp(market_seal_rate * 100)

    score = (
        gene_score * 0.30
        + seal_score * 0.25
        + touch_score * 0.15
        + sector_score * 0.15
        + market_score * 0.15
        - break_penalty * 0.15
    )

    explain = []
    if limitup_count_20d > 0:
        explain.append("近期存在涨停活跃记录")
    if seal_rate_20d >= 0.5:
        explain.append("历史封板率较好")
    if sector_limitup_count >= 3:
        explain.append("所属题材存在板块助攻")

    return {
        "score": clamp(score),
        "level": "强" if score >= 80 else "中" if score >= 60 else "弱",
        "explain": explain,
        "version": "rule_v1"
    }
```

### 22.4 大面风险规则模型

```python
def calc_risk_score(stock: dict) -> dict:
    ret_5d = stock.get("ret_5d", 0)
    ret_10d = stock.get("ret_10d", 0)
    auction_open_pct = stock.get("auction_open_pct", 0)
    upper_shadow_1d = stock.get("upper_shadow_1d", 0)
    break_limit_count_20d = stock.get("break_limit_count_20d", 0)
    market_break_limit_total = stock.get("break_limit_total", 0)

    high_position_risk = clamp(max(ret_5d - 20, 0) * 3 + max(ret_10d - 35, 0) * 2)
    high_open_risk = clamp(max(auction_open_pct - 5, 0) * 15)
    shadow_risk = clamp(upper_shadow_1d * 100)
    break_history_risk = clamp(break_limit_count_20d * 15)
    market_risk = clamp(market_break_limit_total * 3)

    score = (
        high_position_risk * 0.25
        + high_open_risk * 0.20
        + shadow_risk * 0.15
        + break_history_risk * 0.20
        + market_risk * 0.20
    )

    risk_tags = []
    if high_position_risk >= 60:
        risk_tags.append("高位加速")
    if high_open_risk >= 60:
        risk_tags.append("竞价高开过度")
    if break_history_risk >= 60:
        risk_tags.append("历史炸板偏多")
    if market_risk >= 60:
        risk_tags.append("市场炸板风险较高")

    if score >= 80:
        level = "极高风险"
    elif score >= 60:
        level = "高风险"
    elif score >= 30:
        level = "中风险"
    else:
        level = "低风险"

    return {
        "score": clamp(score),
        "risk_level": level,
        "risk_tags": risk_tags,
        "explain": risk_tags,
        "version": "rule_v1"
    }
```

### 22.5 综合分计算

```python
def calc_composite_score(stock: dict) -> dict:
    auction_score = stock.get("auction_score", 0)
    limitup_score = stock.get("limitup_score", 0)
    risk_score = stock.get("risk_score", 0)
    rule_score = stock.get("rule_score", 0)

    score = (
        auction_score * 0.35
        + limitup_score * 0.35
        - risk_score * 0.30
        + rule_score * 0.20
    )

    score = clamp(score)

    if score >= 80 and risk_score < 40:
        advice = "重点关注"
    elif score >= 65 and risk_score < 60:
        advice = "正常关注"
    elif risk_score >= 70:
        advice = "高风险，仅观察"
    else:
        advice = "低优先级"

    return {
        "score": score,
        "advice": advice
    }
```

---

# 结语

本方案的核心不是一次性训练出所有模型，而是让 `xuangu` 先形成一个稳定的多模型闭环：

```text
默认竞价策略产生候选股
  ↓
多个模型分别打分
  ↓
模型中心统一管理
  ↓
前端多维展示
  ↓
综合排序和风险提示
  ↓
真实结果回填
  ↓
模型表现评估
  ↓
逐步训练和替换 LightGBM 模型
```

第一版只要完成 `auction_model + limitup_model + risk_model` 三个规则模型，并成功接入模型中心和选股结果页，就已经具备后续持续优化的基础。

---

# 附录

## 附录 A：第一阶段必需字段总表

| 字段 | 用途 | 历史来源 | 生产来源 | 第一阶段必需 |
|---|---|---|---|---|
| trade_date | 样本标识 | 全部 | 全部 | 是 |
| ts_code | 样本标识 | 全部 | 全部 | 是 |
| strategy_version | 样本一致性 | 系统 | 系统 | 是 |
| data_mode | 区分proxy/live | 系统 | 系统 | 是 |
| prediction_time_type | 区分预测时点 | 系统 | 系统 | 是 |
| auction_open_pct | 竞价强度 | proxy/open | 实时竞价 | 是 |
| auction_volume_pct | 竞价强度 | proxy/分钟线 | 实时竞价 | 是 |
| auction_turnover_rate | 竞价强度 | proxy/Tushare | 实时竞价 | 是 |
| auction_amount_to_float_mv | 竞价强度 | proxy+Tushare | 实时竞价+Tushare | 是 |
| open_5min_return | 9:35模型 | 分钟线 | 实时分钟线 | 是 |
| open_5min_max_drawdown | 风险模型 | 分钟线 | 实时分钟线 | 是 |
| ret_5d | 趋势 | 通达信日线 | 通达信日线 | 是 |
| limitup_count_20d | 涨停基因 | 通达信日线 | 通达信日线 | 是 |
| seal_rate_20d | 封板质量 | 日线/分钟线 | 日线/分钟线 | 是 |
| float_mv | 市值 | Tushare | Tushare | 是 |
| market_seal_rate | 市场环境 | 历史聚合 | 实时/昨日聚合 | 是 |
| sector_limitup_count | 题材环境 | 板块聚合 | 实时/昨日聚合 | 否，建议 |
| intraday_high_return | 标签 | 分钟线 | 结果回填 | 是 |
| intraday_max_drawdown | 标签 | 分钟线 | 结果回填 | 是 |
| seal_limit | 标签 | 日线/分钟线 | 结果回填 | 是 |
| t1_open_return | 标签 | 次日数据 | 结果回填 | 是 |

---

## 附录 B：第一阶段建议训练数据集

```text
1. auction_open_935_proxy_v1
   用途：竞价强度第一版训练
   数据：历史分钟线代理 + T-1日线 + 市场环境
   标签：9:30-10:00 是否走强

2. limitup_open_935_proxy_v1
   用途：封板潜力第一版训练
   数据：历史分钟线代理 + 涨停结构 + 市场环境
   标签：当日是否封板

3. risk_open_935_proxy_v1
   用途：大面风险第一版训练
   数据：开盘5分钟走势 + 高位风险 + 炸板历史 + 市场环境
   标签：是否出现大面风险
```

---

## 附录 C：不允许用于早盘模型训练的字段

以下字段不能用于 `pre_open_925`、`open_930`、`open_935` 早盘模型的训练特征：

```text
T日收盘价
T日全天成交额
T日最终换手率
T日是否最终封板
T日是否最终炸板
T日龙虎榜
T+1开盘价
T+1最高价
T+1收盘价
T+1新闻
T+1收益
```

这些字段只能用于：标签 / 结果回填 / 收盘后模型 premium_afterclose_model / 复盘分析。

---

## 附录 D：推荐结论

当前阶段建议：

```text
1. 不要急着用5天真实样本训练模型。
2. 先用这5天真实样本做样本偏差检测。
3. 如果historical replay与live样本差异小，再用长周期历史proxy样本训练。
4. 训练后的模型先进入observe，不参与综合排序。
5. 从现在开始持续保存live实时快照。
6. live样本累计20-60个交易日后，再训练真正的live模型。
```

最终原则：

```text
先证明训练样本像真实样本，再训练模型；
先保存真实预测快照，再谈长期模型有效性。
```
