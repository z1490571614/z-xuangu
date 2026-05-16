# 默认竞价策略胜率模型 V2 设计

## 背景

当前 `leader_main_t0_lgbm` 训练链路更偏“历史竞价表生成候选 + T+0 封板排序”。它不能直接代表默认竞价策略每天真实选出的股票，也不能覆盖“高溢价”和“连板”两个接力核心目标。

新的模型目标不是替代默认选股策略，而是服务默认策略：对每天默认竞价策略已经选出的股票，预测后续涨停、高溢价、连板的概率，并给出可回测、可解释的排序依据。

由于当前没有大量真实生产环境每日选股列表，训练数据不能只依赖 `selected_stock` 的真实历史记录。需要先用默认策略做历史回放，再用最近几个有真实选股记录的交易日验证回放结果。如果回放选股和真实选股差距不大，才认为该回放策略可用于生成训练样本。

## 目标

新增 `default_auction_relay_v2` 训练体系，支持：

1. 用默认竞价选股策略回放历史交易日，生成候选股票。
2. 用最近真实选股列表验证回放策略有效性。
3. 验证通过后，生成历史训练样本。
4. 给样本生成三个标签：T+0 涨停/封板、T+1 高溢价、T+1 连板。
5. 训练三个独立模型，并输出综合接力分。
6. 在模型中心展示训练指标、TopK 胜率、分桶报告和模型版本。
7. 在当前选股结果中展示概率，不改变默认策略本身。

## 非目标

本期不做：

1. 不训练全市场涨停预测模型。
2. 不用新闻、公告、舆情或 AI 文本因素。
3. 不直接修改默认选股策略条件。
4. 不让模型结果阻断或替代现有选股流程。
5. 不删除旧 `leader_main_t0_lgbm`，仅将其降级为兼容模型。

## 样本口径

训练服务的对象是默认竞价策略选出的股票。

真实样本：

```text
selection_record.task_template = default
+ selected_stock
```

历史回放样本：

```text
DefaultAuctionReplayService
  -> 按默认策略条件回放历史交易日
  -> 生成候选列表
  -> 保存当时可见特征
```

样本必须记录来源：

```text
sample_source = real_selected | replay_backtest
replay_source = mcp_replay | local_replay | historical_backfill
strategy_name = default
strategy_version = default_auction_v2
```

## 策略回放有效性验证

训练前必须先验证回放策略是否接近近期真实选股。

验证集：

```text
最近 N 个有真实 selected_stock 记录的交易日
```

每日对比：

```text
真实列表 = 当天默认策略真实选股
回放列表 = 用默认策略历史数据重新跑出的选股
```

指标：

```text
recall = 真实列表中被回放命中的比例
precision = 回放列表中也出现在真实列表的比例
jaccard = 交集 / 并集
count_error = abs(回放数量 - 真实数量) / max(真实数量, 1)
top_overlap = Top5 / Top10 重合度
```

默认验收线：

```text
平均 recall >= 80%
平均 jaccard >= 60%
每日数量误差 <= 30%
核心差异股票必须可解释
```

如果验收失败，不允许批量生成训练样本。系统应输出差异诊断，包括竞价字段、涨停次数、封板率、近 10 日涨幅、过滤原因和排序差异。

## 竞价数据口径

模型必须贴近生产默认策略的竞价口径。

核心字段：

```text
auction_ratio
auction_turnover_rate
open_change_pct
pre_change_pct
```

历史回放竞价数据优先级：

1. 能复刻生产 MCP/通达信竞价字段的历史数据。
2. 已落库的生产竞价字段。
3. `stock_auction_open` 仅作为历史补齐来源。

所有样本必须保存：

```text
auction_source
auction_ratio_unit
auction_turnover_rate_basis
feature_snapshot_time
```

`auction_ratio` 统一使用百分数口径，例如 `8.19` 表示 `8.19%`。竞价换手率必须记录分母口径，优先贴近生产策略使用的自由流通换手口径。

## 特征设计

不使用新闻因素。明确排除：

```text
integrated_news_service
SentimentAnalyzer
news_sentiment
announcement_alpha_score
has_negative_news
has_reduction_news
has_regulatory_risk
```

竞价特征：

```text
auction_ratio
auction_turnover_rate
open_change_pct
pre_change_pct
auction_amount
auction_volume
```

默认策略结构特征：

```text
limit_up_count
touch_days
limit_up_days
seal_rate
rise_10d_pct
circ_mv
prev_turnover_rate
lu_tag
lu_status
lu_open_num
limit_up_suc_rate
```

评分特征：

```text
rule_score
final_score
score_level_encoded
risk_tags_count
```

市场环境特征：

```text
market_limit_up_count
market_limit_down_count
market_max_connected_board
market_zhaban_rate
market_emotion_score
```

板块特征：

```text
sector_strength
sector_limit_up_count
sector_rank
is_sector_front_runner
sector_change_pct
```

龙头和风险特征，仅使用非新闻部分：

```text
leader_strength_score
retreat_risk_score
health_score
leader_level_encoded
cycle_stage_encoded
risk_total_score
market_score
chip_score
capital_score
lhb_score
sector_score
technical_score
```

## 标签定义

### A. T+0 涨停/封板

```text
label_t0_limit_success = 1
```

条件：

```text
T 日最高价触及涨停价
且 T 日收盘价 >= 涨停价 * 0.997
```

### B. T+1 高溢价

```text
label_t1_premium_success = 1
```

默认满足任一：

```text
T+1 开盘涨幅 >= 3%
T+1 最高涨幅 >= 5%
T+1 收盘涨幅 >= 3%
```

阈值写入模型参数，允许在模型中心调整。

### C. T+1 连板

```text
label_t1_continue_limit = 1
```

条件：

```text
T+1 最高价触及涨停价
且 T+1 收盘价 >= 涨停价 * 0.997
```

### 一字板处理

不直接删除一字板样本。增加标记：

```text
is_t0_one_line_limit_up
is_t1_one_line_limit_up
```

评估时同时输出：

```text
全部样本胜率
可参与样本胜率
一字板样本占比
```

## 数据表

新增表：

```text
default_auction_training_sample
```

建议字段：

```text
id
trade_date
ts_code
name
strategy_name
strategy_version
sample_source
replay_source
matched_recent_real_sample
auction_source
auction_ratio_unit
auction_turnover_rate_basis
feature_json
label_t0_limit_success
label_t1_premium_success
label_t1_continue_limit
t0_high_return
t0_close_return
t1_open_return
t1_high_return
t1_close_return
is_t0_limit_up
is_t1_limit_up
is_t0_one_line_limit_up
is_t1_one_line_limit_up
created_at
updated_at
```

唯一约束：

```text
strategy_version + trade_date + ts_code + sample_source
```

## 模型设计

训练三个独立 LightGBM 模型：

```text
default_auction_t0_limit_lgbm
default_auction_t1_premium_lgbm
default_auction_t1_continue_lgbm
```

三个目标不同，不能混成一个标签。综合接力分在预测后计算：

```text
relay_score =
  t0_limit_prob * 0.25
+ t1_premium_prob * 0.35
+ t1_continue_prob * 0.40
```

初期只展示概率和综合分，不改变默认策略筛选条件。

## 训练切分

按交易日期做时间序列切分，禁止随机打乱：

```text
70% train
15% validation
15% test
```

样本不足时：

1. 输出样本不足诊断。
2. 可训练 LogisticRegression 或小参数 LightGBM 作为 baseline。
3. 不自动激活低样本模型。

## 评估和验收

不能只看 accuracy。必须输出策略场景指标：

```text
默认策略全体基础胜率
模型 Top1 胜率
模型 Top3 胜率
模型 Top5 胜率
概率分桶胜率
按竞昨比分组胜率
按竞价换手分组胜率
按市场情绪分组胜率
按连板高度分组胜率
```

模型通过标准建议：

```text
Top3 胜率 > 默认策略全体胜率 + 10 个百分点
Top5 胜率 > 默认策略全体胜率 + 6 个百分点
测试集命中样本数 >= 30
最近测试区间不能只靠单一天贡献
```

如果模型没有跑赢默认策略基准，不允许自动激活。

## 自动调参与重训闸门

模型训练完成不代表可用。每个目标模型必须先通过验收闸门，未通过时自动调整模型参数重训；达到最大尝试次数仍不通过时，任务状态置为 `rejected`，保留旧 active 模型。

闸门流程：

```text
准备固定训练/验证/测试日期切分
  -> attempt 1 使用默认参数训练
  -> 在同一测试集计算验收指标
  -> 通过：保存版本，可手动或按配置自动激活
  -> 未通过：选择下一组参数重训
  -> 超过 max_retrain_attempts 仍未通过：任务 rejected
```

重训只能调整模型参数，不能自动修改默认选股策略条件，也不能改变标签定义。允许调整：

```text
learning_rate
n_estimators
num_leaves
max_depth
min_child_samples
subsample
colsample_bytree
reg_alpha
reg_lambda
is_unbalance / scale_pos_weight
random_seed
early_stopping_rounds
```

不允许自动调整：

```text
默认策略筛选条件
竞价字段计算口径
新闻/公告/舆情特征
T+0/T+1 标签定义
训练/测试日期边界
```

默认参数候选：

```text
attempt 1: balanced_default
  learning_rate=0.05, num_leaves=31, max_depth=-1,
  min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
  reg_alpha=0, reg_lambda=0, is_unbalance=true

attempt 2: conservative_regularized
  learning_rate=0.03, num_leaves=15, max_depth=4,
  min_child_samples=30, subsample=0.75, colsample_bytree=0.75,
  reg_alpha=0.1, reg_lambda=1.0, is_unbalance=true

attempt 3: shallow_stable
  learning_rate=0.04, num_leaves=7, max_depth=3,
  min_child_samples=40, subsample=0.9, colsample_bytree=0.7,
  reg_alpha=0.2, reg_lambda=2.0, is_unbalance=true

attempt 4: wider_ranker
  learning_rate=0.02, num_leaves=63, max_depth=6,
  min_child_samples=15, subsample=0.8, colsample_bytree=0.9,
  reg_alpha=0.05, reg_lambda=0.5, is_unbalance=true

attempt 5: seed_retry
  使用当前最佳参数，仅更换 random_seed
```

默认最大尝试次数：

```text
max_retrain_attempts = 5
```

每次 attempt 必须写入 `model_training_job.attempts_json`：

```text
attempt_no
param_profile
params
sample_count
positive_count
baseline_rate
top1_rate
top3_rate
top5_rate
top3_lift
top5_lift
auc
precision
recall
accepted
reject_reasons
model_path
model_version
```

验收闸门按目标模型分别判断。

T+0 涨停模型：

```text
Top3 涨停率 >= 默认策略全体 T+0 涨停率 + 8 个百分点
Top5 涨停率 >= 默认策略全体 T+0 涨停率 + 5 个百分点
测试集 TopK 命中正样本数 >= 20
AUC >= 0.55
```

T+1 高溢价模型：

```text
Top3 高溢价率 >= 默认策略全体 T+1 高溢价率 + 10 个百分点
Top5 高溢价率 >= 默认策略全体 T+1 高溢价率 + 6 个百分点
测试集 TopK 命中正样本数 >= 25
AUC >= 0.55
```

T+1 连板模型：

```text
Top3 连板率 >= 默认策略全体 T+1 连板率 + 6 个百分点
Top5 连板率 >= 默认策略全体 T+1 连板率 + 4 个百分点
测试集 TopK 命中正样本数 >= 10
AUC >= 0.53
```

由于连板样本稀疏，T+1 连板模型允许 AUC 门槛更低，但必须满足 TopK 相对提升。若正样本不足，任务应输出 `insufficient_positive_samples`，不允许激活模型。

候选模型选择规则：

```text
先筛选通过验收闸门的 attempt
  -> 优先 top3_lift 最大
  -> 再比较 top5_lift
  -> 再比较 AUC
  -> 再选择参数更保守的模型
```

如果所有 attempt 都失败：

```text
status = rejected
best_model_version = 空或测试模型版本
best_model_path = 空或测试模型路径
error_message = 汇总 reject_reasons
不更新 model_version active
不刷新 selected_stock 预测
```

## 智能化训练与自动归因

训练任务不只保存概率和指标，还必须自动回答两个问题：

```text
这次模型为什么有效或无效？
哪些竞价/结构/市场特征真正贡献了胜率？
```

### 训练前特征质量检查

每次训练前先生成特征质量报告。质量检查不改变样本，只决定是否继续训练、是否降级训练、以及哪些特征需要标记为低可信。

检查项：

```text
missing_rate: 特征缺失率
zero_rate: 零值占比
unique_count: 唯一值数量
outlier_rate: 异常值比例
coverage_by_date: 按交易日覆盖率
positive_negative_ratio: 正负样本比例
train_test_drift: 训练集和测试集分布漂移
source_mix_ratio: real_selected / replay_backtest / historical_backfill 占比
```

默认规则：

```text
缺失率 >= 60% 的特征不参与当次训练
唯一值 <= 1 的特征不参与当次训练
测试集分布漂移严重的特征参与训练但在报告中标记 risk_feature
正样本过少时不训练对应目标模型
```

被剔除或标记的特征必须写入 `model_metrics.feature_quality_report`。

### 自动特征筛选

每个 attempt 训练后都计算特征贡献，下一次 attempt 可以基于贡献结果剔除低价值特征，但不能引入新闻特征，也不能修改默认策略条件。

贡献评估：

```text
lightgbm_feature_importance
permutation_importance
shap_importance
single_feature_bucket_lift
drop_one_feature_delta
```

特征保留建议：

```text
连续多次 importance 接近 0 的特征 -> 下轮降权或剔除
permutation_importance 为负的特征 -> 标记为疑似噪声
SHAP 方向不稳定的特征 -> 标记为不稳定特征
单特征分桶没有区分度 -> 保留但降低解释优先级
```

这些动作只影响模型训练参数和特征列，不影响默认选股策略。

### 自动分桶归因

训练完成后，系统必须对关键特征自动分桶，输出每个区间的基础胜率、模型 TopK 胜率和提升幅度。

重点分桶：

```text
auction_ratio: 4-8, 8-15, 15-30, 30+
auction_turnover_rate: 0.5-1, 1-3, 3-5, 5-10, 10+
open_change_pct: <-3, -3-0, 0-3, 3-7, 7+
seal_rate: <60, 60-80, 80-90, 90+
rise_10d_pct: <0, 0-10, 10-30, 30+
market_zhaban_rate: 低 / 中 / 高
market_max_connected_board: 1-2, 3-4, 5-6, 7+
health_score: <50, 50-65, 65-80, 80+
retreat_risk_score: 低 / 中 / 高
```

输出字段：

```text
feature_name
bucket
sample_count
positive_rate
baseline_rate
lift
topk_positive_rate
conclusion
```

示例结论：

```text
竞昨比 8%-15% 区间 T+1 高溢价率显著高于基准
竞价换手率 5%-10% 区间样本回撤偏大
市场最高板低于 3 时连板模型区分度不足
```

### 单票预测归因

每只股票预测后必须能解释概率高低。解释不使用 AI 文本生成，先用规则模板组合 SHAP/分桶结果。

单票输出：

```text
probability
model_version
positive_factors
negative_factors
neutral_factors
feature_contributions
bucket_explanations
data_quality_warnings
```

正向归因示例：

```text
auction_ratio 位于历史高胜率区间
auction_turnover_rate 充足且不过热
seal_rate 高于同策略样本中位数
market_max_connected_board 显示连板高度打开
health_score 对预测贡献为正
```

负向归因示例：

```text
auction_turnover_rate 过高，历史同区间回撤更大
open_change_pct 偏低，竞价承接不足
market_zhaban_rate 偏高，接力环境弱
retreat_risk_score 对预测贡献为负
sector_strength 不足
```

### 整体训练归因

每次训练任务结束必须输出整体归因摘要：

```text
top_positive_features
top_negative_features
unstable_features
noise_features
best_buckets
worst_buckets
failure_reasons
next_attempt_suggestions
```

如果模型失败，必须给出可执行的失败原因：

```text
回放策略与真实选股相似度不足
正样本数量不足
竞价字段缺失率过高
训练/测试分布漂移
TopK 未跑赢默认策略基准
关键特征贡献不稳定
```

### 存储位置

模型版本指标中保存摘要：

```text
model_version.model_metrics.feature_quality_report
model_version.model_metrics.feature_importance
model_version.model_metrics.permutation_importance
model_version.model_metrics.shap_importance
model_version.model_metrics.bucket_report
model_version.model_metrics.training_attribution
```

训练任务中保存完整过程：

```text
model_training_job.attempts_json[].feature_quality_report
model_training_job.attempts_json[].feature_importance
model_training_job.attempts_json[].bucket_report
model_training_job.attempts_json[].reject_reasons
model_training_job.attempts_json[].next_attempt_suggestions
```

## 诊断报告

训练任务必须输出诊断报告：

```text
1. 回放策略与真实选股差距
2. 默认策略自身基础胜率
3. 各条件分桶胜率
4. 竞昨比区间胜率
5. 竞价换手区间胜率
6. 连板/非连板样本胜率
7. 高分低胜率样本共性
8. 低分高胜率漏判样本共性
```

报告用于判断老模型胜率低的原因：

```text
策略条件过苛刻
策略条件过宽
竞价数据口径错误
标签定义不贴合实盘
模型特征不足
市场阶段导致短期失效
```

## 后端模块

新增服务：

```text
backend/services/model_engine/default_auction_replay_service.py
backend/services/model_engine/replay_validation_service.py
backend/services/model_engine/default_auction_sample_builder.py
backend/services/model_engine/default_auction_label_builder.py
backend/services/model_engine/default_auction_model_trainer.py
backend/services/model_engine/default_auction_model_evaluator.py
```

复用现有能力：

```text
ModelVersion
ModelTrainingJob
lightgbm_service
selected_stock
selection_record
dragon_leader_score
stock_risk_breakdown
dc_board_service
lhb_service
seat_library
```

## API 设计

复用模型中心，在 `backend/api/model_management.py` 下扩展：

```text
POST /api/v1/models/default-auction-replay/validate
POST /api/v1/models/default-auction-replay/build-samples
POST /api/v1/models/default-auction-relay/train
GET  /api/v1/models/default-auction-relay/diagnostics/{job_id}
POST /api/v1/models/default-auction-relay/refresh-predictions
```

训练任务继续写入 `model_training_job`，模型版本继续写入 `model_version`。

## 前端展示

模型中心新增 `default_auction_relay_v2` 区块：

1. 回放验收结果。
2. 样本构建进度。
3. 三个模型的指标。
4. TopK 胜率表。
5. 分桶胜率报告。
6. 诊断报告。

选股结果页新增字段：

```text
T+0 涨停概率
T+1 高溢价概率
T+1 连板概率
综合接力分
模型版本
```

前端必须覆盖 loading / error / empty 三态。

## 错误与降级

1. 回放验收失败：不生成训练样本，输出差异诊断。
2. 历史竞价数据缺失：记录缺失原因，不伪造竞价特征。
3. 标签行情缺失：该样本标签置空，不参与对应模型训练。
4. 模型未通过验收：保存训练结果，不自动激活。
5. 模型预测失败：概率返回 `None`，不影响默认选股。

## 实施顺序

1. 新增训练样本表和轻量迁移。
2. 实现默认策略历史回放服务。
3. 实现近期真实选股对比和回放验收。
4. 实现样本构建和特征快照。
5. 实现 A/B/C 标签生成。
6. 实现三个模型训练和评估。
7. 接入 `ModelTrainingJob` 和 `ModelVersion`.
8. 接入模型中心 API。
9. 接入前端模型中心展示。
10. 接入选股结果概率展示。

## 验收标准

开发完成后应满足：

1. 可以选择一段日期执行默认策略历史回放。
2. 可以用最近真实选股记录验证回放相似度。
3. 回放不达标时不会进入训练。
4. 回放达标后可以生成 `default_auction_training_sample`。
5. 可以分别训练 T+0 涨停、T+1 高溢价、T+1 连板模型。
6. 训练结果包含 Top1 / Top3 / Top5 胜率。
7. 不使用新闻因素。
8. 模型未通过验收时不会替换 active 版本。
9. 当前默认选股流程在模型不可用时正常降级。
