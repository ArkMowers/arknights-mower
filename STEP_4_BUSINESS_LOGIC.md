# Step 4: Business Logic Migration

> 估算: 14-20 天
> 依赖: Step 1-3 完成

## 目标

把 `solvers/base_schedule.py`(4474 行) 拆解为独立 Executor + Planner, 逐个迁移, 每步验证。

## 迁移顺序

### Step 4a: ClueExecutor (独立, 最先做)

| 文件 | 旧来源 | 行数 |
|---|---|---|
| `scheduler/executors/clue.py` | `base_schedule.py:clue_new()` | ~240 |
| `scheduler/planners/clue.py` | `base_schedule.py:clue_task_logic()` | ~80 |
| `scheduler/infra/clue_op.py` | `base_mixin.py:clue_related()` | ~60 |

### Step 4b-g: Executor 逐个迁移

| # | Executor | 依赖 Infra | 旧来源行数 |
|---|---|---|---|
| 4b | CorrectionExecutor | room_mgr, agent_picker | ~200 |
| 4c | FiammettaExecutor | room_mgr, agent_picker | ~150 |
| 4d | WorkshopExecutor | room_mgr, agent_picker | ~260 |
| 4e | SkillExecutor | room_mgr, agent_picker | ~160 |
| 4f | RunOrderExecutor | room_mgr, agent_picker, drone_op | ~350 |
| 4g | ExhaustExecutor | room_mgr, agent_picker | ~120 |
| 4h | ShiftExecutor | room_mgr, agent_picker | ~500 ★ |

### Step 4i-p: Planner 逐个迁移

| # | Planner | 旧来源行数 |
|---|---|---|
| 4i | IdlePlanner | ~100 |
| 4j | ShiftPlanner | ~400 |
| 4k | OrderPlanner | ~200 |
| 4l | FiaPlanner | ~80 |
| 4m | WorkshopPlanner | ~100 |
| 4n | ExhaustPlanner | ~60 |
| 4o | SkillPlanner | ~80 |
| 4p | CluePlanner | ~60 |
| 4q | BackupPlanner | ~100 |

## 关键设计

### InfraRegistry (DI 容器)

```python
# scheduler/infra/registry.py
class InfraRegistry:
    def __init__(self, device: DevicePort):
        self.agent_picker = AgentSelection(device)
        self.room_mgr = RoomManager(device)
        self.mood_scanner = MoodScanner(device)
        self.drone_op = DroneOperator(device)
        self.order_op = OrderOperator(device)
        self.training_op = TrainingOperator(device)
```

Executor 通过 InfraRegistry 调用底层 UI 原语, 不直接调 DevicePort。

### AgentSelection

8 状态显式状态机, 替换旧 `choose_agent()` 的 while+flag:

```
PREPROCESS → FAST_CLEAR → MAIN_PREPARE → SCAN_SELECT
  → SWIPE_NEXT → FREE_ASSIGN → FINAL_SORT → VERIFY → DONE
```

## 验证

- 每个 Executor 迁移后立即回归测试: 输入相同任务 → 输出相同操作序列
- 截图回放对比: 旧 base_schedule.py vs 新 Executor, 基建流程一致
- `solvers/base_schedule.py` 中被迁走的方法标记为 deprecated

## 允许的旧代码改动

- 无。旧代码保留, 新代码并行, 最后 Step 5 切换入口。
