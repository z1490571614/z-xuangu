# 06 - 目录结构设计 (Project Structure)

## Purpose
基于技术栈和业务需求，设计高内聚低耦合的项目目录结构，让代码组织有章可循。

## When to use
- 技术栈确定后，需要设计目录结构时
- 现有项目需要重构目录布局时

## Required inputs
- `specs/技术栈.md` — 决定路由结构、模块组织方式
- `specs/产品概述.md` — 提取核心业务板块映射到模块
- `specs/PROJECT-CONTEXT.md`（如果存在）

## Workflow

### 角色：系统架构师

### 读取上下文
- 技术栈决定目录骨架（Next.js 用 App Router、Go 用 Clean Architecture）
- 产品概述中的核心板块映射为代码模块

### 设计结构
1. **根目录**：标准文件（README.md, .gitignore, .env.example）
2. **源码目录**：根据技术栈选择分层架构或特性架构
   - **特性架构（推荐）**：`src/modules/{auth, posts, analytics}/`
   - **分层架构**：`src/{components, services, utils, hooks}/`
3. **文档目录**：`specs/`（规格文档）、`docs/`（开发文档）
4. **测试目录**：跟随源码（`__tests__/` 或 `.test.ts` 同目录）
5. **配置目录**：`config/` 或使用框架约定

### 核心原则
- **高内聚低耦合**：相关代码放在一起，不相关的严格隔离
- **特性优先**：优先按业务模块组织，其次按技术层
- **遵循框架约定**：不另起一套违背框架最佳实践的结构

### 生成文档
1. 参考 `assets/project-structure-template.md` 格式
2. 包含 ASCII 目录树
3. 每个目录附带用途说明
4. 保存到 `specs/项目结构.md`

## Output format
`specs/项目结构.md`，包含：
- ASCII 目录树
- 每个目录的用途说明
- 模块间依赖方向图
- 关键设计决策说明

## Quality checklist
- [ ] 目录结构符合所选技术栈最佳实践
- [ ] 每个业务模块有清晰的代码归属
- [ ] 公共代码和业务代码有清晰边界
- [ ] 用户确认了结构设计

## Guardrails
- 不混合两种组织方式——要么特性架构，要么分层，不同时使用
- 目录名遵循技术栈约定（kebab-case vs PascalCase）
- 不从空目录开始——按需创建，不为"万一用到"预留

## Common mistakes to avoid
- 把不同技术栈的最佳实践混用（如 Next.js 的项目用 Vue 的目录习惯）
- 过度嵌套——三四层目录就很难找了
- 忽略框架的约定目录（如 Next.js 的 `app/`、`public/`）
