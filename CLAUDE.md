# CLAUDE.md - 选股通知系统开发指南

## 项目概述

| 属性 | 值 |
|------|-----|
| **项目名称** | 选股通知系统 (Stock Selector Notification System) |
| **项目类型** | 量化选股 + 通知推送系统 |
| **当前版本** | v3.0 (三阶段选股架构已完成) |
| **最后更新** | 2026-04-27 |
| **项目成熟度** | ⭐⭐⭐⭐⭐ (5/5 星 - 生产就绪) |

---

## 通用开发指导原则

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## 项目特定开发规范

### 5. 三阶段选股架构规范

**严格分离原则**

| 阶段 | 允许调用 | 禁止调用 | 核心职责 |
|------|----------|----------|----------|
| 阶段1 (选股) | 通达信MCP | Tushare | 服务端筛选，一次查询完成 |
| 阶段2 (分析) | Tushare | 通达信MCP | 补充数据 + 昨涨幅/开涨幅计算 |
| 阶段3 (封板率) | Tushare | 通达信MCP | 触板天数/封板天数/封板率计算 |

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

### 7. 代码规范

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

### 8. 故障排查指南

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

**Q5: 测试覆盖率不达标?**
运行 `pytest tests/backend/ --cov=backend --cov-report=term-missing` 查看未覆盖的代码行。

**Q6: 封板率计算结果为空?**
检查Tushare接口是否返回了涨停价(up_limit)数据，部分股票可能没有涨跌停数据。

**Q7: 昨涨幅/开涨幅显示为空?**
检查阶段2是否正确获取了日线数据，确保有至少2天的交易数据。

---

## 开发工作流

### 9. 开发流程

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
feat(strategy): 实现涨停强度策略
fix(mcp): 修复数值格式问题
```

---

## 性能与安全

### 10. 性能规范

**API 性能**
- **Response Time**: 选股 API < 30 秒
- **Concurrent Requests**: 支持 10+ 并发请求
- **Pagination**: 列表接口必须分页

**数据库性能**
- **Indexing**: 常用查询字段必须添加索引
- **Query Optimization**: 避免 N+1 查询
- **Connection Pool**: 使用连接池

### 11. 安全规范

**敏感信息管理**
- **Environment Variables**: 使用 `.env` 文件 (不提交到 Git)
- **Secrets**: 使用环境变量或密钥管理服务
- **Logging**: 禁止记录敏感信息 (Token, 密码)

**API 安全**
- **Rate Limiting**: 实现请求限流
- **Input Validation**: Pydantic 严格验证
- **Error Handling**: 不暴露敏感错误信息

---

## 监控与维护

### 12. 监控指标

**Prometheus 指标**:
- `http_requests_total` (Counter)
- `http_request_duration_seconds` (Histogram)
- `http_requests_in_progress` (Gauge)

**健康检查**:
- `/api/v1/health` - 系统健康状态

### 13. 日志规范

**双格式输出**:
- `logs/xuangu.json` - JSON格式 (适合日志聚合工具)
- `logs/xuangu.log` - 人类可读格式

**日志轮转**: 10MB/文件, 5个备份

---

## 部署与运维

### 14. 部署架构

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

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

**Last Updated**: 2026-04-27  
**Maintainer**: AI Assistant  
**Version**: 5.0
