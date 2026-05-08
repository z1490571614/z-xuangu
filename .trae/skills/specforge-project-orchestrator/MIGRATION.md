# SpecForge 迁移指南：多个 Skill → 统合总控 Skill

## 1. 为什么从多个 Skill 合并成一个总控 Skill

### 问题
V3 版本的 SpecForge 包含 **12 个独立 Skill**（7 个项目级 + 4 个功能级 + 1 个通用）。每个 Skill 是一个独立的 `SKILL.md` 文件，用户需要在 ChatGPT 中手动触发。

在实际使用中暴露了三个问题：
- **碎片化**：12 个 Skill 来回切换，用户需要记忆触发条件和触发词
- **重复**：上下文协议、边界守卫、角色定义在每个 Skill 中重复出现
- **不连贯**：阶段之间的过渡需要用户手动判断"现在该调用哪个 Skill"

### 解决方案
将 12 个 Skill 合并为一个总控 Skill：**`specforge-project-orchestrator`**

核心理念：
- **一个入口**：用户用自然语言描述需求，总控自动路由到正确的 workflow module
- **轻量总控**：`SKILL.md` 只有 ~60 行，负责意图路由和核心原则
- **详细流程在 references/**：14 个 reference 文件，每个 40-80 行，独立维护

---

## 2. 原 Skills 到新 references 模块的映射表

| 原 Skill | 映射目标 |
|---------|---------|
| `project-requirements-clarification` | `references/04-requirements.md`（项目级需求澄清） |
| `project-product-overview` | `references/04-requirements.md`（需求 → 产品概述转换） |
| `project-tech-stack` | `references/05-tech-stack.md` |
| `project-structure` | `references/06-project-structure.md` |
| `project-dev-standards` | `references/07-dev-standards.md` |
| `project-roadmap-planning` | `references/02-project-lifecycle.md`（planning 阶段） |
| `project-initialization` | `references/02-project-lifecycle.md`（implementation 阶段入口） |
| `feature-requirements-clarification` | `references/04-requirements.md` + `references/08-feature-development.md` |
| `feature-tech-design` | `references/08-feature-development.md`（阶段 2） |
| `feature-task-planning` | `references/08-feature-development.md`（阶段 3） |
| `feature-implementation` | `references/08-feature-development.md`（阶段 4） |
| `feature-evolution` | `references/08-feature-development.md`（evolution 流程） |
| `bugfix-workflow` | `references/09-bug-fix.md` |
| GUARDRAILS（全局机制） | `references/13-guardrails.md` |
| PROJECT-CONTEXT（全局机制） | `references/01-context-protocol.md` |

**新增模块**（原 Skill 中未明确独立的）：
- `references/00-intent-routing.md` — 意图路由（原 Skill 的触发条件现在集中管理）
- `references/03-project-intake.md` — 项目接入（原 project-requirements-clarification 的第一步）
- `references/10-code-review.md` — 代码审查（新能力）
- `references/11-doc-sync.md` — 文档同步（新能力）
- `references/12-state-management.md` — 状态管理（新能力）
- `references/14-trae-adapter.md` — Trae 适配（新能力）

---

## 3. 新目录结构说明

```
specforge-project-orchestrator/
├── SKILL.md                          # 轻量总控：角色 + 路由 + 核心原则（~60 行）
├── references/                       # 详细工作流模块
│   ├── 00-intent-routing.md          # 自然语言意图识别与路由
│   ├── 01-context-protocol.md        # 分层上下文加载策略
│   ├── 02-project-lifecycle.md       # 项目生命周期（11 个阶段）
│   ├── 03-project-intake.md          # 项目接入（从零启动）
│   ├── 04-requirements.md            # 需求澄清（项目级 + 功能级）
│   ├── 05-tech-stack.md              # 技术栈选型
│   ├── 06-project-structure.md       # 目录结构设计
│   ├── 07-dev-standards.md           # 开发规范制定
│   ├── 08-feature-development.md     # 功能开发全流程（含 TDD、evolution）
│   ├── 09-bug-fix.md                 # Bug 修复流程
│   ├── 10-code-review.md             # 代码审查
│   ├── 11-doc-sync.md                # 文档同步
│   ├── 12-state-management.md        # 状态管理（project-status.json）
│   ├── 13-guardrails.md              # 边界守卫（禁止行为、确认规则）
│   └── 14-trae-adapter.md            # Trae 配置生成
├── assets/                           # 可复用模板
│   ├── project-status.schema.json    # 状态文件 JSON Schema
│   ├── project-context-template.md   # PROJECT-CONTEXT.md 模板
│   ├── product-overview-template.md  # 产品概述模板
│   ├── requirements-template.md      # 需求描述模板
│   ├── tech-stack-template.md        # 技术栈模板
│   ├── project-structure-template.md # 项目结构模板
│   ├── dev-standards-template.md     # 开发规范模板
│   ├── feature-spec-template.md      # 功能需求规格模板
│   ├── bug-report-template.md        # Bug 修复报告模板
│   ├── code-review-template.md       # 代码审查报告模板
│   ├── trae-rules-template.md        # Trae rules 模板
│   └── trae-prompts-template.md      # Trae prompt 结构模板
└── MIGRATION.md                      # 本文档
```

此外，在 SpecForge 根目录额外生成了 Trae 原生配置：
```
.trae/
├── rules.md                          # Trae 原生规则文件
└── prompts/
    ├── project-intake.md             # 项目接入 prompt
    ├── create-feature.md             # 创建功能规格 prompt
    ├── implement-task.md             # 实现任务 prompt
    ├── review-code.md                # 代码审查 prompt
    ├── fix-bug.md                    # Bug 修复 prompt
    ├── refactor-module.md            # 重构模块 prompt
    ├── sync-docs.md                  # 同步文档 prompt
    └── generate-tests.md             # 生成测试 prompt
```

---

## 4. SKILL.md 设计原则

- **轻量路由**：只做意图识别和模块分发，不堆所有细节
- **自然语言优先**：不要求用户记忆命令或触发词
- **角色定义清晰**：告诉 AI"你是谁"，不规定"每一步做什么"
- **避免绝对化措辞**：不出现"永远不要"、"绝对不允许"、"必须读取所有文件"
- **外部引用而非内联**：所有详细流程通过 `references/` 引用

## 5. references/ 维护规则

- 每个 reference 文件必须包含 8 个章节：Purpose / When to use / Required inputs / Workflow / Output format / Quality checklist / Guardrails / Common mistakes to avoid
- 文件独立——每个可以单独阅读和理解，不依赖其他 reference 文件的阅读顺序
- 规则不重复——每条规则只在最相关的一个文件中出现
- 编号稳定——`00-14` 是固定编号，新增模块用 `15` 及以后

## 6. assets/ 模板维护规则

- 模板使用 `{{占位符}}` 语法，替换时直接填充
- 每个模板有明确的"用途"说明
- 模板是骨架，AI 根据实际情况填充，不机械套用
- `project-status.schema.json` 扩展时遵循 JSON Schema Draft 07 规范

## 7. project-status.json 维护规则

- 只更新当前任务相关字段
- 保留已有数据——增量更新而非重写
- 不编造已完成状态
- 每次状态变化有追溯（用户确认或文档依据）
- Schema 定义在 `assets/project-status.schema.json`

## 8. 如何在 ChatGPT 中使用这个总控 Skill

1. 将 `specforge-project-orchestrator/` 目录作为 ChatGPT Skill 导入
2. 在对话中使用自然语言描述需求，例如：
   - "我有一个想法，想做个人博客"
   - "给文章列表加个搜索功能"
   - "登录接口返回 500 了，帮我看看"
3. 总控 Skill 自动识别意图并加载对应 workflow module
4. 不需要手动输入 `/feature-requirements-clarification` 之类的命令

## 9. 如何在 Trae 中使用 .trae/rules.md

1. 确保 `.trae/rules.md` 在项目根目录存在
2. Trae 会自动加载该文件作为项目规则（如果是 workspace rules 则放在 `.trae/rules/` 目录）
3. 在 Trae 中开发时，AI 会自动遵守 rules 中定义的角色、上下文策略、阶段规则和禁止行为
4. 如果项目 specs 有重大更新，使用 `references/14-trae-adapter.md` 流程重新生成

## 10. 如何使用 .trae/prompts/*.md

每个 prompt 文件可以直接在 Trae 中作为对话模板使用：
- 打开对应 prompt 文件
- 复制内容作为初始消息发送给 AI
- 或者将 prompt 文件内容作为 `/prompt` 命令的输入

建议用 Trae 的自定义命令功能绑定这些 prompt。

## 11. 如何新增新的 workflow module

1. 在 `references/` 下创建新文件（编号从 15 开始）
2. 遵循 8 章节结构（Purpose / When to use / Required inputs / Workflow / Output format / Quality checklist / Guardrails / Common mistakes to avoid）
3. 在 `SKILL.md` 的意图路由表中添加新条目
4. 如果需要新模板，在 `assets/` 下创建
5. 如果需要新 prompt，在 `.trae/prompts/` 下创建
6. 更新 `MIGRATION.md` 中的目录结构说明

## 12. 已知限制

- **上下文窗口**：reference 文件总计约 15KB，加上 assets 约 30KB，大型项目 specs 文档可能超窗口。通过分层加载策略（01-context-protocol.md）缓解
- **ChatGPT Skill 兼容性**：Skill 目录结构遵循 ChatGPT 的约定（SKILL.md + references/ + assets/），但不同平台可能有细微差异
- **语言**：当前所有文件为中文，海外用户可能不适应
- **项目适配**：模板是通用模板，首次使用时需要根据项目技术栈填充占位符

## 13. 后续优化建议

- **多语言支持**：提供英文版 SKILL.md 和 references（或采用双语）
- **精简 references**：部分 reference 文件可合并（如 10-code-review 和 09-bug-fix 有重叠）
- **自动化测试**：为 references 文件添加一致性检查脚本
- **示例项目**：提供一个完整的"示例项目" specs 目录，帮助新用户快速上手
- **Trae 深度集成**：利用 Trae 的 workspace rules 和自定义命令，实现一键切换 workflow module
