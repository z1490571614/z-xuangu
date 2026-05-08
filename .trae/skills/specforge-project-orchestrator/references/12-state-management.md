# 12 - 状态管理 (State Management)

## Purpose
定义 `project-status.json` 的维护规则，确保项目状态准确、可追溯、不丢失。

## When to use
- 项目阶段变化时（阶段推进/回退）
- 新功能开始/完成时
- Bug 记录/修复时
- 技术决策记录时
- 用户查询项目进度时

## Required inputs
- `project-status.json`（必须存在）
- 对应的文档依据（specs 文档、用户确认记录）

## project-status.json 结构

Schema 定义：`assets/project-status.schema.json`

核心字段：
```json
{
  "project_name": "项目名称",
  "current_stage": "当前阶段",
  "completed_stages": ["已完成阶段列表"],
  "active_feature": "当前活跃功能名（null 表示无）",
  "features": [],
  "bugs": [],
  "technical_debt": [],
  "decisions": [],
  "last_updated": "ISO 时间戳"
}
```

### Feature 子结构
```json
{
  "name": "功能名",
  "status": "pending|requirements|tech-design|task-planning|in-progress|completed",
  "ac_count": 0,
  "completed_tasks": 0,
  "total_tasks": 0,
  "current_stage_index": 0,
  "specs_path": "specs/features/功能名.md"
}
```

### Bug 子结构
```json
{
  "id": "BUG-001",
  "title": "简短描述",
  "severity": "low|medium|high|critical",
  "status": "reported|reproduced|in-progress|fixed|verified",
  "report_path": "docs/BUG修复文档/xxx.md"
}
```

### Decision 子结构
```json
{
  "id": "DEC-001",
  "title": "决策标题",
  "context": "背景",
  "decision": "做出的决定",
  "reason": "理由",
  "date": "日期"
}
```

## Workflow

### 更新规则
- **只更新当前任务相关字段**，不重写整个文件
- **保留已有数据**，修改是增量而非替换
- **不编造已完成状态**——只能记录已经过用户确认的完成
- **每次状态变化有追溯**：能追溯到用户确认或对应文档

### 阶段推进时
1. 用户确认阶段完成
2. 更新 `completed_stages` 追加
3. 更新 `current_stage` 为新阶段
4. 更新 `last_updated`

### 新功能开始时
1. 需求文档生成后
2. 在 `features` 数组中添加记录
3. 设置 `active_feature`

### 功能完成时
1. 所有任务完成、AC 验证通过
2. 更新 feature 状态为 `completed`
3. 清除 `active_feature`（或设为下一个功能）

### Bug 修复时
1. Bug 报告生成后添加记录
2. 修复后更新状态
3. 验证后标记为 `verified`

### 进度查询时
1. 读取 `project-status.json`
2. 展示：当前阶段、活跃功能、完成情况
3. 给出"下一步建议"（参考生命周期阶段）

## Output format
不输出独立文档。对话中以人类可读方式展示进度。文件更新通过 Write 工具进行（增量更新 JSON）。

## Quality checklist
- [ ] 更新的字段有用户确认或文档依据
- [ ] 已有数据未丢失
- [ ] 时间戳已更新
- [ ] JSON 格式有效

## Guardrails
- 不重写整个文件
- 不编造完成状态
- 不记录未确认的决策
- JSON 文件格式错误时主动修复并告知用户

## Common mistakes to avoid
- 推进阶段时忘记更新 `completed_stages` → 下次想不起来已经做了
- 功能已经开始但未更新 `active_feature` → 状态与实际情况脱节
- 手动编辑 JSON 时破坏已有数据结构
