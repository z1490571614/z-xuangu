# Prompt：项目接入 (Project Intake)

## 任务目标
帮用户从一个模糊的想法启动项目——引导对话、深入挖掘需求、生成项目初始描述和 `project-status.json`。

## 必读上下文
| 文件 | 目的 |
|------|------|
| — | 新项目，无需前置上下文 |

## 执行步骤
1. 倾听用户的想法，像好奇的合伙人一样追问
2. 从 WHY / WHO / WHAT / HOW 四个维度引导对话
3. 每次只问 1-2 个问题，给示例降低回答难度
4. 信息足够后进行最终确认
5. 生成初始项目文档：
   - 创建 `specs/` 目录
   - 创建 `specs/PROJECT-CONTEXT.md`
   - 创建 `project-status.json`（阶段设为 `intake`）

## 文件修改边界
**会创建**：`specs/`、`specs/PROJECT-CONTEXT.md`、`project-status.json`
**不会修改**：任何现有文件

## 输出格式
- `project-status.json`（schema 参考 `specforge-project-orchestrator/assets/project-status.schema.json`）
- `specs/PROJECT-CONTEXT.md`（使用 `project-context-template.md`）

## 验证要求
- [ ] 用户确认了项目描述的准确性
- [ ] `project-status.json` 格式有效
- [ ] 用户的核心痛点、目标用户、关键功能被清晰记录

## 禁止行为
- 不猜测用户没说过的需求
- 不在此阶段讨论技术选型
- 不跳过最终确认直接生成文档
