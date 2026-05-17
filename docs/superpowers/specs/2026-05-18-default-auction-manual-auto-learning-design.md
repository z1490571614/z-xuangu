# 默认竞价接力 V2 手动触发自动学习设计

## 背景

当前默认竞价接力 V2 已经具备分散的训练能力：

- 本地日线同步：`POST /api/v1/models/default-auction-relay/sync-local-daily`
- 本地分钟线同步：`POST /api/v1/models/default-auction-relay/sync-local-minute`
- 竞昨比重算：`POST /api/v1/models/default-auction-relay/recalculate-auction-ratios`
- 管道重建：`POST /api/v1/models/default-auction-relay/rebuild-pipeline`
- 三目标训练：`POST /api/v1/models/default-auction-relay/train`
- 训练诊断：`GET /api/v1/models/default-auction-relay/diagnostics/{job_id}`
- 离线回测：`POST /api/v1/models/default-auction-relay/backtest`
- 预测刷新：`POST /api/v1/models/default-auction-relay/refresh-predictions`

这些入口能完成单个动作，但缺少一个可追踪、可恢复、可审计的“手动触发自动学习”工作流。用户现在需要的是：在模型中心点击一次按钮，由系统按固定顺序完成数据补齐、样本增量构建、完整性检查、训练、回测、验收、模型启用和最新选股预测刷新。

本设计不做无人值守定时任务，也不做模型在实盘中自行学习。所有学习动作必须由用户在前端手动触发。

## 目标

新增默认竞价接力 V2 的手动自动学习能力，支持：

1. 用户在模型中心手动创建一次自动学习运行。
2. 系统记录每次运行的参数、阶段、进度、日志、结果和失败原因。
3. 复用现有数据同步、样本构建、审计、训练、诊断、回测和预测刷新能力。
4. 训练前强制执行训练数据完整性审计。
5. 训练后强制执行三目标验收和回测验收。
6. 只有全部门槛通过时才允许启用新模型。
7. 失败时保留旧模型，前端清楚展示失败阶段和根因。
8. 支持增量更新训练数据库和模型版本，避免每次全量重做。

## 非目标

本期不做：

1. 不做定时自动训练。
2. 不做实盘过程中自动改模型、自动改策略或自动改阈值。
3. 不引入新的行情、新闻、龙虎榜或情绪数据源。
4. 不重写默认选股策略、不改变 MCP 实盘选股逻辑。
5. 不用大模型判断训练样本是否可信。
6. 不删除历史模型版本，只增加页面折叠和清理入口的后续扩展空间。

## 方案比较

### 方案 A：直接增强现有 `rebuild-pipeline`

在 `rebuild-pipeline` 接口里继续增加审计、训练轮询、回测、启用和刷新预测逻辑。

优点：

- 改动最少。
- 前端已有部分控件可以复用。

缺点：

- 现有接口是同步返回加后台训练任务的混合模式，难以准确展示完整阶段进度。
- 缺少独立运行记录，失败后不能可靠复盘。
- 后续想暂停、重跑失败阶段、查看历史自动学习记录会变困难。

### 方案 B：新增独立自动学习编排服务和运行表

新增 `DefaultAuctionAutoLearningRun` 表和 `DefaultAuctionAutoLearningService`，由一个手动触发接口创建运行，后台按阶段顺序编排现有服务。

优点：

- 每次运行独立可追踪。
- 阶段边界清晰，失败根因可保存。
- 不污染现有单动作接口。
- 未来可以自然扩展“重跑失败阶段”“对比两次运行”“一键回滚”。

缺点：

- 需要新增一张表、一个服务和一组 API。
- 前端需要新增运行面板。

### 方案 C：只写本地脚本手动执行

新增命令行脚本串联现有服务，前端不改。

优点：

- 开发快。
- 适合开发者临时维护。

缺点：

- 用户看不到进度。
- 不能在模型中心形成固定工作流。
- 容易出现参数不一致、运行结果不可追踪的问题。

## 推荐方案

采用方案 B。

原因：用户要的是长期可用的“手动触发自动学习”，不是一次性维护脚本。独立运行表和编排服务可以把数据库、数据接口、管道重建、本地日线、本地分钟线、训练、回测、验证、测试串成一个闭环，同时保留现有单动作接口用于排障。

## 总体架构

```text
模型中心前端
  -> 创建自动学习运行
  -> 轮询运行详情
  -> 展示阶段进度、审计、训练、回测、启用、预测刷新结果

模型管理 API
  -> DefaultAuctionAutoLearningService
      -> TdxLocalDailySyncService
      -> TdxLocalMinuteSyncService
      -> AuctionDataService
      -> DefaultAuctionReplayService / replay_validation_service
      -> default_auction_sample_builder
      -> default_auction_training_data_audit
      -> default_auction_relay_job_service
      -> default_auction_backtest_service
      -> model_management_service.refresh_record_predictions
      -> model_management_service.activate_model_version

SQLite
  -> default_auction_auto_learning_run
  -> default_auction_training_sample
  -> model_training_job
  -> model_version
```

## 复用清单

必须复用现有能力，不新增重复数据源：

| 能力 | 复用位置 |
|---|---|
| 数据库会话 | `backend.database.SessionLocal` / `get_db` |
| 本地日线同步 | `backend.services.tdx_local_daily_sync_service.TdxLocalDailySyncService` |
| 本地分钟线同步 | `backend.services.tdx_local_minute_sync_service.TdxLocalMinuteSyncService` |
| 竞昨比重算 | `backend.services.auction_data_service.AuctionDataService` |
| 默认策略回放 | `backend.services.model_engine.default_auction_replay_service.DefaultAuctionReplayService` |
| 回放验收 | `backend.services.model_engine.replay_validation_service.validate_replay_against_real` |
| 样本构建 | `backend.services.model_engine.default_auction_sample_builder` |
| 训练数据审计 | `backend.services.model_engine.default_auction_training_data_audit.audit_default_auction_training_data` |
| 三目标训练 | `backend.services.model_engine.default_auction_relay_job_service` |
| 三目标诊断 | `get_default_auction_relay_diagnostics` |
| 离线回测 | `backend.services.model_engine.default_auction_backtest_service.run_default_auction_relay_backtest` |
| 模型启用 | `backend.services.model_engine.model_management_service.activate_model_version` |
| 预测刷新 | `backend.services.model_engine.model_management_service.refresh_record_predictions` |

## 数据模型

新增模型文件：

```text
backend/models/default_auction_auto_learning_run.py
```

新增表：

```text
default_auction_auto_learning_run
```

字段设计：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | 运行 ID |
| `status` | String | `pending/running/passed/failed/cancelled` |
| `phase` | String | 当前阶段 |
| `progress` | Integer | 0-100 |
| `start_date` | String | 训练与样本更新起始交易日 |
| `end_date` | String | 训练与样本更新结束交易日 |
| `tdx_vipdoc_path` | String nullable | 本地通达信目录 |
| `ts_codes_json` | Text nullable | 限定股票列表，空表示按样本或策略自动解析 |
| `selected_record_ids_json` | Text nullable | 需要构建真实样本的选股记录 ID |
| `options_json` | Text | 阶段开关和参数 |
| `stage_results_json` | Text | 每个阶段的结构化结果 |
| `audit_json` | Text nullable | 训练数据完整性审计结果 |
| `training_job_id` | Integer nullable | 关联 `model_training_job.id` |
| `training_diagnostics_json` | Text nullable | 三目标训练诊断 |
| `backtest_json` | Text nullable | 回测结果 |
| `activated_versions_json` | Text nullable | 本次启用的三目标模型版本 |
| `refreshed_record_ids_json` | Text nullable | 已刷新预测的记录 ID |
| `logs_json` | Text | 阶段日志数组 |
| `error_message` | Text nullable | 失败原因 |
| `started_at` | DateTime nullable | 开始时间 |
| `finished_at` | DateTime nullable | 结束时间 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

索引：

```text
idx_default_auction_auto_learning_status(status)
idx_default_auction_auto_learning_created(created_at)
idx_default_auction_auto_learning_phase(phase)
```

不把运行状态塞进 `model_training_job` 的原因：自动学习不只是训练，它还包含数据同步、样本构建、审计、回测、模型启用和预测刷新。单独建表能避免训练任务表职责膨胀。

## 后端 API

新增接口放在 `backend/api/model_management.py`，路径统一归入模型中心。

### 创建手动自动学习运行

```text
POST /api/v1/models/default-auction-relay/auto-learning/runs
```

请求：

```json
{
  "start_date": "20250101",
  "end_date": "20260518",
  "tdx_vipdoc_path": "G:\\new_tdx\\vipdoc",
  "ts_codes": null,
  "selected_record_ids": [49, 47, 46],
  "refresh_record_ids": [49, 47, 46],
  "sync_daily": true,
  "sync_minute": true,
  "recalculate_auction_ratios": true,
  "validate_replay": true,
  "build_real_samples": true,
  "build_replay_samples": true,
  "audit_training_data": true,
  "run_training": true,
  "run_backtest": true,
  "auto_activate": true,
  "refresh_predictions": true,
  "validation_recent_days": 5,
  "minute_interval": 1,
  "commit_every": 5000,
  "params": {
    "max_retrain_attempts": 5
  },
  "acceptance": {
    "min_t0_auc": 0.6,
    "min_t1_premium_auc": 0.55,
    "min_t1_continue_auc": 0.58,
    "max_prediction_failed_count": 0
  }
}
```

响应：

```json
{
  "run_id": 12,
  "status": "pending"
}
```

语义：

- 这是唯一触发入口。
- 接口只创建运行并提交后台任务，不在 HTTP 请求内执行长任务。
- `auto_activate=true` 表示“所有验收通过后自动启用”，不是无条件启用。

### 查看运行详情

```text
GET /api/v1/models/default-auction-relay/auto-learning/runs/{run_id}
```

响应：

```json
{
  "id": 12,
  "status": "running",
  "phase": "training",
  "progress": 70,
  "start_date": "20250101",
  "end_date": "20260518",
  "stage_results": {
    "daily_sync": {"rows_synced": 120000},
    "minute_sync": {"rows_synced": 880000},
    "sample_build": {"real_created_count": 46, "replay_created_count": 2368}
  },
  "audit": null,
  "training_job_id": 11,
  "training_diagnostics": null,
  "backtest": null,
  "activated_versions": null,
  "logs": [
    {"time": "2026-05-18 10:00:00", "level": "info", "message": "开始训练"}
  ],
  "error_message": null
}
```

### 查看最近运行

```text
GET /api/v1/models/default-auction-relay/auto-learning/runs?limit=20
```

用途：

- 模型中心加载最近运行历史。
- 用户能对比最近几次运行是否通过。

### 取消运行

```text
POST /api/v1/models/default-auction-relay/auto-learning/runs/{run_id}/cancel
```

MVP 取消语义：

- `pending` 可直接取消。
- `running` 只设置取消标记，服务在阶段边界检查后停止。
- 已经进入三目标训练的底层训练任务不强杀，只在训练返回后停止后续启用和刷新预测。

## 后端服务

新增服务文件：

```text
backend/services/model_engine/default_auction_auto_learning_service.py
```

公开方法：

```python
def create_auto_learning_run(db: Session, request: DefaultAuctionAutoLearningCreate) -> DefaultAuctionAutoLearningRun:
    ...

def run_auto_learning(run_id: int) -> None:
    ...

def get_auto_learning_run(db: Session, run_id: int) -> dict:
    ...

def list_auto_learning_runs(db: Session, limit: int = 20) -> list[dict]:
    ...

def request_cancel_auto_learning_run(db: Session, run_id: int) -> dict:
    ...
```

`run_auto_learning` 内部必须自己创建数据库会话，不能复用 FastAPI 请求会话。

## 工作流阶段

一次运行按以下顺序执行。

### 1. 创建运行

写入 `default_auction_auto_learning_run`：

```text
status = pending
phase = prepare
progress = 0
```

后台任务启动后更新：

```text
status = running
started_at = 当前时间
```

### 2. 参数解析

检查：

- `start_date`、`end_date` 必须是 8 位日期。
- `start_date <= end_date`。
- 至少启用一个有效阶段。
- `auto_activate=true` 时必须同时启用 `audit_training_data`、`run_training`、`run_backtest`。

如果失败：

```text
status = failed
phase = prepare
error_message = 明确的参数错误
```

### 3. 本地日线同步

启用 `sync_daily` 时调用：

```python
TdxLocalDailySyncService(tdx_vipdoc_path=tdx_vipdoc_path).sync_range(
    start_date,
    end_date,
    ts_codes=ts_codes,
    commit_every=commit_every,
)
```

结果写入：

```text
stage_results.daily_sync
```

### 4. 本地分钟线同步

启用 `sync_minute` 时调用：

```python
TdxLocalMinuteSyncService(tdx_vipdoc_path=tdx_vipdoc_path).sync_range(
    start_date,
    end_date,
    ts_codes=resolved_minute_ts_codes,
    interval=minute_interval,
    commit_every=commit_every,
)
```

`resolved_minute_ts_codes` 解析优先级：

1. 请求传入的 `ts_codes`。
2. `selected_record_ids` 对应的真实选股代码。
3. `default_auction_training_sample` 中日期范围内已有样本代码。
4. 默认策略回放候选代码。

如果本地分钟文件缺失，不能伪造分钟数据。服务应在结果中记录：

```text
missing_files
missing_codes
```

是否阻断由后续样本特征完整性审计决定。

### 5. 竞昨比重算

启用 `recalculate_auction_ratios` 时调用：

```python
AuctionDataService().recalculate_auction_ratios_from_daily_cache(start_date, end_date)
```

结果写入：

```text
stage_results.auction_ratio_recalc
```

### 6. 回放验收

启用 `validate_replay` 或 `build_replay_samples` 时执行。

逻辑复用：

```python
DefaultAuctionReplayService.get_recent_real_selection_days()
DefaultAuctionReplayService.replay_trade_date()
validate_replay_against_real()
```

验收失败时：

- 不允许构建 replay 训练样本。
- 不允许训练。
- 不允许启用模型。
- 运行状态置为 `failed`。

失败信息必须包含：

```text
reject_reasons
daily recall / jaccard / count_error
差异股票诊断
```

### 7. 构建真实选股样本

启用 `build_real_samples` 时执行。

输入：

- 优先使用 `selected_record_ids`。
- 如果为空，使用最近 N 个有默认策略真实选股的记录，N 由前端传入，默认 5。

调用：

```python
build_samples_from_selected_record(db, record_id, "real_selected")
```

要求：

- 已存在的 `(strategy_version, trade_date, ts_code, sample_source)` 样本应更新而不是重复插入。
- T+1 标签未成熟的样本可以入库，但训练前审计必须阻断标签缺失。

### 8. 构建回放样本

启用 `build_replay_samples` 时执行。

调用：

```python
build_samples_from_replay_range(db, start_date, end_date, "replay_backtest")
```

要求：

- 只能构建 A 股普通股票样本。
- 每日样本数量异常时，必须由审计脚本阻断。
- `seal_rate`、`touch_days`、`limit_up_days` 必须来自真实公式计算结果，不能用空值或默认值代替。

### 9. 训练数据完整性审计

启用 `audit_training_data` 时执行。

调用：

```python
audit_default_auction_training_data(db)
```

必须阻断训练和启用的错误：

```text
replay_sample_count_below_threshold
replay_trade_date_count_below_threshold
replay_avg_count_above_threshold
replay_daily_count_above_threshold
required_feature_missing
non_a_share_sample_detected
duplicate_training_sample_keys
replay_validation_failed
任一目标标签 known_count 为 0
任一目标标签 missing_count > 0 且样本日期已经过 T+1 成熟日
```

审计结果写入：

```text
audit_json
stage_results.training_data_audit
```

### 10. 三目标训练

启用 `run_training` 时执行。

调用：

```python
create_default_auction_relay_job(
    db,
    start_date=start_date,
    end_date=end_date,
    params=params,
    auto_activate=False,
)
run_default_auction_relay_training_job(job.id)
```

这里固定 `auto_activate=False`。原因：自动学习编排层要先拿到训练诊断和回测结果，再统一决定是否启用三目标模型。

训练完成后读取：

```python
get_default_auction_relay_diagnostics(db, job.id)
```

验收规则：

- `model_training_job.status` 必须是 `passed`。
- 三个目标模型都必须训练成功。
- 三个目标都必须有有效树数量。
- 三个目标都必须通过各自 acceptance。

### 11. 离线回测

启用 `run_backtest` 时执行。

调用：

```python
run_default_auction_relay_backtest(db, start_date, end_date, version=None)
```

注意：如果训练刚生成了新版本但尚未启用，回测必须支持按新版本回测。实现时应从训练诊断里解析本次三目标版本，分别传入目标模型回测；如果现有 `run_default_auction_relay_backtest` 只能测 active version，需要扩展为支持三目标版本映射。

回测最低门槛：

| 指标 | 默认阈值 |
|---|---|
| 任一目标 `prediction_failed_count` | 必须等于 0 |
| T0 AUC | >= 0.60 |
| T1 高溢价 AUC | >= 0.55 |
| T1 连板 AUC | >= 0.58 |
| TopK 命中指标 | 不低于当前 active 版本 |

如果训练样本较少导致 AUC 波动大，不能降低门槛直接启用。应把运行置为失败，并提示继续补充样本。

### 12. 受保护模型启用

只有以下条件全部满足，才执行启用：

```text
audit.ok = true
training_job.status = passed
training_diagnostics 三目标全部 passed
backtest 三目标全部通过阈值
auto_activate = true
```

启用动作：

```python
activate_model_version(db, "default_auction_t0_limit_lgbm", t0_version)
activate_model_version(db, "default_auction_t1_premium_lgbm", t1_premium_version)
activate_model_version(db, "default_auction_t1_continue_lgbm", t1_continue_version)
```

启用前必须记录旧 active 版本：

```text
stage_results.previous_active_versions
```

启用后记录新版本：

```text
activated_versions_json
```

如果任一启用失败：

- 不继续刷新预测。
- 运行置为 `failed`。
- 错误信息写明哪个目标模型启用失败。
- 不自动删除已生成模型文件。

### 13. 刷新最新选股预测

启用 `refresh_predictions` 时执行。

输入：

- 优先使用 `refresh_record_ids`。
- 如果为空，使用最近 N 个默认策略选股记录，默认 5。

调用：

```python
refresh_record_predictions(db, "default_auction_relay_v2", record_id, version=None)
```

结果写入：

```text
stage_results.refresh_predictions
refreshed_record_ids_json
```

刷新失败不回滚模型启用，但运行状态应标记为 `failed` 或 `passed_with_warning`。MVP 为了状态简单，采用 `failed`，并在错误信息中明确“模型已启用，预测刷新失败”。

## 状态机

```text
pending
  -> running
      -> passed
      -> failed
      -> cancelled
```

阶段枚举：

```text
prepare
sync_daily
sync_minute
recalculate_auction_ratios
validate_replay
build_real_samples
build_replay_samples
audit_training_data
training
training_diagnostics
backtest
activate
refresh_predictions
finish
```

阶段进度建议：

| 阶段 | 进度 |
|---|---:|
| prepare | 5 |
| sync_daily | 15 |
| sync_minute | 25 |
| recalculate_auction_ratios | 35 |
| validate_replay | 45 |
| build_real_samples | 52 |
| build_replay_samples | 60 |
| audit_training_data | 68 |
| training | 78 |
| backtest | 88 |
| activate | 94 |
| refresh_predictions | 98 |
| finish | 100 |

## 增量更新策略

训练数据库可以增量更新，原则如下：

1. 日线和分钟线同步按日期范围更新。
2. 真实样本按 `selected_record_ids` 增量更新。
3. 回放样本按日期范围增量更新。
4. 样本唯一键保持：

```text
strategy_version + trade_date + ts_code + sample_source
```

5. 已存在样本重新计算特征和标签后更新，不新增重复样本。
6. 训练仍然使用指定日期范围内的全量可用样本，而不是只用新增样本训练。

不做在线增量训练。原因：当前 LightGBM 训练链路和验收体系是离线批训练，新模型要通过完整审计和回测后才能启用。所谓“增量更新模型”在本期定义为：增量补数据和样本，然后重新训练一个新版本。

## 前端设计

修改：

```text
frontend/src/views/ModelCenter.vue
```

新增区域：

```text
默认竞价接力 V2 -> 手动自动学习
```

控件：

- 起始日期。
- 结束日期。
- 通达信本地目录。
- 选股记录 ID，多 ID 用逗号分隔。
- 刷新预测记录 ID，多 ID 用逗号分隔。
- 同步本地日线开关。
- 同步本地分钟线开关。
- 重算竞昨比开关。
- 回放验收开关。
- 构建真实样本开关。
- 构建回放样本开关。
- 训练数据审计开关，默认开启且不可关闭。
- 三目标训练开关。
- 离线回测开关。
- 验收通过后自动启用开关，默认开启。
- 刷新最新预测开关。
- 最大重训次数。

按钮：

```text
开始自动学习
```

运行展示：

- 当前状态。
- 当前阶段。
- 进度条。
- 每个阶段的结果摘要。
- 审计错误和警告。
- 三目标训练指标。
- 回测指标。
- 启用的新旧版本。
- 预测刷新数量。
- 错误信息和重试按钮。

三态要求：

- loading：显示“自动学习运行中”和阶段进度。
- error：显示失败阶段、失败原因和重试按钮。
- empty：没有运行记录时显示“暂无自动学习运行”。

页面文案必须用中文，不直接暴露英文模型名。三目标展示名称：

| 模型名 | 中文展示 |
|---|---|
| `default_auction_t0_limit_lgbm` | 当日涨停概率 |
| `default_auction_t1_premium_lgbm` | 次日高溢价概率 |
| `default_auction_t1_continue_lgbm` | 次日连板概率 |

## 验收规则

一次手动自动学习运行视为通过，必须满足：

1. 本地日线同步阶段没有异常退出。
2. 本地分钟线同步阶段没有异常退出。
3. 回放验收通过。
4. 训练数据完整性审计 `ok=true`。
5. 三目标训练任务 `status=passed`。
6. 三目标模型全部生成版本。
7. 离线回测全部通过阈值。
8. 如果 `auto_activate=true`，三目标模型全部成功启用。
9. 如果 `refresh_predictions=true`，目标选股记录预测刷新成功。

## 失败处理

失败时必须根本定位，不做静默降级：

| 失败点 | 处理 |
|---|---|
| 日期参数错误 | 运行失败，提示具体字段 |
| 本地文件缺失 | 记录缺失代码和文件路径，交给审计决定是否阻断 |
| 回放验收失败 | 阻断样本构建、训练和启用 |
| 特征缺失 | 审计失败，列出缺失字段和数量 |
| 标签缺失 | 审计失败，列出缺失目标 |
| 非 A 股样本 | 审计失败，列出代码 |
| 三目标训练失败 | 阻断回测、启用和预测刷新 |
| 回测失败 | 阻断启用 |
| 启用失败 | 阻断预测刷新，保留错误 |
| 预测刷新失败 | 记录失败，提示模型是否已启用 |

禁止行为：

- 禁止用 0、空字符串或均值填充 `seal_rate/touch_days/limit_up_days` 后继续训练。
- 禁止回放验收失败后继续构建 replay 样本。
- 禁止训练失败后启用部分模型。
- 禁止只启用三目标中的一个或两个模型。
- 禁止自动删除旧模型版本。

## 测试计划

### 后端单元测试

新增：

```text
tests/test_default_auction_auto_learning_service.py
```

覆盖：

1. 创建运行时保存参数和默认选项。
2. 日期非法时拒绝创建运行。
3. `auto_activate=true` 但未启用审计、训练或回测时拒绝创建。
4. 阶段执行成功时逐步更新 `phase/progress/stage_results`。
5. 回放验收失败时阻断后续阶段。
6. 审计失败时不创建训练任务。
7. 训练失败时不回测、不启用。
8. 回测失败时不启用。
9. 三目标全部通过时才调用启用。
10. 取消运行时在阶段边界停止。

### 后端 API 测试

新增或扩展：

```text
tests/test_model_management_api.py
```

覆盖：

1. `POST /auto-learning/runs` 返回 `run_id`。
2. `GET /auto-learning/runs/{run_id}` 返回运行详情。
3. `GET /auto-learning/runs?limit=20` 返回最近运行。
4. `POST /auto-learning/runs/{run_id}/cancel` 可以取消 pending 运行。

### 前端测试

新增或扩展：

```text
frontend/src/views/__tests__/ModelCenter.spec.js
```

覆盖：

1. 自动学习面板渲染中文字段。
2. 点击“开始自动学习”发送正确 payload。
3. 运行中展示 loading 状态和阶段。
4. 失败时展示错误和重试按钮。
5. 无运行记录时展示 empty 状态。
6. 三目标模型使用中文名称展示。

### 手工验证

按顺序执行：

1. 启动后端和前端。
2. 打开模型中心。
3. 输入日期范围和本地通达信目录。
4. 点击“开始自动学习”。
5. 观察运行进度从 `prepare` 到 `finish`。
6. 确认审计结果 `ok=true`。
7. 确认三目标训练 `passed`。
8. 确认回测三目标指标通过。
9. 确认 active 模型版本更新。
10. 打开选股列表，确认概率已刷新且显示中文说明。

验证命令：

```powershell
pytest tests/test_default_auction_auto_learning_service.py -v
pytest tests/test_model_management_api.py -v
cd frontend
npm test -- ModelCenter
npm run build
```

## 实施顺序

1. 新增 `DefaultAuctionAutoLearningRun` ORM 模型并注册到 `backend/models/__init__.py`。
2. 新增自动学习服务的请求解析、运行状态读写和阶段日志工具。
3. 先写服务层失败路径测试，再实现参数校验和状态机。
4. 接入本地日线、分钟线、竞昨比重算阶段。
5. 接入回放验收、真实样本构建、回放样本构建阶段。
6. 接入训练数据完整性审计，并把审计失败作为硬阻断。
7. 接入三目标训练和训练诊断读取。
8. 扩展回测服务支持“本次训练版本”回测，而不是只能回测 active 版本。
9. 接入受保护模型启用。
10. 接入预测刷新。
11. 新增 API 路由和 API 测试。
12. 更新模型中心前端面板和前端测试。
13. 运行完整后端测试、前端测试和构建。

## 交付标准

完成后应达到：

1. 用户能在模型中心手动触发一次完整自动学习。
2. 每次运行都能查询历史记录。
3. 任一阶段失败都能看到明确失败原因。
4. 训练前必审计，审计失败不训练。
5. 回测失败不启用。
6. 三目标必须一起通过；如果用户选择“验收通过后自动启用”，则三目标必须一起启用。
7. 旧模型版本保留可回滚。
8. 选股列表能展示刷新后的三目标概率和中文说明。
