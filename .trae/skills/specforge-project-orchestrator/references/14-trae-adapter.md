# 14 - Trae 适配器 (Trae Adapter)

## Purpose
从项目 specs 文档生成 Trae 原生配置（`.trae/rules.md` 和 `.trae/prompts/*.md`），让 AI 在 Trae IDE 中有完整的项目上下文和开发规范。

## When to use
- 项目 specs 文档完善后，首次生成 Trae 配置
- specs 有重大更新需要同步 Trae 配置
- 用户说"生成项目规则"、"生成 Trae rules"

## Required inputs
- `specs/` 下的项目文档（产品概述、技术栈、项目结构、开发规范）
- `specs/features/` 下的功能文档（如存在）
- 项目的实际代码结构

## Workflow

### 核心原则
Trae rules 和 prompts 必须来自当前项目的 specs 文档，不能凭空编造。每个规则都应该能在 specs 中找到依据。

### 生成 .trae/rules.md

从以下 spec 文档提取内容生成：

| 规则类别 | 来源 |
|---------|------|
| AI role | 从产品概述提取项目定位 |
| Source of truth | `specs/` 目录结构（所有项目文档） |
| Required context files | 从 PROJECT-CONTEXT.md 提取必读文档清单 |
| Context loading strategy | 分层加载策略（参考 01-context-protocol.md） |
| Development workflow | 项目生命周期（参考 02-project-lifecycle.md） |
| File modification boundaries | 从 GUARDRAILS.md 提取 |
| Requirements phase rules | 从 04-requirements.md 提取 |
| Design phase rules | 从 05-tech-stack.md、06-project-structure.md 提取 |
| Implementation phase rules | 从 07-dev-standards.md、08-feature-development.md 提取 |
| Testing rules | 从 08-feature-development.md 的 TDD 流程提取 |
| Documentation sync rules | 从 11-doc-sync.md 提取 |
| Git and commit rules | 从 07-dev-standards.md 的 Git 工作流提取 |
| Forbidden behaviors | 从 13-guardrails.md 提取 |
| Output format | 从 SKILL.md 的输出风格提取 |

格式参考：`assets/trae-rules-template.md`

### 生成 .trae/prompts/

从 workflow modules 提取，每个 prompt 对应一个常见开发任务：

| Prompt 文件 | 来源模块 |
|------------|---------|
| `project-intake.md` | `03-project-intake.md` |
| `create-feature.md` | `04-requirements.md` + feature 需求流程 |
| `implement-task.md` | `08-feature-development.md` 编码阶段 |
| `review-code.md` | `10-code-review.md` |
| `fix-bug.md` | `09-bug-fix.md` |
| `refactor-module.md` | `10-code-review.md` 重构视角 |
| `sync-docs.md` | `11-doc-sync.md` |
| `generate-tests.md` | `08-feature-development.md` TDD 流程 |

每个 prompt 必须包含：
- 任务目标
- 必读上下文（具体到文件路径）
- 执行步骤
- 文件修改边界
- 输出格式
- 验证要求
- 禁止行为

格式参考：`assets/trae-prompts-template.md`

### 维护
- specs 更新后，如果涉及开发流程或规范变化，同步更新 Trae 配置
- 不要手动在 Trae 配置中写入没有 spec 依据的规则
- 同步时对比差异，增量更新而非全量重写

## Output format

### .trae/rules.md
可直接用于 Trae IDE 的规则文件，包含 AI role、上下文策略、阶段规则、禁止行为等。

### .trae/prompts/*.md
可直接在 Trae 中使用的 prompt 模板，每个对应一个具体开发任务。

## Quality checklist
- [ ] 每条规则在 specs 中有依据
- [ ] 规则具体、可执行（不是"遵循最佳实践"）
- [ ] prompts 覆盖了常见开发任务
- [ ] prompts 的必读上下文指向真实文件路径

## Guardrails
- 不凭空编造不在 specs 中的规则
- 不把通用规则不经定制直接写入——Trae 配置是针对本项目生成的
- 不把 Trae 配置当作"真理源"——specs 才是唯一真理源

## Common mistakes to avoid
- 从其他项目复制粘贴规则，不根据当前项目 specs 定制
- 规则写得太大——"确保代码质量"没有意义，需要具体可执行规则
- 忘记同步——specs 更新了但 Trae 配置还是旧的
