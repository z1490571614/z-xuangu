# 🚀 选股通知系统 - 一键开发指南

## ⚠️ 重要说明

**本文档是 Phase 1 的 AI 一键开发入口。**
**Phase 1 完成后，AI 将自动生成 Phase 2 的一键开发文档。**

---

## 🎯 Phase 1: MVP 版本（一键开发）

### 🎯 开发目标

完成选股通知系统的 MVP 版本，包括：
- ✅ 后端 API 服务（FastAPI）
- ✅ 多策略选股引擎
- ✅ 飞书通知服务
- ✅ 定时任务调度
- ✅ 前端管理界面
- ✅ 直接部署 (Supervisor + Nginx)

### 📂 项目结构

```
xuangu/
├── backend/              # FastAPI 后端
├── frontend/             # Vue 3 前端
├── monitoring/           # Prometheus + Grafana 配置
├── data/                 # SQLite 数据库
├── logs/                 # 日志目录 (JSON+人类可读)
├── docs/                 # 文档目录
└── requirements.txt
```

### 🚀 一键开发命令

在 Trae AI 中新建对话，复制以下**完整提示词**：

---

```
# 🎯 Phase 1: MVP 版本开发

## 项目信息
- 项目名称: 选股通知系统
- 技术栈: FastAPI + Vue 3 + SQLite + Tushare
- 端口: 9999
- 核心功能: 多策略选股 + 飞书通知 + 定时任务

## 📚 参考文档（必须阅读）
1. 系统架构: /AGENTS.md
2. 开发指南: /CLAUDE.md
3. 技术方案: /docs/development.md
4. 项目规范: /.trae/rules/project_rules.md

## 🛠️ Skills 调用说明

本项目使用 Trae Skills 体系，按以下顺序调用：

| 阶段 | Skill | 作用 |
|------|-------|------|
| 后端-P1 | 05_Backend_Python | FastAPI 框架搭建 |
| 后端-P2 | 05_Backend_Database | SQLAlchemy 数据库设计 |
| 后端-P3 | 05_Backend_Python | 业务逻辑实现 |
| 前端-P1 | 02_Designer_UIUXIntelligence | UI/UX 设计 |
| 前端-P2 | 02_Designer_FrontendImplementation | Vue 3 实现 |
| 前端-P3 | 02_Designer_WebGuidelines | 代码规范检查 |
| 测试 | 04_Tester_BrowserAutomation | 自动化测试 |
| 部署 | 05_DevOps_GitOps | Supervisor + Nginx 直接部署 |

### Skill 调用示例

每个开发步骤开始前，先调用对应的 Skill：

```
# Step 1: 项目初始化 - 调用 05_Backend_Python
请使用 05_Backend_Python Skill 初始化 FastAPI 项目...

# Step 2: 数据库设计 - 调用 05_Backend_Database
请使用 05_Backend_Database Skill 设计数据库...

# 依此类推...
```

## 🎯 开发任务（按顺序执行）

### Step 1: 项目初始化 → 调用 Skill: 05_Backend_Python
1. 创建目录结构: backend/, frontend/, data/, logs/
2. 创建 requirements.txt (FastAPI, SQLAlchemy, Tushare, APScheduler, httpx 等)
3. 配置 Supervisor 和 Nginx
4. 创建 .env.example 文件
5. 初始化 Git 仓库

### Step 2: 后端 - 数据库设计 → 调用 Skill: 05_Backend_Database
1. 创建 backend/database.py (SQLAlchemy 连接)
2. 创建 backend/models/ 目录
3. 创建以下 ORM 模型:
   - SelectionRecord (选股记录)
   - SelectedStock (股票详情)
   - TaskLog (任务日志)
   - SystemConfig (系统配置)
   - ScheduledTask (定时任务)
4. 添加必要的索引

### Step 3: 后端 - 数据采集层 → 调用 Skill: 05_Backend_Python
1. 创建 backend/services/data_collector.py
2. 实现 TushareDataCollector 类:
   - get_stock_basic() - 股票基础信息
   - get_daily_data() - 日线行情
   - get_limit_list() - 涨跌停数据
   - is_trading_day() - 交易日判断
3. 创建 backend/utils/trading_date.py (交易日工具函数)

### Step 4: 后端 - 选股引擎 → 调用 Skill: 05_Backend_Python
1. 创建 backend/services/strategy/ 目录
2. 创建策略基类 base_strategy.py:
   - BaseStrategy (抽象基类)
   - StrategyResult (结果数据类)
   - StockData (股票数据类)
   - StrategyRegistry (注册表)
   - StrategyManager (管理器)
3. 创建具体策略:
   - market_cap_strategy.py (市值策略)
   - price_strategy.py (价格策略)
   - trend_strategy.py (趋势策略)
   - limit_up_strategy.py (涨停强度策略)
   - auction_activity_strategy.py (竞价活跃度策略)
4. 创建主选股函数 select_stocks()

### Step 5: 后端 - 任务调度 → 调用 Skill: 05_Backend_Python
1. 创建 backend/services/scheduler.py
2. 实现 TaskScheduler 类
3. 配置 APScheduler 定时任务
4. 实现交易日自动判断
5. 配置 Cron: "25 9 * * 1-5" (每个交易日9:25)

### Step 6: 后端 - 通知服务 → 调用 Skill: 05_Backend_Python
1. 创建 backend/services/notification.py
2. 实现 FeishuNotifier 类
3. 构建富文本卡片消息
4. 实现异步发送和重试机制

### Step 7: 后端 - API 接口 → 调用 Skill: 05_Backend_Python
1. 创建 backend/schemas/ (Pydantic 模型)
2. 创建统一响应格式
3. 创建 backend/api/ 路由:
   - stock.py (选股 API)
   - task.py (任务 API)
   - config.py (配置 API)
4. 实现以下接口:
   - POST /api/v1/stock/select
   - GET /api/v1/stock/results
   - GET /api/v1/stock/results/{id}
   - GET /api/v1/tasks
   - POST /api/v1/tasks
   - PUT /api/v1/tasks/{id}
   - DELETE /api/v1/tasks/{id}
   - GET /api/v1/config
   - PUT /api/v1/config/{key}
   - POST /api/v1/config/test-notification
   - GET /api/v1/health
5. 添加 Swagger 文档注释

### Step 8: 前端 - UI/UX 设计 → 调用 Skill: 02_Designer_UIUXIntelligence
1. 参考 /docs/development.md 第7章前端界面设计
2. 设计 Dashboard 首页布局
3. 设计选股结果表格
4. 设计任务管理表单
5. 设计系统设置页面

### Step 9: 前端 - 项目搭建 → 调用 Skill: 02_Designer_FrontendImplementation
1. 使用 Vite 创建 Vue 3 项目
2. 安装依赖: Element Plus, Pinia, Axios
3. 配置项目结构:
   - src/views/ (页面)
   - src/components/ (组件)
   - src/api/ (API 调用)
   - src/stores/ (状态管理)

### Step 10: 前端 - 页面开发 → 调用 Skill: 02_Designer_FrontendImplementation
1. 创建 src/views/Dashboard.vue (首页仪表盘)
2. 创建 src/views/StockResult.vue (选股结果页)
3. 创建 src/views/TaskManage.vue (任务管理页)
4. 创建 src/views/Settings.vue (系统设置页)
5. 创建公共组件:
   - src/components/StockTable.vue
   - src/components/TaskCard.vue
   - src/components/StatCard.vue

### Step 11: 前端 - API 对接 → 调用 Skill: 02_Designer_FrontendImplementation
1. 创建 src/api/index.js (Axios 实例)
2. 创建 src/api/stock.js (选股 API)
3. 创建 src/api/task.js (任务 API)
4. 创建 src/stores/stock.js (Pinia Store)
5. 对接所有后端 API

### Step 12: 前端 - 规范检查 → 调用 Skill: 02_Designer_WebGuidelines
1. 检查 Vue 3 Composition API 使用
2. 检查 Element Plus 组件规范
3. 检查响应式布局
4. 检查性能优化

### Step 13: 测试 → 调用 Skill: 04_Tester_BrowserAutomation
1. 创建 tests/ 目录
2. 编写后端单元测试 (pytest)
3. 编写 API 集成测试
4. 编写前端 E2E 测试
5. 运行测试确保通过

### Step 14: 部署 → 调用 Skill: 05_DevOps_GitOps
1. 配置 Supervisor 进程管理
2. 配置 Nginx 反向代理
3. 验证服务正常运行
4. 更新 /docs/development.md 标记完成状态

## ⚠️ 重要约束

1. **代码规范**: 必须遵循 /.trae/rules/project_rules.md
2. **类型注解**: 所有 Python 代码必须添加类型注解
3. **异常处理**: 所有 API 必须有异常处理
4. **敏感信息**: 禁止硬编码，使用环境变量
5. **API 文档**: 必须添加 Swagger 注释

## 📝 完成后任务

完成 Phase 1 后，必须执行以下任务：

### 1. 更新开发进度

**更新 /AGENTS.md：**
- Phase 1 状态改为 ✅ 完成
- Phase 2 状态改为 ⏳ 待开始
- 更新"开发进度"章节中的 Milestone 完成状态
- 更新"核心模块说明"章节（如果接口有变化）
- 更新"数据流"章节（如果执行流程有变化）

**更新 /CLAUDE.md：**
- Phase 1 MVP 版本进度全部改为 ✅ 完成
- 更新"核心技术细节"章节中的代码示例（如有变化）
- 更新"开发规范"章节（如有变化）
- 添加 Phase 1 完成后的经验总结

### 2. 生成 Phase 2 一键开发文档

在 /docs/ 创建 phase2_backtest.md，包含：
- Phase 2 (回测系统) 的完整开发任务
- 所有技术细节和代码示例
- 一键开发提示词
- 包含对应的 Skills 调用说明

### 3. 提交代码

遵循 Conventional Commits 规范提交所有代码

### 4. 文档同步检查清单

```
□ /AGENTS.md - 开发进度已更新
□ /AGENTS.md - 核心模块说明与代码一致
□ /CLAUDE.md - Phase 1 进度已更新
□ /CLAUDE.md - 代码示例已验证
□ /docs/development.md - 功能状态已标记
□ /README.md - 如有变化需同步更新
```

## 🎉 验收标准

1. ✅ 后端服务正常运行
2. ✅ API 文档可访问 (http://localhost:9999/docs)
3. ✅ 前端页面正常显示
4. ✅ 选股功能正常工作
5. ✅ 飞书通知正常发送
6. ✅ 定时任务正常执行
7. ✅ 所有测试通过

## 🚀 开始开发

请严格按照以上任务顺序执行，调用对应的 Skills 完成开发。完成后生成 Phase 2 文档。
```

---

## 🛠️ Skills 速查表

| Skill | 用于步骤 | 官方文档 |
|-------|----------|---------|
| `05_Backend_Python` | 1, 3, 4, 5, 6, 7 | `.trae/skills/05_Backend_Python/SKILL.md` |
| `05_Backend_Database` | 2 | `.trae/skills/05_Backend_Database/SKILL.md` |
| `02_Designer_UIUXIntelligence` | 8 | `.trae/skills/02_Designer_UIUXIntelligence/SKILL.md` |
| `02_Designer_FrontendImplementation` | 9, 10, 11 | `.trae/skills/02_Designer_FrontendImplementation/SKILL.md` |
| `02_Designer_WebGuidelines` | 12 | `.trae/skills/02_Designer_WebGuidelines/SKILL.md` |
| `04_Tester_BrowserAutomation` | 13 | `.trae/skills/04_Tester_BrowserAutomation/SKILL.md` |
| `05_DevOps_GitOps` | 14 | `.trae/skills/05_DevOps_GitOps/SKILL.md` |

---

## 📋 当前开发状态

| 阶段 | 状态 | 一键开发文档 |
|------|------|-------------|
| **Phase 1** | ✅ 已完成 | 本文档 |
| **Phase 2** | ⏳ 待开始 | /docs/phase2_backtest.md |
| **Phase 3** | ⏳ 待开始 | Phase 2 完成后自动生成 |
| **Phase 4** | ⏳ 待开始 | Phase 3 完成后自动生成 |
| **Phase 5** | ⏳ 待开始 | Phase 4 完成后自动生成 |
| **Phase 6** | ⏳ 待开始 | Phase 5 完成后自动生成 |

---

**🎯 开始开发**: 复制上面的完整提示词到 Trae AI 新建对话即可。
