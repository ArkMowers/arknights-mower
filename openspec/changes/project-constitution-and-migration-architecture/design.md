## Context

arknights-mower v5 重构已产出大量文档（AGENTS.md、REFACTORING_PLAN.md、STEPS_OVERVIEW.md、PROJECT_MEMORY.md、7 个 STEP_*.md），但缺乏统一的 spec 格式以支持 OpenSpec SDD 工作流。需要将核心约束和架构蓝图结构化，成为后续所有 change proposal 的引用基线。

## Goals / Non-Goals

**Goals:**
- 将 AGENTS.md 的 8 条硬性要求 + 3 条核心原则 + 5 条禁止项 转为结构化 spec
- 将当前迁移架构 + 进度合成为可引用的架构 spec
- 为后续 migration change proposals 建立"宪法 + 蓝图"双基线

**Non-Goals:**
- 不修改任何代码
- 不改变现有文档
- 不新增设计约束
- 不规划新功能

## Decisions

1. **两份 spec 而非一份**: `project-constitution` 聚焦约束（不变），`migration-architecture` 聚焦状态（演进）。后续迁移 change 引宪法做约束检查，引架构做上下文。

2. **spec 内容从已有文档抽取，不新造**: proposal/design/spec/tasks 全部基于 AGENTS.md + PROJECT_MEMORY.md + STEPS_OVERVIEW.md + REFACTORING_PLAN.md + STEP_*.md 的已有内容，只做结构化整理。

3. **Scenario 以 AI 编码助手的合规检查为视角**: 每条 scenario 描述"AI 编码助手在写代码时如何验证合规"，而非用户操作流程。

## Risks / Trade-offs

- [Risk] 宪法规约过于刚性可能导致后续 change 频繁违反 → Mitigation: 宪法 spec 可通过后续 change 的 MODIFIED Requirements 演进
- [Risk] 架构蓝图和 PROJECT_MEMORY.md 内容冗余 → Mitigation: 架构 spec 作为 baseline snapshot，后续 PROJECT_MEMORY.md 可精简为"当前未完成清单"
