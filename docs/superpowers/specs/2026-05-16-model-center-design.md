# 模型中心与训练验收设计

## 背景

当前系统已有 `leader_main_t0_lgbm` 模型、`model_version` 版本表、`/api/v1/model/status` 状态接口、`/api/v1/backtest/leader-main-t0/train` 同步训练接口，以及结果页中的 `t0_limit_success_prob` 展示。现有能力可以训练和展示概率，但缺少统一的模型选择、版本切换、刷新预测、训练进度、参数微调和训练后胜率验收。

## 目标

新增独立“模型中心”页面，支持：

1. 查看模型列表、active 版本、历史版本和指标。
2. 选择某个模型版本作为当前预测版本。
3. 对某条选股记录刷新预测结果。
4. 在训练前配置常用参数和高级参数。
5. 先执行测试训练，再执行正式训练。
6. 训练时实时展示阶段进度、日志和当前指标。
7. 训练完成后按胜率门槛验收，不达标自动重新训练，最多 3 次。
8. 验收通过后允许设为 active；验收失败时保留旧 active 模型。

## 非目标

本期不新增外部数据源，不重做特征工程，不替换现有选股策略，不把模型输出直接变成买卖建议。所有训练数据继续来自现有数据库表和服务。

## 页面结构

新增前端路由 `/models`，页面名为“模型中心”。

页面分为四个工作区：

1. 模型概览
   - 展示 `leader_main_t0_lgbm`、`active_auction_lgbm` 等已登记模型。
   - 显示 active 版本、训练区间、AUC、precision、recall、样本数、模型文件是否存在。
   - 提供“设为 active”和“查看版本指标”操作。

2. 预测刷新
   - 选择模型版本。
   - 选择选股记录 ID，默认填最新有数据记录。
   - 点击“刷新预测”，后端批量重算该记录下股票的预测概率，并更新 `selected_stock` 的模型概率和模型版本字段。
   - 刷新结束后给出成功数、失败数、模型版本和耗时。

3. 训练控制台
   - 常用参数：训练开始日期、训练结束日期、测试集比例、学习率、树数量、叶子数、概率阈值、胜率门槛、最小命中数、最大自动重训次数、是否启用样本平衡。
   - 高级参数：max_depth、subsample、colsample_bytree、early_stopping_rounds、random_seed。
   - 操作按钮：测试训练、正式训练、停止任务。
   - 测试训练只评估并保存临时任务结果，不写 active 模型。
   - 正式训练通过验收后生成模型版本，用户可手动设为 active；如果开启“通过后自动启用”，则自动切 active。

4. 训练任务与日志
   - 显示最近训练任务列表：任务 ID、模型名、状态、阶段、进度、开始时间、结束时间、验收结果。
   - 展示当前任务实时日志。
   - 展示每次重训 attempt 的指标和阈值评估表。

## 后端设计

新增模型管理 API，建议放在 `backend/api/model_management.py`，避免继续扩大 `backend/main.py`。

核心接口：

1. `GET /api/v1/models`
   - 返回模型列表、active 版本、历史版本、指标、参数、模型文件可用状态。

2. `POST /api/v1/models/{model_name}/versions/{version}/activate`
   - 将指定版本设为 active。
   - 同一 `model_name` 只允许一个 active。
   - 模型文件不存在时拒绝启用。

3. `POST /api/v1/models/{model_name}/refresh-predictions`
   - 请求参数：`record_id`、`version` 可选。
   - 复用现有 `SelectedStock` 数据和 `batch_predict_model` 预测逻辑。
   - 更新 `selected_stock.t0_limit_success_prob` 和 `t0_limit_success_model_version`。
   - 不重新选股，不重跑评分系统。

4. `POST /api/v1/models/{model_name}/training-jobs`
   - 创建训练任务并后台执行。
   - 返回 `job_id`。
   - 任务状态和日志通过 WebSocket `models` 频道推送，也可通过轮询接口查询。

5. `GET /api/v1/models/training-jobs/{job_id}`
   - 返回任务状态、阶段进度、日志摘要、attempt 指标、验收结果。

6. `POST /api/v1/models/training-jobs/{job_id}/cancel`
   - 对未完成任务标记取消。
   - 任务在阶段边界检查取消标记，无法强杀底层训练时也要安全降级为“取消中/已取消”。

## 训练任务模型

新增数据库表 `model_training_job`。

字段：

- `id`
- `model_name`
- `status`: `pending` / `running` / `succeeded` / `failed` / `rejected` / `cancelled`
- `phase`: `prepare` / `load_samples` / `train` / `evaluate` / `acceptance` / `persist`
- `progress`
- `train_start_date`
- `train_end_date`
- `params_json`
- `acceptance_json`
- `attempts_json`
- `best_model_version`
- `best_model_path`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`

训练日志可先存在 `model_training_job.logs_json`，如果日志增长太快，再拆 `model_training_job_log` 表。本期优先单表，控制只保留最近 300 条日志。

## 训练服务

新增 `backend/services/model_engine/training_job_service.py`。

职责：

1. 创建任务。
2. 后台执行测试训练或正式训练。
3. 推送 WebSocket 进度。
4. 记录每次 attempt 指标。
5. 按验收线判断是否通过。
6. 通过后写入 `model_version`。
7. 失败时保留旧 active。

验收规则默认值：

- `precision >= 0.50`
- `hit_count >= 30`
- `threshold = 0.50`
- `max_retrain_attempts = 3`

如果默认阈值不满足，可以在同一次训练的 `threshold_evaluation` 中查找满足 `precision` 和 `hit_count` 的最优阈值。找到后把推荐阈值写入 `model_metrics.accepted_threshold`，供前端展示。本期预测仍输出概率，不按阈值过滤股票。

自动重训策略：

- 每次 attempt 使用不同 `random_seed`。
- 仍使用同一训练区间和参数。
- 每次 attempt 独立评估。
- 若任一 attempt 通过验收，任务成功。
- 若全部失败，任务状态为 `rejected`，不切 active。

## 进度推送

复用现有 `backend/services/websocket_service.py` 的 channel 机制，新增 `models` 频道消息。

消息类型：

- `model_job_update`
- `model_job_log`
- `model_job_completed`
- `model_job_failed`
- `model_job_rejected`

前端连接 `/ws` 后发送：

```json
{"type": "subscribe", "channel": "models"}
```

断线时页面每 5 秒轮询 `GET /api/v1/models/training-jobs/{job_id}`，保证进度不丢。

## 参数设计

常用参数默认值：

- `start_date`: 最近 2 年可用样本起点
- `end_date`: 最新交易日
- `test_size`: `0.10`
- `learning_rate`: `0.05`
- `n_estimators`: `500`
- `num_leaves`: `31`
- `threshold`: `0.50`
- `min_precision`: `0.50`
- `min_hit_count`: `30`
- `max_retrain_attempts`: `3`
- `is_unbalance`: `true`

高级参数默认值：

- `max_depth`: `-1`
- `subsample`: `0.8`
- `colsample_bytree`: `0.8`
- `early_stopping_rounds`: `50`
- `random_seed`: `42`

后端需要校验参数范围，非法参数返回 422，不进入训练。

## 错误与降级

1. 模型文件不存在：不能激活，预测刷新返回错误。
2. 样本不足：训练任务失败，提示样本数和最低要求。
3. 测试集只有单一标签：训练任务失败，提示不能计算可靠胜率。
4. WebSocket 断开：前端切轮询。
5. 训练未通过验收：任务状态 `rejected`，保留旧 active。
6. 预测刷新部分失败：返回失败股票列表，其余股票正常更新。

## 测试策略

后端单元测试：

1. 模型列表接口返回 active 和历史版本。
2. 模型文件不存在时不能激活。
3. 预测刷新只更新指定记录，不重新选股。
4. 创建训练任务后写入 `model_training_job`。
5. 验收通过时任务成功，并记录通过阈值。
6. 验收失败且达到最大 attempt 后任务为 `rejected`。
7. 参数非法时返回 422。

前端测试：

1. 模型中心能展示 loading / error / empty 三态。
2. 参数表单能提交测试训练。
3. WebSocket 消息能更新进度和日志。
4. 训练失败时显示错误和重试入口。
5. 预测刷新成功后更新表格里的模型版本和概率。

## 实施顺序

1. 后端：抽出模型状态 API，不再放在 `main.py`。
2. 后端：新增训练任务表和轻量迁移。
3. 后端：新增模型管理 API。
4. 后端：新增训练任务服务和验收逻辑。
5. 前端：新增 `/models` 路由和模型中心页面。
6. 前端：接入模型列表、版本激活、预测刷新。
7. 前端：接入训练参数表单、进度展示和日志。
8. 结果页：增加“刷新当前记录预测”的轻量入口。
9. 测试：补齐后端单元测试和关键前端测试。

## 已确认决策

当前设计已确认：

- 主入口采用独立“模型中心”。
- 结果页只保留轻量模型选择和刷新预测。
- 默认验收线为 `precision >= 50%` 且 `hit_count >= 30`。
- 不达标最多自动重训 3 次。
- 参数范围采用“常用参数 + 高级折叠区”。

实现时按本设计推进。
