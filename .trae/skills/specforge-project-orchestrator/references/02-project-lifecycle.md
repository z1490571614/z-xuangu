# 02 - 项目生命周期 (Project Lifecycle)

## Purpose
定义项目的完整生命周期阶段。每个阶段有明确的输入、输出和边界，确保开发流程可控、可追溯。

## When to use
- 新项目启动时（依次推进各阶段）
- 检查当前项目进度时
- 用户询问"接下来做什么"时
- 阶段推进/回退时

## Required inputs
- `project-status.json`（如有）
- 用户意图

## 项目阶段定义

```
intake (项目接入)
  ↓
product-overview (产品概述)
  ↓
requirements (需求澄清)
  ↓
tech-stack (技术栈选型)
  ↓
project-structure (目录结构设计)
  ↓
dev-standards (开发规范制定)
  ↓
planning (路线图规划)
  ↓
implementation (编码实现) ←→ testing (测试)
  ↓
release (发布)
  ↓
maintenance (维护)
```

### intake（项目接入）
**描述**：从零开始的项目启动。用户有一个想法，AI 需要通过引导对话了解项目全貌。
**输入**：用户的模糊想法
**输出**：项目描述文档（`specs/` 初始结构）
**参考**：`references/03-project-intake.md`

### product-overview（产品概述）
**描述**：将需求描述升级为正式的产品文档，明确愿景、价值、板块、用户、场景。
**输入**：项目描述（intake 产出）
**输出**：`specs/产品概述.md`
**参考**：原 `project-product-overview` Skill

### requirements（需求澄清）
**描述**：深入细化产品需求，明确核心价值、目标用户、关键约束。
**输入**：产品概述
**输出**：完善后的 `specs/产品概述.md`（或对应的需求文档）
**参考**：`references/04-requirements.md`

### tech-stack（技术栈选型）
**描述**：基于产品需求，推荐最合适的技术栈。
**输入**：产品概述
**输出**：`specs/技术栈.md`
**参考**：`references/05-tech-stack.md`

### project-structure（目录结构设计）
**描述**：基于技术栈和业务需求，设计高内聚低耦合的目录结构。
**输入**：产品概述、技术栈
**输出**：`specs/项目结构.md`
**参考**：`references/06-project-structure.md`

### dev-standards（开发规范制定）
**描述**：制定代码规范、Git 工作流、AI 协作协议等开发规则。
**输入**：技术栈、项目结构
**输出**：`specs/开发规范.md`
**参考**：`references/07-dev-standards.md`

### planning（路线图规划）
**描述**：基于模块依赖，规划功能开发顺序和里程碑。
**输入**：产品概述、项目结构
**输出**：`specs/开发路线图.md`
**参考**：原 `project-roadmap-planning` Skill

### implementation（编码实现）
**描述**：按路线图逐个功能开发。每个功能走需求→技术方案→任务规划→编码的闭环。
**输入**：对应的 feature 文档
**输出**：代码 + 测试 + 完成报告
**参考**：`references/08-feature-development.md`

### testing（测试）
**描述**：TDD 内嵌在 implementation 阶段，不独立。编写测试（单元/集成/E2E）验证功能是否符合 AC。
**参考**：TDD 流程在 `references/08-feature-development.md` 中定义

### release（发布）
**描述**：版本发布，生成发布说明，部署到生产环境。
**当前版本**：由用户自行管理，本工作流主要覆盖开发阶段。

### maintenance（维护）
**描述**：Bug 修复、文档同步、功能迭代。
**参考**：`references/09-bug-fix.md`、`references/11-doc-sync.md`、`references/08-feature-development.md`（evolution 流程）

## 阶段推进规则

- 默认遵守阶段边界：只有当前阶段完成后才能进入下一阶段
- 阶段推进前需要用户确认
- 阶段变化记录到 `project-status.json` 的 `current_stage` 和 `completed_stages`
- 允许受控例外：
  - 项目已存在代码时可跳过 intake 和初始化
  - 简单项目可适当合并阶段（如 product-overview + requirements）
  - 但例外必须有用户确认，不自作主张跳阶段

## Output format
不输出独立文档。阶段推进通过更新 `project-status.json` 记录，在对话中口头告知用户当前阶段和可选动作。

## Quality checklist
- [ ] 用户确认了当前阶段的状态
- [ ] 如果阶段未完成，不进入下一阶段（除非用户明确同意跳过）
- [ ] `project-status.json` 中的阶段信息与实际进度一致

## Guardrails
- 不自动推进阶段——每个阶段的出口门槛是用户确认
- 不跳过阶段——除非用户明确表示不需要某个阶段
- 阶段回退时，记录回退原因和影响范围

## Common mistakes to avoid
- 用户描述了功能想法就直接开始写代码——跳过需求和技术设计的阶段
- 用户说"可以了"就进入下一阶段，不确认当前阶段的产出是否正确
- 手动修改 `project-status.json` 中的阶段，但不更新对应的文件产出
