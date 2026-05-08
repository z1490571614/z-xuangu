# CLAUDE.md - 选股通知系统开发指南

## 项目概述

| 属性 | 值 |
|------|-----|
| **项目名称** | 选股通知系统 (Stock Selector Notification System) |
| **项目类型** | 量化选股 + AI分析 + 通知推送系统 |
| **当前版本** | v5.0 (四阶段选股 + AI分析 + 新闻舆情 + 龙虎榜 + 风险拆解已完成) |
| **最后更新** | 2026-04-30 |
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

### 11. 龙虎榜模块开发规范

**模块位置**
- 核心服务: `backend/services/lhb_service.py`
- 数据模型: `backend/models/stock_lhb.py`
- 前端组件: `frontend/src/components/stock/LhbPanel.vue`

**数据接口**（Tushare，需15000积分全可用）:
| 接口 | 用途 | 最低积分 |
|------|------|---------|
| `top_list` | 龙虎榜每日明细（上榜日、涨幅、成交额、净买入） | 2000 |
| `top_inst` | 席位买卖明细（营业部、买入额、卖出额、净买额） | 5000 |
| `hm_list` | 游资名录（用于营业部→游资别名匹配） | 5000 |

**席位标签规则**（纯规则匹配 20+条）:
- `机构专用` → 机构
- `沪股通专用` / `深股通专用` → 北向
- `华泰证券深圳益田路` / `中信证券杭州延安路` → 一线游资
- `华泰证券成都南一环路` / `长城证券仙桃钱沟路` → 核按钮
- `东方财富证券拉萨团结路` / `东方财富证券拉萨东环路` → 散户

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

| 维度 | 权重 | 数据源 | 所需积分 |
|------|------|--------|---------|
| 行情风险 | 4分 | Tushare `daily_basic(turnover_rate)` + `daily(high/low/pre_close)` — 昨日数据 | 2000 |
| 筹码风险 | 18分 | Tushare `cyq_perf(winner_rate)` + `rise_10d_pct` | 5000 |
| 公告风险 | 25分 | `integrated_news_service` 新闻关键词匹配（减持/立案/亏损等） | 0 |
| 资金风险 | 20分 | Tushare `moneyflow(net_mf_amount)` | 2000 |
| 舆情风险 | 10分 | `SentimentAnalyzer` 利空新闻计数 | 0 |
| 龙虎风险 | 13分 | `lhb_service(risk_tips/action_tag)` | 已有 |
| 行业风险 | 10分 | Tushare `ths_daily(板块行情)` | 6000 |

**等级判定**:
```
≤20 低 / ≤40 中 / ≤70 高 / >70 极高
```

### 13. 代码规范

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

### 14. 故障排查指南

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
检查 `sentiment_analyzer.py` 中的关键词库是否覆盖了相关场景。情感分析在查询时实时计算，修改规则后刷新即可生效，无需回填数据。

**Q7: 龙虎榜缓存不生效?**
首次调 Tushare API 取数成功后自动写入 `stock_lhb` 表，后续请求优先读 DB。如需强制刷新，传 `force_refresh=true` 参数。

**Q8: 风险拆解得分异常?**
检查各维度的输入数据是否完整：
- 行情风险：需 `daily_basic` 和 `daily` 接口权限
- 筹码风险：需 `cyq_perf` 接口（5000积分）
- 资金风险：需 `moneyflow` 接口（2000积分）
- 行业风险：需 `ths_daily` 接口（6000积分）
- 公告/舆情/龙虎：复用已有模块

**Q9: 龙虎榜买入/卖出金额为0?**
Tushare `top_inst` 接口可能需要5000积分，积分不足时返回空数据。此时系统会降级使用 `top_list` 的汇总数据。

**Q10: 游资别名不显示?**
需要调用 Tushare `hm_list` 接口（5000积分）建立营业部→游资映射。首次调用后缓存，重启服务后重新加载。

---

## 开发工作流

### 15. 开发流程

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
```

---

## 性能与安全

### 16. 性能规范

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
- 纯规则引擎，无AI依赖
- 关键词匹配 + 正则，单条新闻 < 1ms
- 在新闻查询时实时计算，不影响预加载速度

**龙虎榜性能**
- DB缓存优先：首次API拉取后写入 `stock_lhb` 表，后续读DB ~20ms
- 预加载：选股完成后后台批量拉取（5线程），不阻塞选股流程

**风险拆解性能**
- 纯规则计算，无AI耗时
- 7维度并行数据采集，单只股票 < 2秒
- 预加载：选股完成后后台批量计算，不阻塞选股流程

### 17. 安全规范

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

### 18. 监控指标

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
- 各情感类别分布（positive/negative/neutral 比例）
- 情感分析平均耗时

### 19. 日志规范

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
- 记录匹配的关键词和权重
- 记录最终判定结果

---

## 部署与运维

### 20. 部署架构

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

**Last Updated**: 2026-04-30  
**Maintainer**: AI Assistant  
**Version**: 7.0
