# LightGBM 模块开发进度与后续任务

> 给新的 AI 对话使用：先读本文，再继续执行量化训练、样本扩展、模型评估和工程化任务。本文记录的是截至 2026-05-09 当前分支的真实状态。

## 1. 当前分支与总体状态

| 项目 | 当前值 |
|------|--------|
| 工作目录 | `H:\project_development\xuangu` |
| 当前分支 | `codex/auction-lightgbm-dev` |
| 基线分支 | `dev` |
| 最近提交 | `56d04b1 feat: sync local tdx daily cache for training` |
| 远端状态 | 本地领先远端 1 个提交，`git push` 因 GitHub 网络连接失败未推上去 |
| 当前目标 | 训练“龙头主升 T+0 非一字涨停成功率”LightGBM 初版模型 |

已经完成的核心链路：

1. 历史开盘集合竞价数据入库：`stock_auction_open`。
2. 本地通达信 `.day` 日线读取与同步：`stock_daily_data`。
3. `TushareDataCollector.get_daily_data()` 优先读取本地日线库，其次本地 `.day`，最后才降级 Tushare。
4. 基于候选池构建 `leader_main_t0_training_sample`。
5. 基于 T 日日线生成标签：是否“非一字且触板且收板”。
6. 训练 `leader_main_t0_lgbm` 并写入 `model_version` active 版本。

## 2. 已完成代码改动

### 2.1 竞价增强与回测接口

相关文件：

- `backend/services/auction_data_service.py`
- `backend/api/backtest.py`
- `backend/models/auction_backtest.py`
- `tests/backend/unit/test_auction_data_service.py`
- `tests/backend/unit/test_backtest_api.py`

已实现能力：

- `AuctionDataService.sync_auction_open(trade_date)`：同步单日 Tushare `stk_auction_o`。
- `AuctionDataService.sync_auction_open_date_range(start_date, end_date)`：同步日期区间竞价。
- `AuctionDataService.recalculate_auction_ratios_from_daily_cache(start_date, end_date)`：用 `stock_daily_data` 中 T-1 成交量重算已入库竞价数据的 `auction_ratio`。

API：

- `POST /api/v1/backtest/auction/sync`
- `POST /api/v1/backtest/auction/sync-range`
- `POST /api/v1/backtest/auction/recalculate-ratios`

注意：`auction_ratio` 的当前口径是：

```text
auction_ratio = 开盘集合竞价成交量(股) / T-1日线成交量(手)
```

由于分子是股、分母是手，这个比值天然等价于百分比数值。例如 `819000 / 100000 = 8.19`，表示竞昨比 `8.19%`。不要再额外乘以 100。

### 2.2 本地通达信日线建库

相关文件：

- `backend/services/tdx_local_selector.py`
- `backend/services/tdx_local_daily_sync_service.py`
- `backend/services/data_collector.py`
- `tests/backend/unit/test_tdx_local_daily.py`

已实现能力：

- 从 `TDX_VIPDOC_PATH` 或默认 `G:\new_tdx\vipdoc` 扫描 `sh/lday/*.day`、`sz/lday/*.day`。
- 将 `.day` 数据同步到已有 `stock_daily_data` 表，不另建重复日线表。
- `stock_daily_data` 使用唯一键 `(ts_code, trade_date)` upsert，重复执行不会插重复数据。
- `get_daily_data()` 优先从 `stock_daily_data` 读取，避免训练时频繁走 Tushare。

关键单位修正：

```text
.day price:   原始整数 / 100
.day vol:     原始成交量 / 100     -> 对齐 Tushare daily.vol，单位“手”
.day amount:  原始成交额 / 1000    -> 对齐 Tushare daily.amount
```

这个单位修正非常重要。此前样本为 0 的根因之一就是本地 `.day` 的成交量、成交额未缩放，导致竞价相关过滤口径错乱。

API：

- `POST /api/v1/backtest/tdx-local-daily/sync`

请求示例：

```json
{
  "start_date": "20250723",
  "end_date": "20260508"
}
```

可选只同步指定股票：

```json
{
  "start_date": "20260507",
  "end_date": "20260508",
  "ts_codes": ["000001.SZ", "000002.SZ"]
}
```

### 2.3 样本与标签

相关文件：

- `backend/services/backtest/leader_main_t0_feature_builder.py`
- `backend/services/backtest/leader_main_t0_label_builder.py`
- `backend/models/auction_backtest.py`

样本表：

- `leader_main_t0_training_sample`

当前候选过滤核心条件：

- 非 ST、非北交所、非停牌。
- 流通市值 `< 2000` 亿。
- T-1 收盘价 `< 500`。
- 近 10 日上涨。
- 近 100 日涨停次数 `>= 3`。
- T-1 连板高度 `>= 2`。
- 市场高度排名 `<= 10`。
- T-1 真实换手达标。
- T-1 成交量不小于 T-2。
- MA5 >= MA10。
- 竞昨比在 `4% ~ 30%`。
- 竞价换手率在 `0.5% ~ 10%`。

标签规则：

```text
label_t0_limit_success = 1
当且仅当：
  T日不是一字涨停
  且 T日最高价触及涨停附近
  且 T日收盘封住涨停附近
```

一字板样本标签置为 `None`，不参与训练。

## 3. 真实数据状态

### 3.1 本地日线库

已同步区间：

```text
20250723 ~ 20260508
```

同步结果：

```text
stocks_scanned: 10337
stocks_with_rows: 8426
rows_synced: 1495103
```

口径校验样例：

```text
002903.SZ 20260507
stock_daily_data.vol    = 124398.16
stock_daily_data.amount = 554477.248
close                   = 45.22
```

这个数量级已与 Tushare `daily` 基本一致。

### 3.2 竞价数据与竞昨比重算

训练区间：

```text
20260202 ~ 20260508
```

已用本地日线库重算：

```text
trade_dates: 60
updated_count: 310804
missing_count: 17754
```

注意：如果以后重建或补充 `stock_daily_data`，必须再次执行竞昨比重算，否则 `stock_auction_open.auction_ratio` 可能仍是旧口径。

### 3.3 训练样本

训练区间：

```text
20260202 ~ 20260508
```

当前样本：

```text
sample_rows: 127
usable_rows: 123
labels: {0: 91, 1: 32}
```

这只是初版小样本，能跑通链路，但不能作为成熟胜率模型。

### 3.4 当前 active 模型

模型名：

```text
leader_main_t0_lgbm
```

active version：

```text
20260509_142056
```

模型文件：

```text
H:\project_development\xuangu\backend\models\leader_main_t0_lgbm_20260509_142056.pkl
```

训练输出：

```text
validation best iteration: 4
validation auc: 0.719444
```

`model_version.model_metrics`：

```json
{
  "auc": 0.9375,
  "accuracy": 0.8,
  "precision": 0.0,
  "recall": 0.0,
  "sample_count": 123,
  "train_dates": 39,
  "validation_dates": 12,
  "test_dates": 6
}
```

解释：

- AUC 看起来高，但样本太少，测试日期只有 6 个，不能过度相信。
- 默认阈值 `0.5` 下 precision/recall 都是 0，说明模型偏保守，当前更适合输出排序概率，不适合直接给买卖结论。
- 下一阶段重点是扩样本、校准概率、找最佳阈值。

## 4. 复现当前状态的命令

以下命令在项目根目录执行：

```powershell
cd H:\project_development\xuangu
```

### 4.1 同步本地通达信日线

```powershell
$code = @'
from backend.services.tdx_local_daily_sync_service import TdxLocalDailySyncService
result = TdxLocalDailySyncService().sync_range("20250723", "20260508", commit_every=10000)
print(result)
'@
python -c $code
```

### 4.2 重算竞昨比

```powershell
$code = @'
from backend.services.auction_data_service import AuctionDataService
result = AuctionDataService(collector=object()).recalculate_auction_ratios_from_daily_cache("20260202", "20260508")
print(result)
'@
python -c $code
```

### 4.3 重建样本和标签

```powershell
$code = @'
from collections import Counter
from backend.database import SessionLocal
from backend.models.auction_backtest import StockAuctionOpen, LeaderMainT0TrainingSample
from backend.services.backtest.leader_main_t0_feature_builder import LeaderMainT0FeatureBuilder
from backend.services.backtest.leader_main_t0_label_builder import LeaderMainT0LabelBuilder

start_date = "20260202"
end_date = "20260508"

with SessionLocal() as db:
    trade_dates = [
        r[0]
        for r in db.query(StockAuctionOpen.trade_date)
        .filter(StockAuctionOpen.trade_date.between(start_date, end_date))
        .distinct()
        .order_by(StockAuctionOpen.trade_date)
        .all()
    ]
    db.query(LeaderMainT0TrainingSample).filter(
        LeaderMainT0TrainingSample.trade_date.between(start_date, end_date)
    ).delete(synchronize_session=False)
    db.commit()

builder = LeaderMainT0FeatureBuilder()
saved = 0
for trade_date in trade_dates:
    features = builder.build_leader_main_t0_features_for_date(trade_date)
    saved += builder.save_training_samples(trade_date, features)

updated = LeaderMainT0LabelBuilder().build_leader_main_t0_labels(start_date, end_date)

with SessionLocal() as db:
    rows = db.query(LeaderMainT0TrainingSample).filter(
        LeaderMainT0TrainingSample.trade_date.between(start_date, end_date)
    ).all()
    usable = [r for r in rows if r.label_t0_limit_success is not None]
    labels = Counter(r.label_t0_limit_success for r in usable)

print({"saved": saved, "updated": updated, "sample_rows": len(rows), "usable_rows": len(usable), "labels": dict(labels)})
'@
python -c $code
```

期望接近：

```text
sample_rows: 127
usable_rows: 123
labels: {0: 91, 1: 32}
```

### 4.4 训练模型

```powershell
$code = @'
from backend.services.model_engine.lightgbm_service import train_leader_main_t0_lgbm
print(train_leader_main_t0_lgbm("20260202", "20260508"))
'@
python -c $code
```

### 4.5 验证状态

```powershell
$code = @'
import json, os
from collections import Counter
from backend.database import SessionLocal
from backend.models import ModelVersion, LeaderMainT0TrainingSample
from backend.models.seal_rate import StockDailyData
from backend.services.model_engine.lightgbm_service import LEADER_MAIN_T0_MODEL_NAME

with SessionLocal() as db:
    local_rows = db.query(StockDailyData).filter(
        StockDailyData.trade_date >= "20250723",
        StockDailyData.trade_date <= "20260508",
    ).count()
    samples = db.query(LeaderMainT0TrainingSample).filter(
        LeaderMainT0TrainingSample.trade_date.between("20260202", "20260508")
    ).all()
    usable = [s for s in samples if s.label_t0_limit_success is not None]
    labels = Counter(s.label_t0_limit_success for s in usable)
    mv = db.query(ModelVersion).filter(
        ModelVersion.model_name == LEADER_MAIN_T0_MODEL_NAME,
        ModelVersion.is_active == 1,
    ).order_by(ModelVersion.id.desc()).first()
    print({"local_daily_rows": local_rows, "sample_rows": len(samples), "usable_rows": len(usable), "labels": dict(labels)})
    print({"active_version": mv.version, "model_path": mv.model_path, "exists": os.path.exists(mv.model_path), "metrics": json.loads(mv.model_metrics)})
'@
python -c $code
```

### 4.6 回归测试

```powershell
python -m pytest tests/backend/unit/test_backtest_api.py tests/backend/unit/test_model_status_api.py tests/backend/unit/test_auction_data_service.py tests/backend/unit/test_tdx_local_daily.py tests/backend/unit/test_leader_main_t0_label_builder.py tests/backend/unit/test_leader_main_t0_lightgbm.py tests/backend/unit/test_leader_main_t0_feature_builder.py tests/backend/unit/test_leader_main_t0_label_service.py tests/backend/unit/test_stock_api_t0_model_fields.py tests/backend/unit/test_tushare_client_intraday.py tests/backend/unit/test_seal_rate_calculator.py tests/backend/unit/test_mcp_fallback.py -q
```

当前已验证结果：

```text
47 passed, 13 warnings
```

## 5. 新 AI 接下来要做什么

### 任务 1：先处理 Git 状态

当前本地分支有 1 个提交未推送：

```powershell
git status --short --branch
git push
```

如果仍然失败，多半是 GitHub 网络问题。不要重复改代码来“修复 push”。

注意未跟踪文件：

```text
backend/models/leader_main_t0_lgbm_20260509_130055.pkl
backend/models/leader_main_t0_lgbm_20260509_142056.pkl
docs/竞价增强回测与LightGBM开发文档.md
量化训练开发.md
```

模型 `.pkl` 默认不要提交，除非用户明确要求纳入仓库或建立模型产物管理规则。

### 任务 2：把训练区间扩大到更多历史

当前只有 60 个交易日，样本太少。下一步建议扩到至少 1 年，最好 2 年：

```text
建议区间：20240501 ~ 20260508
```

执行顺序必须是：

1. 确认 `stock_auction_open` 有对应区间竞价数据；缺多少先同步多少。
2. 同步本地日线库，日线起点要比训练起点早至少 130 个交易日。
3. 重算竞昨比。
4. 重建样本。
5. 生成标签。
6. 训练模型。
7. 查看标签分布、AUC、precision、recall、分日期表现。

不要跳过第 3 步。

### 任务 3：做阈值评估，不要只看 0.5

当前 `precision=0.0`、`recall=0.0` 的主要原因是默认阈值 `0.5` 不适合小样本。后续应增加阈值评估：

输出每个阈值下的：

```text
threshold
precision
recall
hit_count
avg_return
max_drawdown_like
```

建议先评估：

```text
0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50
```

### 任务 4：扩展特征，但不要引入标签泄露

可以优先增加的特征：

- 龙虎榜 Alpha：复用 `backend/services/lhb_service.py` 和 `backend/services/seat_library.py`。
- 新闻情感：复用 `backend/services/news_sentiment/analyzer.py`，不要新建新闻源。
- 板块强度：复用 `dc_board_service`、`ths_board_service` 或已有板块快照。
- 近期涨停结构：最高连板、断板反包、炸板次数。
- 竞价质量：`auction_vwap_gap_pct`、竞价成交额/流通市值。

禁止：

- 用 T 日收盘后的信息做 T 日开盘前特征。
- 新建外部新闻、龙虎榜、席位判断数据源。
- 重新维护席位关键词表，必须用 `seat_library`。

### 任务 5：工程化模型使用方式

当前模型已经通过：

```python
batch_predict_leader_main_t0(stocks_data)
```

给候选股写入：

```text
t0_limit_success_prob
t0_limit_success_prob_model_version
```

后续要确认前端或选股结果里是否展示：

- T+0 成功率。
- 模型版本。
- 数据免责声明。
- 模型不可用时显示 `None`，不能影响原有 `final_score`。

### 任务 6：建立模型产物策略

当前 `.pkl` 在：

```text
backend/models/
```

但未提交。后续需要用户确认：

1. 是否把模型文件纳入 Git。
2. 是否改为本地产物，仅数据库 `model_version` 记录路径。
3. 是否建立 `models/.gitignore`，只保留 README 或 manifest。

未确认前不要随便提交 `.pkl`。

## 6. 易错点

1. `.day` 没有集合竞价过程数据，只能提供日线 OHLCV；竞价量来自 Tushare `stk_auction_o`。
2. `.day` 成交量必须 `/100`，成交额必须 `/1000`。
3. `auction_ratio` 不要额外乘以 100。
4. 重建本地日线库后，必须重算竞价表里的 `auction_ratio`。
5. 训练样本为 0 时，先查拒绝原因，不要直接放宽过滤条件。
6. 样本不足时，不要夸大模型指标。
7. 本项目规则要求优先复用已有服务，不要新造 Tushare 直连接口绕过业务层。

## 7. 建议下一条给 AI 的指令

可以直接对新的 AI 说：

```text
请先阅读 docs/LightGBM模块开发进度与后续任务.md，然后继续扩大 LightGBM 训练样本到 20240501~20260508。按文档顺序执行：同步缺失竞价数据、同步本地日线、重算竞昨比、重建样本、生成标签、训练模型、输出阈值评估。不要提交模型 pkl，先给我训练结果和下一步建议。
```
