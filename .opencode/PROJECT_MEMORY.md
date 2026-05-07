# arknights-mower v5 重构项目记忆

> 基线: `4.1.6` | 分支: `redesign` | 最后更新: 2026-05-02

## 架构总览

```
scheduler/                    ← 新世界, 纯 Python, 跨平台
├── domain/                   ← 纯数据类 + 派生属性
│   ├── operators.py          Operator + Dormitory + OperatorType + RestPriority
│   ├── task.py               SchedulerTask + TaskTypes
│   └── plan.py               PlanConfig + Room + Plan + BaseProduct
├── state.py                  SchedulerState (10 方法: swap_plan, available_free, evaluate_expression...)
├── queue.py                  TaskQueue (heapq)
├── dispatch.py               TaskDispatch (register/resolve/safe_execute)
├── device_port.py            DevicePort ABC (tap/swipe/screencap/back/launch/exit/check_focus)
├── graph.py                  SceneGraph + build_default_graph() (74n/133e)
├── navigator.py              Navigator (45 action handlers + TapPosition enum)
├── scene.py                  Scene IntEnum (138 scenes)
├── loop.py                   MainLoop (peek → execute → pop + 暂停)
├── errors.py                 5 exception classes
├── constants.py              Server/Locale/FacilityType/DORM_ROOM_PREFIX/TapPosition/i18n _t()
├── infra/                    PauseController + PCDevicePort + InfraRegistry
├── planners/                 3 完成 + 5 stub
├── executors/                8 stub
├── services/                 plan_service + task_service
├── copilot/                  combat_plan + loader + executor + tile + deployer + battle_state + skill_mgr
└── database/                 core stubs

utils/recognize/              ← 拆分后的识别层
├── __init__.py               Recognizer (find() 策略 dispatch)
├── constants.py              COLOR + TEMPLATE_MATCHING + FEATURE_MATCH_RES
├── find_color.py             ColorMatcher
├── find_template.py          TemplateMatcher
├── find_feature.py           FeatureMatcher
└── scene.py                  SCENE_RULES 表
```

## 关键设计决策

1. **Data Class vs Service**: domain 只放派生属性 (is_high/is_resting/current_mood) + 纯计算, 有副作用/硬编码/跨对象逻辑 → 移 service
2. **SchedulerState 替代 Operaters**: state 持有 operators dict + dormitories dict + 运行时方法
3. **dormitories: dict[tuple[str,int], Dormitory]** → O(1) lookup
4. **零硬编码坐标**: TapPosition enum
5. **零 utils.log 依赖**: stdlib logging
6. **跨平台**: scheduler 纯 Python, 平台代码仅 pc_device_port.py (包装旧 Device)
7. **异常隔离**: safe_execute() + MainLoop pop 后继续
8. **暂停机制**: PauseController (threading.Event)
9. **i18n**: _t() placeholder, TASK_DISPLAY_NAMES 仅 ZH_CN 有值
10. **三层调度架构**: Planner(计划) → Dispatch(分发+重连) → Executor(执行+FSM)
11. **优先级抢占在 TaskQueue.pop()**: 不是 planner 也不是 executor, 出队时检查时间窗口内的优先级
12. **重连在 DevicePort 层**: executor 不处理, Dispatch 只调 device.reconnect(), 每个平台自己实现
13. **Planner 无状态轮询**: frequency + condition + make_task, 每次返回单个 SchedulerTask | None
14. **screencap 自愈 + tap/swipe 快速失败**: screencap 内部 while True 自恢复, tap/swipe 失败抛 DeviceError 给 dispatch 兜底
15. **跨平台 DevicePort.reconnect()**: PC 重启模拟器, Android 重启 MediaProjection/Accessibility, Dispatch 不感知

## 三层调度架构详解

```
MainLoop
  │
  ├── planners: list[AbstractPlanner]     ← 轮询, 推送未来任务
  │    每个 planner:
  │      ├── should_run()                  frequency 节流
  │      ├── condition(state) → bool       检查状态是否满足
  │      └── make_task(state) → task|null  创建任务
  │
  ├── TaskQueue                            ← 优先级队列
  │     └── pop():
  │          1. 取 `time <= now + WINDOW` 窗口内所有任务
  │          2. 按 (priority, time) 排序
  │          3. 返回最优任务 (非最早, 而是最高优先级中最早的)
  │
  └── TaskDispatch
        └── execute(task):
              1. resolve executor
              2. try executor.run(task)
              3. on DeviceError → device.reconnect() → retry (3×)
              4. on other error → log + return False
```

### 错误处理策略

```
方法              策略                        谁 recover
───────────────────────────────────────────────────────────
screencap()      while True 自愈              DevicePort 内部
tap()/swipe()    快速失败, 抛 DeviceError      不处理, 让上层兜底
Dispatch         兜底: reconnect + retry       Dispatch 层
```

### DevicePort.reconnect() 平台实现

```python
class DevicePort(ABC):
    @abstractmethod
    def reconnect(self) -> None: ...

class PCDevicePort(DevicePort):
    def reconnect(self) -> None:
        restart_simulator()
        check_server_alive()
        Session().connect(adb)
        start_droidcast()  # if enabled

class AndroidDevicePort(DevicePort):
    def reconnect(self) -> None:
        media_projection.restart()
        accessibility_service.reconnect()
```
- executor 不处理 DeviceError, 只写业务逻辑
- Dispatch 只调 device.reconnect(), 不关心理实现

### 任务类型注册 (bootstrap)

```
必选: shift, order, exhaust, fiammetta, clue, correction, skill, workshop
可选 (根据 config):
  recruit_enable     → RecruitPlanner
  skland_enable      → SklandPlanner
  check_mail_enable  → MailPlanner
  maa_depot_enable   → DepotPlanner
  maa_enable         → MaaPlanner
```

### 迁移路线

| Phase | 内容 | 状态 |
|-------|------|------|
| 1 | bootstrap 正式入口 + dispatch 重连 + TaskQueue 优先级 | 🔶 实现中 |
| 2 | MainLoop 时间调度 + idle 填充 (每日任务) | ⏳ |
| 3 | Planner 逐个实现 (shift/order/exhaust/...) | ⏳ |
| 4 | 存档恢复 (mood/time_stamp/position) | ⏳ |
| 5 | Email 通知 / MAA 集成 (作为 planner 任务) | ⏳ |

## 已完成的 Planner (纯计算, 不依赖设备)

| Planner | 行数 | 关键方法 |
|---------|------|----------|
| ExhaustPlanner | 107 | `plan`, `_get_resting_plan`, `_check_fia` → SHIFT_OFF task |
| IdlePlanner | 81 | `plan`, `_add_release_dorm` → RELEASE_DORM task |
| BackupPlanner | 38 | `plan` → `evaluate_expression` → `swap_plan` |
| FiammettaPlanner | 87 | `plan` → fia threshold logic → FIAMMETTA task |
| OrderPlanner | 45 | `plan_room`, `plan_all` → RUN_ORDER task |

## Database 层 (新)

```
scheduler/database/
├── engine.py          DatabaseEngine (sqlite3 → @app/tmp/mower.db)
├── session.py         Session (context manager, 事务 commit/rollback)
├── errors.py          DatabaseError
└── repositories/
    ├── base.py        BaseRepository (find_by_id/find_all/delete/count)
    └── agent_action.py  AgentActionRepo + SavedStateRepo (save/load JSON)
```

## 剩余待做

| 分类 | 数量 | 说明 |
|------|------|------|
| Planner | 4 | Shift/Workshop/Skill/Clue (stub) |
| Executor | 8 | 需要设备交互, ~2000 行 |
| Infra | 4 | AgentSelectionFSM/RoomManager/MoodScanner/DroneOperator |
| Hooks | 7 | LifecycleHook 链 |
| get_scene | 1 | 接入 SCENE_RULES 表 |

## 参考

- F:\Git\MaaAssistantArknights — Copilot JSON 格式参考
- https://github.com/Fate-Grand-Automata/FGA — Android 参考
- F:\Git\mower-ng — 旧重构参考

## 跨平台抽象 (3 个 ABC)

| ABC | PC 实现 | Android 实现 |
|-----|---------|-------------|
| DevicePort | PCDevicePort (包装旧 Device) | AndroidDevicePort (MediaProjection+Accessibility) |
| PauseController | ThreadPauseController (threading.Event) | HandlerPauseController (Looper) |
| StoragePort | SQLiteStorage (@app/tmp/) | SharedPrefsStorage (SharedPreferences) |

## 下次 pick up 的推荐路径

1. **AgentSelectionFSM** ← 当前焦点 (见 `.opencode/选人.md`)
2. 用 FSM 实现 ClueExecutor (计划里说"独立最先做")
3. 剩余 3 个 Planner (workshop/skill/clue — 非纯计算, 低优先)
4. 其余 Executor 逐个迁移

## 🔴 当前进行中: AgentSelectionFSM

状态机设计已完成 (`.opencode/选人.md`)
- 7 状态: PREPROCESS → FAST_CLEAR → MAIN_PREPARE → SCAN_SELECT → FREE_ASSIGN → FINAL_SORT → DONE
- 替代旧 `choose_agent()` 250 行 while+flag
- 文件位置: `scheduler/infra/agent_selection_fsm.py` (待创建)
