# {{项目名称}} — 项目结构

## 目录树

```
{{项目名}}/
├── src/
│   ├── modules/                  # 业务模块（特性架构）
│   │   ├── {{模块1}}/
│   │   │   ├── components/       # 模块内组件
│   │   │   ├── hooks/            # 模块内 Hooks
│   │   │   ├── services/         # 模块内服务
│   │   │   ├── types/            # 模块内类型
│   │   │   ├── __tests__/        # 模块内测试
│   │   │   └── index.ts          # 模块入口
│   │   └── {{模块2}}/
│   ├── shared/                   # 跨模块公共代码
│   │   ├── components/           # 通用组件
│   │   ├── hooks/                # 通用 Hooks
│   │   └── utils/                # 通用工具函数
│   └── lib/                      # 第三方服务封装
│       ├── db.ts
│       └── auth.ts
├── specs/                        # 项目规格文档【真理源】
│   ├── PROJECT-CONTEXT.md
│   ├── 产品概述.md
│   ├── 技术栈.md
│   ├── 项目结构.md
│   ├── 开发规范.md
│   ├── 开发路线图.md
│   └── features/                 # 功能规格文档
├── docs/                         # 开发文档
│   ├── 开发记录/
│   └── BUG修复文档/
├── tests/                        # 全局测试和 E2E
├── public/                       # 静态资源
├── .env.example
├── .gitignore
├── package.json
└── README.md
```

---

## 模块依赖方向

```
┌─────────────┐
│  shared/    │ ◄── 所有模块都可引用
└─────────────┘
       ▲
       │
┌──────┴──────┐
│  modules/   │ ◄── 模块间通过 shared 通信，不直接引用
└─────────────┘
       ▲
       │
┌──────┴──────┐
│  lib/       │ ◄── 底层服务封装，modules 通过它访问外部
└─────────────┘
```

**禁止的依赖**：
- 模块之间直接引用对方的内部文件（`moduleA/components/X` 不要被 moduleB 直接引用）
- `shared/` 引用 `modules/` 中的文件
- 循环依赖

---

## 目录说明

| 目录 | 用途 | 命名规则 |
|------|------|---------|
| `modules/` | 业务模块 | {{kebab-case}} |
| `shared/` | 跨模块代码 | {{按功能命名}} |
| `lib/` | 第三方封装 | {{按服务命名}} |
| `specs/` | 规格文档 | {{中文 + kebab-case}} |
| `docs/` | 开发文档 | {{按类型分目录}} |

---

## 文件命名约定

| 类型 | 风格 | 示例 |
|------|------|------|
| 组件文件 | {{PascalCase}} | `UserProfile.tsx` |
| 工具函数 | {{camelCase}} | `formatDate.ts` |
| 服务文件 | {{camelCase}} | `apiClient.ts` |
| 类型文件 | {{camelCase}} | `user.ts` |
| 测试文件 | {{*.test.ts / *.spec.ts}} | `UserProfile.test.tsx` |

---

## 变更日志

| 日期 | 变更内容 | 原因 |
|------|---------|------|
| {{日期}} | {{初始创建}} | — |
