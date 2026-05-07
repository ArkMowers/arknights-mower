# arknights-mower v5 重构方案

> 基线: `4.1.6` | 分支: `redesign`
> 策略: 核心调度从零重写, 底层工具保留复用
> 目标: 7 步完成架构重塑 + 跨平台

## 现状

| 文件 | 行数 | 问题 |
|---|---|---|
| `solvers/base_schedule.py` | 4474 | God Class, 72 方法 |
| `__main__.py` | 366 | 巨型 simulate(), global 变量 |
| `solvers/base_mixin.py` | 577 | UI 原语与业务逻辑混合 |
| `solvers/record.py` | 636 | Raw SQL 散布 |
| `utils/recognize.py` | 1049 | 3 种匹配路径, 冗余 |

## 7 步总览

| # | 阶段 | 目标 | 估算 |
|---|------|------|------|
| 1 | Architecture Redesign | 领域骨架 + DevicePort + 状态机规范 | 2-3 天 |
| 2 | Graph / Navigation | SceneGraph 纯数据 + Navigator 执行 | 2-3 天 |
| 3 | Recognition 简化 | 代码拆分, 保留 3 条匹配路径(不动 ORB+SVM) | 2-3 天 |
| 4 | Business Logic | 逐个迁移 Executor/Planner, 每步验证 | 14-20 天 |
| 5 | Full Chain | MainLoop + Hooks + Services + DB | 5 天 |
| 6 | Copilot | 自动战斗子系统 | 7 天 |
| 7 | Android | Chaquopy 打包 + Google Store | 5-7 天 |
| | **总计** | | **37-48 天** |

## 设计原则

1. **显式状态机** — 所有 while+flag 替换为 State enum + method dispatch
2. **零硬编码坐标** — 通过 Device 层 resize 截图解决, 识别层不感知分辨率
3. **跨平台** — `scheduler/` 全系 pure Python, 平台代码隔离在 device/ 三层
4. **渐进迁移** — 旧代码保留到最后一刻, 每步独立可验证

## 详细步骤

各步骤详情见独立文档:

- [STEPS_OVERVIEW.md](./STEPS_OVERVIEW.md) — 7 步完整时间线 + 依赖关系
- [STEP_1_ARCHITECTURE.md](./STEP_1_ARCHITECTURE.md) — 架构重塑
- [STEP_2_GRAPH.md](./STEP_2_GRAPH.md) — 场景图迁移
- [STEP_3_RECOGNITION.md](./STEP_3_RECOGNITION.md) — 识别简化
- [STEP_4_BUSINESS_LOGIC.md](./STEP_4_BUSINESS_LOGIC.md) — 业务逻辑迁移
- [STEP_5_FULL_CHAIN.md](./STEP_5_FULL_CHAIN.md) — 全链路打通
- [STEP_6_COPILOT.md](./STEP_6_COPILOT.md) — 自动作战
- [STEP_7_ANDROID.md](./STEP_7_ANDROID.md) — 跨平台打包
