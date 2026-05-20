# 当日涨停模型日线模拟盘回测系统设计

## 背景

当前默认竞价接力 V2 已经训练出三目标模型，但本期回测需求收窄为只验证一个模型：

```text
default_auction_t0_limit_lgbm
```

该模型用于预测“当日涨停/当日强势成功”的概率。用户需要一个简单、可读、接近模拟盘的日线级别回测网页：每天按模型概率选前 2 只股票，开盘买入，收盘按止盈止损和持仓规则卖出，并展示初始金额、每笔买卖时间、盈亏率和盈亏金额。

本设计不做分钟级撮合，不做盘中触发，不做三个模型对比。

## 目标

1. 只使用 `default_auction_t0_limit_lgbm` 做回测。
2. 每个交易日按模型预测概率降序，最多新买入前 2 只股票。
3. 总持仓数量最多 4 只。
4. 买入价使用买入交易日 `stock_daily_data.open`。
5. 卖出价使用卖出交易日 `stock_daily_data.close`。
6. 买入时间固定展示为 `YYYY-MM-DD 09:30`，卖出时间固定展示为 `YYYY-MM-DD 15:00`。
7. 支持配置初始资金，默认 `100000` 元。
8. 每只股票记录买入金额、买入价、卖出价、盈亏率、盈亏金额、卖出原因。
9. 回测结果创建一个新网页展示，不塞进模型中心的大面板里。
10. 缺少日线价格、模型文件或必要特征时不填假数据，明确记录失败和跳过原因。

## 非目标

本期不做：

1. 不做真实自动交易。
2. 不做分钟线止盈止损。
3. 不做盘中最高价/最低价触发。
4. 不做次日溢价模型、次日连板模型回测。
5. 不做行业、板块、市值分组统计。
6. 不做复杂仓位择时或动态加减仓。
7. 不把回测结果写回 `selected_stock`。

## 核心口径

### 股票池

默认从 `default_auction_training_sample` 读取候选样本：

- `strategy_version = "default_auction_v2"`
- `trade_date` 在请求日期区间内
- `ts_code` 只允许 `.SH`、`.SZ`
- 默认排除 `.BJ`
- 默认样本来源为 `real_selected`

可选样本来源：

| 值 | 含义 |
|---|---|
| `real_selected` | 真实选股样本 |
| `replay_backtest` | 历史回放样本 |
| `all` | 全部样本；同一交易日同一股票优先使用 `real_selected` |

### 模型排序

每天执行：

1. 加载 `default_auction_t0_limit_lgbm` 的 active 版本，或用户指定版本。
2. 使用样本 `feature_json` 做预测。
3. 剔除当前已经持仓的股票。
4. 按预测概率从高到低排序。
5. 如果可用持仓槽位大于 0，则买入最多 2 只，并且总持仓不超过 4 只。

示例：

```text
当前持仓 3 只 -> 当天最多只能再买 1 只
当前持仓 2 只 -> 当天最多可以买 2 只
当前持仓 4 只 -> 当天不买入
```

### 买入规则

买入时间：

```text
买入交易日 09:30
```

买入价：

```text
stock_daily_data.open
```

仓位规则：

```text
单只目标仓位 = 当前总资产 / 4
实际买入金额 = min(可用现金, 单只目标仓位)
```

如果现金不足以买入一手，本期先不做手数约束，按金额模拟。

### 卖出规则

每天收盘后检查所有持仓，卖出时间固定为：

```text
卖出交易日 15:00
```

卖出价：

```text
stock_daily_data.close
```

默认卖出条件：

| 条件 | 默认值 | 卖出原因 |
|---|---:|---|
| 止盈 | 收盘较买入价 `>= +8%` | `take_profit` |
| 止损 | 收盘较买入价 `<= -5%` | `stop_loss` |
| 最长持仓 | 持仓满 3 个交易日 | `max_holding_days` |

卖出判断只使用收盘价，不使用盘中最高价/最低价。也就是说，即使盘中涨停但收盘未达到止盈条件，本系统也不会按涨停价卖出。

用户可在页面调整：

- 止盈比例
- 止损比例
- 最长持仓天数
- 初始资金

### 每日流程顺序

为避免同一天卖出后又立刻重新加仓导致口径复杂，默认顺序为：

1. 开盘前读取当天候选样本并计算模型概率。
2. 09:30 根据现金和持仓上限买入当日概率前 2。
3. 15:00 检查全部持仓是否满足卖出条件。
4. 更新现金、持仓、市值、当日权益。

当天卖出的资金不参与当天 09:30 的买入，只能下一交易日再使用。

## 收益计算

单笔交易：

```text
gross_return_pct = (sell_price - buy_price) / buy_price * 100
net_return_pct = gross_return_pct - buy_fee_pct - sell_fee_pct - slippage_pct * 2
profit_amount = buy_amount * net_return_pct / 100
sell_amount = buy_amount + profit_amount
```

默认成本：

```text
buy_fee_pct = 0
sell_fee_pct = 0
slippage_pct = 0
```

组合权益：

```text
cash = 现金
market_value = 未卖出持仓按当日收盘价估值
equity = cash + market_value
total_return_pct = (equity - initial_cash) / initial_cash * 100
```

最大回撤：

```text
drawdown = (equity - history_peak_equity) / history_peak_equity * 100
```

## 指标定义

### 汇总指标

| 字段 | 说明 |
|---|---|
| `initial_cash` | 初始资金 |
| `final_equity` | 最终权益 |
| `total_return_pct` | 总收益率 |
| `total_profit_amount` | 总盈亏金额 |
| `max_drawdown_pct` | 最大回撤 |
| `trade_count` | 已完成交易数量 |
| `open_position_count` | 期末未平仓数量 |
| `win_rate` | 已完成交易中盈利交易占比 |
| `avg_trade_return_pct` | 单笔平均收益率 |
| `best_trade_return_pct` | 最好单笔收益率 |
| `worst_trade_return_pct` | 最差单笔收益率 |
| `skipped_buy_count` | 因持仓满、现金不足或数据缺失跳过的买入数量 |
| `prediction_failed_count` | 模型预测失败样本数 |
| `missing_price_count` | 缺少开盘价/收盘价的样本数 |

### 每日权益

| 字段 | 说明 |
|---|---|
| `trade_date` | 交易日 |
| `cash` | 收盘现金 |
| `market_value` | 收盘持仓市值 |
| `equity` | 收盘权益 |
| `daily_return_pct` | 当日权益收益率 |
| `drawdown_pct` | 当前回撤 |
| `position_count` | 收盘持仓数量 |

### 交易明细

每只股票一条完整交易记录：

| 字段 | 说明 |
|---|---|
| `trade_id` | 交易 ID |
| `ts_code` | 股票代码 |
| `name` | 股票名称 |
| `model_prob` | 买入时模型概率 |
| `rank` | 买入日模型排名 |
| `buy_date` | 买入日期 |
| `buy_time` | 买入时间，固定 `09:30` |
| `buy_price` | 买入价 |
| `buy_amount` | 买入金额 |
| `sell_date` | 卖出日期，未卖出为空 |
| `sell_time` | 卖出时间，固定 `15:00` |
| `sell_price` | 卖出价 |
| `holding_days` | 持仓交易日数 |
| `return_pct` | 盈亏率 |
| `profit_amount` | 盈亏金额 |
| `sell_reason` | `take_profit/stop_loss/max_holding_days/end_of_backtest` |
| `status` | `closed/open` |

回测结束时仍持仓的股票按结束日收盘价做期末估值；页面中状态显示为 `open`。用户勾选“结束日强制平仓”时，系统可用结束日收盘价生成 `end_of_backtest` 卖出记录。

## 数据来源

必须复用已有表和服务：

| 数据 | 复用位置 |
|---|---|
| 候选样本和特征 | `backend.models.DefaultAuctionTrainingSample` |
| 模型版本 | `backend.models.ModelVersion` |
| 模型预测 | `backend.services.model_engine.lightgbm_service._predict_with_model_path` |
| 日线开收盘价 | `backend.models.seal_rate.StockDailyData` / `stock_daily_data` |
| 数据库会话 | `backend.database.SessionLocal` / `get_db` |

不得新增外部行情接口来补价格。价格缺失时记录缺失，不用 0、昨日收盘或训练标签收益字段代替。

## 数据模型

新增模型文件：

```text
backend/models/t0_simulation_backtest.py
```

### `t0_simulation_backtest_run`

保存一次模拟盘回测。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | 回测 ID |
| `status` | String | `pending/running/passed/failed` |
| `start_date` | String | 起始交易日 |
| `end_date` | String | 结束交易日 |
| `model_name` | String | 固定 `default_auction_t0_limit_lgbm` |
| `model_version` | String nullable | 指定版本，空表示 active |
| `resolved_model_version` | String nullable | 实际使用版本 |
| `sample_source` | String | 样本来源 |
| `initial_cash` | Float | 初始资金 |
| `buy_top_n` | Integer | 默认 2 |
| `max_positions` | Integer | 默认 4 |
| `take_profit_pct` | Float | 默认 8 |
| `stop_loss_pct` | Float | 默认 -5 |
| `max_holding_days` | Integer | 默认 3 |
| `cost_json` | Text | 费用参数 |
| `summary_json` | Text | 汇总指标 |
| `error_message` | Text nullable | 失败原因 |
| `started_at` | DateTime nullable | 开始时间 |
| `finished_at` | DateTime nullable | 完成时间 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

索引：

```text
idx_t0_sim_backtest_run_status(status)
idx_t0_sim_backtest_run_created(created_at)
idx_t0_sim_backtest_run_date(start_date, end_date)
```

### `t0_simulation_backtest_daily`

保存每日权益。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | ID |
| `run_id` | Integer FK | 回测 ID |
| `trade_date` | String | 交易日 |
| `cash` | Float | 现金 |
| `market_value` | Float | 持仓市值 |
| `equity` | Float | 权益 |
| `daily_return_pct` | Float | 当日收益率 |
| `drawdown_pct` | Float | 当前回撤 |
| `position_count` | Integer | 持仓数量 |

唯一约束：

```text
uk_t0_sim_backtest_daily(run_id, trade_date)
```

### `t0_simulation_backtest_trade`

保存交易明细。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | 交易 ID |
| `run_id` | Integer FK | 回测 ID |
| `ts_code` | String | 股票代码 |
| `name` | String | 股票名称 |
| `model_prob` | Float | 买入概率 |
| `rank` | Integer | 买入日排名 |
| `buy_date` | String | 买入日期 |
| `buy_time` | String | 固定 `09:30` |
| `buy_price` | Float | 买入价 |
| `buy_amount` | Float | 买入金额 |
| `sell_date` | String nullable | 卖出日期 |
| `sell_time` | String nullable | 固定 `15:00` |
| `sell_price` | Float nullable | 卖出价 |
| `holding_days` | Integer | 持仓交易日数 |
| `return_pct` | Float nullable | 盈亏率 |
| `profit_amount` | Float nullable | 盈亏金额 |
| `sell_reason` | String nullable | 卖出原因 |
| `status` | String | `open/closed` |

索引：

```text
idx_t0_sim_backtest_trade_run(run_id)
idx_t0_sim_backtest_trade_buy_date(buy_date)
idx_t0_sim_backtest_trade_stock(ts_code)
```

## 后端服务设计

新增服务：

```text
backend/services/model_engine/t0_simulation_backtest_service.py
```

核心函数：

```python
def create_t0_simulation_backtest_run(db, request) -> T0SimulationBacktestRun:
    """创建回测运行。"""


def run_t0_simulation_backtest(db, run_id: int) -> dict:
    """执行日线模拟盘回测，写入每日权益和交易明细。"""


def list_t0_simulation_backtest_runs(db, limit: int = 20) -> list[dict]:
    """查询回测历史。"""


def get_t0_simulation_backtest_run(db, run_id: int) -> dict:
    """查询单次回测详情。"""
```

执行步骤：

1. 读取回测参数。
2. 加载 `default_auction_t0_limit_lgbm` 模型版本。
3. 查询日期区间内的训练样本。
4. 查询对应股票的 `stock_daily_data`。
5. 对每天样本做模型预测并排序。
6. 开盘按 Top2 和持仓上限买入。
7. 收盘按止盈、止损、最长持仓条件卖出。
8. 计算每日权益和回撤。
9. 写入交易明细和每日权益。
10. 汇总胜率、收益率、盈亏金额、最大回撤。

## API 设计

新增接口放在模型管理 API 或独立回测 API 中，路径使用：

```text
POST /api/v1/backtest/t0-simulation/runs
GET  /api/v1/backtest/t0-simulation/runs
GET  /api/v1/backtest/t0-simulation/runs/{run_id}
```

### 创建回测

请求：

```json
{
  "start_date": "20250101",
  "end_date": "20260518",
  "model_version": null,
  "sample_source": "real_selected",
  "initial_cash": 100000,
  "buy_top_n": 2,
  "max_positions": 4,
  "take_profit_pct": 8,
  "stop_loss_pct": -5,
  "max_holding_days": 3,
  "force_close_on_end": false,
  "cost": {
    "buy_fee_pct": 0,
    "sell_fee_pct": 0,
    "slippage_pct": 0
  }
}
```

响应：

```json
{
  "run_id": 1,
  "status": "pending"
}
```

### 查询详情

响应包含：

```json
{
  "id": 1,
  "status": "passed",
  "summary": {
    "initial_cash": 100000,
    "final_equity": 118500,
    "total_return_pct": 18.5,
    "total_profit_amount": 18500,
    "max_drawdown_pct": -7.2,
    "trade_count": 126,
    "win_rate": 0.57
  },
  "daily": [],
  "trades": []
}
```

## 前端页面设计

新增独立页面：

```text
frontend/src/views/T0SimulationBacktest.vue
```

新增路由：

```text
/backtest/t0-simulation
```

在顶部导航新增入口：

```text
日线模拟回测
```

### 页面控件

- 起始日期
- 结束日期
- 初始资金
- 样本来源
- 模型版本，默认 active
- 每日买入数量，默认 2
- 最大持仓数，默认 4
- 止盈比例，默认 8%
- 止损比例，默认 -5%
- 最长持仓天数，默认 3
- 是否结束日强制平仓
- 开始回测按钮
- 历史回测选择

### 页面展示

顶部汇总：

- 初始资金
- 最终权益
- 总盈亏金额
- 总收益率
- 最大回撤
- 已完成交易数
- 胜率
- 当前未平仓数量

主体区域：

- 权益曲线
- 每日资产表
- 交易明细表

交易明细表必须展示：

- 股票代码
- 股票名称
- 模型概率
- 买入日期时间
- 买入价
- 买入金额
- 卖出日期时间
- 卖出价
- 盈亏率
- 盈亏金额
- 卖出原因
- 状态

### 三态

必须覆盖：

- loading：创建回测、运行中、加载详情。
- error：模型缺失、样本为空、价格缺失严重、接口失败。
- empty：尚未运行或无历史回测。

## 错误处理

1. 模型版本不存在：运行失败。
2. 模型文件不存在：运行失败。
3. 日期区间无样本：运行失败。
4. 单个样本预测失败：跳过，累计 `prediction_failed_count`。
5. 买入日缺少开盘价：跳过买入，累计 `missing_price_count`。
6. 持仓期间缺少收盘价：当天不卖出、不估值，记录 `missing_price_count`。
7. 持仓满 4 只时，后续候选不买入，累计 `skipped_buy_count`。

## 测试设计

新增：

```text
tests/backend/unit/test_t0_simulation_backtest_service.py
```

覆盖：

1. 每日最多买入模型概率前 2。
2. 总持仓永远不超过 4。
3. 买入价使用开盘价，卖出价使用收盘价。
4. 止盈条件触发卖出。
5. 止损条件触发卖出。
6. 最长持仓天数触发卖出。
7. 盈亏率和盈亏金额计算正确。
8. 缺少价格时不填假数据。

新增：

```text
tests/backend/unit/test_t0_simulation_backtest_api.py
```

覆盖：

1. 创建回测返回 `run_id`。
2. 查询列表返回历史运行。
3. 查询详情返回 summary、daily、trades。
4. 非法参数返回 422。

前端验证：

```text
cd frontend
npm run build
```

## 开发顺序

1. 新增 ORM 模型和数据库迁移补齐逻辑。
2. 新增日线模拟盘回测服务和纯计算测试。
3. 新增 API。
4. 新增 `T0SimulationBacktest.vue` 页面和路由导航。
5. 前后端联调。
6. 跑后端测试和前端构建。

## 验收标准

1. 回测只使用 `default_auction_t0_limit_lgbm`。
2. 每日新买入股票不超过 2 只。
3. 总持仓数不超过 4 只。
4. 买入价来自日线开盘价，卖出价来自日线收盘价。
5. 页面能看到初始金额、最终权益、盈亏金额、收益率和最大回撤。
6. 每笔交易能看到买入卖出时间、盈亏率和盈亏金额。
7. 缺失价格不被填充为假数据。
8. 后端单元测试通过。
9. 前端 `npm run build` 通过。
