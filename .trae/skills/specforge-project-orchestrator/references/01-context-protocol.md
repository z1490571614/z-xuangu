# 01 - 上下文加载协议 (Context Protocol)

## Purpose
定义分层上下文加载策略，避免每次对话都读取所有文件导致上下文爆炸。目标是用最少的信息建立足够的项目认知。

## When to use
每次新对话开始、每次 Skill 切换、每次加载新 workflow module 时使用。

## Required inputs
- `project-status.json`（读取当前阶段）
- 用户意图（决定加载层级）

## Context loading levels

### Level 1：项目全局认知（始终加载）
**文件**：
- `project-status.json` — 当前阶段、活跃功能、已完成阶段
- `specs/PROJECT-CONTEXT.md` — 项目概述、技术栈摘要、目录结构摘要

**目的**：让 AI 知道"这是什么项目、现在处于什么阶段"。

**加载时机**：每次对话开始时必须加载。

### Level 2：按任务域加载
根据用户意图类型，加载对应的核心 specs：

| 意图 | 加载文件 |
|------|---------|
| 功能开发 / 迭代 | `specs/产品概述.md`、`specs/技术栈.md`、`specs/开发规范.md`、`specs/项目结构.md` |
| 技术咨询 / 选型 | `specs/产品概述.md`、`specs/技术栈.md` |
| 代码审查 | `specs/开发规范.md`、`specs/项目结构.md` |
| 文档同步 | 扫描 `specs/` 下所有文件名，判断需要同步的范围 |
| Bug 修复 | 搜索相关 feature 文档和代码文件 |

**目的**：让 AI 知道"项目用什么技术、有什么规范、代码在哪"。

**加载时机**：用户意图确定后，进入对应 workflow module 之前。

### Level 3：当前任务上下文
根据任务需要，加载具体的 feature 文档和代码文件：

| 任务类型 | 加载文件 |
|---------|---------|
| 功能需求澄清 | 不加载（从零对话） |
| 功能技术设计 | `specs/features/{功能名}.md`（需求文档） |
| 功能任务规划 | 需求文档 + `specs/features/{功能名}_技术方案.md` |
| 功能编码实现 | 需求文档 + 技术方案 + `specs/features/{功能名}_任务规划.md` |
| 功能迭代 | 需求文档 + 技术方案 + 任务规划（如存在） |
| Bug 修复 | 相关 feature 文档 + 相关代码文件 |

**目的**：让 AI 知道"当前这个任务具体要做什么"。

### 全局加载例外
只在以下情况允许加载所有相关功能文档：
- 用户要求全局审计
- 文档同步时扫描整个 `specs/` 目录
- 路线图重估
- 用户明确要求"把所有文档读一遍"

## Workflow

1. **Level 1 强制加载**：读取 `project-status.json` 和 `specs/PROJECT-CONTEXT.md`
2. **判断 Level 2 需求**：根据意图类型决定是否加载 `specs/` 下的核心文档
3. **按需 Level 3**：进入具体任务后，加载对应的 feature 文档和代码

## Guardrails
- 不每次都读取所有文件——上下文是有限资源
- 如果 `project-status.json` 不存在（新项目），直接走项目接入流程
- Level 2 和 Level 3 之间可以跳过——如果意图不需要加载核心 specs（如单纯的进度查询），只加载 Level 1
- 发现关键信息缺失时，补充加载，而不是继续用不完整的信息工作

## Common mistakes to avoid
- "我先读取所有 specs/ 下的文档再开始"——除非用户要求全局审计
- 跳过 Level 1 直接开始干活——不建立项目认知就开始，容易出错
- 在不需要技术知识的对话中加载技术文档——浪费上下文
