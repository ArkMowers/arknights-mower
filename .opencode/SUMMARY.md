# arknights-mower v5 重构进度总览

> 基线: `4.1.6` | 分支: `redesign` | 日期: 2026-05-02

## 完成进度

| Step | 阶段 | 状态 | 文件数 |
|------|------|------|--------|
| 1 | Architecture Redesign | ✅ 完成 | 21 |
| 2 | Graph / Navigation | ✅ 完成 | 3 |
| 3 | Recognition 拆分 | ✅ 完成 | 6 |
| 4 | Business Logic Migration | 🔶 框架 | 19 |
| 5 | Full Chain | 🔶 框架 | 4 |
| 6 | Copilot | ✅ 基础完成 | 7 |
| 7 | Android | ⏳ 规划 | 0 |

## Step 1: 领域骨架 (已完成 ✅)

### 数据层
- `scheduler/domain/operators.py` — `Operator` + `Dormitory` + `OperatorType` + `RestPriority`
  - 纯数据类 + 4 个派生属性 (`is_high`, `is_resting`, `is_working`, `current_mood`)
  - 业务逻辑方法移出到 `SchedulerState` 的方法中
- `scheduler/domain/plan.py` — `PlanConfig` + `Room` + `Plan` + `BaseProduct` + `PlanTriggerTiming`
  - `is_*` 系列简单查询方法保留在类上
  - `merge_config` + `is_refresh_trading` 移出到 `services/plan_service.py`
- `scheduler/domain/task.py` — `SchedulerTask` + `TaskTypes` + `set_type_enum()`
  - `format()` 移出到 `services/task_service.py`

### 运行时管理
- `scheduler/state.py` — `SchedulerState` (替代旧 `Operators` 类)
  - 持有 `operators: dict[str, Operator]` + `dormitories: dict[tuple[str,int], Dormitory]`
  - 方法: `swap_plan()`, `not_valid()`, `predict_exhaust()`, `need_to_refresh()`, `get_dormitory()` (O(1))
- `scheduler/queue.py` — `TaskQueue` (heapq, push/pop/peek/find/remove)
- `scheduler/dispatch.py` — `TaskDispatch` (register/resolve/execute 含 safe_execute)

### 基础设施
- `scheduler/device_port.py` — `DevicePort` ABC (tap/swipe/screencap/back/launch/exit/check_focus)
- `scheduler/infra/pause_controller.py` — `PauseController` (threading.Event 实现)
- `scheduler/executors/base.py` — `AbstractExecutor` (safe_execute + check_pause)
- `scheduler/planners/base.py` — `AbstractPlanner`

### 常量
- `scheduler/constants.py` — `Server`, `Locale`, `FacilityType`, `DORM_ROOM_PREFIX`, `TapPosition` (15 个导航坐标)

### 规范文档
- `AGENTS.md` 新增 **Data Class 界定** 章节: 什么放 domain (派生属性/纯计算), 什么移 service (副作用/硬编码/跨对象逻辑)
- `AGENTS.md` 新增 **任务执行必须异常隔离** 规范

## Step 2: 场景图 + 导航 (已完成 ✅)

### 核心文件
- `scheduler/scene.py` — `Scene IntEnum` (138 个场景, 与旧 utils/scene.py 一致)
- `scheduler/graph.py` — `SceneGraph` (networkx DiGraph 封装)
  - `add_transition()` / `find_path()` / `can_reach()` / `transition` 装饰器
  - `build_default_graph()` — 初始化全图 (74 节点, 133 条边)
- `scheduler/navigator.py` — `Navigator` (45 个 `_action_*` handler + `_cback` + `_tap_element`)
  - 依赖 `DevicePort` + `get_scene` callable + optional `Recognizer`
  - 所有导航坐标使用 `TapPosition` enum → 零硬编码坐标 ✅
  - Handler 目录: back_to_index, index_to_infra, leave_infrastructure, index_nav, infra_back 等

### 验证通过
- `SceneGraph.find_path(INDEX, INFRA_MAIN)` → 正确路径 `[(INFRA_MAIN, 'index_to_infra')]`
- `SceneGraph.find_path(INFRA_MAIN, INDEX)` → `[(INDEX, 'back_to_index')]`
- `SceneGraph.can_reach(INDEX, UNKNOWN)` → `False`
- 全图: 74 nodes, 133 edges

## Step 3: Recognition 拆分 (基础完成 🔶)

### 完成
- `utils/recognize/` package 结构
- `utils/recognize/constants.py` — COLOR (61), TEMPLATE_MATCHING (62), TEMPLATE_MATCHING_SCORE (20), FEATURE_MATCH_RES (8)
- `utils/recognize/__init__.py` — find() 不再内联 dict, 改用策略类 dispatch
- `utils/recognize/find_color.py` — ColorMatcher 策略 (cmatch + SSIM)
- `utils/recognize/find_template.py` — TemplateMatcher 策略 (cv2.matchTemplate)
- `utils/recognize/find_feature.py` — FeatureMatcher 策略 (ORB+SVM + scope/threshold overrides)
- `utils/recognize/scene.py` — SCENE_RULES 规则表 (50+ simple rules), SCOPED_RULES, CUSTOM_DETECTORS
- `utils/recognize.py` → bridge import

### 待完成
- get_scene() 接入 SCENE_RULES 表 (复杂逻辑需保留 custom detectors)
- 全场景回归测试 (新旧 find() 结果一致)

## Step 4: 业务逻辑迁移 (框架 🔶)

### 已创建 (stubs 含 `NotImplementedError`)

**8 个 Executor:**
- `scheduler/executors/clue.py` — ClueExecutor (线索)
- `scheduler/executors/correction.py` — CorrectionExecutor (纠错)
- `scheduler/executors/fiammetta.py` — FiammettaExecutor (菲亚梅塔)
- `scheduler/executors/workshop.py` — WorkshopExecutor (加工站)
- `scheduler/executors/skill.py` — SkillExecutor (专精)
- `scheduler/executors/run_order.py` — RunOrderExecutor (跑单)
- `scheduler/executors/exhaust.py` — ExhaustExecutor (用尽)
- `scheduler/executors/shift.py` — ShiftExecutor (换班)

**9 个 Planner:**
- idle, shift, order, fiammetta, workshop, exhaust, skill, clue, backup

**Infra:**
- `scheduler/infra/registry.py` — InfraRegistry (待实现 DI 容器)

### 待迁移 (~4000+ 行从 `solvers/base_schedule.py`)
- AgentSelectionFSM (8 状态状态机)
- 每个 executor/planner 的具体业务逻辑
- 截图回放验证

## Step 5: 全链路 (框架 🔶)

### 已创建
- `scheduler/loop.py` — `MainLoop.run_forever()` (已实现核心逻辑)
  - peek → execute(safe) → pop → repeat
  - 异常隔离: 失败任务记录 + 漏过
  - 暂停支持: PauseController 集成
- `scheduler/hooks.py` — LifecycleHook (stub)
- `scheduler/database/core.py` — DatabaseEngine (stub)

### 待完成
- LifecycleHook 链 (7 个 hook: 维护/每日/仓库/生息/隐秘/休眠/更新)
- Database 完整持久化 (repository 模式)
- services/ 外部集成 (MAA client, 每日任务, 仓库扫描)
- `__main__.py` 瘦身

## Step 6: Copilot 自动战斗 (框架 🔶)

### 已完成
- `scheduler/copilot/combat_plan.py` — MAA JSON format 兼容数据类
  - `StageInfo`, `Action`, `ActionType` (10 types), `Direction`, `OperatorGroup`, `CombatDoc`
- `scheduler/copilot/loader.py` — JSON → StageInfo 解析器 (MAA OF-1 验证通过 ✅)
- `scheduler/copilot/tile.py` — TileSystem (tile ↔ pixel 坐标转换)
- `scheduler/copilot/deployer.py` — Deployer 接口 (deploy/retreat/activate_skill)
- `scheduler/copilot/executor.py` — CopilotExecutor 指令 dispatch

### 待完成
- executor.py 实际指令执行 (战斗截图识别)
- battle_state.py (战场状态: 费用/部署位/干员)
- skill_mgr.py (技能自动释放)
- 战斗截图识别 连通 (reuse utils/recognize)

### 参考
- F:\Git\MaaAssistantArknights (MAA copilot JSON format)
- OF-1_credit_fight.json 已作为格式参考

## Step 7: Android (仅规划 ⏳)

### 待创建
- Kotlin app (MediaProjection + AccessibilityService)
- Chaquopy Python integration
- Game area detection (16:9 letterbox → crop → resize to 1920x1080)
- Google Store 合规

### 参考
- https://github.com/Fate-Grand-Automata/FGA (同技术栈: Kotlin + OpenCV + MediaProjection + AccessibilityService)

## 关键文件清单

### 新增核心文件 (25 个)
```
scheduler/
├── constants.py          # 枚举 + 坐标常量
├── errors.py             # 5 异常类
├── device_port.py        # DevicePort ABC
├── state.py              # SchedulerState (运行时)
├── queue.py              # TaskQueue
├── dispatch.py           # TaskDispatch
├── graph.py              # SceneGraph
├── navigator.py          # Navigator
├── scene.py              # Scene IntEnum
├── loop.py               # MainLoop
├── hooks.py              # LifecycleHook
├── domain/operators.py   # Operator + Dormitory
├── domain/task.py        # SchedulerTask + TaskTypes
├── domain/plan.py        # PlanConfig + Room + Plan
├── executors/base.py     # AbstractExecutor
├── planners/base.py      # AbstractPlanner
├── infra/pause_controller.py
├── infra/registry.py
├── services/plan_service.py
├── services/task_service.py
├── copilot/combat_plan.py
└── database/core.py
```

### 修改的旧文件
- `AGENTS.md` — 新增 Data Class 界定 + 异常隔离规范
- `utils/recognize/__init__.py` — 从 recognize.py 抽出至 package
- `utils/recognize/constants.py` — 新文件, 提取匹配字典
- `utils/recognize.py` — 改为桥接 import
- `REFACTORING_PLAN.md` — Step 3 描述修正
- `STEP_1_ARCHITECTURE.md` — 反映实际执行 (Operators 留旧, SchedulerState 不引用 utils)
- `STEP_2_GRAPH.md` — 新增坐标约定 + utils 依赖说明
- `STEP_5_FULL_CHAIN.md` — 新增暂停机制设计

### 详细未完成清单
- `.opencode/SKIPPED.md`
