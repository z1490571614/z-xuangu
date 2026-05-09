# 竞价增强回测与 LightGBM 量化模型开发文档

| 项目 | 内容 |
|------|------|
| 文档版本 | v1.0 |
| 创建日期 | 2026-05-09 |
| 适用项目 | 选股通知系统 v5.2 |
| 核心目标 | 使用 Tushare `stk_auction_o` 补齐历史集合竞价数据，优先训练“龙头主升 T+0 非一字涨停成功率模型” |
| 当前结论 | 已具备回测龙头主升 T+0 非一字涨停成功率的关键数据源 |

---

## 1. 背景与结论

原始结论是：通达信本地 `.day` 日线数据只能提供开盘价、最高价、最低价、收盘价、成交量、成交额，不能提供 9:25 集合竞价成交量，因此无法历史还原 `竞昨比` 和 `竞价换手率`。

现在已购买 Tushare `stk_auction_o` 接口权限，该接口提供历史开盘集合竞价成交量、成交额和均价。由此可以补齐当前选股条件中最关键的两个竞价指标：

```text
竞昨比 = 9:25集合竞价成交量 / 前一交易日全天成交量 * 100
竞价换手率 = 9:25集合竞价成交量 / 当日流通股本 * 100
```

因此，系统可以进入两个开发阶段：

1. **龙头主升 T+0 历史回测**：复刻“连板抱团・追强”战法在 9:25/9:30 可见条件下的候选池，验证非一字候选当日能否涨停。
2. **LightGBM T+0 成功率模型**：在真实历史竞价特征与日线强度特征基础上，训练候选股“当日非一字涨停成功率”模型。

本阶段暂不训练四套战法，也暂不训练 T+1/T+3 连板延续模型。后续可以在 T+0 模型稳定后扩展。

---

## 2. 数据源规范

### 2.1 Tushare `stk_auction_o`

用途：获取开盘集合竞价数据，用于计算 `竞昨比`、`竞价换手率`、竞价成交额、竞价均价、竞价涨幅等特征。

关键字段：

| 字段 | 含义 | 用法 |
|------|------|------|
| `ts_code` | 股票代码 | 主键之一 |
| `trade_date` | 交易日期 | 主键之一 |
| `open` | 集合竞价开盘价 | 计算开盘涨幅 |
| `vol` | 集合竞价成交量 | 计算竞昨比、竞价换手率 |
| `amount` | 集合竞价成交额 | 竞价资金强度特征 |
| `vwap` | 集合竞价均价 | 价格质量特征 |

注意事项：

- `stk_auction_o` 是盘后接口，适合历史回测和训练。
- 当前实盘选股仍以 MCP 返回的当日竞价字段为主，因为系统需要盘中或开盘前后的实时可用性。
- 回测时使用 `stk_auction_o`，实盘时使用 MCP，两者必须经过同一套字段标准化函数，保证口径一致。

### 2.2 Tushare `daily`

用途：日线行情、开盘涨幅、昨日涨幅、10日涨幅、涨停次数、标签生成。

关键字段：

| 字段 | 含义 | 用法 |
|------|------|------|
| `open` | 开盘价 | 计算 `open_change_pct` |
| `close` | 收盘价 | 计算涨跌幅、趋势 |
| `pre_close` | 昨收价 | 计算开盘涨幅 |
| `pct_chg` | 当日涨跌幅 | 标签、昨日涨幅 |
| `vol` | 全天成交量，单位手 | 计算竞昨比的分母 |
| `amount` | 全天成交额 | 量价特征 |

### 2.3 Tushare `daily_basic`

用途：流通股本、市值、换手率、量比等基础指标。

关键字段：

| 字段 | 含义 | 用法 |
|------|------|------|
| `float_share` | 流通股本，单位万股 | 计算竞价换手率 |
| `circ_mv` | 流通市值，单位万元 | 过滤流通市值、模型特征 |
| `turnover_rate` | 全天换手率 | 日线基础特征 |
| `volume_ratio` | 量比 | 日线活跃度特征 |

### 2.4 涨停数据源

优先级：

1. `limit_list_d` 或可用的 Tushare 涨跌停列表接口。
2. 基于日线涨停价规则计算。
3. 现有 `SealRateCalculator` 缓存结果。

用途：

- 近 100 日涨停次数。
- 近 100 日触板次数。
- 近 100 日封板率。
- 连板结构。

### 2.5 当前实盘 MCP 数据

用途：当日实时选股、实时规则评分、实盘特征快照。

必须保留：

- `auction_ratio`
- `auction_turnover_rate`
- `limit_up_count`
- `rise_10d_pct`

约束：

- 新执行的选股任务不能从历史 `selected_stock` 回填这些字段。
- 竞价字段只接受 MCP 当前返回值或回测阶段 `stk_auction_o` 计算值。
- 不允许用通达信实时 quote 的非竞价字段反推竞价量。

---

## 3. 指标口径

### 3.1 开盘涨幅

```text
open_change_pct = (daily.open - daily.pre_close) / daily.pre_close * 100
```

如果 `stk_auction_o.open` 与 `daily.open` 同时存在，回测以 `stk_auction_o.open` 为优先，用于贴合竞价阶段。

### 3.2 昨日涨幅

```text
pre_change_pct = previous_daily.pct_chg
```

### 3.3 竞昨比

Tushare `daily.vol` 单位为手，`stk_auction_o.vol` 按股处理。

```text
yesterday_volume_shares = previous_daily.vol * 100
auction_ratio = stk_auction_o.vol / yesterday_volume_shares * 100
```

等价简化：

```text
auction_ratio = stk_auction_o.vol / previous_daily.vol
```

输出单位：百分比数值。

示例：

```text
auction_ratio = 8.19
表示竞昨比 8.19%
```

### 3.4 竞价换手率

Tushare `daily_basic.float_share` 单位为万股。

```text
float_share_shares = daily_basic.float_share * 10000
auction_turnover_rate = stk_auction_o.vol / float_share_shares * 100
```

输出单位：百分比数值。

示例：

```text
auction_turnover_rate = 0.83
表示竞价换手率 0.83%
```

### 3.5 10 日涨幅

```text
rise_10d_pct = (today_close - close_10_trading_days_ago) / close_10_trading_days_ago * 100
```

### 3.6 近 100 日涨停次数

优先使用涨跌停列表接口统计。

备用规则：

```text
limit_up_count_100d = count(close >= calculated_limit_up_price)
```

需要按市场类型区分涨跌停幅度：

| 类型 | 涨停幅度 |
|------|----------|
| 主板非 ST | 10% |
| 创业板、科创板 | 20% |
| ST | 5%，但当前选股应排除 ST |
| 北交所 | 当前选股应排除 |

### 3.7 封板率

复用现有 `SealRateCalculator`：

```text
封板率 = 100日内涨停天数 / 100日内触板天数 * 100
```

---

## 4. 龙头主升相关选股条件回测复刻

目标：使用历史数据尽量 1:1 复刻龙头主升 T+0 候选条件。

### 4.1 回测过滤条件

| 条件 | 数据源 | 是否可完整还原 |
|------|--------|----------------|
| 非 ST | `stock_basic` + 名称过滤 | 是 |
| 非停牌 | 当日 `daily` 存在成交 | 是 |
| 非北交所 | 代码与交易所过滤 | 是 |
| 流通市值 < 2000 亿 | `daily_basic.circ_mv` | 是 |
| T-1 收盘价 < 500 | T-1 `daily.close` | 是 |
| T-1 前近 10 日股价上涨 | `daily` | 是 |
| T-1 前近 100 日涨停次数 >= 3 | 涨跌停列表或日线计算 | 是 |
| 竞昨比 4%-30% | `stk_auction_o.vol` + 昨日 `daily.vol` | 是 |
| 竞价换手率 0.5%-10% | `stk_auction_o.vol` + `daily_basic.float_share` | 是 |

---

## 5. 龙头主升 T+0 非一字涨停成功率模型

### 5.1 模型定位

模型名称：

```text
leader_main_t0_lgbm
```

核心问题：

```text
在龙头主升战法筛出的候选股中，排除一字板后，哪些股票当日大概率能够涨停并封住。
```

该模型不是全市场涨停预测模型，而是“龙头主升候选池内的成功率排序模型”。

适用时点：

1. 9:25 集合竞价完成后。
2. 9:30 开盘后。
3. 后续若接入分钟线，可扩展到 9:31 第一根 1 分钟 K 线确认后。

第一版只使用 9:25 前后可历史还原的数据：

- T-1 及以前的日线、涨停结构、板块强度。
- T 日 `stk_auction_o` 开盘竞价数据。
- 不使用 T 日收盘后才知道的信息作为特征。

### 5.2 候选池定义

训练样本必须先经过龙头主升战法候选生成，不能直接拿全市场训练。

第一版候选硬条件：

| 维度 | 条件 | 数据源 |
|------|------|--------|
| 基础过滤 | 非 ST、非停牌、非北交所 | `stock_basic` + `daily` |
| 龙头强度 | T-1 连续涨停 >= 2 | 涨停列表或日线计算 |
| 市场地位 | T-1 连板高度处于市场前 10 | 每日连板统计 |
| 非一字可交易 | T 日不是一字板 | `stk_auction_o` + `daily` |
| 真实换手 | T-1 换手率 >= 3%，创业板 >= 5% | `daily_basic.turnover_rate` |
| 量价结构 | T-1 涨停日成交量 >= T-2 成交量 | `daily.vol` |
| 均线趋势 | T-1 收盘价站上 MA5、MA10，且 MA5 >= MA10 | `daily` |
| 板块热点 | 所属板块 T-1 或 T 日为热点，板块涨幅 >= 2%，涨停数 >= 3 | 东财板块/同花顺标签 |
| 竞价活跃 | T 日竞昨比 4%-30% | `stk_auction_o.vol` + T-1 `daily.vol` |
| 竞价换手 | T 日竞价换手率 0.5%-10% | `stk_auction_o.vol` + `daily_basic.float_share` |

关于“所属板块为主线热点”的第一版实现：

- 优先复用 `dc_board_service`、`dc_board_alias_service`、涨停标签映射。
- 若历史板块涨幅或涨停数缺失，可先降级为“所属题材匹配当日涨停标签热词”，并记录数据缺失标记。
- 不允许为模型临时硬编码一套独立板块词典。

### 5.3 一字板排除规则

一字板不参与训练，也不作为正样本。

原因：

- 一字板没有真实换手买点。
- 龙头主升战法定位是“换手龙”，不是“一字死龙”。
- 一字板进入训练会让模型错误偏好不可参与标的。

第一版一字板判定：

```text
is_one_line_limit_up = (
    open >= limit_up_price * 0.997
    and high >= limit_up_price * 0.997
    and low >= limit_up_price * 0.997
    and close >= limit_up_price * 0.997
)
```

如果只有开盘竞价阶段数据，则使用保守过滤：

```text
auction_open >= limit_up_price * 0.997
and auction_vol 极低或竞价换手率低于可交易阈值
```

训练数据最终分类：

| 类型 | 是否入训练 |
|------|------------|
| 一字板 | 否，剔除 |
| 非一字，当日收盘涨停 | 是，正样本 |
| 非一字，当日未涨停或未封住 | 是，负样本 |

### 5.4 标签定义

第一版主标签：

```text
label_t0_limit_success = 1
```

满足：

```text
当日非一字板
且当日最高价触及涨停价
且当日收盘价 >= 涨停价 * 0.997
```

否则：

```text
label_t0_limit_success = 0
```

如果后续有封板时间、炸板次数、封单额数据，可升级为更严格标签：

```text
label_t0_seal_success = 1
当日非一字板
且收盘涨停
且炸板次数 <= 2
且首次封板时间不晚于 10:30
```

第一版必须额外保存连续结果字段：

| 字段 | 含义 |
|------|------|
| `t0_high_return` | 当日最高涨幅 |
| `t0_close_return` | 当日收盘涨幅 |
| `t0_low_return` | 当日最低涨幅 |
| `t0_touched_limit` | 当日是否触板 |
| `t0_closed_limit` | 当日是否收盘涨停 |
| `is_one_line_limit_up` | 是否一字板 |

### 5.5 特征设计

第一版训练特征以“可回测、可解释、可实盘复用”为原则。

T-1 及以前特征：

```text
limit_up_streak
market_height_rank
limit_up_count_100d
seal_rate_100d
rise_5d_pct
rise_10d_pct
pre_change_pct
yesterday_turnover_rate
yesterday_amount
yesterday_volume_ratio
ma5_gap_pct
ma10_gap_pct
ma5_gt_ma10
prev_day_volume_ge_prev2
prev_day_open_board_count
sector_change_pct
sector_limit_up_count
sector_hot_rank
is_sector_leader
```

T 日竞价特征：

```text
open_change_pct
auction_ratio
auction_turnover_rate
auction_amount
auction_vwap_gap_pct
auction_volume
auction_amount_to_circ_mv
```

风险过滤特征：

```text
has_negative_news
has_reduction_news
has_regulatory_risk
is_high_position
```

第一版可缺省但要预留的分钟线特征：

```text
first_1m_return
first_1m_volume_ratio
first_1m_drawdown
first_1m_upper_shadow_pct
```

在没有历史分钟线数据前，上述分钟线特征不参与训练。

### 5.6 训练数据生成流程

```text
遍历历史交易日 T
  -> 读取 T-1 及以前日线、涨停、板块数据
  -> 读取 T 日 stk_auction_o
  -> 生成龙头主升候选池
  -> 排除 T 日一字板
  -> 计算 T 日竞昨比、竞价换手率
  -> 计算 T 日是否触板、是否收盘涨停
  -> 写入 leader_main_t0_training_sample
```

严格约束：

- 候选生成只能使用买入时点可见数据。
- 标签生成可以使用 T 日收盘行情，但标签不能反哺特征。
- 最新交易日如果缺少完整 T 日收盘数据，不生成标签。

### 5.7 建议训练样本表

表名建议：

```text
leader_main_t0_training_sample
```

唯一键：

```text
trade_date + ts_code
```

核心字段：

| 字段 | 说明 |
|------|------|
| `trade_date` | 交易日 T |
| `ts_code` | 股票代码 |
| `name` | 股票名称 |
| `strategy_name` | 固定为 `leader_main_t0` |
| `feature_json` | 完整特征快照 JSON |
| `label_t0_limit_success` | 主标签 |
| `t0_touched_limit` | 是否触板 |
| `t0_closed_limit` | 是否收盘涨停 |
| `is_one_line_limit_up` | 是否一字板 |
| `t0_high_return` | 当日最高涨幅 |
| `t0_close_return` | 当日收盘涨幅 |
| `created_at` | 创建时间 |

如果为了查询性能，也可以将核心特征拆成列，`feature_json` 保留完整快照。

### 5.8 模型输出

模型输出：

```text
t0_limit_success_prob: 0-100
```

解释含义：

```text
当前龙头主升候选股，当日非一字涨停并封住的概率。
```

建议分层：

| 概率 | 等级 | 解释 |
|------|------|------|
| >= 80 | S | 极强，优先关注 |
| 65-80 | A | 强势，可参与观察 |
| 50-65 | B | 有机会，但需确认 |
| 35-50 | C | 弱成功率，谨慎 |
| < 35 | D | 不参与 |

### 5.9 与后续连板模型的边界

本阶段模型只回答：

```text
今天能不能从非一字候选走到涨停并封住？
```

不回答：

```text
明天能不能继续连板？
未来三天收益是多少？
龙头周期是否退潮？
```

后续可单独训练：

```text
leader_main_t1_continue_lgbm
```

该模型的训练对象应是 T+0 已经涨停成功的样本，用于预测 T+1/T+3 连板延续或高溢价概率。

### 5.10 回测输出

每个交易日输出：

- 当日龙头主升 T+0 候选股票列表。
- 每只股票的完整条件字段。
- T+0 是否触板、是否收盘涨停。
- T+0 最高涨幅、最低涨幅、收盘涨幅。
- 是否一字板及剔除原因。
- `label_t0_limit_success`。
- 规则评分。
- T+0 涨停成功率，若存在有效模型。

### 5.11 第一版成功标准

第一版完成时，应满足：

- 可以生成历史每个交易日的龙头主升 T+0 候选池。
- 可以排除一字板。
- 可以计算 `auction_ratio` 和 `auction_turnover_rate`。
- 可以生成 `label_t0_limit_success`。
- 可以训练 `leader_main_t0_lgbm`。
- 可以输出每只候选股的 T+0 涨停成功率。
- 模型不存在或预测失败时，不影响现有选股流程。

---

## 6. 数据库设计

### 6.1 新增历史竞价表

表名建议：`stock_auction_open`

唯一键：`trade_date + ts_code`

字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer | 主键 |
| `trade_date` | String(10) | 交易日 |
| `ts_code` | String(20) | 股票代码 |
| `open` | Float | 集合竞价开盘价 |
| `high` | Float | 接口若提供则保存 |
| `low` | Float | 接口若提供则保存 |
| `close` | Float | 接口若提供则保存 |
| `vol` | Float | 集合竞价成交量，按股 |
| `amount` | Float | 集合竞价成交额 |
| `vwap` | Float | 集合竞价均价 |
| `auction_ratio` | Float | 派生竞昨比 |
| `auction_turnover_rate` | Float | 派生竞价换手率 |
| `source` | String(30) | `tushare_stk_auction_o` 或 `mcp_live` |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

### 6.2 新增龙头主升 T+0 训练样本表

表名建议：`leader_main_t0_training_sample`

唯一键：`trade_date + ts_code`

字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `strategy_version` | String(50) | 固定为 `leader_main_t0` |
| `trade_date` | String(10) | 选股日期 |
| `ts_code` | String(20) | 股票代码 |
| `name` | String(50) | 股票名称 |
| `limit_up_count_100d` | Integer | 100日涨停次数 |
| `seal_rate_100d` | Float | 100日封板率 |
| `rise_10d_pct` | Float | 10日涨幅 |
| `pre_change_pct` | Float | 昨涨幅 |
| `open_change_pct` | Float | 开盘涨幅 |
| `auction_ratio` | Float | 竞昨比 |
| `auction_turnover_rate` | Float | 竞价换手率 |
| `circ_mv` | Float | 流通市值，亿元 |
| `rule_score` | Float | 规则评分 |
| `label_t0_limit_success` | Integer | T+0 非一字涨停成功标签 |
| `t0_touched_limit` | Integer | 当日是否触板 |
| `t0_closed_limit` | Integer | 当日是否收盘涨停 |
| `is_one_line_limit_up` | Integer | 是否一字板 |
| `t0_high_return` | Float | 当日最高涨幅 |
| `t0_close_return` | Float | 当日收盘涨幅 |
| `t0_low_return` | Float | 当日最低涨幅 |
| `feature_json` | Text | 完整特征快照 |
| `created_at` | DateTime | 创建时间 |

### 6.3 扩展模型版本表

当前 `model_version` 已存在，应继续复用，但需要增强约束。

建议新增或写入 `params/model_metrics` 的内容：

| 字段 | 内容 |
|------|------|
| `model_name` | `leader_main_t0_lgbm` |
| `feature_cols` | 训练时真实使用的特征 JSON |
| `model_metrics` | AUC、accuracy、precision、recall、收益分层统计 |
| `params` | 模型参数、标签规则、样本范围、特征版本 |
| `is_active` | 同一模型名只能有一个 active |

重要约束：

- 预测必须读取当前 active 模型版本的 `feature_cols`。
- 不允许预测阶段使用硬编码全局特征列表。
- 模型文件路径和状态接口必须保持一致。

---

## 7. 服务设计

### 7.1 数据采集服务

建议新增：`backend/services/auction_data_service.py`

职责：

- 调用现有 Tushare 客户端，不重复创建新数据源。
- 拉取 `stk_auction_o`。
- 拉取同日 `daily_basic` 和前一交易日 `daily`。
- 计算 `auction_ratio`、`auction_turnover_rate`。
- upsert 到 `stock_auction_open`。

核心方法：

```python
sync_auction_open(trade_date: str) -> int
get_auction_features(trade_date: str, ts_code: str) -> dict
batch_get_auction_features(trade_date: str, ts_codes: list[str]) -> dict
```

### 7.2 龙头主升 T+0 特征构建服务

建议新增：`backend/services/backtest/leader_main_t0_feature_builder.py`

职责：

- 以交易日为单位构建龙头主升候选特征。
- 复刻“连板抱团・追强”T+0 候选条件。
- 输出候选股列表、剔除原因和完整特征。
- 不做训练，不做评分融合。

核心方法：

```python
build_leader_main_t0_features_for_date(trade_date: str) -> list[dict]
filter_leader_main_t0_candidates(features: list[dict], config: dict) -> list[dict]
build_leader_main_t0_range(start_date: str, end_date: str) -> int
```

### 7.3 标签生成服务

建议新增：`backend/services/backtest/leader_main_t0_label_builder.py`

职责：

- 根据 T 日行情生成 `label_t0_limit_success`。
- 识别触板、收盘涨停、一字板。
- 不使用 T 日结果参与候选特征。
- 标签只在训练前生成，最新交易日缺少完整收盘行情时不打标签。

核心方法：

```python
build_leader_main_t0_labels(start_date: str, end_date: str) -> int
```

### 7.4 模型训练服务

改造现有：`backend/services/model_engine/lightgbm_service.py`

第一阶段不删除旧接口，但新增模型口径。

建议模型名：

```text
leader_main_t0_lgbm
```

训练特征第一版：

```text
limit_up_streak
market_height_rank
limit_up_count_100d
seal_rate_100d
rise_5d_pct
rise_10d_pct
pre_change_pct
open_change_pct
auction_ratio
auction_turnover_rate
circ_mv
sector_change_pct
sector_limit_up_count
```

可选增强特征：

```text
auction_amount
auction_vwap_gap_pct
turnover_rate
volume_ratio
```

切分方式：

```text
70% 训练集
20% 验证集
10% 测试集
```

必须按交易日期切分，不能随机切分。

### 7.5 评分接入服务

接入原则：

- 没有 active 模型时，系统维持纯规则评分。
- 有 active 模型时，先在龙头主升候选股上计算 `t0_limit_success_prob`。
- 第一阶段 `t0_limit_success_prob` 只作为候选排序和展示，不直接覆盖原有 `final_score`。
- 列表页、详情页、V2评分必须使用同一融合口径。

如果回测验证通过，第二阶段可启用低权重融合：

```text
final_score = rule_score * 0.7 + t0_limit_success_prob * 0.3
```

原因：

- 当前模型初期样本有限，不宜直接给 40% 以上权重。
- 规则分仍然是主线，模型只做统计增强。

后续可根据回测结果调权。

---

## 8. 开发步骤

### 阶段 A：数据落库

目标：把 `stk_auction_o` 历史竞价数据稳定落库。

任务：

1. 新建 `StockAuctionOpen` ORM 模型。
2. 新建数据库表。
3. 实现 `AuctionDataService`。
4. 支持按单日同步。
5. 支持按日期区间同步。
6. 实现去重 upsert。
7. 编写单元测试覆盖公式和单位。

验收：

- 任意交易日可同步全市场开盘竞价数据。
- `auction_ratio` 和 `auction_turnover_rate` 与手工计算一致。
- 重复同步不会重复插入。

### 阶段 B：龙头主升 T+0 候选回测

目标：复刻龙头主升 T+0 非一字候选条件。

任务：

1. 构建交易日历。
2. 拉取并缓存日线、每日指标、涨停数据。
3. 构建 100 日涨停次数。
4. 构建 10 日涨幅。
5. 合并竞价指标。
6. 执行连板高度、非一字、换手、板块热点等过滤条件。
7. 输出 `leader_main_t0_training_sample` 特征样本。

验收：

- 可以指定 `start_date/end_date` 跑龙头主升 T+0 回测。
- 输出每个交易日的候选股和一字板剔除列表。
- 每只候选股都有完整字段和过滤原因。

### 阶段 C：标签生成

目标：给候选股生成 T+0 涨停成功标签。

任务：

1. 读取候选表。
2. 读取 T 日行情。
3. 计算当日触板、收盘涨停、一字板、最高涨幅、收盘涨幅。
4. 生成 `label_t0_limit_success`。
5. 保存标签。

验收：

- 标签生成过程不修改当日特征。
- 无完整 T 日收盘行情的最新交易日不打标签。
- 标签规则记录在模型参数或策略版本中。

### 阶段 D：LightGBM 训练

目标：训练龙头主升 T+0 非一字涨停成功率模型。

任务：

1. 新增 `leader_main_t0_lgbm` 训练入口。
2. 使用候选表和已生成标签的数据训练。
3. 使用日期 70/20/10 切分。
4. 保存模型、特征列、指标、参数。
5. 输出特征重要性。
6. 输出分数分层收益分析。

验收：

- 模型训练不使用未定义特征。
- 预测读取 `ModelVersion.feature_cols`。
- 模型指标保存到数据库。
- 测试集分层结果可查看。

### 阶段 E：接入评分

目标：把 T+0 成功率模型结果安全接入当前选股。

任务：

1. 当前龙头主升候选结果生成后调用模型预测。
2. 模型不存在或预测失败时降级为无模型排序。
3. 第一阶段只展示 `t0_limit_success_prob`，不覆盖原有 `final_score`。
4. 前端展示 T+0 成功率、模型版本和模型是否启用。
5. 记录每次选股使用的模型版本。

验收：

- 模型故障不影响选股主流程。
- 同一股票在列表和详情里分数口径一致。
- 能看到 T+0 成功率、规则分、最终分。

---

## 9. 测试计划

### 9.1 单元测试

必须覆盖：

- `auction_ratio` 单位计算。
- `auction_turnover_rate` 单位计算。
- `daily.vol` 手到股的转换。
- `float_share` 万股到股的转换。
- 缺少竞价数据时降级。
- 重复同步不重复入库。
- 一字板识别和剔除。
- `label_t0_limit_success` 生成。
- 预测使用模型版本特征列。
- 模型不存在时返回 `t0_limit_success_prob=None`。

### 9.2 回测一致性测试

抽取 3 到 5 个历史交易日：

- 手工计算竞昨比。
- 手工计算竞价换手率。
- 手工核对一字板剔除和 T+0 标签。
- 对比龙头主升 T+0 回测候选输出。

### 9.3 端到端测试

流程：

```text
同步竞价数据
  -> 构建龙头主升 T+0 候选
  -> 生成 T+0 标签
  -> 训练模型
  -> 激活模型
  -> 执行一次选股
  -> 查看列表与详情评分
```

验收：

- 全流程不报错。
- 没有模型时能正常降级。
- 有模型时能生成 `model_score`。

---

## 10. 风险与约束

### 10.1 权限和限流

`stk_auction_o` 单次最多返回一定数量记录。全市场长周期同步需要按交易日循环，必要时加限流和断点续传。

### 10.2 数据时间差

`stk_auction_o` 是盘后历史接口，不能替代实盘 MCP。

规则：

- 回测和训练用 `stk_auction_o`。
- 当日实盘选股用 MCP。
- 两者统一字段标准化和单位。

### 10.3 特征泄露

禁止在候选特征中使用 T 日收盘后才可见的信息。

尤其注意：

- 标签生成必须独立于特征构建。
- 龙头主升 T+0 候选生成不能使用当日 `daily.close`、当日最高价、当日最低价。
- 当日收盘、最高价、最低价只能用于标签生成和回测统计。

### 10.4 样本偏差

只训练候选股会得到“候选股二次排序模型”，不是全市场选股模型。第一版建议接受这个定位，因为它贴合当前系统。

### 10.5 评分污染

模型未验证前不得高权重接入最终评分。

建议：

- 第一阶段只展示 `model_score`，不参与最终分。
- 第二阶段回测通过后以 30% 权重接入。
- 第三阶段再根据实盘表现调整。

---

## 11. 推荐实施顺序

推荐按以下顺序推进：

1. **先做数据层**：`stk_auction_o` 同步、落库、公式校验。
2. **再做回测层**：复刻龙头主升 T+0 候选条件。
3. **再做标签层**：T+0 非一字涨停成功标签。
4. **再做模型层**：`leader_main_t0_lgbm` 训练、评估、版本化。
5. **最后接评分层**：先展示 T+0 成功率，再低权重融合。

不建议一开始就把模型直接接入 `final_score`，因为需要先确认回测收益分层和模型稳定性。

---

## 12. 第一版完成标准

第一版开发完成时，应满足：

- 可以同步指定日期范围内的 `stk_auction_o` 数据。
- 可以准确计算历史 `竞昨比` 和 `竞价换手率`。
- 可以完整回测龙头主升 T+0 候选条件。
- 可以生成 T+0 非一字涨停训练样本和标签。
- 可以训练 `leader_main_t0_lgbm`。
- 可以保存模型版本、特征列、测试指标。
- 当前选股在模型不可用时不受影响。
- 模型启用时，预测特征与训练特征完全一致。

---

## 13. 与现有系统的关系

现有模块复用关系：

| 需求 | 复用模块 |
|------|----------|
| Tushare 客户端 | `TushareDataCollector` 或现有 Tushare 初始化逻辑 |
| 交易日 | 现有 trading date 工具 |
| 日线数据 | `data_collector.get_daily_data()` 优先复用 |
| 每日指标 | `data_collector.get_daily_basic()` 优先复用 |
| 封板率 | `SealRateCalculator` |
| 规则评分 | `RuleScoreService` |
| V2评分融合 | `FinalScoreService` |
| 模型版本 | `ModelVersion` |
| 候选快照 | `StockFeatureSnapshot` 可保留，但回测建议新建候选表 |

原则：

- 不重复创建 Tushare 初始化逻辑。
- 不从历史选股结果回填新任务字段。
- 不用伪造竞价数据训练模型。
- 不让模型故障阻断选股主流程。
