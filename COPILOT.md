# MAA Copilot 移植分析

## 概述

MAA 的 copilot 系统是一个 **JSON 驱动的回合制战斗指令执行器**。核心约 4000 行 C++，分布在 9 个文件。移植到 Python 的目标是完全复用其 JSON schema（社区标准），用 Python 重写执行逻辑。

---

## MAA 文件 → Python 映射

### 数据结构 (C++ header → Python data class)

| MAA C++ 文件 | 内容 | Python 对应 |
|---|---|---|
| `AsstBattleDef.h:17-24` | `SkillUsage` 枚举 | `copilot/combat_plan.py` 数据类 |
| `AsstBattleDef.h:67-74` | `DeployDirection` 枚举 | 同上 |
| `AsstBattleDef.h:76-88` | `Role` 枚举 | 同上 |
| `AsstBattleDef.h:393-411` | `ActionType` 枚举 (Deploy/UseSkill/Retreat/SwitchSpeed/BulletTime/SkillUsage/Output/SkillDaemon/MoveCamera/DrawCard) | 同上 |
| `AsstBattleDef.h:413-434` | `Action` 结构体 (kills/costs/location/direction/name/pre_delay/post_delay) | `copilot/combat_plan.py` `Action` dataclass |
| `AsstBattleDef.h:436-444` | `BasicInfo` 结构体 (stage_name, minimum_required, doc) | 同上 |
| `AsstBattleDef.h:446-451` | `CombatData` 结构体 (info + groups + actions) | 同上 |

### JSON 解析器

| MAA C++ | 内容 | Python 对应 |
|---|---|---|
| `CopilotConfig.h` / `.cpp` | `parse_basic_info()`, `parse_groups()`, `parse_actions()` | `copilot/loader.py` — 直接 json.load → dataclass |

### 战斗执行引擎

| MAA C++ | 内容 | Python 对应 |
|---|---|---|
| `BattleHelper.h:44` | `calc_tiles_info()` — 加载关卡 tile 地图 | `copilot/tile.py` 复用 `tile_pos.py` |
| `BattleHelper.h:50` | `update_deployment()` — OCR 识别部署区干员 | `copilot/battle_state.py` |
| `BattleHelper.h:56-57` | `update_kills()`, `update_cost()` — OCR 识别杀敌数和费用 | 同上, 用 `rapidocr` |
| `BattleHelper.h:61-63` | `deploy_oper()`, `retreat_oper()` — 部署/撤退 | `copilot/deployer.py` |
| `BattleHelper.h:64-67` | `is_skill_ready()`, `use_skill()` — 技能检测+使用 | `copilot/skill_mgr.py` |
| `BattleHelper.h:68-70` | `check_pause_button()`, `check_skip_plot_button()` | 复用 `recognizer` |
| `BattleHelper.h:46-47` | `pause()`, `speed_up()` | 复用 `solver.tap` |
| `BattleHelper.h:75-77` | `wait_until_start()`, `wait_until_end()`, `use_all_ready_skill()` | `copilot/executor.py` |

### 流程编排

| MAA C++ | 内容 | Python 对应 |
|---|---|---|
| `BattleProcessTask.h:22-43` | `_run()` 主循环: wait_condition → do_action → loop | `copilot/executor.py` `ActionRunner` |
| `BattleProcessTask.h:43` | `wait_condition()` — 检查 kills/costs/cooling/time_elapsed | 同上 |
| `BattleProcessTask.h:39` | `do_action()` — switch(type) 分发 | 同上, match/case |
| `BattleProcessTask.h:38` | `to_group()` — 干员组 → 具体干员 | `copilot/combat_plan.py` |

### 关卡地图

| MAA 资源 | 内容 | Python 对应 |
|---|---|---|
| `resource/tile/*.json` | 每个关卡的 tile 坐标映射 | `utils/tile_pos.py` 已经有关卡 tile 数据 |

---

## JSON Schema (直接复用 MAA 标准)

```json
{
    "stage_name": "1-7",
    "minimum_required": "v4.0.0",
    "doc": { "title": "1-7 信赖", "details": "简单挂机" },
    "opers": [
        { "name": "山", "skill": 2, "skill_usage": 2 }
    ],
    "groups": [
        { "name": "先锋组", "opers": [
            { "name": "桃金娘", "skill": 1, "skill_usage": 1 },
            { "name": "极境", "skill": 1, "skill_usage": 1 }
        ]}
    ],
    "actions": [
        { "type": "Deploy", "name": "先锋组", "location": [4, 3], "direction": "Down", "costs": 10 },
        { "type": "Skill",   "name": "先锋组", "kills": 5 },
        { "type": "Deploy",  "name": "山",     "location": [3, 4], "direction": "Right", "costs": 15 },
        { "type": "SkillDaemon" }
    ]
}
```

Action 字段:

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | Deploy / Skill / Retreat / SkillDaemon / SpeedUp / BulletTime / SkillUsage / MoveCamera |
| `name` | string | 干员名或组名 |
| `location` | [col, row] | tile 坐标 |
| `direction` | string | Left / Right / Up / Down / None |
| `kills` | int | 等待杀敌数达到 |
| `costs` | int | 等待费用达到 |
| `cost_changes` | int | 等待费用变化量 |
| `cooling` | int | 等待冷却中的干员数 |
| `pre_delay` | int | 动作前等待 ms |
| `post_delay` | int | 动作后等待 ms |
| `timeout` | int | 超时 ms |
| `skill_usage` | int | 0=不用 1=自动 2=用X次 3=时机 |
| `skill_times` | int | 技能使用次数 |
| `skip_if_not_ready` | bool | 技能未就绪则跳过 |

---

## Python 实现架构

```
scheduler/
├── copilot/                          # 自动战斗子系统 (约 1500 行)
│   ├── combat_plan.py               # Action, CombatPlan, OperatorUsage 数据类 (纯 Python)
│   ├── loader.py                    # JSON → CombatPlan 加载器
│   ├── tile.py                      # tile 坐标 → 像素坐标 (复用 tile_pos.py)
│   ├── battle_state.py              # BattleState 追踪: 费用/杀敌/时间/部署表
│   ├── deployer.py                  # 部署/撤退/方向选择 (视频 auto_fight.py)
│   ├── skill_mgr.py                 # 技能检测/使用/SkillDaemon
│   └── executor.py                  # ActionRunner 主循环
│
├── executors/
│   └── copilot.py                   # CopilotExecutor (调度入口)
│
├── planners/
│   └── operation.py                 # 作战计划生成器
│
└── services/
    └── squad_builder.py             # 编队管理
```

---

## 核心执行循环 (executor.py)

```python
class ActionRunner:
    def __init__(self, solver, plan: CombatPlan, tile_calc: TileCalc):
        self.solver = solver
        self.plan = plan
        self.tile = tile_calc
        self.state = BattleState()

    def run(self):
        self._wait_for_battle_start()
        self.state.kills = self._read_kills()

        for action in self.plan.actions:
            self._wait_condition(action)          # 检查前置条件
            self._do_action(action)               # 执行动作
            self.state.update(action)

        self._wait_until_end()

    def _wait_condition(self, action: Action):
        while True:
            if action.kills > 0 and self.state.kills < action.kills:
                self.state.kills = self._read_kills()
                continue
            if action.costs > 0 and self.state.costs < action.costs:
                self.state.costs = self._read_costs()
                continue
            if action.pre_delay > 0:
                sleep(action.pre_delay)
            break

    def _do_action(self, action: Action):
        match action.type:
            case "Deploy":
                self.deployer.deploy(action.name, action.location, action.direction)
            case "Skill":
                self.skill_mgr.use_skill(action.name)
            case "Retreat":
                self.deployer.retreat(action.name)
            case "SkillDaemon":
                self.skill_mgr.wait_with_auto_skill()
            case "SpeedUp":
                self.solver.tap((0.95, 0.05))      # 右上角二倍速
            case "BulletTime":
                self.solver.tap(self.tile.to_pixel(action.location))
                self.skill_mgr.wait_for_skill_ready(action.name)
```

---

## 各模块与 `auto_fight.py` 的关系

当前 `auto_fight.py` 已经有部分战斗能力:

```python
class AutoFight(BaseSolver):
    def deploy(self)         # ❌ 只能放指定位置的干员, 不支持指定 tile
    def withdraw(self)       # ✅ 撤退可用
    def use_skill(self)      # ✅ 技能可用
    def update_operators()   # 🟡 检测场上干员状态
    def cost()               # 🟡 费用识别
    def kills()              # 🟡 杀敌识别
    def skill_ready()        # ✅ 技能就绪检测
```

copilot 子系统会 **复用** `auto_fight.py` 的 `BaseSolver` 方法（`tap`/`swipe`/`find`），但战斗逻辑独立重写，避免耦合。

---

## 移植工作量

| 模块 | 估计 | 依赖 |
|---|---|---|
| `combat_plan.py` (数据类) | 半天 | 无, 纯 Python |
| `loader.py` (JSON 解析) | 半天 | 无 |
| `tile.py` (坐标转换) | 半天 | `tile_pos.py` |
| `battle_state.py` (战场状态) | 1 天 | `rapidocr` 识别杀敌/费用 |
| `deployer.py` (部署/撤退) | 2 天 | 游戏测试, tile 坐标验证 |
| `skill_mgr.py` (技能管理) | 1 天 | 游戏测试 |
| `executor.py` (主循环) | 1 天 | 以上全部 |
| `copilot_executor.py` (调度) | 半天 | MainLoop |
| **总计** | **~7 天** | |

---

## 不用的 MAA 模块

以下 MAA 模块在 Python 侧不需要:

| MAA 模块 | 原因 |
|---|---|
| `BattleFormationTask` | 编队用我们已有的 `agent_picker` + `squad_builder` |
| `CreditFightTask` | 已有独立的 `credit_fight.py` |
| `StageDropsTaskPlugin` | 掉落识别在 `operation.py` |
| `DrGrandetTaskPlugin` | 理智管理在 `operation.py` |
| `MedicineCounterTaskPlugin` | 同上 |
| `FightTimesTaskPlugin` | 同上 |
| `MultiCopilotTaskPlugin` | 多关链式执行通过 scheduler planners 实现 |
