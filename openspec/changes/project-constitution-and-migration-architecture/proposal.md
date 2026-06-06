## Why

arknights-mower v5 重构已推进到 Step 4 (Business Logic Migration) 中期，现有文档分散在 AGENTS.md、REFACTORING_PLAN.md、STEPS_OVERVIEW.md、PROJECT_MEMORY.md 和 7 个 STEP_*.md 中，AI 编码助手每次需要重新理解大量上下文。需要一份结构化的"宪法 + 架构全景图"作为 OpenSpec 的基线 spec，让后续所有 change proposal 有统一约束和架构蓝图可引用。

## What Changes

- 将 AGENTS.md 的 8 条硬性要求 + 3 条核心原则 + 5 条禁止项 整理为 spec 格式的**项目宪法**
- 将 PROJECT_MEMORY.md + STEPS_OVERVIEW.md 的架构总览 + 迁移进度 整理为**迁移架构蓝图**
- 建立 specs 基线，后续每个迁移阶段的 change proposal 可引用宪法约束和架构蓝图

## Capabilities

### New Capabilities

- `project-constitution`: 项目硬性约束（scene-driven 状态机、tap-once、零硬编码坐标、禁止 time.sleep 等 8 条规范 + 代码组织 + 命名 + Data Class 界定）
- `migration-architecture`: 当前架构全景（DevicePort → InfraKit → MainLoop → planner/executor 分层）、7 步迁移依赖关系、已完成/未完成清单

### Modified Capabilities

<!-- 无已有 specs 需要修改 -->

## Impact

- 无代码改动。纯文档层面整合。
- 新文件: `openspec/specs/project-constitution/spec.md`, `openspec/specs/migration-architecture/spec.md`
- 后续所有 OpenSpec change 将引用这两个 spec 作为基线约束
