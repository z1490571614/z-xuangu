# Tushare 数据接口使用规则

当用户提出要从 Tushare 获取数据的需求时，按以下步骤操作：

## 步骤

1. **查接口目录** → 先打开 `h:\project_development\xuangu\.trae\skills\tushare\references\数据接口.md`，根据用户描述的数据需求（如行情、财务、资金流向等），找到对应的接口名称（如 `daily_basic`、`moneyflow`、`income` 等）

2. **查接口文档** → 然后在 `h:\project_development\xuangu\.trae\skills\tushare\references\api_docs\` 目录下找到对应接口的文档（如 `daily_basic.md`），参考其中的 **输入参数**、**输出参数** 和 **接口用法（Python 示例）** 来编写代码

## 示例

用户需求："获取股票每日基本面指标"

1. 打开 [数据接口.md](file:///h:/project_development/xuangu/.trae/skills/tushare/references/数据接口.md) → 找到 `daily_basic`（每日指标）接口
2. 打开 [daily_basic.md](file:///h:/project_development/xuangu/.trae/skills/tushare/references/api_docs/daily_basic.md) → 参考 Python 示例：

```python
pro = ts.pro_api()
df = pro.daily_basic(ts_code='', trade_date='20180726', fields='ts_code,trade_date,turnover_rate,volume_ratio,pe,pb')
```
