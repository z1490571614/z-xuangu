# {{项目名称}} — 开发规范

## 1. 语言与运行时

- **语言**：{{TypeScript 5.x / Go 1.x / Python 3.x}}
- **运行时**：{{Node.js 20 / Bun / Python 3.11+}}
- **包管理器**：{{pnpm / npm / yarn}}（版本 {{x}}）
- **TypeScript 严格模式**：`strict: true`（如适用）

## 2. 代码风格与 Lint

- **格式化**：{{Prettier / Black}}，配置 {{关键选项}}
- **Lint**：{{ESLint / Biome / Ruff}}，规则集 {{推荐配置}}
- **IDE 配置**：formatOnSave = true

## 3. 命名约定

| 元素 | 风格 | 示例 |
|------|------|------|
| 文件 | {{kebab-case / PascalCase}} | `user-profile.tsx` |
| 目录 | {{kebab-case}} | `user-management/` |
| 组件 | {{PascalCase}} | `LoginForm` |
| 函数/变量 | {{camelCase}} | `getUserById` |
| 常量 | {{UPPER_SNAKE_CASE}} | `MAX_RETRY_COUNT` |
| 类型/接口 | {{PascalCase}} | `UserProfile` |
| 数据库表 | {{snake_case}} | `user_profiles` |

## 4. 语言特定规范

```typescript
// ❌ 禁止
const data: any = await fetchData()
const name = user!.name

// ✅ 推荐
const data: UserData = await fetchData()
const name = user?.name ?? '未知'
```

## 5. 框架特定规范

组件文件内部结构：
```
1. import 语句（分组：外部库 → 内部模块 → 类型 → 样式）
2. 类型/接口定义
3. 组件函数
4. 导出
```

## 6. 样式规范

- **样式方案**：{{Tailwind CSS / CSS Modules / styled-components}}
- **禁止**：内联 style、!important 滥用、魔法数值
- **响应式**：{{移动优先 / 桌面优先}}，断点 {{sm/md/lg/xl}}

## 7. Git 工作流

- **分支策略**：{{Trunk-Based / Git Flow}}
- **分支命名**：`<type>/<description>`，如 `feat/user-auth`
- **提交规范**：Conventional Commits
  ```
  <type>(<scope>): <subject>
  
  feat(auth): 添加登录功能
  fix(api): 修复用户查询返回值
  ```

## 8. 代码注释

**需要注释**：复杂算法、非显而易见的决策、临时方案（FIXME/TODO）
**不需要注释**：能看懂的代码、函数签名已自解释的
**注释内容**：解释"为什么这么做"，不解释"做了什么"
**格式**：
- `// TODO(user): 需要做的改进 — 2024-01-01`
- `// FIXME: 已知问题 — 条件说明`

## 9. 错误处理

- 服务端：统一错误响应格式 `{ code, message, details }`
- 客户端：用户友好的提示，不暴露内部错误
- 关键操作：try-catch + 日志记录

## 10. 测试规范

- **方法**：TDD（RED → GREEN → REFACTOR）
- **工具**：{{Vitest / Jest / Pytest}} + {{Playwright / Selenium}}
- **优先级**：核心业务逻辑 > API 端点 > UI 组件 > 工具函数
- **覆盖率目标**：{{80%}}（非红线，但低于 70% 需要说明）

## 11. 依赖管理

- 新增依赖前检查：是否已有类似功能、是否活跃维护、体积是否可接受
- 安装命令：`{{pnpm add}} / {{npm install}} / {{pip install}}`
- 版本锁定：使用 lockfile

## 12. 环境变量

- **客户端暴露**：`NEXT_PUBLIC_` 前缀（Next.js）
- **服务端**：不暴露给客户端
- **必须提供** `.env.example`

## 13. AI 协作协议

**写代码前必读**：
1. `specs/开发规范.md` — 代码风格约定
2. `specs/项目结构.md` — 文件归属
3. 对应的 feature 文档 — 理解上下文

**写代码规则**：
| 规则 | 说明 |
|------|------|
| 读后写 | 先读相关文件再写代码 |
| 最小改动 | 只改任务需要的 |
| 不猜版本 | 用 `package.json` 中已有的版本 |
| 不复写已有 | 项目已有类似的先用 |
| 遵循模式 | 与周围代码风格一致 |

**写完代码后**：
- [ ] 类型检查和 Lint 通过
- [ ] 测试通过（包括已有测试）
- [ ] 没有引入新依赖（如果有，列出原因）
- [ ] 没有遗留 TODO（如果有，标注负责人和日期）

## 14. 依赖方向

```
shared/ → 任何模块可引用
modules/ → 通过 shared 通信，不互相直接引用
lib/ → modules 依赖 lib，lib 不依赖 modules
```

**禁止**：循环依赖、下层引用上层

## 15. 安全编码

- 所有用户输入必须校验（前端 + 后端双重校验）
- 数据库查询使用参数化（防 SQL 注入）
- XSS：用户内容输出时做转义
- 密钥/Token 只在环境变量中，不硬编码、不提交 Git
- 文件上传：限制类型、大小，不在用户可控路径存储

---

## 变更日志

| 日期 | 变更内容 | 原因 |
|------|---------|------|
| {{日期}} | {{初始创建}} | — |
