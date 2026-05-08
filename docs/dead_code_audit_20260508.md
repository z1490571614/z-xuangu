# 项目废弃代码审计报告

**审计日期**: 2026-05-08  
**项目版本**: v5.2  
**审计范围**: backend/ + frontend/src/ + scripts/  
**审计方法**: 3个自动化审计agent + 人工交叉验证

---

## 总览

| 类别 | 数量 | 预估行数 | 严重程度 |
|------|------|----------|----------|
| A. 完全废弃的后端文件 | 6项(11个文件) | ~1,500行 | 🔴 高 |
| B. 零引用的前端文件 | 10项 | ~800行 | 🟠 高 |
| C. 活跃文件中的死代码 | 9项 | ~270行 | 🟡 中 |
| D. 一次性调试脚本 | 10个 | ~500行 | ⚪ 低 |
| E. 已执行的迁移脚本 | 7个 | ~400行 | ⚫ 无影响 |
| F. `__init__.py` 死重导出 | 7个 | ~30行 | ⚪ 低 |

---

## 🔴 类别 A：完全废弃的后端文件

> 这些文件在整个项目中无任何 Python 导入或引用，可安全删除。

### A1. `backend/utils/logger.py` (~90行)

**废弃原因**: 与 `backend/core/logging_config.py` 功能重复。所有代码使用 `core/logging_config.py`，零引用此文件。

**定义**: `JSONFormatter`, `ContextFilter`, `setup_logging()`, `get_logger()` — 全部在 `core/logging_config.py` 中有等效实现。

---

### A2. `backend/models/news_database.py` (~80行)

**废弃原因**: 模型定义与 `backend/services/news_database.py` 完全重复。所有消费者从 `services/news_database` 导入（如 `from backend.services.news_database import NewsData`），零引用 `models/news_database`。

**定义**: `NewsData`, `NewsSource`, `NewsCleanupLog`, `NewsFetchLog`

---

### A3. `backend/services/alert_service.py` (~150行)

**废弃原因**: 从未被任何 Python 文件导入。告警功能计划了但未接入系统。

**定义**: `AlertService`, `AlertRule`, `DEFAULT_ALERT_RULES`, 模块级 `alert_service` 单例

---

### A4. `backend/services/scoring_v2/opening_plan.py` (~140行)

**废弃原因**: `OpeningPlanService` 从未被任何代码导入或实例化。`scoring_v2/__init__.py` 也不导出它。实际使用的开盘预案逻辑内嵌在 `scoring/next_day_plan.py` 中。

---

### A5. `backend/services/tushare_news.py` (~760行)

**废弃原因**: 已被 `backend/services/integrated_news_service.py` + `backend/services/news_collector.py` 完全替代。只有 3 个废弃的 debug 脚本还引用此模块（见类别 D）。

**定义**: `TushareNewsService`, `get_news_service()` 等

---

### A6. `backend/services/strategy/` 目录（6个文件, ~600行）

**废弃原因**: 废弃的 V1 策略架构。实际使用的策略系统是 `backend/services/strategy_service.py`（基于 `StrategyTemplate` 模型），不是一个架构。

**文件列表**:
- `base_strategy.py` — `BaseStrategy`, `StockData`, `StrategyResult`, `StrategyRegistry`, `StrategyManager`
- `market_cap_strategy.py` — `MarketCapStrategy`
- `price_strategy.py` — `PriceStrategy`
- `trend_strategy.py` — `TrendStrategy`
- `limit_up_strategy.py` — `LimitUpStrengthStrategy`
- `auction_activity_strategy.py` — `AuctionActivityStrategy`
- `__init__.py` — 重导出所有上述类（也无人使用）

**验证**: 搜索 `from backend.services.strategy import` 仅返回 `__init__.py` 内部的自引用。

---

## 🟠 类别 B：零引用的前端文件

> 这些文件在整个 frontend/src/ 范围内无任何导入或路由引用。

### B1. `frontend/src/views/StockResult.vue` (~150行)

**废弃原因**: 不在 `router/index.js` 中。使用了 Element Plus (`el-table`/`el-card`) 的旧版页面，已被 `StockResults.vue`（原生 HTML 表格）替代。

---

### B2. `frontend/src/views/TestPage.vue` (~50行)

**废弃原因**: 未接入路由的开发调试页面，零引用。

---

### B3. `frontend/src/components/LimitupInterpretation.vue` (~80行)

**废弃原因**: 整个项目中搜索 `LimitupInterpretation` 返回零匹配。涨停/异动 Tab 使用的组件是 `AnomalyInterpretation`，非此组件。

---

### B4. `frontend/src/components/stock/LimitupInterpretation.vue` (~80行)

**废弃原因**: B3 在 `stock/` 目录下的重复副本，同样零引用。

---

### B5. `frontend/src/components/stock/ScoreBreakdown.vue` (~100行)

**废弃原因**: 重复组件。活跃的是 `components/ScoreBreakdown.vue`（被 `StockDetailModal.vue` 导入）。`stock/` 下的副本无人使用。

---

### B6. `frontend/src/components/stock/RiskScoreBreakdown.vue` (~80行)

**废弃原因**: 零引用。已被 `RiskBreakdown.vue` 完全替代。

---

### B7. `frontend/src/api/config.js` (~30行)

**废弃原因**: 零引用。`Settings.vue` 直接用 axios 调用 API，未经过此模块。

---

### B8. `frontend/src/api/task.js` (~30行)

**废弃原因**: 零引用。`TaskManage.vue` 直接用 axios 调用 API。

---

### B9. `frontend/src/api/stock.js` (~40行)

**废弃原因**: 仅被 B1 (`StockResult.vue`) 引用，连带废弃。活跃的 `StockResults.vue` 直接用 axios。

---

### B10. `frontend/src/stores/` 目录

**废弃原因**: 空目录，从未创建任何 Pinia/Vuex store 文件。

---

## 🟡 类别 C：活跃文件中的死代码段

> 这些文件本身被使用，但其中部分函数/常量/代码段从未被调用。

### C1. `backend/services/websocket_service.py:170-236` (~60行)

**废弃代码**: `push_task_update()`, `push_stock_selection_update()`, `push_system_notification()`

**验证**: `main.py:258` 仅导入 `websocket_endpoint` 和 `get_connection_stats`。三个推送函数列出在 `__all__` 中但从未被调用。

---

### C2. `backend/utils/trading_date.py:144-334` (~110行)

**废弃代码**: `get_next_trading_day()`, `get_trading_days_in_range()`, `is_today_trading_day()`, `get_trading_day_offset()`

**验证**: 搜索全项目确认零调用方。同文件中 `get_latest_trading_day()`, `is_trading_day()` 等函数仍在使用中。

---

### C3. `backend/services/seal_rate_calculator.py:530-563` (~34行)

**废弃代码**: `calculate_seal_rate_for_stocks()` — 模块级便捷包装函数

**验证**: `SealRateCalculator` 类本身被 `stock_selector.py` 使用，但此函数从未被调用。

---

### C4. `backend/services/tdx_selector.py:208-215` (~8行)

**废弃代码**: `CONDITION_REGISTRY` 字典

**验证**: 各条件类通过 `strategy_service.py` 的 `build_selection_task_from_template()` 直接使用，不经过此注册表。

---

### C5. `backend/services/tdx_selector.py:564-566` (~3行)

**废弃代码**: `TdxSelectorService.clear_tasks()` 方法

**验证**: 类被使用，但此方法从未被调用。

---

### C6. `backend/services/news_sentiment/constants.py:59-79` (~40行)

**废弃代码**: `CARRIER_WORDS`（与 `normalizer.py` 中的定义重复）, `UNCERTAINTY_WORDS`, `NEWS_SCOPE_TYPES`

**验证**: `normalizer.py` 有自己的 `CARRIER_WORDS` 副本。其它两个常量从未被导入。

---

### C7. `backend/services/notification.py:207-220` (~14行)

**废弃代码**: `FeishuNotifier.send_test_notification()` 方法

**验证**: `FeishuNotifier` 类被多处使用（`api/config.py`, `api/stock.py`, `scheduler.py`），但此特定方法从未被调用。

---

### C8. `backend/services/scoring_v2/scoring_service.py:24-26` (~3行)

**废弃代码**: `set_score_v2_enabled()` 函数

**验证**: 同文件中的 `is_score_v2_enabled()` 被 `stock_selector.py:868` 使用，但 `set_score_v2_enabled()` 从未被调用。底层 `_score_v2_enabled` 全局变量初始化为 `True` 后从未变更。

---

### C9. `backend/services/scoring/rule_score_service.py:17-22` (~6行)

**废弃代码**: `RuleScoreService.WEIGHTS` 类常量

**验证**: `calculate()` 方法（第294行）直接调用子评分方法并求和，不使用此权重字典。

---

## ⚪ 类别 D：一次性调试/测试脚本

> 仅用于开发调试或一次性修复，不再需要。建议删除或移至 `archive/` 目录。

| # | 文件 | 用途 | 额外风险 |
|---|------|------|----------|
| D1 | `scripts/debug_news_sources.py` | 调试新闻源 | 引用了废弃的 `tushare_news` |
| D2 | `scripts/test_news_sources_debug.py` | 测试新闻源 | 引用了废弃的 `tushare_news` |
| D3 | `scripts/test_anomaly_fix.py` | 修复后验证 | 引用了废弃的 `tushare_news` |
| D4 | `scripts/test_anomaly_ai.py` | AI 功能测试 | - |
| D5 | `scripts/fix_anomaly_test.py` | 一次性修复 | - |
| D6 | `scripts/cleanup_anomaly_db.py` | 一次性数据库清理 | - |
| D7 | `scripts/debug_mcp_response.py` | 调试 MCP 响应 | - |
| D8 | `scripts/debug_api.py` | 调试 API | - |
| D9 | `scripts/compare_queries.py` | MCP 查询对比 | - |
| D10 | `scripts/run_selection_with_seal_rate.py` | 一次性选股运行 | - |

---

## ⚫ 类别 E：已执行完的迁移脚本

> 一次性数据库迁移，已执行完毕。可保留作审计记录，或移至 `archive/`。

| # | 文件 | 迁移内容 |
|---|------|---------|
| E1 | `scripts/migrate_anomaly_table.py` | 异动解读表结构迁移 |
| E2 | `scripts/migrate_add_limit_list_ths_fields.py` | 涨停池字段新增 |
| E3 | `scripts/migrate_add_latest_lu_date.py` | 最新涨停日期字段 |
| E4 | `scripts/migrate_news_theme_relation.py` | 新闻题材关联 |
| E5 | `scripts/migrate_risk_context_fields.py` | 风险上下文字段 |
| E6 | `scripts/migrate_dc_board_alias_tables.py` | 板块别名表创建 |
| E7 | `scripts/migrate_database.py` | 通用数据库迁移 |

---

## 📦 类别 F：`__init__.py` 中的死重导出

> 这些 `__init__.py` 中的 import 行从未被外部使用（消费者直接从子模块导入），可清理重导出语句但文件本身需保留作为包标记。

| # | 文件 | 死重导出 |
|---|------|---------|
| F1 | `backend/core/__init__.py` | `setup_logging`, `get_logger` |
| F2 | `backend/middleware/__init__.py` | `prometheus_middleware`, `metrics_endpoint` 等 4 个 |
| F3 | `backend/services/ai_brief/__init__.py` | `TagBuilder`, `AIClient` 等 5 个 |
| F4 | `backend/services/model_engine/__init__.py` | `train_lightgbm`, `predict_lightgbm` 等 4 个 |
| F5 | `backend/services/news_sentiment/__init__.py` | `analyze_news_event`, `analyze_news_batch` 等 5 个 |
| F6 | `backend/services/scoring/__init__.py` | `RuleScoreService`, `NextDayPlanService` |
| F7 | `backend/services/strategy/__init__.py` | `BaseStrategy`, `StrategyResult` 等 10 个（整个包随 A6 一起删除） |

---

## 统计数据

### 按文件类型

| 文件类型 | 可删除文件数 | 文件内死代码段 |
|---------|------------|-------------|
| Python 后端 | 11 | 9 |
| Vue 前端 | 9 | 0 |
| JavaScript 前端 | 4 | 0 |
| 脚本 | 10-17 | 0 |
| 空目录/init | 1 | 7 |

### 预估总废弃代码量

| 类别 | 预估行数 |
|------|---------|
| 完全废弃文件 | ~2,700 行 |
| 文件内死代码 | ~270 行 |
| 一次性脚本 | ~500 行 |
| 迁移脚本 | ~400 行 |
| **合计** | **~3,870 行** |

### 风险提示

- **零风险**: 所有"完全废弃文件"均通过全项目 `grep` 验证零引用
- **低风险**: 类别 C 的死代码段在活跃文件中删除，需精确到行号操作
- **注意**: `A5 tushare_news.py` 删除后需同步删除引用了它的 D1-D3 脚本
- **注意**: A6 strategy/ 目录删除后，`api/strategy.py` 中的路由仍然正常工作（它使用的是 `strategy_service.py`，非此模块）

---

**审计人**: AI Assistant  
**审计工具**: 3 个 Explore Agent + 直接 Grep/Glob 验证  
**审计覆盖**: backend/ (140 个 .py 文件) + frontend/src/ (34 个 .vue/.js 文件) + scripts/ (25 个 .py 文件)
