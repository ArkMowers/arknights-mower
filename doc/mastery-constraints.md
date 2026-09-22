# 全自动专精（训练室）功能约束与开发文档

本文件是「全自动专精（训练室）子系统」的技术规范与架构约束文档，系统梳理了该子系统在状态机、视觉判定、调度派发、排班互斥、协助位规划及外部接口上的设计约束与实现标准，供开发、维护及调试参考。

---

## 目录

1. [概述与系统架构](#1-概述与系统架构)
   - 1.1 业务边界与核心设计哲学
   - 1.2 核心模块职责与代码地图
2. [系统核心约束与不变量](#2-系统核心约束与不变量)
   - 2.1 视觉事实权威（截图权威）
   - 2.2 动作分级与进房职责隔离
   - 2.3 训练位与排班互斥保护
   - 2.4 幂等更新与通知去重
3. [状态机设计与数据持久化](#3-状态机设计与数据持久化)
   - 3.1 房间视觉状态与计划持久化状态
   - 3.2 计划生命周期与合法状态迁移
   - 3.3 异常状态收敛与恢复机制
   - 3.4 数据库表结构契约
4. [训练室视觉感知与判定矩阵](#4-训练室视觉感知与判定矩阵)
   - 4.1 屏幕检测区域与基准坐标
   - 4.2 三态倒计时判定机制
   - 4.3 状态分类矩阵与容错重试
   - 4.4 训练室特殊保护规则（逻各斯 / 艾丽妮）
5. [训练执行流与生命周期管理](#5-训练执行流与生命周期管理)
   - 5.1 开训触发入口与任务派发
   - 5.2 完整开训流程
   - 5.3 收取流程与完成收敛
6. [协助位规划与减半换人机制](#6-协助位规划与减半换人机制)
   - 6.1 协助方案双轨架构
   - 6.2 顺延减半累积机制与换人时机计算
   - 6.3 换人任务派发与执行
   - 6.4 换人异常降级与兜底策略
7. [排班系统与全局控制集成](#7-排班系统与全局控制集成)
   - 7.1 排班 Gate 检查机制
   - 7.2 专精干员状态保护
   - 7.3 全局开关 `enable_mastery` 行为边界
8. [技能命名规范与文本解析](#8-技能命名规范与文本解析)
   - 8.1 规范化技能命名格式与懒填充
   - 8.2 屏幕文本容错解析
   - 8.3 占位符技能兼容匹配
9. [推荐系统、材料核算与加工站联动](#9-推荐系统、材料核算与加工站联动)
   - 9.1 专精推荐标准与链路级材料核算
   - 9.2 加工站自动备料联动
   - 9.3 专精清空时的加工站恢复
10. [HTTP 接口契约与通知系统](#10-http-接口契约与通知系统)
    - 10.1 HTTP API 契约
    - 10.2 统一通知矩阵
11. [关键边界考量与测试验证](#11-关键边界考量与测试验证)
    - 11.1 关键边界与容错设计
    - 11.2 自动化测试集与验证命令

---

## 1. 概述与系统架构

### 1.1 业务边界与核心设计哲学

全自动专精子系统负责执行干员技能专精（专一、专二、专三）的全自动化管理，包括计划维护、材料核算、开训执行、协助位智能规划与中途换人、训练完成收取以及与基建排班系统的互斥调度。

系统遵循三项核心设计原则：

1. **视觉事实权威**：数据库记录仅代表用户的“意图配置”与调度辅助缓存。游戏界面（视觉截图）反映的是游戏运行时的不可逆物理事实。任何调度决策与状态修正均以当前房间的视觉判定结果为唯一准绳。
2. **动作分级与单次进房收敛**：进房动作严格划分为“短动作”（排班顺路状态校准/收取）与“长动作”（真正启动训练）。调度器进房时执行全量感知并在单次进房内完成收敛，严禁无谓的二次进房开销。
3. **排班隔离与防破坏**：专精占用的训练位属于不可移动设施。排班系统在任何情况下均不得覆写或强插正处于专精阶段的训练位，避免游戏内操作失败引发级联超时。

### 1.2 核心模块职责与代码地图

| 模块路径 | 核心职责 | 关键接口 / 入口 |
|---|---|---|
| `solvers/mastery.py` | 训练执行器：开训流程、开训确认、初始协助位安排、路线换人、阈值计算 | `run_mastery_task`, `run_swap_support`, `_start_new_training`, `_confirm_training_started`, `calc_swap_threshold`, `DEFAULT_ROUTES` |
| `solvers/mastery_reader.py` | 共享读取器：房态识别、三态倒计时、状态矩阵对齐、收取流程、保护判定 | `read_room_state`, `reconcile_and_act`, `reconcile_short`, `collect_flow`, `_compute_protected` |
| `utils/mastery_db.py` | 数据持久化：计划与路线 CRUD、状态原子更新、通知去重、干员忙碌判定 | `update_plan_status`, `get_active_plan`, `get_next_idle_plan`, `retry_failed_plans`, `should_notify`, `insert_plan`, `add_plan_checked` |
| `utils/mastery_support.py` | 专精协助公共层：逐计划协助规划、职业通用路线计算、参考教官表 | `plan_supports`, `profession_training_routes`, `profession_reference_trainers` |
| `utils/mastery_support_data.py` | 协助数据层：BOX 缓存、排班冲突排除、技能解锁状态核查 | `owned_roster`, `schedule_context`, `candidates`, `trainer_stats` |
| `utils/mastery_optimizer.py` | 协助求解器：多阶段动态规划求解最佳训练与接班路线 | `optimize_supports`, `stage_route` |
| `utils/mastery_support_types.py` | 协助契约类型：阶段参数、执行输入、JSON 编解码工具 | `TrainingInputs`, `StageSpec`, `decode_supports`, `encode_supports` |
| `utils/mastery_support_edits.py` | 协助编辑层：前端编辑方案校验与阶段约束拦截 | `edit_supports` |
| `utils/mastery_rules.py` | 规则编译：解析游戏数据构建训练加速规则并生成静态资源 | `compile_training_data`, `compile_buff` |
| `solvers/mastery_support_runtime.py` | 协助运行时：开训前只读预检、阶段匹配与执行态恢复 | `prepare_plan_supports`, `recover` |
| `solvers/mastery_support_dispatch.py` | 协助换人派发：换人任务调度只读入口与容错降级 | `run_planned_swap` |
| `solvers/mastery_support_state.py` | 协助执行状态：运行快照持久化、换人任务入队、告警去重 | `save_runtime`, `record_work`, `schedule_support_swap`, `notify_support_failure` |
| `solvers/mastery_support_swap.py` | 协助换人执行：实际协助者换入与槽位有效性确认 | `perform_swap`, `place_support` |
| `utils/skill_label.py` | 技能文本处理：规范化技能命名格式化与屏幕识别容错解析 | `format_skill_label`, `normalize_skill_text`, `resolve_panel_skill`, `panel_skill_matches` |
| `utils/mastery_recommendation.py` | 推荐与排程：全量干员专精推荐、仓库扫描联动与整链材料核算 | `get_mastery_recommendations`, `auto_schedule_mastery_tasks`, `get_skill_data` |
| `utils/workshop_automation.py` | 加工站联动：基于专精队列材料缺口的自动化备料接管与恢复 | `update_workshop_config`, `restore_if_no_plans`, `workshop_task_snapshot` |
| `solvers/base_schedule.py` | 排班中枢集成：训练室 Gate 拦截、任务分发、休息排除、仓库扫描钩子 | `agent_arrange_room`, `infra_main`, `observe_scheduling_train`, `_auto_schedule_mastery_after_scan`, `_dispatch_scan_start_tasks` |
| `views/mastery.py` | Web API：计划与路线配置的 HTTP 视图路由（带 Token 鉴权） | `MasteryPlanView`, `MasteryRouteView`, `MasteryPlanSupportsView`, `MasteryPlanOrderView` |
| `agent/tools/mastery_plan.py` | Agent 扩展：提供给智能体调用的计划添加与管理工具 | `add_mastery_plan` |

---

## 2. 系统核心约束与不变量

以下约束构成本子系统的核心架构基石，在后续迭代中必须无条件遵守：

### 2.1 视觉事实权威（截图权威）
- 在对训练室执行任何写操作（点击开始、更换协助位、收取完成等）前，**必须先通过截图识别房间实际状态**。
- 数据库字段（如 `status`、`expires_at`）仅作为意图追踪和调度唤醒提示，绝不能作为物理状态判定的证据。
- 当数据库状态与屏幕截图冲突时，**始终以截图为准修正数据库**：
  - 数据库显示计划处于 `training`，但屏幕为空闲：将计划重置为 `idle` 并视情况重新调度。
  - 数据库计划为 `failed` 或 `idle`，但屏幕上该干员技能正在训练：立刻将其恢复为 `training` 并纠正到期时间，撤销误判。

### 2.2 动作分级与进房职责隔离
- **长动作（开始训练流程）**：包含进房、选人、选技能、选档位、确认开训、安排协助位等一整套耗时操作，**只允许在定时任务派发链（`SKILL_UPGRADE` 任务 -> `run_mastery_task`）中执行**。
- **短动作（状态核对与顺路维护）**：在基建排班循环进房或例行检查时，通过 `reconcile_short` 执行。仅允许执行只读核查、假状态重置、静默更新到期时间、顺路收取或帮收。**严禁在排班路径内启动新的训练，且退出房间的控制权交由外部调用方维护**。

### 2.3 训练位与排班互斥保护
- 游戏机制决定了一旦训练开始，训练位干员直至专精结束无法调离。
- 排班系统（`agent_arrange_room`）在扫描房间时，若识别到训练室处于占用（`training` / `waiting_collect`）、特殊保护或识别失败状态：
  - 若用户配置了 `assistant_follows_schedule = True`，排班仅调整上排协助位（`idx0`），训练位（`idx1`）强制写入 `"Current"` 予以冻结；
  - 若 `assistant_follows_schedule = False`，排班系统直接跳过该房间，不写入任何排班调整。
- 处于活跃训练中的干员被纳入全局调度保护名单（`scheduling_protection`），宿舍休息规划（`resting`）自动忽略该干员，避免因休息调度导致房间空转冲突。

### 2.4 幂等更新与通知去重
- 数据库的所有状态变更必须通过统一入口函数完成，禁止零散的裸 SQL 写入。
- 针对用户的所有邮件与系统通知，均需通过 `mastery_notify` 表并结合特定业务维度的去重键（`dedup_key`）进行去重，确保同类型事件在单次生命周期内至多发送一次。

---

## 3. 状态机设计与数据持久化

### 3.1 房间视觉状态与计划持久化状态

系统在设计上清晰分离两层状态：

1. **房间视觉状态（`RoomState.state`）**：表示当前物理房间的屏幕视觉判定结果。
   - `empty`：训练室内无正在进行的训练。**只能靠正证据判定**：命中「空闲中」模板（`training_idle`）——三项读不出来只算「没读到」，不算空闲（见 §4.3）。
   - `training`：训练室内有正在进行的专精训练（有非零有效倒计时，干员名、技能名及专精星级清晰可见）。三项读数矛盾 / 全部读不出来时的保守结论也是 `training`（`read_failed=True`）。
   - `waiting_collect`：训练已完成，等待领奖（倒计时为 `00:00:00`，或出现“训练完成”标记）。
2. **计划持久化状态（`mastery_plan.status`）**：记录于数据库中的训练任务状态。
   - `idle`：计划就绪，等待分配资源或开训。
   - `arranging`：瞬态，表示执行器正在进入训练室并安排开训。
   - `training`：当前计划正在游戏内训练室执行。
   - `completed`：计划已达到最终目标等级，正常归档。
   - `failed`：前置条件不满足、材料不足或开训超时失败，附带 `failed_reason`。

> **关于 `waiting_collect` 状态的定位说明**：
> 虽然 `mastery_db.VALID_STATUSES` 包含 `"waiting_collect"`，且部分活跃计划查询兼容该状态，但在当前系统的写入实现中，**数据库从来不会将计划状态持久化为 `"waiting_collect"`**。当物理房间进入完成待收取阶段时，视觉状态为 `RoomState(state="waiting_collect")`；执行器收取后，数据库计划将原子地流转为 `completed`（已达目标）或 `idle`（继续下一级）。

### 3.2 计划生命周期与合法状态迁移

```
       ┌────────────────────────────────────────────────────────┐
       │                                                        │
       ▼                                                        │
   [ idle ] ────(SKILL_UPGRADE / _start_new_training)───► [ arranging ]
       ▲                                                        │
       │                                     ┌──────────────────┴──────────────────┐
       │                                     ▼                                     ▼
       │                              [ training ]                            [ failed ]
       │                                     │                        (材料不足/超时/配置错误)
       │                        ┌────────────┴────────────┐                        │
       │                        ▼                         ▼                        │
(未到目标级收取)           (达到目标级)            (视觉读出冲突/房间空)           (仓库扫描核算材料)
       │                        │                         │                        │
       └─────────────── [ completed ]                     └────────────────────────┘
```

- `idle -> arranging`：仅在 `mastery.py` 的 `_start_new_training` 长动作开始时触发。
- `arranging -> training`：当且仅当确认开训后，在训练室主页面读出有效未来倒计时（剩余时间 > 30 分钟），随同写入 `expires_at` 并重置 `swap_frozen = 0`。
- `arranging -> completed`：开训前检测到技能当前档位已满足或超过目标等级（`target_level`），直接转为完成。
- `arranging -> failed`：开训流程中遇到材料不足、超时（5 分钟纯墙钟限制）、不可恢复的槽位冲突，或安排流程中途抛出异常（`MowerExit` 除外），记录 `failed_reason` 并退出房间。异常路径的出口是 `_fail_arranging`（`mastery.py`），`failed_reason` 为 `"安排训练时出错："` 拼接异常原文。
- `arranging -> idle`：瞬态异常保护。任何对齐流程（`reconcile`）一旦发现数据库残留 `arranging` 状态，无条件重置回 `idle`。
- `training -> training`：更新到期时间。重新读取到更准确的倒计时时静默刷新 `expires_at`，不发送通知。
- `training -> completed`：收取训练成果，且主面板专精星级达到计划设定的 `target_level`。
- `training -> idle`：
  - 收取训练成果，但当前等级尚未达到 `target_level`：更新为 `idle` 并提高优先级，以备在同一会话中无缝续开下一级。
  - 房间为空或屏幕上正在训练非本计划干员：视作假记录，重置回 `idle` 并根据去重规则发送通知。
- `failed -> training`：屏幕视觉恢复。当屏幕正在进行有效训练，且干员名与技能解析结果与某条 `failed` 计划严格吻合时，撤销失败标记，恢复为 `training`。
- `failed -> idle`：两条路径都会触发，都清除 `failed_reason`：
  - 仓库材料扫描（`_auto_schedule_mastery_after_scan`）调用 `retry_failed_plans()`，批量把所有 `failed` 计划置回 `idle` 并重新评估材料；
  - 「添加到专精计划」按钮路径（`POST /mastery-plan`）撞上一条同 (干员, 技能) 的 `failed` 计划时，由 `_reuse_existing_plan` 把这一条置回 `idle`，不新建重复行，随后走派发让它排上。置回失败（写库没成功）时按错误回报给前端，不谎报「已重新排入待执行」。

### 3.3 异常状态收敛与恢复机制

- **Arranging 失败置 failed（异常路径）**：安排训练从写下 `arranging` 到训练确认开始的整段（`_start_new_training` 及其内部调用）由 `run_mastery_task` 的调用点统一包一层 `try/except`。中途抛出任何异常（`MowerExit` 除外，那是用户点了停止）都会先经 `_fail_arranging` 把计划置 `failed` 并发送一次 ERROR 通知（通知⑩，按计划 id 去重），随后异常原样上抛。排班主循环的通用兜底（记 traceback、`skip()`、`error = True`）照旧执行，本出口只补「把状态写对」这一件事。
- **Arranging 瞬态残留回收**：如果调度器在调用 `update_plan_status(id, "arranging")` 之后、进入训练室前发生网络崩溃、进程被杀或断电中断（没有代码在跑，异常出口没机会执行），该计划会停留在 `arranging`；在下一次进房检查或例行对齐时，读取器会自动检测并将其重置为 `idle`，防止该干员被排班系统永久锁定。这条是启动自检缺位时的兜底路径，与上一条不冲突。
- **冷启动与掉电恢复（视觉对齐）**：系统重启后，任务队列可能丢失或落后。排班系统在轮询至训练室时调用 `reconcile_short`，根据屏幕上的干员名、技能名和倒计时精确重构内部计划状态，并在需要时为减半换人和收取补发调度任务。
- **误报与外部干预收敛**：若用户手动在游戏内提前中止或更换了训练，系统在下次进房识别出“面板干员与活跃计划不一致”后，立即将旧计划置为 `idle`，并发送一次告警通知，随后无缝接管当前房间。

### 3.4 数据库表结构契约

系统在 `@app/tmp/data.db`（SQLite）中维护以下三张表：

#### `mastery_plan` 表（专精任务）
```sql
CREATE TABLE IF NOT EXISTS mastery_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id TEXT NOT NULL,
    char_name TEXT,
    skill_index INTEGER NOT NULL,
    skill_name TEXT,
    target_level INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    failed_reason TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    swap_frozen INTEGER DEFAULT 0,
    support_plan TEXT,
    support_runtime TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```
- `id`：自增主键，单调递增，严禁复用已删除的主键，确保外部任务与去重键引用的稳定性。
- `target_level`：目标专精等级（1、2 或 3），默认 3。
- `swap_frozen`：标记当前专精阶段是否冻结换人操作（1 表示已执行换人或换人异常，后续不再换人）。
- `support_plan`：逐计划协助规划结果（JSON 字符串），记录各阶段的初始协助者与换入协助者。
- `support_runtime`：当前执行阶段的运行时快照（JSON 字符串），包含本级生效的换人阈值、协助者状态及完成时间。

#### `mastery_route` 表（职业通用专精路线）
```sql
CREATE TABLE IF NOT EXISTS mastery_route (
    profession TEXT NOT NULL,
    supports TEXT NOT NULL DEFAULT '{}',
    is_default INTEGER DEFAULT 0,
    optimal INTEGER NOT NULL DEFAULT 0,
    half_off INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(profession, is_default)
);
```
- `profession`：职业中文名（先锋、近卫、重装、狙击、术师、医疗、辅助、特种）。特别地，`"__mastery_settings__"` 保留行用于持久化全局设置（中枢加成与换人缓冲时间）。
- `supports`：阶段协助配置的 JSON 结构，包含各等级教官名、效率、是否匹配及减半接班人。

#### `mastery_notify` 表（通知去重表）
```sql
CREATE TABLE IF NOT EXISTS mastery_notify (
    notify_type TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    sent_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (notify_type, dedup_key)
);
```
- 通过 `(notify_type, dedup_key)` 联合主键实现 `INSERT OR IGNORE` 去重。`should_notify` 查询采用 Fail-Open 准则：若数据库异常则放行发送。

---

## 4. 训练室视觉感知与判定矩阵

### 4.1 屏幕检测区域与基准坐标

以 1080p（1920×1080）分辨率为基准规范，系统定义了三个核心识别区域：

| 识别区常量 | 坐标范围 `((x1, y1), (x2, y2))` | 业务含义 |
|---|---|---|
| `PANEL_REGION` | `((235, 930), (755, 972))` | 左下角信息区：`[干员名]技能名` 文本 |
| `COUNTDOWN_REGION` | `((236, 978), (380, 1020))` | 训练位倒计时数字区：格式 `HH:MM:SS` |
| `MASTERY_ICON_REGION` | `((337, 833), (373, 866))` | 专精图标区域：用于识别当前专精星级 |

专精图标内三颗专精星位置（`MASTERY_ICON_PIPS`）：
- 专一星（顶点）：`((346, 835), (358, 847))`
- 专二星（右下）：`((353, 848), (365, 860))`
- 专三星（左下）：`((338, 848), (350, 860))`

单颗星判亮算法（`_box_is_lit`）：在框内缩进 2 像素内核区域进行亮度统计，当灰度值超过 150 且高亮像素占比 ≥ 45% 时判定为点亮。亮星数量直接对应当前正在专精的目标等级。

### 4.2 三态倒计时判定机制

倒计时读取函数（`_read_train_countdown`）放弃将所有非正常状态折叠为空值的做法，严格返回三态结构（`countdown_state`）：

1. `"active"`：成功解析出合法的未来剩余时间（`countdown` 字段为确切的完成时刻）。
2. `"zero"`：识别到倒计时读数为 `00:00:00`，表示训练已完成，进入待收取阶段。
3. `"failed"`：未读取到数字、OCR 失败或区域为空。

### 4.3 状态分类矩阵与容错重试

读取器先确认画面仍在训练室主界面（`TRAIN_MAIN`），再按「空闲中」模板与三项维度联合判定。

**空闲判定靠正证据，不靠否定式读数**：左下角「空闲中」模板（`training_idle`，`_idle_marker_visible`）命中即判空闲，面板文本、专精星、倒计时**三项都不读**。这是游戏自己给出的直接证据（空闲 = 没在专精且没有待收取，与房间里坐着谁无关），比三项否定式读数可靠，也省掉倒计时最多 5 次的重试。命中与未命中都记 debug 日志（未命中的那条是后续评估阈值的观测）。

模板未命中时才进入状态矩阵（`classify_room_state`）：

| 倒计时状态 | 干员/技能文本 | 专精星亮起 | 判定房间状态 | 动作与流转分支 |
|---|---|---|---|---|
| `zero` (00:00:00) | 任意 | 任意 | `waiting_collect` | 待收取阶段：执行收取流程 |
| `active` (非零) | 存在 | 有亮星 (1~3) | `training` | 正常训练中：核实计划匹配并维护倒计时 |
| **其余全部组合** | 任意 | 任意 | `ocr_fail` | **原地连续重试 5 次** |

**为什么 `failed` 三项全否不再判空闲**：那三项都是否定式证据——「没读到」不等于「读到了空」。三项全否只说明这次没读到东西（面板区可能读到别页的文本，倒计时区可能读到非时间文本），据此判空房会重置正在跑的计划（实机事故：219 技能选择页的天赋文本被当身份/倒计时读，正在跑的专一训练被判空房）。空闲必须有正证据：要么「空闲中」模板命中，要么训练完成横幅（`training_completed`）命中转 `waiting_collect`。

**OCR 不一致重试逻辑**：
当出现 `ocr_fail` 时，系统判定为 OCR 临时干扰或画面动画过渡，**原地重新截屏重试至多 5 次**。每一轮都重新确认画面仍在训练室主界面（`read_main_panel` 内部判，判不到返回 `None`）；画面在重试期间被换掉时读出来的东西不算数，直接结束重试。若重试 5 次后仍无法取得自洽状态，系统采取保守策略，将房间状态标定为 `training`（且 `read_failed = True`），**不修改任何状态，不安排立即重试**，静默等待下一次排班进房再次校准。

**读取时的画面确认**：`read_main_panel` 在读面板之前先确认画面还在训练室主界面，不是就返回 `None`（本次读数作废）；读取链里那个最多 5 次的重试也每轮各确认一次。`read_room_state` 与 `_retry_ocr` 拿到 `None` 一律走保守分支按训练中处理，不读槽位、不判空房。整条读取链要重试、每次重新截图，可能持续数秒；画面在这期间被换掉时，非主页面的左下角不是主面板（219 那里是协助位天赋文本），会被 OCR 当成身份/倒计时读出来。代价是每次确认多截一张图做模板匹配（约 0.2~0.3 秒）。

**进驻详情浮窗的读取范围（`read_room_state`）**：
读取器除左下角面板外，还会打开进驻详情浮窗读协助位与训练位两个槽位（`_fill_slots_and_protection`）。触发时机是 `want_mood=True`（排班 gate 读心情），或房间状态属于 `waiting_collect` / `empty` / `training`。`training` 纳入范围的目的是观测：判定日志里记下当时的协助位，读数跳变时可以直接对照是不是换了人。槽位未读（`slots_read=False`，如 OCR 失败早返回）或读失败不可靠（`slots_reliable=False`，如浮窗未确认），与「读到空位」（`slots_reliable=True` 且干员为空串 `''`）不是一回事——判定日志会分别记录「未展开进驻详情」、「进驻浮窗读取不可靠」或空干员名（`''` 与心情 `-1`）把它们严格区分开。OCR 失败那条早返回（`_retry_ocr` 五次不一致后保守按训练中）不读槽位。

### 4.4 训练室特殊保护规则（逻各斯 / 艾丽妮）

游戏机制中，干员**逻各斯**与**艾丽妮**具有特殊的“专精加速累积”机制（辅助满 5 小时后下一次同职业专精时间减半）。为防止排班系统盲目替换这二位干员导致减半增益丢失，系统建立了严格的保护检查机制（`_compute_protected`）：

- **保护生效前提**：
  1. 全局开关 `enable_mastery` 处于开启状态。
  2. 当前协助位入驻干员为**逻各斯**或**艾丽妮**。
- **分场景保护判定**：
  - **待收取状态（`waiting_collect`）**：若当前完成的档位不是专三（专一或专二），房间进入保护状态，禁止排班替换协助位，以便将减半效果顺延至下一级开训。若已是专三，保护解除。
  - **空闲状态（`empty`）**：
    - **计划干员就位旁路**：若当前进房带有待执行的开训计划（`scan_plan`），且训练位上的干员与该计划干员完全一致，开训过程不会移动训练位，保护机制不适用，**直接放行且跳过深读**（返回 `False`），彻底避免无谓点击破坏开训现场。
    - **未就位深读判定**：其余情形进技能选择页深度读取该干员的全部技能专精状态。**只要存在专一或专二技能，房间判定为受保护**，排班不得更换此二人；若全部技能为专零或已全部专三，保护解除。
    - **深读防污染保证**：深读函数（`_train_slot_has_mastery`）严格执行转场轮询，并在 `finally` 块中必定调用 `solver.back()` 等待安全退回 `TRAIN_MAIN`，严禁在异常或读取失败时将画面滞留在技能选择页。
- **开训放行特例**：
  若空闲房间处于上述保护状态，但 Mower 待执行的计划干员**恰好已经坐在训练位上**，由于此时开训无需调动训练位人员，系统允许放行 Mower 启动训练。

---

## 5. 训练执行流与生命周期管理

### 5.1 开训触发入口与任务派发

Mower 不使用轮询检测空闲，开训操作由以下两条事件驱动通路触发：

1. **仓库扫描联动派发**：
   在基建例行仓库扫描完成后，依次执行：
   `cultivateDepotSolver().start()` -> `DepotSolver().run()` -> `retry_failed_plans()` -> `auto_schedule_mastery_tasks()`。
   材料核算确认齐全的 `idle` 计划将由 `_dispatch_scan_start_tasks` 封装为 `TaskTypes.SKILL_UPGRADE` 调度任务，以当前时间入队。
   该函数为**两轮扫描**：先记下正被 reconcile 管着的键（`arranging` / `training` / `waiting_collect`），再对每个 `(干员, 技能)` 只派发第一条 `idle` 行。存量库里同一技能可能有多行（`insert_plan` 无去重），按行派发会发出多条一模一样的任务，只有一条能真跑。
2. **一键专精即时响应派发**：
   用户在 Web UI 或通过 Agent 创建新计划时，后台服务通过 `_dispatch_new_plans_immediately` 尝试即时派发：
   - 首先检查森空岛干员数据（`cultivate.json`），若过期或有新干员缺失则即时静默刷新；
   - 重新执行材料核算；
   - 若材料完备，立即入队 `SKILL_UPGRADE` 任务，并触发 `wake_scheduler` 事件唤醒调度器主循环，实现“确认添加后立即开始训练”。
   - **派发范围收窄到本次点的这几条** `(干员, 技能)`：按钮的字面意思是「把这一条排上」，不是「顺手把所有材料够的都排一遍」（与仓库扫描、批量一键专精刻意不一致）。
   - 材料不足的条目不再静默跳过，`POST /mastery-plan` 回 `insufficient` 让前端明说「材料不足，暂不开始」——旧行为是白建一行还回「已添加」。
   - **同一 `(干员, 技能)` 已有未结束的计划时不新建行**（`add_plan_checked` 统一拦截，HTTP API 与 Agent 工具两条路一起覆盖）：待执行的复用那条并派发；训练中 / 待收取的不碰不派发；`failed` 的先放回待执行（`get_all_plans` 不含 `failed`，不放回去就进不了待练名单）再派发，提示里带上此前的失败原因。`completed` 不拦——先练到专一完成、过一阵继续练专三，要能再建。数据库不加唯一约束（存量库已有重复行，直接建索引会建不上）。
3. **多级连续进阶当场续训**：
   专一或专二训练收取后，若该计划 `target_level` 尚未达成，计划状态转为 `idle` 并在当前调度会话中直接返回启动流程，无缝开启下一级专精。

### 5.2 完整开训执行流程

由 `SKILL_UPGRADE` 任务唤醒 `mastery.py` 的 `_start_new_training` 执行：

```
[进房并核验场景] ──► [校验训练位干员] ──► [进入技能选择页] ──► [核实档位是否已达标]
                                                                        │ 否 (未达标)
[安排换人/收取任务] ◄── [安排初始协助位] ◄── [确认开训并读倒计时] ◄── [点击技能并确认开训]
```

1. **进房与场景收敛**：进入训练室，收敛至主页面（`TRAIN_MAIN`）。若进房后直接发现处于技能选择页（Scene 219，未在主界面核验训练位干员身份）：
   - **自愈机制**：触发一次自愈尝试，调用 `solver.back()` 并等待返回 `TRAIN_MAIN` 重新核验训练位，核验通过后再正常进入技能选择页，避免直接保守退出导致任务在 `idle` 与扫描派发间死循环。若回退失败且仍在 219，才保守退出回 `idle` 重排。
2. **训练位核验与换人**：读取训练位人员。若训练位空缺或坐错人员，调用 `choose_train(['Current', target_operator])` 换入被训练干员并重新核验；若训练位干员已与计划一致，直接确立身份归属（`identity_confirmed = True`），点击进入技能选择页。**读不到训练位时（浮窗读取失败 / `reconcile` 未能可信地读到槽位，`RoomState.slots_reliable = False`）既不换人也不进入技能选择页**：保持 `idle`、重排到 now+2min、退出房间，等下一轮重读——「读失败」与「真空位」不可混同（截图权威：读不到就没有依据可动手）。
3. **进入技能选择页（Scene 219）**：点击技能区域进入选择列表，通过星级像素检测读取目标技能当前的实际专精星级。
4. **已达标检测（Target Check）**：若检测到当前星级已 ≥ `target_level`，无需重复训练，将计划更新为 `completed` 并发送完成通知。
5. **确认开训**：点击对应技能行，在弹出的开训确认页（Scene 218）点击对钩确认。若因材料缺损弹出错误窗（`TRAIN_SKILL_UPGRADE_ERROR`），将计划更新为 `failed`（`failed_reason="材料不足"`）并告警退出。
6. **场景退出与倒计时核实**：开训成功后游戏退回技能页，执行退出操作返回训练室主界面，读取左下角倒计时。倒计时确认有效后，将数据库计划状态原子更新为 `training`，写入 `expires_at`。
7. **初始协助位入驻**：调用 `_arrange_support`，根据协助规划（逐计划或通用路线）换入对应的初始协助干员。返回值 `None` = 不用安排或已安排成功，错误文案 = 这一级没安排成（取路线失败或换人失败）。
8. **倒计时校准与任务排程**：协助位变更后倒计时产生加速突变，用带重试的读法（最多 5 次，每次确认训练室主页面、浮窗先关）重读最终倒计时并刷新数据库 `expires_at`。调用 `_schedule_swap_if_needed` 决定是安排中途换人任务（`SWAP_SUPPORT`）还是直接安排收取任务。

**收尾步骤的就地容错**：第 6 步把状态置 `training` 之后，「训练已经在跑」的收尾步骤（第 7、8 步，以及协助者出勤记录 `refresh_end`、中途换人任务、到点收取任务）**各自就地处理异常**，绝不外抛——外抛会被 `_fail_arranging` 把正在跑的训练记成失败。失败只记日志，并在开训邮件（级别仍为 INFO，训练确实开始了）末尾追加一句如实说明：

| 失败步骤 | 邮件补充句 |
|---|---|
| 换协助位后没能重读到剩余时间 | `换协助位后没能重新读到剩余时间，完成时间按换人前的读数记，实际可能更早` |
| 协助者出勤记录没保存（`refresh_end`） | `协助者出勤记录没能保存，下一级开始时可能算不准减半时长` |
| 没能安排中途换人 | `没能安排中途换人（原因），这一级的减半累积没做上，下一级可能不会减半` |
| 协助位没能安排（第 7 步取路线失败） | `协助位没能安排（原因），这一级仍按原协助位练完` |

第 8 步到点收取任务排不上时另发一封 WARNING（通知⑪ `collect_schedule`，按计划 id 去重）：`{干员} {技能} 专{N}：到点收取任务没能排上（原因），稍后进训练室时会顺路收取`。中途换人的目的是给**下一级**攒减半时长（减半累积在上一级），排不上丢的是下一级的减半，这一级的训练照旧在跑，所以只报告、不标失败；「排了换人就不排收取」的连带也不成立——换人任务排不上时收取任务照常排。

**失败出口**：以上整段由 `run_mastery_task` 在调用点统一包一层 `try/except`。中途抛出任何异常（`MowerExit` 除外）先经 `_fail_arranging` **复核计划当前状态**：仍是 `arranging` 才把计划置 `failed`、`failed_reason` 记 `"安排训练时出错："` 加异常原文，并发送通知⑩（按计划 id 去重）；已经是 `training`（收尾阶段出错）则**不改状态、不发通知**，异常照旧上抛。这样「失败」有确定的意思——看到失败，就是这次训练没开起来。读状态读不出来（DB 异常 / 计划已删）时按「还停在 `arranging`」处理，照旧置失败——「不得留在 `arranging`」是硬要求。异常上抛后由排班主循环的通用兜底（记 traceback、跳过本轮、插一次纠错）接手。正常该回 `idle` 的出口（训练室有人在练、待收取、技能选择页归属未确认、档位读取失败）走 `_exit_occupied`，不属于失败；该函数只把**真正从屏幕上读到**的干员写进重检任务标签（`{干员}（技能） 重读训练室状态`，读不到就只有 `重读训练室状态`），退出原因进日志不进标签。

### 5.3 收取流程与完成收敛

当房间视觉状态进入 `waiting_collect`（倒计时为 `00:00:00`）时，由 `collect_flow` 执行安全收取：

1. **点击完成标记**：在主页面识别并点击 `training_completed` 模板，进入结算横幅页。
2. **确认跳过**：等待并点击 `skill_collect_confirm` 按钮跳过动画。
3. **拍照留证与专三邮件**：在结算界面抓取高清截图。若本次收取对应专三（M3）完成，立即发送带截图的完成通知邮件。
4. **数据库收敛**：
   - 目标等级达成：将计划更新为 `completed`。
   - 存在后续等级：将计划状态更新为 `idle` 并提高优先级，以便调度器当场续训。
5. **退出结算**：再次点击确认按钮，轮询确认画面完全退回训练室主界面。
6. **未托管计划帮收**：若屏幕完成的训练不属于 Mower 数据库中的任何活动计划（例如用户手动开启的训练），系统执行静默收取，并发送“帮忙收取”通知（通知④），避免训练室永久被堵塞。

---

## 6. 协助位规划与减半换人机制

### 6.1 协助方案双轨架构

系统支持两套解耦的协助位方案：

1. **逐计划自动方案（`support_plan`）**：
   - 用户已同步森空岛 BOX 时的默认首选方案。
   - 依据干员实际精英阶段、等级、分支及专属加成，由动态规划算法（`mastery_optimizer.py`）计算总耗时最短的阶段配置。
   - **排班排除法则**：主排班与所有备用排班中，只要出现在任何非训练室设施（包括宿舍）的主力或替换干员，均自动从候选教官名单中剔除。
   - **控制中枢加成推导**：若排班中枢名单中存在阿斯卡纶、烛煌或斩业星熊，系统自动推导中枢加速 +5%。
2. **职业通用路线（`mastery_route` 与 `DEFAULT_ROUTES`）**：
   - 无 BOX、未同步或用户显式指定使用通用路线时的回退方案。
   - 预设 8 个职业在专一、专二、专三阶段的标准初始干员与换入干员。
   - 全局设置行（`__mastery_settings__`）统一存储中枢加成偏置与换人缓冲时间，对所有职业统一生效。

### 6.2 顺延减半累积机制与换人时机计算

**游戏减半机制**：艾丽妮（近卫/狙击）与逻各斯（术师/辅助/先锋/特种等）的减半技能为**顺延机制**——协助位累计辅助专精时间**超过 5 小时（300 分钟）**，则**下一次同职业专精基础时间减半**（例如 16 小时减为 8 小时）。换人操作的核心目标是让减半干员在当前等级训练结束前，恰好在岗工作满 5 小时加安全缓冲。

换人计算公式（`calc_swap_threshold`）：
- 目标在岗时长：`target_minutes = 300 + buffer`（默认缓冲为 10 分钟，即 310 分钟）。
- 速率折算：
  $$\text{swap\_total} = 100 + 5 + (30 \text{ if job\_match else } 0) + \text{central\_bonus}$$
  $$\text{current\_total} = 100 + \text{current\_efficiency} + 5$$
  - *保守口径*：中枢加成（`central_bonus`）在计算排期时仅分配给减半接班人，不预先假设路线干员享受中枢加成，确保换人时机“只早不晚”，杜绝因中枢换班导致减半时间累计不足 5 小时。
- 换人阈值（倒计时剩余分钟数）：
  $$\text{threshold} = \text{target\_minutes} \times \frac{\text{swap\_total}}{\text{current\_total}}$$
- **301 分钟收益守卫（值得门）**：
  $$\text{real\_time\_after\_swap} = \text{remaining\_minutes} \times \frac{\text{current\_total} + \text{central\_bonus}}{\text{swap\_total}}$$
  若换人后该干员实际折算在岗时间 $< 301$ 分钟，意味着无论如何无法累计满 5 小时，换人毫无意义，系统将**直接放弃换人**并保持原教官。
- 最终目标级（专三）永不换人：专三已是技能终点，不再需要为后续阶段累积减半，路线数据中 `swap_target` 恒定为 `None`。

### 6.3 换人任务派发与执行

1. **任务入队**：开训倒计时确认后，根据剩余时间是否超过阈值计算换人时刻，将 `TaskTypes.SWAP_SUPPORT` 任务入队。
2. **执行前身份核查**：换人任务触发时，首先在主界面核对训练位倒计时。随后打开进驻详情浮窗读取实际在岗协助者：
   - **已是目标接班人**：表明此前已完成换人，无需重复操作。
   - **协助位为空（空位定夺）**：直接根据当前剩余时间一步定夺——若满足换人门槛且值得换，直接放入减半干员；若剩余时间尚早，放入原路线干员拿前半程加成，并重新安排稍后的换人任务。
   - **在岗者为陌生人（坐错人员）**：首先纠正为路线初始教官，重读倒计时后重新评估是否换人。
3. **完成换人**：调用换人指令进驻减半干员，换人完成后标记 `swap_frozen = 1`，防止后续流程产生误换。随后重新读取倒计时并安排最终的收取任务。

### 6.4 换人异常降级与兜底策略

- **换人重试机制**：换人执行过程中若遇到网络波动或控件未响应，立即原地重试，上限为 5 次（`SWAP_RETRY_LIMIT`）。
- **降级放弃与收取保全**：若重试耗尽或当前剩余时间已跌破 5 小时，系统执行降级放弃，发送换人失败通知（通知⑧或⑨）。**此时无论换人是否成功，均强制为当前训练安排收取任务**，确保后续专精成果按时领回，不因换人失败导致房间永久卡死。

---

## 7. 排班系统与全局控制集成

### 7.1 排班 Gate 检查机制

排班主流程在轮询安排设施时，对训练室实行专属 Gate 拦截（`base_schedule.py`）：

1. **物理读房**：每轮心情刷新都将训练室加入待读房间，使用房间级 2.5 小时限频避免调度循环反复进房；即使训练室静态排班为空、没有活动专精计划或关闭 `enable_mastery`，也会读取训练位。
2. **工作干员冲突停机**：训练位干员若出现在主排班或任一备用排班的非训练室主力／替换中，立即发送 WARNING、设置 `stop_mower` 并退出。自动专精的仓库扫描派发和真正开训前也使用同一名单复核；计划允许保留，但冲突解除前不换人、不开始训练。
3. **顺路短动作更新（`reconcile_short`）**：
   - 处于开启状态时，根据截面对齐数据库（纠正假活跃、核实倒计时）。
   - **防抢收竞态控制（`defer_collect = True`）**：若房间存在待收取的训练，且调度队列中已存在计划专精任务，排班 Gate 会**跳过本次顺路收取**，将收取动作留给专精任务自身处理，避免在队列中留下无主的死任务。
4. **互斥判定与跳过**：
   - 若房间处于占用（`locked`，含训练中与待收取）、受特殊保护（`protected`）或读房失败（`room_state is None`）：
     - `assistant_follows_schedule = True`：训练位写入 `"Current"` 冻结，仅安排协助位。
     - `assistant_follows_schedule = False`：整房跳过，直接退出，保持物理现状。

### 7.2 专精干员状态保护

- **排班互斥集（`protected_names`）**：状态处于 `arranging`、`training` 或 `waiting_collect` 的干员名称会被加入全局排班保护集合。批量排班引擎（`scheduling_batch.py`）将禁止把上述干员分配给其他任何基建房间。
- **休息规划豁免（`resting`）**：当全局专精开启且数据库存在活跃专精任务时，训练室内的干员自动从宿舍休息计算中剥离，避免产生让专精干员回宿舍休息的无效调度。

### 7.3 全局开关 `enable_mastery` 行为边界

全局开关 `config.conf.enable_mastery` 具有清晰的行为边界：

| 行为类别 | 开启 (`enable_mastery = True`) | 关闭 (`enable_mastery = False`) |
|---|---|---|
| 自动开训派发（定时/即时） | 正常派发 `SKILL_UPGRADE` 任务 | **完全停用**，不产生开训任务 |
| 自动换协助位与减半调度 | 正常计算并执行换人 | **完全停用**，跳过协助位换人 |
| 自动收取与完成结算 | 正常收取并处理后续阶段 | **完全停用**，不主动收取 |
| 排班 Gate 顺路状态修正 | 执行 `reconcile_short` 校准 | **完全停用**，排班时不触碰专精数据库 |
| 工作干员训练位冲突检查 | **保持生效**：冲突时 WARNING 并停止 Mower | **保持生效**：冲突时 WARNING 并停止 Mower |
| 特殊保护（逻各斯/艾丽妮） | 按规则执行房间保护 | **完全停用**，`_compute_protected` 恒返回 False |
| **排班训练位防卡检查** | **保持生效**：锁定房间不强排 | **保持生效**：避免强塞导致排班超时饿死 |
| **仓库材料扫描与推荐计算** | **保持生效**：扫描并刷新材料 | **保持生效**：保留后台材料盘点与建议 |

---

## 8. 技能命名规范与文本解析

### 8.1 规范化技能命名格式与懒填充

- **唯一标准命名格式**：`{序数}技能·{技能真名}`，例如 `一技能·精神爆发`、`二技能·飞翔瞪射`、`三技能·假日风暴`。
- **统一格式化器（`format_skill_label`）**：前端展示、邮件通知、日志输出与持久化存储均统一调用此函数。传入真名时自动拼装为规范格式；已符合规范的文本原样返回。
- **懒填充机制（`lazy_fill_plan_names`）**：历史残留数据或外部 API 创建时若缺失干员中文名或技能真名，数据库读取管道在向业务层交付前会自动通过 `skill_data.json` 懒填充真名，确保消费端永远获得规范命名的对象。

### 8.2 屏幕文本容错解析

游戏内训练室左下角面板为小字号文本，且常常受到前置符号、特殊字符与长技能名截断影响：

1. **面板干员提取（`_parse_panel_text`）**：从左括号 `[`（含全角 `【`/`［`）与其后的右括号 `]`（含全角 `】`/`］`）之间提取干员姓名，两界均可半角全角混用，且自动剥离括号前的 OCR 噪点。左括号整个被漏识（`泡泡]飞翔瞪射`）时改用右括号定位：右括号左边的文本作干员名、其后作技能名——技能名不含方括号（`skill_data.json` 的 1147 条技能名条目实测零命中，去重后 907 条），故右括号只可能来自干员名定界符。左右括号都漏识（`泡泡飞翔瞪射`）时无从定位姓名边界，仍按纯技能名交付。
2. **唯一反查解析器（`resolve_panel_skill`）**：
   将识别到的技能文本与该干员在 `skill_data.json` 中配置的已知技能列表（至多 3 个）进行归一化互含匹配（文本去空格、去特殊标点）。仅当能在该干员技能池中**无歧义地唯一命中**某一技能时，才返回对应技能序号（0/1/2）；若存在多重歧义或未收录，则返回空并降级。

### 8.3 占位符技能兼容匹配

- 当干员属于游戏最新实装但静态资源尚未补充技能真名时，系统允许使用 `技能1`、`技能2`、`技能3` 占位符。
- 占位符计划在进行屏幕面板比对时享有**单向豁免权**：若屏幕读出了真实技能真名，系统对照技能序号放行匹配，不因数据库存储为占位符而误判为“假记录”。

---

## 9. 推荐系统、材料核算与加工站联动

### 9.1 专精推荐标准与链路级材料核算

- **推荐门槛**：干员已提升至精英二阶（`evolvePhase >= 2`），且技能当前等级尚未达到专三。
- **目标等级对齐**：所有推荐与创建入口（Web UI、Agent 工具）统一默认目标等级为专三（`target_level = 3`）。
- **整链材料核算**：从当前专精等级提升至目标等级所需的全部精英材料与技巧概要实行链路级汇总。在自动排程（`auto_schedule_mastery_tasks`）计算中，按计划优先级顺序扣减虚拟仓库库存，只有**整条升级链所需全部材料库存均满足**时，计划才被标记为 `scheduled`。

### 9.2 加工站自动备料联动

专精子系统与加工站自动化模块（`utils/workshop_automation.py`）深度协同：

1. 加工站备料引擎按专精队列优先级，自动为队首技能准备升级所需材料配方。
2. 当队首技能正在训练且倒计时处于安全窗口时，系统允许提前为队列中下一个 `idle` 技能合成材料，同时预留当前技能后续阶段所需的下位材料。
3. 详细配方调度规则与保护策略参见 [加工站干员设置文档](workshop-operators.md)。

### 9.3 专精清空时的加工站恢复

当所有专精任务全部执行完成，或用户清空了专精计划列表时，`views/mastery.py` 在删除操作后自动触发 `restore_if_no_plans()`，加工站自动化模块立即解除材料合成接管，将加工站的配置与干员阵容平滑恢复为用户原本保存的手动配置。

---

## 10. HTTP 接口契约与通知系统

### 10.1 HTTP API 契约

所有 API 路由均挂载于 `mastery` 蓝图下，若服务端启用了全局 Token，所有请求头必须携带有效的 `token` 字段，否则返回 HTTP 403。

| HTTP 路由 | 方法 | 功能描述 | 请求参数 / 载荷规范 | 响应结构 |
|---|---|---|---|---|
| `/mastery-plan` | `GET` | 获取计划列表与历史记录 | 无 | `{"plans": [...], "history": [...]}` |
| `/mastery-plan` | `POST` | 创建专精计划并尝试即时派发 | `{"items": [{"name": str, "skill_index": int, "target_level": int, "support_mode": "auto"\|"route"}]}` 或扁平字典 `{"干员名": skill_index}` | `{"results": [{"key": str, "status": "added"\|"existing"\|"insufficient"\|"error", "id": int, "reason": str}]}`。`added` = 新建并派发；`existing` = 该技能已有计划，未新建（`reason` 说明是已在计划中 / 已在训练中 / 此前失败已重新排入待执行）；`insufficient` = 材料不足，暂不开始；`error` = 校验失败，`reason` 为原因 |
| `/mastery-plan` | `DELETE` | 删除指定计划并清空残留调度 | `{"id": int}`（强类型校验，拒绝非整数与布尔值） | `{"status": "ok"}` |
| `/mastery-plan/order` | `PATCH` | 批量更新计划优先级 | `[{"id": int, "priority": int}]` | `{"status": "ok"}` |
| `/mastery-plan/supports` | `GET` | 获取可用协助者与中枢加成推导 | 无 | `{"operators": [{"name": str, "blocked": [str]}], "central_bonus": int}` |
| `/mastery-plan/supports` | `PATCH` | 修改指定计划的协助方案 | `{"id": int, "stages": [...]}`（严格校验阶段锁定与状态并发） | `{"status": "ok", "support_plan": [...]}` |
| `/mastery-route` | `GET` | 查询职业通用路线配置 | 无 | `{"routes": {...}, "defaults": {...}, "best_trainers": {...}, "settings": {...}}` |
| `/mastery-route` | `POST` | 保存指定职业的通用路线 | `{"profession": str, "supports": list\|dict\|str}` | `{"status": "ok"}` |
| `/mastery-route/settings` | `GET/POST` | 查询或设置全局换人缓冲与中枢加成 | `{"central_bonus": 0\|5, "mastery_swap_buffer": int}` | `{"status": "ok"}` |
| `/mastery-history` | `DELETE` | 清空专精历史记录 | 无 | `{"status": "ok"}` |

### 10.2 统一通知矩阵

系统统一定义了 11 类通知，通过 `mastery_notify` 表实施去重，确保业务生命周期内绝不重复打扰：

| 编号 | 通知类型 (`notify_type`) | 触发时机 | 级别 | 去重键格式 (`dedup_key`) | 核心内容 |
|---|---|---|---|---|---|
| ① | `blocked` | 训练室内存在非 Mower 托管的外部训练占用 | INFO | 结束时间字符串或 `"unknown"` | 提示训练室被占用，附预计空出时间 |
| ② | `fake_reset` | 活跃计划干员/技能与屏幕真实画面冲突 | WARNING | `str(plan_id)` | 提示数据库状态异常并已自动重置回待执行 |
| ③ | `m3_collect` | 专三（M3）训练顺利完成收取 | INFO | `str(plan_id)` | 邮件附带结算截图，汇报干员技能专三达成 |
| ④ | `help_collect` | 顺路帮收外部或未托管干员的专精成果 | INFO | `{operator}:{skill}` | 提示帮收了不在计划内的专精训练 |
| ⑤ | `protected` | 训练室受保护（逻各斯/艾丽妮在岗）导致 Mower 无法开训 | WARNING | `{support_slot}:{train_slot}` | 提示训练室受减半保护，已跳过本次开训 |
| ⑥ | `at_target` | 开训前检测到技能已达到或超过目标等级 | INFO | `str(plan_id)` | 提示技能已达标，计划已自动完成归档 |
| ⑦ | `swap_correction_failed` | 通用路线协助位坐错人，纠正为原教官失败 | WARNING | `str(plan_id)` | 提示纠正协助者失败，本次训练跳过减半换人 |
| ⑧ | `swap_failed_giveup` | 通用路线减半换人连续失败超限或不足 5 小时 | WARNING | `str(plan_id)` | 提示换人失败已放弃，减半收益可能丢失 |
| ⑨ | `support_swap` | 逐计划协助换人执行失败或减半时长累计不足 | WARNING | `{plan_id}:{level}` | 提示特定阶段换人失败，已降级保全正常收取 |
| ⑩ | `arrange_error` | 安排训练中途抛出异常（`MowerExit` 除外），计划仍停在 `arranging` | ERROR | `str(plan_id)` | 提示本次安排失败并附异常原文，状态已置失败、待仓库扫描重试 |
| ⑪ | `collect_schedule` | 训练已开始后，到点收取任务没排上 | WARNING | `str(plan_id)` | 提示少了一次到点收取，稍后进训练室会顺路收取（训练本身不受影响） |

---

## 11. 关键边界考量与测试验证

### 11.1 关键边界与容错设计

1. **不可撤销机制容错**：游戏内训练一旦开启无法中途取消。因此，系统绝不会因为数据库误判或网络异常主动去点按界面上的重置类按钮；在屏幕状态未取得 100% 把握前，严禁点击任何确认类控件。
2. **删除计划残留消除**：删除计划（`DELETE /mastery-plan`）不仅物理清理数据库，还会同步移除调度器活任务队列中对应 `plan_key` 的调度项，并重写已持久化的队列快照，彻底根除重启后已删除计划被死灰复燃派发的问题。
3. **Fail-Open 通知设计**：通知去重机制采用“宁可偶发多报，不可漏报重要异常”的取向。当去重数据库发生磁盘只读或 IO 错误时，`should_notify` 默认放行发送。

### 11.2 自动化测试集与验证命令

涉及本子系统的代码修改必须通过以下核心测试集的检验：

```bash
# 1. 专精核心测试集（读取器、状态机、DB、换人公式、Web视图与调度契约）
pytest arknights_mower/tests/mastery_reader_tests.py \
       arknights_mower/tests/mastery_db_tests.py \
       arknights_mower/tests/mastery_arranging_tests.py \
       arknights_mower/tests/mastery_formula_tests.py \
       arknights_mower/tests/mastery_view_tests.py \
       arknights_mower/tests/mastery_task_contract_tests.py \
       arknights_mower/tests/base_scheduler_tests.py -q

# 2. 逐计划协助方案专项测试集
pytest arknights_mower/tests/mastery_support_*tests.py -q

# 3. 代码风格与规范核查
ruff check arknights_mower/solvers/mastery*.py \
           arknights_mower/utils/mastery*.py \
           arknights_mower/views/mastery.py
```
