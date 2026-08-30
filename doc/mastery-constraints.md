# 全自动专精（训练室）功能约束文档

> 协作入口：本文件把「全自动专精子系统」的设计约束、不变量、待办风险浓缩成一份参考。
> 决策源头：GitHub issue [#55（Wayfinder Map）](https://github.com/NiceAfternoon/arknights-mower/issues/55) 及子票 #56–#63、#60。
> 代码：fork `NiceAfternoon/arknights-mower`，分支 `feat/mastery-rewrite`。
>
> 改动涉及本子系统的任何代码前，先读「§3 铁律」；改完跑「§15 验证」。

## 目录
1. 这是什么 / 适用边界
2. 模块地图
3. 铁律（最高优先级，违反即缺陷）
4. 计划状态机（DB）
5. 共享读取器与恢复矩阵
6. 收取流程与通知
7. 减半换人（协助位）
8. 排班集成（#59 gate）
9. 全局开关 `enable_mastery`
10. 技能名规范
11. DB 契约
12. 推荐 / 自动排程
13. HTTP API 契约
14. 待办 / 已知风险（实机校准等）
15. 验证方式
16. #73 进房读全再判定 + 状态矩阵重设计（2026-08-14 定案，待实现）

---

## 1. 这是什么 / 适用边界

全自动专精 = 干员技能训练（专精 1/2/3）的全自动执行。地图 #55 四块工作：

1. **① 恢复/纠错**：重启后、游戏内被干预后，以截图为准纠正 DB 状态并继续执行。
2. **② 全局开关**：`enable_mastery` OFF 停专精自动化、保留仓库扫描。
3. **③ 调度效率**：每级最多 3 次进房，事件驱动非轮询。
4. **④ 冲突修复**：排班不再硬改被专精锁定的训练位。

**已删除的旧代码（#60）**：`base_schedule.py` 中 `refresh_skill_time` 链、`skill_upgrade` 旧入口、`has_in_progress_plan/get_pending_plans` 段已全部删除。`REFRESH_TIME` 任务现在**只**做 `plan_run_order`，不含任何专精/占用逻辑。

## 2. 模块地图

| 模块 | 职责 | 关键入口 |
|---|---|---|
| `solvers/mastery.py` | 执行流：开始训练、确认开始、协助位安排、换人 | `run_mastery_task` / `run_swap_support` / `_start_new_training` / `_confirm_training_started` / `calc_swap_threshold` / `DEFAULT_ROUTES` |
| `solvers/mastery_reader.py` | 共享读取器：读房、恢复矩阵、收取、通知、gate 辅助 | `read_room_state` / `reconcile_and_act` / `reconcile_short` / `collect_flow` / `train_slot_locked` |
| `utils/mastery_db.py` | 计划/路线 DB、通知去重、`is_operator_busy` | `update_plan_status` / `get_active_plan` / `get_next_idle_plan` / `retry_failed_plans` / `should_notify` / `insert_plan` / `get_route` |
| `utils/skill_label.py` | 技能名规范唯一格式化器 | `format_skill_label` / `normalize_skill_text` / `panel_skill_matches` |
| `utils/mastery_recommendation.py` | 推荐 + 自动排程 + 仓库扫描联动 + 材料核算 | `get_mastery_recommendations` / `auto_schedule_mastery_tasks` / `compute_workshop_config` / `get_skill_data` |
| `utils/scheduler_task.py` | 任务类型定义 | `TaskTypes.SKILL_UPGRADE / SWAP_SUPPORT / REFRESH_TIME` |
| `solvers/base_schedule.py` | 排班集成：gate L0/L1、dispatch、`resting`、仓库扫描钩子 | `agent_arrange_room`（train gate）/ `infra_main`（dispatch）/ `_auto_schedule_mastery_after_scan` / `_is_mastery_busy` |
| `views/mastery.py` | HTTP API（token 保护） | `GET/POST/DELETE /mastery-plan`、`PATCH /mastery-plan/order`、`GET/POST /mastery-route` |
| `agent/tools/mastery_plan.py` | agent 工具：新增计划 | `add_mastery_plan` |

**依赖关系**：`mastery.py`（执行）→ `mastery_reader.py`（读）→ `mastery_db.py`（数据）；`base_schedule.py` 是调度中枢，通过 dispatch 调 `mastery.py`、通过 gate 调 `mastery_reader.py`。

## 3. 铁律（最高优先级，违反即缺陷）

以下规则没有任何例外，改动时不得放宽：

1. **截图权威**：任何训练室动作之前**必须先读房**（主页面面板）；DB 只是「意图缓存」，DB 与截图冲突**以截图为准**，**适用于所有计划状态（含 failed/idle）**——failed/idle 计划读到面板匹配 + 倒计时 active → 恢复 training（#98，见 §4 SM-09 例外 / §16.4）。（`mastery_reader.py:6-10`，#61/#63/#98）
2. **`expires_at` 只是调度提示**，永不作为判定权威；训练状态永远从房内截图读。（#61）
3. **一次进房做完全部**：读全部状态 + 做全部动作，不拆成两次进房。（#61/#63）
4. **开始训练（长动作）只由 `SKILL_UPGRADE` dispatch（`run_mastery_task`）执行**；排班路径 / `reconcile_short` 只做短动作（核实/帮收/重置/对账），**永不开始训练、永不退出房间**（退出由调用方 gate 负责）。（#61/#63）
5. **协助位只动在训练确认开始之后**；确认开始之前不得改协助位。（#16 §8）
6. **协助位安排无守卫例外（2026-08-17 #103 删减半守卫）**：路线 operator 每次开始照常安排，**跨「收取 → 下一次开始」边界也不例外**——`arrange_support` 恒 True，收集级联不再传 False；「专三不换减半对象」由路线数据保证（level_3 路线 `swap_target=None`，见铁律 7），不靠「不动协助位」。（#63 → #103；详见 §7 C-15）
7. **专三（当前步）永不换人**（调度侧与执行侧都要挡）：由 level_3 路线 `swap_target=None` 保证（#76 2026-08-15 用户定案删显式 `target_level==3` 守卫、靠路线数据；自定义路线若给专三填 swap_target 会打破该保证）。
8. **通知共 8 类（①-⑧，完整清单见 §16.9）、各至多一次**，用 `mastery_notify` 表去重。（#61/#73/#79/#81）
9. **ARRANGING 超时/失败必须置 `failed`**（不得置 `idle`，否则 infra 主循环每轮重派 idle 刷屏）；**不得在 ARRANGING 内重试**，重试只走仓库扫描 `retry_failed_plans()`。（#15/#19）
10. **`enable_mastery=False` 时任何训练室动作/通知/守卫都不执行**（dispatch/reconcile/swap 直接返回）；但 N 小时仓库材料扫描 + DB 自动排程**保留**。（#55 ②）
11. **排班永不写锁定训练位（idx1）**，与 `enable_mastery` 开关无关：`assistant_follows_schedule=False` 整房跳过，`True` 冻结 idx1=Current。（#59）

## 4. 计划状态机（DB）

### 状态集合（唯一合法值，`update_plan_status` 拒绝其它字符串）
`idle` / `arranging` / `training` / `waiting_collect` / `completed` / `failed`
（`mastery_db.py:47-54`）

> ⚠️ **`waiting_collect` 陷阱**：它在合法状态集内、也被 `get_active_plan`/`is_operator_busy` 查询，但**当前没有任何代码路径把它写进 DB**——它是读取器根据截图推导出的 `RoomState`。若未来有人假设 DB 会存 `waiting_collect`，行为会静默改变。（open_risks）

### 一次一个 active
`get_active_plan()` 返回状态 ∈ {arranging, training, waiting_collect} 的唯一计划（LIMIT 1）；不存在多个 active。（`mastery_db.py:204-214`）

### 合法迁移（约束）
- `idle → arranging`：**只在** `_start_new_training` 内（长动作，归 SKILL_UPGRADE dispatch）；排班 gate / `reconcile_short` 不得触发。（SM-02）。**空闲 idle 计划由带 plan_key 的 SKILL_UPGRADE dispatch 拉起**（#74 第3段，2026-08-14 用户拍板「都去掉」：任何 plan_key 任务在空闲格都会开始其指定计划，无逻辑标记）；收取后继续本级一律当场开（同样无记号）。（见 §8 / §11 TASK-01）
- `arranging` 是**瞬态**：任何后续 reconcile 遇到仍为 arranging 的计划，**无条件重置 idle**，绝不假设 arranging 能跨 dispatch 存活。（SM-01 / C-07）
- `arranging → training`：**只在读到有效倒计时**（结束时间 > now+30min）后；同一 `update_plan_status` 里必须同时写 `expires_at` 和 `swap_frozen=0`。（SM-03）
- `arranging → completed`：合法，走「已到target检测」（技能选择页读目标槽档位 ≥ target）。（SM-04）
- `arranging → failed`：必带 `failed_reason`；覆盖 5 分钟纯墙钟超时（无加载豁免）、材料不足、换错人失败；标记后退出房间 + 恰好一次 ERROR 通知。（SM-05）
- `training → training`（更新 expires_at）：静默重读倒计时、刷新 expires_at、重排收取任务，**不发通知**。（SM-06 / C-06）
- 收取对账：档位 == target → `completed`（**不级联**，等扫描，用户定案 #74 第2段）；档位 ≠ target → `idle`（继续本级），**一律当场开下一级**（2026-08-14 用户拍板「都去掉」：不分扫描链/重启，重启后也不保守等扫描；材料不足由确认页 fail-fast 兜底）。**档位高于目标不记账完成**（#67/B6：专二收取不得关掉专一计划——本次收取不属于早已满足的计划，保持 idle 由已到target检测正确完成）。（SM-08 / #67 / #74 第3段）
- `completed` 是执行循环的终态：从 `get_all_plans` 和 `_match_plan` 排除，只进 `get_all_history`；**唯一回到 idle 的路是 `retry_failed_plans()`**。（SM-09 / DB-03）
- `failed` **例外（#98，2026-08-16）**：通常同 completed 视为终态（`get_all_plans` 不含 failed），但 reconcile 计划集 **`get_reconcile_plans` 纳入 failed**（= 非终态 + failed，completed 仍排除，按 priority/id 排序）——面板干员名+技能名**都可读且与某计划匹配** + 倒计时 active → 该 failed 计划恢复 training（撤销 false-failure，**不依赖 `retry_failed_plans`**）；不可读/含混 → 不恢复、静默等待（B8 稳为先）。failed 待收取阶段**不接管**（防无材料强开下一级），由扫描 `retry_failed_plans` 兜底。（SM-09 / DB-03 / #98）
- `failed → idle`：仅 `retry_failed_plans()`（清 `failed_reason`），且只从仓库扫描路径 `_auto_schedule_mastery_after_scan` 调用。（DB-06）

### 其它
- 所有计划字段/状态改动必须走 `update_plan_status`（改优先级用 `update_plan_priority`）；**HTTP API 只能 insert/delete/reorder，不得直写 status**。（DB-02）
- 表结构演进走 `_ensure_tables` 的 DROP-or-ALTER 模式：缺 `target_level` 就 drop 表，缺 `optimal`/`half_off` 用 ALTER ADD COLUMN；不得用裸 CREATE TABLE 引入新必填列。（DB-07）

## 5. 共享读取器与恢复矩阵

> ⚠️ **#73 已实现（2026-08-14）**：本节已被 §16 取代——进房先读两样（进驻详情浮窗 + 左下角）→ 三态倒计时 → 状态矩阵（待收取/空闲/训练中 + OCR失败6组合原地重试5次）→ 保护检查（逻各斯/艾丽妮）。完整定案与实现索引见 §16。本节保留仅供考古。

### 房间分类约定（`classify_room_state`）
- `TRAIN_FINISH` → 恒 `waiting_collect`。
- `TRAIN_MAIN` → 有未来倒计时 = `training`；无有效倒计时且无 `training_completed` 模板 = `empty`；有模板则升级为 `waiting_collect`。
- 其它房内场景**保守视为 `training`**。
- `training`/`waiting_collect` 均算「锁定」。（C-37 / MX-10）

### 恢复矩阵（DB 行 × 截图列）
| DB | 截图 | 动作 |
|---|---|---|
| arranging | 任意 | 先重置 idle，再继续对账（不发通知） |
| active(training) | 🔴 training 一致 | 静默 `_refresh_training_plan`：重读倒计时、刷新 expires_at（同值跳过 DB 写）、先换人判定再排收取——排了换人则不排收取（§16.10 半重叠消除，**#82**）；不发通知 |
| active | 🟡 waiting_collect | `_collect_plan` 收取，级联返回 `arrange_support=False` |
| active | ⚪ 空房 | 重置 idle + 重开（**不发 ② fake_reset**，空房无从比对） |
| active | 干员/技能与截图不一致（且面板可读） | 重置 idle + 发 ② fake_reset（dedup key=plan id） |
| idle 命中 | 🔴 training | 保持 idle，静默重排 SKILL_UPGRADE 到 倒计时+2min（`ARRANGING_RETRY_BUFFER`），**不打断训练** |
| 无 active、无命中 | 🔴 training | 发 ① blocked（dedup key=倒计时结束时刻；**仅面板干员名可读时**，否则静默等待） |
| 无 active、无命中 | 🟡 waiting_collect | 静默收取（无通知、无对账） |

（C-05~C-07、C-23、MX-01~MX-10、SM-10~SM-13）

### 读取与匹配的稳为先规则
- 面板干员名/技能名 **OCR 不可读 → 一律视为匹配**，不判不一致、不 reset、不发 blocked。（C-36 / MX-06）
- **B8 采纳门（#68，2026-08-15；用户 08-15 定案修订）**：`_update_expiry` 只在面板**干员名+技能名都可读且与计划匹配**时采纳倒计时（`_can_adopt_expiry`）；任一不可读 → 不采纳（不刷新、不改写状态）、**不排重检**，静默等排班系统下次自然进房重读——幻影/外人倒计时不得「祝福」计划，`waiting_collect` 不被无校验刷新降回 `training`。C-36 的「不可读=匹配」仍用于 reset/通知守卫（load-bearing），**不宽恕采纳**。
- 匹配 = 干员名一致 且（技能名可读时）面板技能名 ⊂ 计划 skill_name（包含匹配，兼容长名截断；面板技能名先经 `resolve_panel_skill` 对照已知技能表解析，见 §10 LBL-06）。（LBL-04）
- `_settle_in_room` 对瞬态场景循环收敛（INFRA_MAIN→enter_room、INFRA_DETAILS→back、CONNECTING/UNKNOWN→sleep），至多 15 次，不在瞬态场景上动作。（C-38）
- 进房先读倒计时定分支，**不盲点技能按钮**。（C-04）

## 6. 收取流程与通知

### `collect_flow`（固定顺序，不得重排）（C-34）
主面板已读 → 点完成标记（模板 `skill_collect_confirm`/`training_completed` 优先，旧坐标 `(0.05w,0.95h)` 仅兜底）→ sleep ~2s → 点任意处跳过动画 → **截图**（收集页不读文本）→ 专3 才邮件（截图 + 面板信息）→ 对账 → 点勾确认。**#106（2026-08-17）**：`collect_flow` 函数体止于专3 邮件，对账/点勾确认由调用方 `_collect_plan`/`_collect_silent` 在 `collect_flow` 返回后按此顺序执行（对账先、确认后，不得重排）——崩溃窗口里 DB 先收敛，不会把已收的 target 计划误当 training 重开。
- 对账档位**只用主面板第 1 步读取值**（`panel.mastery_tier`），收集页不重读。（C-33）
- 专3 邮件条件：命中计划（plan 非 None）且档位 == 3。（C-13）

### 通知清单（8 类，①-⑧ 完整清单见 §16.9；`mastery_notify` 表，`INSERT OR IGNORE` 去重）
| 类型 | 触发 | dedup_key |
|---|---|---|
| ① blocked | 计划外训练占用训练室 | 倒计时结束时刻字符串（不可读 → `'unknown'`，训练未变不重发） |
| ② fake_reset | active 计划 ≠ 截图 | plan id |
| ③ m3_collect | 专3 完成收取 | plan id |

（NTFY-01/02、C-11）
- 所有通知必须走 `should_notify`；`should_notify` **fail open**：DB 出错返回 True（宁可多发不可漏发）。（NTFY-03）
- 新增通知类型必须刻意为之并沿用同样 key 约定，否则会过度/漏通知。
- ✅ 通知已扩到 8 类（①-⑧ 完整清单见 §16.9）：#73 加 ④帮收（key=`{干员}:{技能}`）、⑤训练室受保护（key=`{协助位}:{训练位}`）、⑥已到target（key=plan id）；#79 加 ⑦协助位纠错失败、#81 加 ⑧换人失败放弃（均 key=plan id，WARNING），均已按本契约补 dedup key。

## 7. 减半换人（协助位）

### 触发点（三条，都要守卫）
1. 训练确认开始后：`_schedule_swap_if_needed` 计算，需要时排 `SWAP_SUPPORT` 任务并
   返回其触发时刻（#90：None=不换人；开始训练邮件「有减半」的完成时间 = 触发时刻 +
   `300 + 换人缓冲` 分钟，缓冲值见 §7 路线配置的全局设置行）。
2. `SWAP_SUPPORT` dispatch：`run_swap_support` 执行换人。
3. **#77 重启恢复补排（2026-08-15）**：`_reconcile_training` training×一致 时
   `_maybe_recover_swap` 补排丢失的 SWAP_SUPPORT（短动作，不碰房间、不退出，铁律 4）。
   门控照搬：enable_mastery 开、非跟随排班、`swap_frozen=0`、队列无同计划 SWAP 任务
   （SWAP 任务带 `plan_key` 去重键，与 SKILL_UPGRADE 同形）、倒计时可读且**复用**
   `_schedule_swap_if_needed`（`calc_swap_threshold` 公式口径一致，剩余 <5h 不补排）。
   实际读协助位/纠错/换人仍由 SWAP dispatch 的 #79 `run_swap_support` 完成，补排
   不重复实现协助位比对。
   **#80 陌生人纠错（2026-08-15）**：判陌生人时 `_maybe_recover_swap` **自己读协助位**
   （作为读房的一部分，铁律 3 一次进房做完全部；`_read_slots` 开浮窗读后关回；不依赖
   排班读心情的数据）——协助位 ∉ {路线 operator, swap_target}（陌生人/坐错）且队列
   无换人任务 → 排一条立即执行的纠错 SWAP 任务（`_schedule_correction_swap`，带
   plan_key）。派发仍走 run_swap_support：先纠成路线 operator → 重读倒计时 →
   `calc_swap_threshold` 判值不值得 → 值得才换 swap_target，不值只排收取。**专三
   （swap_target=None）/剩余 <5h 的步也纠成路线人**（只纠不换减半对象）。已减半
   （协助位 == swap_target）→ 不再排换人、只排收取。**#81 换人失败**（2026-08-15）：
   run_swap_support 减半换人失败 → **立刻原地重试**（无 +5min 间隔，不排新任务），
   连续 SWAP_RETRY_LIMIT 次仍失败 / 剩余不足 5h → 放弃 + ⑧ 通知，**不再置
   swap_frozen=1**——reconcile 下次进房重新补排再试一轮，暂时性失败可被救回。
   **#101 空协助位一步定夺（2026-08-16）**：受管理计划训练中协助位**空着**同样需纠——
   `_maybe_recover_swap` 读协助位**可靠地空着**（`_read_slots_checked`，读失败不算空）
   → 确保一条 `plan_key=计划ID` 的 SWAP 任务现在执行（`_upsert_swap_task_now`，已有则
   改到 now，不再排独立 `fill-{id}` 补位任务、两条不并存）。空位当前效率已知=0，
   dispatch（run_swap_support）按 `calc_swap_threshold(0,...)` **一步定夺**：**should_swap
   （含 301 值得门，= 剩余≤阈值 且 换后真实≥301）= True → 直接放 swap_target**（等价一次
   减半换人，不先放 operator 再立刻换的浪费；仅剩余≤阈值不够——低剩余窗 swap_target 速率
   ≤ 路线 operator，直接换反而更慢，review 修复）；**should_swap=False（剩余 > 阈值 或
   值得门不满足，或倒计时读失败 failed）→ 放路线 operator** 拿加成、**不立刻换**（补位后
   重读倒计时排阈值时刻的换人任务，阈值时机不丢；**重读失败 → 轻量重试读
   `_read_countdown_with_retry` 重排阈值任务**，防 #101 合并后阈值任务被本 dispatch 消费、
   只排收取丢减半；重试也读不到 → 保守排收取）。**只在倒计时 active 或 failed 时动协助位**
   （00:00:00 zero 收取边界不动，铁律 6）、**读协助位失败不动**（稳为先：读不到就不动作）。
   空位放 operator 失败 → 不阻塞减半（直接尝试换入 swap_target）。
   门控：enable_mastery 开、非跟随排班、swap_frozen=0；已减半（协助位 == swap_target）/
   保护（逻各斯/艾丽妮在协助位）→ 不补。
   **#107 保护分档（2026-08-17）**：逻各斯/艾丽妮在协助位且 ∉ {operator, swap_target}
   （非路线干员/非减半对象）时，按剩余倒计时分档：**剩余 < 300+缓冲 分钟 → 不纠不换**
   （她们本身是最优加成，路线干员+减半收益赶不上；expires_at 照常刷新，只排收取）；
   **剩余 ≥ 300+缓冲 → 照常纠成路线 operator 再走减半流程**。实现点：`_maybe_recover_swap`
   陌生人分支与 `run_swap_support` 纠错分支前（后者必须整段 return，防 did_swap 用路线
   效率误判直接换减半）。非保护陌生人（含专三）照旧纠（只纠不换减半对象，不变）。

### `calc_swap_threshold` 公式（`mastery.py:238-271`）
- `target_minutes = 300 + buffer`（buffer 默认 10）。
- `swap_total = 100 + 5 + (30 if job_match else 0) + central_bonus`；`current_total = 100 + current_efficiency + 5 + central_bonus`。（+5 是协助位基数，central_bonus 进分子分母两侧）
- `threshold = target_minutes × swap_total / current_total`。
- **永不换当 `real_time_after_swap = remaining × current_total / swap_total < 300`**（边界 ==300 换）。
- `should_swap = remaining_minutes <= threshold`。

### 换人前置门（`run_swap_support`，C-16/S-09）
满足全部才执行：`enable_mastery` 开、非 `assistant_follows_schedule`、active 状态 `=='training'`、`swap_frozen` 为假、route 有 `swap_target`（当前步非专三——level_3 路线 swap_target=None，铁律 7；#76 2026-08-15 删显式 `target_level != 3` 守卫靠路线数据）。**换人成功（choose_train 无异常）后必须置 `swap_frozen=1`**；下一次确认训练开始时清 `swap_frozen=0`。（SM-07 / C-17）
**#78 整合（2026-08-15）加「读全 + 倒计时门」**：进房用 `read_main_panel` 一次截图读干员/技能/图标/倒计时，**场景只在训练室主页面（TRAIN_MAIN）且倒计时 active（读到非 0 秒）才算训练确认**，才读图标/算路线/换人（铁律 1）。219（技能选择页读不出倒计时）不再放行；zero(00:00:00 待收取)/failed(读失败，DB 过期/空房) 都不换——防 DB 过期/空房时按回退 target_level 路线误换人。换人公式/路线沿用稳定方案，只加倒计时门。
**#79 协助位确认（2026-08-15）**：倒计时确认后开进驻浮窗（`_read_slots`，读后自动关）读实际协助位——**协助位 ∉ {operator, swap_target}（陌生人/坐错）先 `choose_train([operator, "Current"])` 纠错**，纠错成功重读倒计时（此时效率已知 = route["efficiency"]）才算换人；**纠错失败 → ⑦ 邮件通知 + 不换人 + 排收取退出**。**协助位已 = swap_target（已减半）→ 不再换、不置 swap_frozen**（防跨步残留重复换）。换人公式/路线仍沿用稳定方案。
**#80/#81 换人值得门（2026-08-15）**：`did_swap` 追加 **`_swap_worthwhileness` 判定**（= calc_swap_threshold 的 301 守卫，换后真实剩余 <5h 不值得）——纠错任务由 reconcile 排（排程时不做值得判定，专三/时间不足的步也纠），派发到这里守住「纠错不触发不该发生的减半换人」（#80 acceptance 2）；正常减半任务排程时已判值得，这里复查只更保守，无回归。

### 协助位安排（C-15，2026-08-17 修订）
- **路线 operator 每次开始照常安排**：`_arrange_support` 在每次确认开始后把路线
  operator 放进协助位——包括「收取 → 下一次开始」级联边界（2026-08-17 用户拍板，
  原 #63 减半守卫的 `arrange_support=False` 已删：它把「专三不换减半对象」过度实现成
  「完全不动协助位」，路线 operator 也没放，专三只留上一级减半干员）。
- **减半换人**由路线 `swap_target` + `_schedule_swap_if_needed` 决定：专一/专二步
  swap_target 非空 → 阈值时刻换减半对象；专三步 swap_target=None → 不换（铁律 7）。
- 协助位换人**只在训练确认开始之后**（读到有效倒计时、DB 已置 training）。
- `assistant_follows_schedule=True` 时跳过全部协助位安排与换人（协助位归排班系统管）。（C-21 / C-28）

### 路线配置（`_get_plan_route` → `get_route_config`）
- 查找链：自定义路线（`is_default=0`）→ 默认路线（`is_default=1`）→ 硬编码 `DEFAULT_ROUTES`；None = 不安排协助位 / 不换人。（TASK-04 / RTE-01）
- **#91（2026-08-16）自定义路线 `supports` 存 JSON 数组**：前端 `buildMasteryRoutePayload`（ui/src/masteryRoute.js）产出 `[{name, skill_level, efficiency, swap, swap_name, match}, ...]`，`get_route_config` 按 `skill_level` 匹配当前步级（旧代码按 `{"level_N":{}}` 字典读、数组恒回退 DEFAULT——自定义路线从未生效的根因）。兼容三种形态：数组、包装对象 `{"supports":[...], "central_bonus":N}`（agent `set_route` 文档形态）、旧字典 `{"level_N":{...}}`；数组条目映射 `name→operator`、`match(bool/'yes'/'no')→job_match`、`swap+swap_name→swap_target`（swap=false 或 swap_name 空 → None）。level_3 若在自定义路线里填了 swap_target 仍会打破铁律 7（数据驱动，用户负责）。
- **#91 修订（2026-08-16）中枢加成 + 换人缓冲进路线配置全局设置行，不再存 conf**：`central_bonus`（0/5，**默认 0**——无中枢 buff 不假设 +5%）与 `mastery_swap_buffer`（分钟，**默认 10**）存 `mastery_route` 保留行 `__mastery_settings__`（supports JSON），`get_route_config` 统一从 `get_route_settings()` 读并注入自定义/回退两条路径——**改一处全职业生效**，且归在「路线配置」里（DB 管理删「专精路线配置」会一起清掉、回默认）。`conf.py` 的 `mastery_control_center`/`mastery_swap_buffer` 已删（旧 conf.yml 残留字段被 pydantic 忽略）。前端路线设置弹窗：中枢加成改**单个开关**（阿斯卡纶/烛煌/斩业星熊 +5% 提示）+ 缓冲输入，modal 级（全职业共用）。API：`GET/POST /mastery-route/settings`；`get_all_routes` 排除设置行。换人公式 `central_bonus` 默认从 5 改 0。
- **#76（2026-08-15）路线按「当前步目标级」加载**：`_get_plan_route(plan, step_level)` 用 step_level（确认后/换人前进房读主面板专精图标 = 当前步目标级，亮 N 颗=专N），step_level 缺省/读失败回退 `plan["target_level"]`（=旧行为，保守）。专三计划 专一→专二→专三 三步分别用 level_1/2/3 路线：专一/专二步正常减半换人，专三步由 level_3 swap_target=None 挡住（铁律 7）。三个消费点：`_arrange_support` / `_schedule_swap_if_needed`（确认开始后，`_confirm_training_started` 内读图标传参）、`run_swap_support`（SWAP 派发，进房读图标）。
- `DEFAULT_ROUTES` 按 8 职业 × level_1..3 键控，每条必带 operator/efficiency/job_match/swap_target（swap_target=None 表示该级不换）。（RTE-02）

## 8. 排班集成（#59 gate）

### L0：先读再判（进房读屏幕，截图权威更新 DB）（#74，2026-08-14 改）
**删除**「DB active 就跳过」的预判（原 base_schedule.py:3257 死锁——DB 是意图缓存可能过期，排班一进门就因 DB active 整房跳过、永不读屏幕、永不修正 DB → 重启后训练室僵住，违背「截图为准」铁律 1）。现在 `agent_arrange_room` 排班进训练室一律：`enter_room('train')` → `read_room_state(enter=False)` → `enable_mastery=True` 时 `reconcile_short`（据截图修正 DB：空闲×DB active 冲突 → 重置 idle）→ 重读 → 按锁定/保护判定：`assistant_follows_schedule=False` 整房跳过（delete 房间、back、返回）；`True` 冻结 idx1=Current（仅当 `len(plan[room]) > 1`）只排 idx0。不再依赖 `find_next_task(SKILL_UPGRADE)`。（C-07 改为截图权威）

### 排班路径内联短动作 `reconcile_short`
核实/帮收/重置/对账可内联；**不得开始训练、不得退出房间**；`enable_mastery=True` 时在所有房间状态上运行（#74：空闲格也据截图修正 DB，不再仅锁定格）。（C-06/C-36/MX-11）
- **#75 方案 C（2026-08-14 已实现）**：gate 以 `reconcile_short(self, room_state, defer_collect=True)` 调用。`_reconcile_waiting_collect` 在待收取格命中计划且队列已有任一 SKILL_UPGRADE 任务时**跳过本次收集**、留给队列任务收（任何 dispatch 进房都会收待收取格，收完被消费 → 无残留任务，防残留任务空闲房触发开始训练）；队列空照常收集（恢复兜底）。**专三同样纳入 skip**（2026-08-14 用户撤回「gate 收专三」例外）。dispatch 路径 `defer_collect` 恒 False 永不跳过。

### `choose_train` D4（锁定检测确定化）
idx1 在 `select_targets` 里时，先跑 `train_slot_locked`（截图权威）判锁定，锁定则丢弃 idx1，避免 2 分钟超时空转；**若 idx1 是唯一待换槽位（调用方明确要换训练位，如 `_swap_into_wrong_slot`）则抛异常**（#69/B3：换人失败不得静默 return，否则流程误以为换人成功继续点错干员开始）。详情浮层开着时先关详情读倒计时再重开，防动画中误退房。（C-10 / CS-04 / #69）

### `resting()` 用 DB active，不用队列
`resting()` 跳过训练室干员的休息规划，依据 `get_active_plan()`（重启后队列可能为空，队列失真不影响休息规划），且**只在 `enable_mastery=True` 时跳过**（**#109**：OFF 恒放行休息，残留 active 计划不得把训练室干员耗到心情尽；§9 OFF 清单）。（C-27）

### 槽位约定（固定）
`get_agent_from_room('train')` scan[0] = 上排 = 协助位，scan[1] = 下排 = 训练位；`choose_train` idx0 → `choose_agent`，idx1 → `choose_train_ope`。（CS-01/CS-05）
`'Current'` = 该槽保持原样，必须替换为扫描到的真实名，**绝不**传给 `choose_agent/choose_train_ope`。（CS-02）
无倒计时 + 训练位坐错人 → 只换训练位：`choose_train(['Current', 目标])`，idx0 恒 Current 保协助位。（C-22）

### 其它
- 错误清理（>15 分钟清空）必须保留 `SKILL_UPGRADE`/`REFRESH_TIME` 两类任务；错误空任务仅在「无 next 任务 且 无 SKILL_UPGRADE 任务」时才生成。（C-17）
- **keepalive 已删（#74 第3段）**：不再有任何「DB 有计划就自动入队 now-task」的逻辑（含 #66 的 60s 守卫 `_skill_upgrade_just_dispatched`）。开始训练只由**扫描派发**：`_auto_schedule_mastery_after_scan`（`base_schedule.py`）在 `retry_failed_plans` + `auto_schedule_mastery_tasks` 之后，对**材料足够（scheduled 结果）的 idle 计划**入队一条 `SKILL_UPGRADE`（`plan_key=计划id`，`meta_data` 仅描述性标签、无逻辑标记，`_schedule_scan_start`）。重启恢复：active 计划靠排班 gate 进房顺路 `reconcile_short` 重排收取（用户确认「靠排班收取、等待可接受」）；idle 计划靠扫描派发兜底。

## 9. 全局开关 `enable_mastery`

- 默认 `True`（`conf.py:333`）。OFF 语义边界（conf.py:332 注释原文：仅保留仓库材料扫描）：
  - **关**：`run_mastery_task`、`run_swap_support`、`reconcile_and_act` 全部直接返回；扫描派发入队（`_dispatch_scan_start_tasks`）也被 gate；排班内联 `reconcile_short` 不运行；排班 `resting()` 不再因 active DB 计划跳过训练室干员休息规划（**#109**，OFF 恒放行休息）。
  - **留**：N 小时仓库扫描钩子（`retry_failed_plans` + `auto_schedule_mastery_tasks` + `compute_workshop_config`）照跑。
  - **且**：排班永不触碰锁定训练位（L0/L1 freeze/skip）**不受开关影响**，必须保持。
- 相关配置：`assistant_follows_schedule`（默认 False）。中枢加成（0/5）与换人缓冲时间已迁到路线配置全局设置行（§7 #91 修订），不再在 conf。
- ✅ **2026-08-14 定案并已实现**（#73 §16.11）：OFF = 自动收取/开始/换人/保护/通知全停；排班照常，**保留「被占用就不硬塞」防卡检查**（即上一条「排班永不写锁定训练位」，防排班硬写训练中训练位卡超时饿死其它任务）。实现：`_compute_protected` 在 OFF 时恒返回 False（保护全停）、`reconcile_and_act`/`run_mastery_task`/`run_swap_support` 直接返回，`reconcile_short` 受 gate 的 `enable_mastery` 门控。

## 10. 技能名规范

- **规范格式**：`{序数}技能·真名`（如 `二技能·飞翔瞪射`）；序数一/二/三，分隔符 `·`。
- **`format_skill_label` 是唯一格式化器**，前端/日志/邮件/API 统一调用（`skill_label.py`）。幂等：已是 `^[一二三四五六]技能·` 原样返回；真名 → `{序数}技能·{真名}`；占位/缺失回退 `技能{N}`（1-indexed）。（LBL-01/LBL-03）
- **占位符**：`技能{N}`（匹配 `^技能[0-9]+$`）表示「真名未知」，必须懒填充，永不作最终存储值。（LBL-02）
- **比较前先 `normalize_skill_text`**：去 `[]`、统一分隔符族 `·．.。 ` 与全角空格/Tab 为 `·`。（LBL-05）
- **匹配 = 包含**，不是相等：面板技能名 ⊂ 计划 skill_name（面板可能显示截断前缀）；只对当前计划判，**无全局反查表**（技能名在干员内不重复，无歧义）。（LBL-04）
- **面板技能名先经 `resolve_panel_skill` 解析（#95，2026-08-16）**：面板技能文本对照干员已知技能表（skill_data.json `characters[char_id].skills[].name`，每干员 ≤3 技能）做归一化互含匹配（面板 ⊂ 真名 或 真名 ⊂ 面板，容忍截断与 OCR 首尾噪声），命中**唯一**技能才返回序号；查无干员 / 无命名技能 / 多候选含混 → 返回 None 回退包含匹配（LBL-04）。调用点 `_plan_matches_room` / `_match_plan`（mastery_reader.py），归属校验（mastery.py #69/B2）与 B8 采纳门（`_can_adopt_expiry`）一并受益。干员名反查 char_id 用 `_resolve_operator_char_id`（撞名保守不采纳）；`get_skill_data` 函数内懒加载避免循环导入。（LBL-06）
- **`insert_plan` 必须存规范 skill_name + 非 NULL char_name**；存量计划（NULL char_name / 占位 skill_name）读取时懒填充（`lazy_fill_plan_names`，写回仅在传入 connection 时发生，不改行为）。（LZ-01/LZ-03）

## 11. DB 契约

- **计划字段**：id、char_id、char_name、skill_index、skill_name、target_level、status、priority、expires_at、failed_reason。
- **计划 id（#102 定案）**：`mastery_plan.id` 由 `INTEGER PRIMARY KEY AUTOINCREMENT` 生成，**单调递增、删除后不复用**——日志中的高 id 是历史编号，不代表现存计划数（删 1、2、4 后现存计划从 3 开始属正常）。**切勿改成普通 `INTEGER PRIMARY KEY`（rowid 别名）**：删掉最大行后 id 会被复用，使残留的 `plan_key=旧id` 队列任务 / `dedup_key=旧id` 通知去重行指向新计划。
- **状态唯一写法** `update_plan_status`；优先级 `update_plan_priority`。（DB-02）
- **`is_operator_busy`**（`mastery_db.py:302-325`）：
  - busy 状态集 = 恒 {arranging, training, waiting_collect}（waiting_collect 的干员仍在房内，不得被排走）；增删状态必须同步改此集合。（BUSY-01）
  - 按 `char_id` **或** `char_name` 匹配；NULL char_name 存量行先解析出名字再判，否则会把训练中的干员当空闲移走。（BUSY-02）
  - **异常安全**：任何 DB 错误返回 False，绝不因 DB 故障冻住宿舍/基建排班。（BUSY-03）
- **通知去重表** `mastery_notify`：(notify_type, dedup_key) 主键 + `INSERT OR IGNORE`；`should_notify` fail open。（NTFY-01/03）
- **懒填充**：所有把计划交给消费者的读路径（`get_all_plans`/`get_plan_by_id`/`get_active_plan`/`get_next_idle_plan`）都必须过 `lazy_fill_plan_names`，消费者永不看到 NULL char_name 或占位 skill_name。（LZ-02）
- **建表只跑一次（#82，2026-08-15）**：`_ensure_tables` 按库路径进程内只跑一次（模块级 `_tables_created` 集合），连接仍每次新开；库文件被删/被清空（0 字节）→ 重置该库标记，下次连接重建表（#86 同款守卫，防运行中丢库后 no-such-table）。
- **队列不变量**：`SKILL_UPGRADE` 同形状任务恒 ≤1（按 plan_key 去重，到点改期不新增）；`plan_key=None` 是占用重检，`meta_data` 留空；`plan_key=计划id` 是收取任务或扫描驱动的开始任务（均无逻辑标记，meta_data 仅描述性标签；房间状态决定行为：空闲→开始、待收取→收集+继续本级当场开）。开始任务在计划开始后按 plan_key 原位升级为收取任务（`_schedule_collect` 去重命中）。（TASK-01/C-32）
- `expires_at` 存 localtime 文本 `%Y-%m-%d %H:%M:%S`，仅用于调度重查，改格式会破坏比较。

## 12. 推荐 / 自动排程

- `get_mastery_recommendations` 恒返回 `{'operators': [], 'has_data': bool, 'error': str|None}`；cultivate.json 缺失/不可读或 chars 空 → `has_data=False` + error。消费方以 `has_data` 门控。（R-01）
- `auto_schedule_mastery_tasks` 在 `has_data` 为 False 时直接返回空。（R-02）
- **只推荐精二**（evolvePhase ≥ 2）且技能当前等级 < 3；`target_level` 恒 3。（R-03）
- **创建默认目标 = 专三**（#65/B7）：所有计划创建入口（API 扁平/批量、agent 工具 `add_mastery_plan`、前端添加）统一走 `add_plan_checked`——`target_level` 缺省 3（与推荐一致，消除「推荐专三、创建专一」分歧），校验范围（1/2/3）+ 干员当前等级（cultivate.json，读不到跳过）。前端不传 target_level，由服务端默认。
- **材料核算是链路级**：同一 `remaining_inventory` 跨阶段递减，任一短缺 → 整链不可达；`chain_total_needed` 按整链汇总。（R-06）
- **自动排程条件**（R-10）：(char_id, skill_index) ∈ plan_set 且 current_level < 3 且 **每条链级材料 owned ≥ count** 才 `scheduled`，否则 `skipped`。
- **仓库扫描钩子固定顺序**（R-15）：`cultivateDepotSolver().start()` → `DepotSolver().run()` → `retry_failed_plans()` → `auto_schedule_mastery_tasks()` → `compute_workshop_config()`。（`base_schedule.py:4445-4480`）
- **`matery_plan.json` 已废弃（#83，2026-08-15）**：`auto_schedule_mastery_tasks` 与
  `compute_workshop_config` 改为直接读 DB 计划（`get_all_plans()` 非终态），不再读
  `@app/tmp/matery_plan.json`（原文件是全仓库无写入者的孤儿文件，UI/API/agent 新增计划
  不在里面 → 扫描自动开始失效）。completed/failed 计划不核算材料（不消耗；failed 由
  扫描钩子 `retry_failed_plans` 先重置 idle）。扫描开始路径、材料核算与实际计划一致。（R-09 已替换）
- **`PROF_MAP`（EN→CN，8 职业）在两个模块重复定义**（`mastery_recommendation.py:707` 与 `mastery.py:183`），必须保持同步，否则路线/协助位查找静默分歧。（R-16）
- 技能名产出用 `format_skill_label`，保证规范格式。（R-05）
- 阶段展示 `from_level=stage+7 / to_level=stage+8`，末阶段 to_level 到 10 —— 纯展示约定，消费者不得把 to_level 当真实等级。（open_risks）

## 13. HTTP API 契约

全部视图带 `_require_token`：`current_app.token` 有值时，请求头 `token` 必须相等，否则 `abort(403)`。（C-18）

| 端点 | 契约 |
|---|---|
| `GET /mastery-plan` | `{plans:[...], history:[...]}`；plans 每项含 id/char_id/name/skill_index/skill_name/target_level/status/priority/expires_at/failed_reason；history 含 char_id/name/skill_index/skill_name/target_level/status/failed_reason/time。⚠️ **#69 展示约定**：plans = `get_all_plans()`（非终态）**追接** `get_failed_plans()`（failed，带 failed_reason）——failed 计划也返回给前端显示，不"凭空消失"；执行循环仍只读非终态（#4 SM-09） |
| `POST /mastery-plan` | 两种 body：`{'items':[{name, skill_index, target_level}]}` 或扁平 `{name: skill_index}`；扁平路径 skill_index 必须 ∈ {0,1,2} 否则 `invalid skill_index`；未知干员 → `{status:'error', reason:'operator not found'}`；成功 → `{status:'added', id}`。⚠️ **#65/B7 target_level 统一校验**（两路径都走 `add_plan_checked`）：缺省/默认 专三（与推荐一致）；越界（非 1/2/3，含非整数、布尔 `true`）→ `reason='目标专精等级无效: ...'`；干员 cultivate.json 当前等级 ≥ target → 拒绝（`reason='...已专N...'`，不落库；cultivate 读不到则跳过等级校验，执行层已到target检测兜底）。⚠️ bulk `items` 路径**不校验** skill_index ∈ (0,1,2)（open_risks） |
| `DELETE /mastery-plan` | body 需 id（缺 → 400；**#113** 非数字 id / bool → 400）；`delete_plan` 失败 → 500。**#97 清理**：删除后顺带清该计划 `plan_key=计划ID`（#101 补位已并入同一键，无独立 fill-{id}）的队列任务（SKILL_UPGRADE/SWAP）+ `mastery_notify` 中 `dedup_key=str(id)` 的去重行——残留任务不再按 plan_key 派发到已删计划 |
| `PATCH /mastery-plan/order` | body 是 `[{id, priority}]`；未知/缺失 id 容忍；**#113** id/priority 非整数（含 bool、数字字符串）→ 400；返回 `{'status':'ok'}` |
| `GET /mastery-route` | `{routes, defaults}`，defaults = `solvers.mastery.DEFAULT_ROUTES` |
| `POST /mastery-route` | profession 非空（否则 400）；supports 接受 str 或 list；**#114 写入端校验：supports 须是合法 JSON 且形态是数组/包装对象/旧字典之一（level_N 值须为对象），否则 400 拒绝保存**；`is_default` 恒 0；optimal/half_off 透传，half_off 默认 True |

API 只增删计划与调优先级，**不得直写 status**（状态由执行层 `update_plan_status` 写）。（DB-02）

> **#71 `/task` 契约（一键专精流接入 DB 计划架构）**：原始「技能专精」`/task`（旧流不带
> operator/skill，dispatch 只认 DB 计划，提交即死路）被**明确拒绝**并指引
> `POST /mastery-plan`（server 的 `add_task` SKILL_UPGRADE 分支改为清晰报错，不再落旧路线
> 逻辑）；`upgrade_support` 载荷移除（后端本无消费者；`op_data.skill_upgrade_supports`
> 字段按 #60 保留为快照往返数据，无实时写入者）。前端一键专精（MasteryRecommendation.vue）
> 与手动对话框（TaskDialog.vue，运行日志页「添加任务」）都走 `POST /mastery-plan`
> `{items:[{name, skill_index, target_level}]}`：一键流不传 target_level（服务端默认专三，
> 与推荐/确认弹窗「→ M3」一致）；手动对话框**保留用户选的目标等级**（可能非专三，`target_level`
> 显式传）。确认后由扫描派发（`_dispatch_scan_start_tasks`）经 SKILL_UPGRADE dispatch 真正
> 开始训练。契约测试：`mastery_task_contract_tests.py`（/task 拒绝 + 前端源码契约）。

## 14. 待办 / 已知风险（实机校准等）

### 像素/坐标待实机校准
- 专精图标亮灯计数（主面板 `MASTERY_ICON_PIPS`）已从"按宽度 3 列分槽"改为**逐框判亮**：三颗星 12×12 框（专一顶/专二右下/专三左下，1080p 实测校准），复用 `_box_is_lit`（`PIP_BRIGHTNESS=150`、`PIP_LIT_RATIO=0.45`、`PIP_INSET=2`，已实机校准）。旧 `_count_lit_from_region`/`MASTERY_ICON_BRIGHTNESS`/`MASTERY_ICON_LIT_RATIO` 已删。（C-39）
- **「已到target检测」已启用**：`SKILL_SLOT_PIPS`（技能选择页，每技能 3 颗星坐标，点亮顺序 顶→右下→左下：专一顶/专二右下/专三左下）已按实机坐标填入；`_read_slot_mastery_tier` 逐框判亮计数（阈值同上）。读失败（无此技能/无截图/异常）→ None，#70 起调用方**保守处理**：保持 idle 重排退出，**绝不盲点技能行开始**（档位不可读 = 无法确认是否已到 target，可能重训已完成的档位）；档位读到 0（明确低于 target）才正常开始。（C-30 / #70）
- **#72 页面模型**：219（TRAIN_SKILL_SELECT）只读得到 `SKILL_SLOT_PIPS` 星星，无倒计时、读不到主面板 `[干员名]技能名`——**219 分支不再读主面板区域（COUNTDOWN/PANEL）当占用探针**。`_start_new_training` 用 `identity_confirmed` 标志做数星星前的身份确认：只在 TRAIN_MAIN 训练位校验通过并主动点开技能选择页时置位；未置位就出现 219（重启停在技能选择页/手动进入）→ 保守 idle 重排退出（重排到 now+2min 重检，不读倒计时/不数星星、不点技能行——219 读不到主面板/倒计时，无法确认星星归属；下次 dispatch 正确判为 TRAIN_MAIN 时按「倒计时+2min」收敛）。（C-30 / #72）
- **#89 `_confirm_training_started` 的 219 = 真技能选择页（读不出倒计时）**：确认升级后游戏自动退回 219，须先 `back()` 一次回训练室主页面（217）再读倒计时（§16.10 第 3 步「再退出一次」）。旧表述「运行页被误判成 219」写反语义——219 左下角是协助位天赋文本，会被 OCR 当倒计时反复读（卡 ~15 秒），甚至偶然读出类时间文本 → 假确认开始。（C-30 / #89）
- `_tap_finish_mark` 兜底坐标 `(0.05w,0.95h)` 实机疑似打不中（#63）；`_tap_collect_confirm` 兜底 `(0.5w,0.85h)` 未验证；模板优先路径未实机验证。（C-35）
- **#92 换协助位坐标（2026-08-16 已修）**：`choose_train` 在训练室主页面开进驻信息浮窗的旧坐标 `(0.25w,0.95h)`=(480,1026) 落在左下角技能/进度面板、点出技能详情浮窗（Scene -1 空转 7s 后出房重进）——改 `_open_check_in_detail` 用 `arrange_check_in` 模板（屏幕左侧 ~(101,441)）开（`base_schedule.py`，INFRA_DETAILS 浮窗未开与 TRAIN_MAIN 两分支共用；换人语义=主页带进驻信息浮窗右侧换）。
- **#93 训练室开始流程收敛（2026-08-16 已修）**：dispatch 的 `reconcile_and_act` 返回已读的 `RoomState`（`(plan, arrange_support, room)`），`run_mastery_task` 传给 `_start_new_training`——开始流程复用 reconcile 已读的槽位，不再重复 `enter_room`、不再 `_training_slots` 重开进驻浮窗读槽位（消除双进房 + 一次重复浮窗开关；浮窗 4→3：reconcile 保护读槽位 + choose_train 换协助位扫描/确认为必需）。**槽位复用**：`room.train_slot` 非空直接复用；读到空串无法区分「真空」与「读浮窗失败」→ 重读一次兜底（读失败恢复「空闲但训练位坐错人」换人校验、真空重读仍空无害）。注：TRAIN_FINISH=220 只靠主动点左下角完成标记（`skill_collect_confirm`）才进得去，进房必是 217（`train_main`），练完未收也是 217 + `training_completed` 模板照常读槽位。**技能选择页进 2 次保留为残留**：保护深读（§16.5 逻各斯/艾丽妮空房判专一/专二）与开始流程自身的技能页进入（数星星 + 点技能行开始）语义上都需要——合并需把保护深读的逐技能档位透传到开始流程、且仅 train_slot==计划干员 时有效，收益仅限该场景、over-engineering（用户「最简实现」取向）。**未做 #92 已拒绝的「调用方先开浮窗」大重构**（choose_train 换协助位的两次浮窗开关为换人必需，保持现状）。
- **#94 统一训练室读取（2026-08-16 已修）**：`agent_get_mood` 训练室分支原为 `get_agent_from_room`（开浮窗读心情）+ `read_room_state`（`_read_slots` 再开一次浮窗读槽位）→ 一次进房开两次浮窗。现统一走 `read_room_state(want_mood=True)` 一次进房读全（协助位+训练位+心情+左下角面板）→ `reconcile_short` → 返回心情（对齐 mood_info）。`read_room_state`/`_read_slots`/`_fill_slots_and_protection` 加 `want_mood` 参数：浮窗读槽位顺带收集心情返回 `(RoomState, mood_data)`（mood_data=浮窗槽位扫描，含 mood）；心情取不到的状态（TRAIN_FINISH 横幅页浮窗不可靠 / OCR 失败保守训练中只读面板）返回空列表 `[]`；默认 `want_mood=False` 返回 `RoomState` 不破坏现有调用（gate/reconcile_and_act 不变）。`enable_mastery` OFF 分支保留旧 `get_agent_from_room` 通用心情读取（铁律 10）。
- **训练室心情读取频率与其它房间对齐（2026-08-16 已修）**：`agent_get_mood` 原 `room != "train"` 跳过免除（#881 为配合 `should_read_train_in_mood` gate 加的，gate 已在 #886 删）使训练室永不跳过 → 计划在训练室但未进驻（等待中）的陈旧干员把训练室永远留在待读集合 → 2h 内读心情十多次。已移除免除，训练室与其他房间一致（当前房内干员都近期读过则跳过）。**行为变更**：训练室进房时顺路 reconcile（破重启待收取死锁，522b7fa1）的触发从「每轮循环」降为「~2.5h 占用干员心情陈旧 / 重启后 current_working 空」。正常收取由 dispatch 收取任务覆盖，死锁兜底保留（重启必触发）。
- `TRAIN_MAIN` 区分「空」与「刚完成」仅靠 `training_completed` 模板；模板/OCR 漏判会误分类房间、可能误触发重置。（open_risks）

### 行为/契约风险
- **#65/B7 创建校验是 best-effort**：当前等级取自 cultivate.json（上次森空岛拉取），过期时可能放过「实际已到 target」的计划——由执行层已到target检测（截图）按真实档位正确完成，#70 档位读失败保守化兜底，不会重训已完成档位。（open_risks）
- **`waiting_collect` 无写入路径**（见 §4 陷阱）——未来若有人写它会静默改变行为。
- **并发进房无互斥**：共享读取器被 dispatch / 排班房间循环 / 仓库扫描多触发点顺路调用，`reconcile_short` 与 dispatch 若并发进房可能互相干扰。`now..now+30min` 带内的倒计时既非「占用重排判定」也非「确认开始」，两个调用点判定口径必须保持一致。
- `should_notify` fail open → dedup 表损坏时会**多发**通知（宁可多发不可漏发，属有意）。
- `is_operator_busy` / `_is_mastery_busy` 在 DB 异常时返回 False → 专精中的干员可能被当空闲排走（fail-safe 取向的代价）。
- `insert_plan` 无去重；API/tool 重复调用（或 `retry_plan_tool` 重试全部 failed）可能累积重复计划。
- `swap_frozen` 只在下次确认训练开始时显式清 0；重置为 idle 再重排会清，但没有独立 unfreeze 路径。
- 换人公式基于经验参数（300+10min buffer），实机效率数据未校准。
- 读倒计时失败返回 `now` 会把 `TRAIN_MAIN` 分类为空（靠模板补）。
- **#72 残留边缘**：TRAIN_MAIN 倒计时 OCR 失败 + 训练位恰为计划干员（DB 过期，实际在训练）→ 训练位校验通过、点开该干员真实技能页数星星。这是旧代码同样存在的边缘（旧 219 守卫在真技能页上同样读不到倒计时/面板，`identity_confirmed` 并未弱化它）；档位 ≥ target 仍正确判完成，target > 当前档位时可能误点技能行重开训练。#69 换人失败置 failed 已挡「训练位坐错人」情形。（open_risks / #72）
- 确认开始门槛 `>now+30min` + 纯墙钟 5 分钟 deadline（2026-08-14 用户把 10 分钟改为 5 分钟）：慢设备/模拟器可能 false-fail。
- ✅ **#109（2026-08-17 已修）**：原风险「`resting()` 的跳过只 gate 在 `get_active_plan()`，未 gate `enable_mastery`——开关 OFF 但存在 active DB 计划时干员仍被屏蔽休息规划，确认是否符合 OFF 语义」定案为**不符合**，已修：`has_active_mastery = config.conf.enable_mastery and get_active_plan() is not None`——OFF 时恒 False，训练室干员正常排 SHIFT_OFF，残留 active DB 计划不再把训练室干员耗到心情尽。
- **#74 第3段 扫描派发（2026-08-14 实现）**：
  - keepalive 已删（含 #66 的 60s 守卫 `_skill_upgrade_just_dispatched`）：不再有「DB 有计划就自动入队 now-task」。空闲 idle 计划开始入口 = **扫描派发**（`_dispatch_scan_start_tasks`，材料足够才入队）；普通重启会从 data.db 恢复任务队列（含已入队的扫描任务），缓存清零重启则清空队列。
  - **「都去掉」定案（2026-08-14 用户拍板）**：扫描任务标记（`SCAN_START_MARKER`）与进程内存记号（`_scan_started_plan_ids`）**均已删除**。设计退化为最简：任何带 `plan_key` 的 SKILL_UPGRADE 任务在空闲×未保护格都会开始其指定计划（房间状态决定分支：空闲→开始、待收取→收集+继续本级当场开）；继续本级一律当场开，重启后也不保守等扫描。**已知代价**（用户接受，出问题再回来）：重启后材料不足 → 确认页 fail-fast → 临时 failed + 报错邮件；残留/时间错任务在空闲房会直接开计划（触发时机不可控）；瞬时 completed/空跑噪音更频繁。安全性由 #69 面板归属校验 / #70 档位读失败保守 / 已到target检测兜底（不会开错训练）。
  - **排班先收竞态（✅ #75 方案 C 已修，2026-08-14）**：原为排班 gate 抢在收取任务前用 `reconcile_short` 收了练完的训练 → 残留收取任务触发时空闲房**直接开下一级**（「都去掉」后无标记拦截）。修法：gate 传 `defer_collect=True`，待收取格命中计划且队列已有任一 SKILL_UPGRADE 任务（排除当前 dispatch）→ 跳过本次收集、留给队列任务收（任何 dispatch 进房都会收待收取格，收完被消费 → 无残留）；队列空（如缓存清零重启丢了）→ 照常收集（恢复兜底）。**专三同样纳入 skip**（2026-08-14 用户撤回例外：③ 邮件在任务 dispatch 收取时发、不丢）；**不查任务时间**（用户拍板：任务时间排错时收集拖延可接受——「拖很久就拖很久」）。dispatch 路径（reconcile_and_act，当前任务即收集任务）defer 恒 False 永不跳过。
  - **计划来源 = DB（#83，2026-08-15）**：`_dispatch_scan_start_tasks` 对
    `auto_schedule_mastery_tasks` 的 `scheduled`（按 DB 计划核算材料）匹配 DB idle 计划
    入队开始任务——UI/API/agent 新增计划都会被扫描自动拉起，不再依赖 matery_plan.json。
  - **训练无法取消（游戏机制，prts.wiki）**：训练开始后不可中止，训练位干员直到完成不可移动。因此训练室不可能出现「训练中途被取消 → 空房」；空闲房只来自「从未开始」或「完成并已收取」。
- 测试环境坑：`mastery_choose_train_tests.py` 必须在 import 时 stub `arknights_mower.utils.skland`（base_schedule 导入链会触发 `SecuritySm.get_d_id` 网络调用）——环境性 flake。
- **#78 浮窗识别盲区（2026-08-15 修复）**：`get_train_scene` 新增 `find("room_detail") → INFRA_DETAILS(205)`（浮窗头，放在 train_main 之前）——浮窗开着时不再被误标 217/219。**不可用 `arrange_check_in`**（裸主页面也有，加了会恒 205、217 永远不出来）。复活所有「`INFRA_DETAILS → back()` 关浮窗」死代码：`_read_slots`（读完进驻详情自己关，调用方 `_fill_slots_and_protection` 不再二次关）、`_settle_in_room`、`_start_new_training`、`run_swap_support`、`train_slot_locked`、`_read_train_countdown`。`back()`→`sleep()`→`recog.update()` 重置场景缓存，无死循环。`_training_slots` 仍不关浮窗（由 `_start_new_training` 唯一调用方关，单次 back 无二次退出）。**顺带整合（#78 comment 拍板）**：`run_swap_support` 换人前改 `read_main_panel` 读全 + 倒计时门（见 §7 换人前置门）——场景只在 TRAIN_MAIN 且倒计时 active 才换，219/zero/failed 不换，删场景标签依赖。
- **#73 风险（§16，已实现 2026-08-14）**：
  - 待收取+非专三+协助位逻各斯/艾丽妮+干员技能都不在计划 → 长期保护：现读现判下若无新训练开始、无人换协助位，训练室持续不可排班（符合定案，需用户知晓）。
  - 材料门控已删（§16.7，用户 2026-08-14 决定）：无开始前材料检查，材料不足走确认页 fail-fast 兜底（旧行为，`_exit_failed`）。
  - **TRAIN_FINISH（完成横幅）场景保护判定缺失协助位**：`_read_slots` 只在 TRAIN_MAIN 上可靠，TRAIN_FINISH 场景 support_slot 可能为空 → 逻各斯/艾丽妮保护在该瞬态场景降级为可排班（正常完成房间多为 TRAIN_MAIN+00:00:00，走矩阵正确保护）。
  - **读倒计时最坏 ~20 次截图**：`read_time` 内部已重试 4 次 + 状态矩阵 OCR 失败再重试 5 次（§16.2），慢设备/动画中可能放大误读窗口；`_retry_ocr` 的 5 次在 `read_time` 之上叠加（规格要求，未裁剪）。
  - **`_schedule_swap_if_needed` 立即换人分支行为变更**：旧代码在 `remaining ≤ threshold`（应立即换人）时静默丢弃不排任务，现改为立即排 `SWAP_SUPPORT`（修复 silent-drop，§16.10 排了换人则不排收取依赖它）——需实机确认 SWAP 任务在训练刚确认后立即执行不与确认动画冲突。
  - **换人失败不重试（pre-existing，#73 保证收集不丢）**：`run_swap_support` 的 choose_train 异常仍被吞掉、不重试（减半收益丢失），但 §16.10 的收集现在无论换人成功与否都会补排（`_schedule_collect_after_swap` 移出 try），不再丢收集任务。

## 15. 验证方式

```bash
python -m pytest arknights_mower/tests/mastery_reader_tests.py \
  arknights_mower/tests/mastery_arranging_tests.py \
  arknights_mower/tests/mastery_choose_train_tests.py \
  arknights_mower/tests/mastery_db_tests.py \
  arknights_mower/tests/mastery_formula_tests.py \
  arknights_mower/tests/mastery_view_tests.py \
  arknights_mower/tests/mastery_task_contract_tests.py \
  arknights_mower/tests/base_scheduler_tests.py -q
python -m pytest arknights_mower/tests/*.py -q        # 全量
python -m ruff check arknights_mower/solvers/ arknights_mower/utils/ arknights_mower/views/ arknights_mower/agent/
```

- 全量 245 tests 通过（#71 新增 `mastery_task_contract_tests.py`；GBK 控制台 print/logging 报错或尾部日志关闭噪音为环境性，与本子系统无关）。
- 改动涉及本子系统后，全仓 grep 确认无对已删符号（`refresh_skill_time`/`_calculate_swap_from_api`/`get_pending_plans`/`has_in_progress_plan`/`get_in_progress_plan`/`set_plan_status`/`_skill_upgrade_just_dispatched`）的新引用。

---

## 16. #73 进房读全再判定 + 状态矩阵重设计（2026-08-14 定案，✅ 已实现）

> 本节的定案与用户逐条对齐（会话内 grilling），**2026-08-14 #73 已实现并取代/并入
> §5（恢复矩阵）、§6（通知）、§9（开关）**；§8（排班 gate）按 §16.4/§16.5 补充保护检查。
> 实现要点文件索引：三态倒计时/状态矩阵/7 格动作/保护/恢复/日志 → `mastery_reader.py`；
> 开始训练术语流/⑥ 通知 → `mastery.py`；gate 保护 → `base_schedule.py`。

### 16.1 进房读全流程（enable_mastery ON）

1. 进训练室。
2. 读**进驻详情浮窗**：协助位/训练位干员 + 心情（心情只记入结构化日志，不 gate 判定）。
3. 读**左下角**：干员名 / 技能名 / 倒计时 / 专精图标。
4. 按状态矩阵判定（16.2）。
5. **凡「干员+技能都在计划内」的情况，一律用左下角信息更新 DB**（以截图为准）。**#98：failed/idle 计划同样适用**——面板干员名+技能名都可读且匹配某计划 + 倒计时 active → 恢复该计划为 training（撤销 false-failure；恢复门比 B8 采纳门更严，见 §16.4）。

### 16.2 状态矩阵（倒计时三态 × 干员/技能存在性 × 图标亮点）

- **倒计时为 0（00:00:00）→ 待收取**。
- **倒计时为空 + 无名无亮点 → 空闲**。
- **倒计时非 0 + 名存在 + 有亮点 → 训练中**。
- **其余 6 种不一致组合 → OCR / 亮点计算失败 → 原地重试 5 次**（重读截图，不点动画）；仍不一致 → 保守按训练中处理（不动、记日志、**不排重检**，等排班系统下次自然进房重读——用户 08-15 定案）。

> **空闲定义（用户 2026-08-14 补充）**：训练室**没在专精**（无训练倒计时）、**没有待收取**（不是 00:00:00），但**协助位 + 训练位可以有人**（干员坐在里面）。即「空闲」≠「空房无人」——收取后干员仍在训练位/协助位、且未再开训练时，也是空闲。
> 判定上：**倒计时空 + 干员名/图标可读（有人）一般是倒计时 OCR 出错 → 走「其余 6 种不一致组合」原地重试 5 次**，不是直接下结论是空闲或训练中；重试后仍不一致才保守按训练中处理（矩阵本条不因「空闲可以有人」而改变）。

### 16.3 待收取（00:00:00）动作

| 图标 | 协助位 | 干员/技能在计划 | 动作 |
|---|---|---|---|
| 专三 | 任意 | 任意 | 正常收取 → 邮件带截图（③ m3_collect）→ 无论如何不保护 → 可排班 |
| 非专三 | 非逻各斯/艾丽妮 | 都不在计划 | 收取 → 通知帮收（④）→ 可排班 |
| 非专三 | 非逻各斯/艾丽妮 | 干员在、技能不在 | 收取 → 通知帮收（④）→ 可排班 |
| 非专三 | 非逻各斯/艾丽妮 | 都在计划 | **换人出问题** → 恢复流程（16.6）→ 期间排班接管 |
| 非专三 | 逻各斯/艾丽妮 | 都不在计划 | 收取 → 通知帮收（④）→ **不可排班**（保护，16.5） |
| 非专三 | 逻各斯/艾丽妮 | 干员在、技能不在 | 收取 → 通知帮收（④）→ **不可排班**（保护） |
| 非专三 | 逻各斯/艾丽妮 | 都在计划 | **重启清缓存恢复（丢失收取任务）** → 恢复流程（16.6）→ **期间排班不能接管**（保护） |

> **#98 failed 例外**：待收取格命中的是 **failed** 计划（恢复错过了训练期）→ **不接管**——静默收取、不按该计划记账/续训（避免无材料强开下一级、把他人训练误记为计划进度），并**抑制④帮收通知**（干员确实在 failed 计划里，「不在专精计划中」文案误导）；由扫描 `retry_failed_plans` 置 idle 后经已到target检测兜底。

### 16.4 训练中 / 空闲动作

**训练中（倒计时非 0）**
- **#98 恢复（截图为准适用于所有状态）**：无 active 时从匹配的 failed/idle 计划中按 priority/id 选一条，**恢复门 `_can_recover_plan`**（比 B8 采纳门更严）通过 → `_recover_to_training` 恢复 training（同一 update_plan_status 写 status + expires_at + swap_frozen=0 + 清 failed_reason，撤销 false-failure），此后按「计划匹配」正常管理（换人/收取）。恢复门要求：面板**干员名可读**且**技能被 `resolve_panel_skill` 无歧义命中并 == 计划 skill_index**（**禁子串回退**——OCR 退化片段如「技能」⊂ 所有技能名会把同干员另一技能的计划误恢复；截断前缀由解析器正确解析不受影响）。**反向约束**：不可读 / 含混 / 倒计时不可读 → 不恢复、不改写状态；技能可读时保留原重检（练完由 dispatch/gate 收），技能不可读静默等待（B8 稳为先）。
- 开了跟随排班（`assistant_follows_schedule=True`）→ 协助位可换（无论谁/计划），训练位不可移动（游戏设计）→ 冻结训练位。
- 未开跟随排班 + 计划匹配（干员+技能都在计划）→ 加载路线配置，结合倒计时 + 左下角 + 进驻详情 → 决定是否换人/收取 → 排换人任务或收取任务（去重，同计划只一条）→ **保护训练室**（后续排班不进训练室）。
- 未开跟随排班 + 不匹配（其他情况）→ 不动房间 + 通知① blocked 一次（按倒计时结束时刻去重，PRD #64 保留；通知≠动房间）→ **排一条未来重检**（倒计时结束 + 2min，`_upsert_skill_upgrade_task` 按 plan_key 去重恒 ≤1 条）。重检到点再进房，若占用已结束走待收取动作（16.3）。（#66/B1：原「下次排班再看」若无排班事件会一直不重检 → 每 ~4s 进出训练室死循环；排未来重检让队列不空。keepalive 已删，#74 第3段。）

**空闲（倒计时空 / 读失败）**
- **开始训练由带 plan_key 的 SKILL_UPGRADE dispatch**（#74 第3段「都去掉」）：`_reconcile` 空闲×未保护格在 `scan_plan`（任务 plan_key 指定计划）非 None 且仍 idle 时返回该计划开始；`plan_key=None`（占用重检）与排班顺路（`reconcile_short`）在空闲格不开始。
- 协助位不是逻各斯/艾丽妮 → 可排班。
- 协助位是逻各斯/艾丽妮 + 训练位有人 → 进技能选择页读该干员**所有**技能：**有专一/专二 → 不能动**（保护）；全专三或专0 → 可动。
- 协助位是逻各斯/艾丽妮 + 训练位没人 → 可排班。

### 16.5 保护检查（现读现判）

- **定义**：训练室的训练位/协助位保持现状不被排班系统改动。
- **解除时机**：每次排班进训练室重新读房重判，条件一变自动解除（开始训练 / 协助位换人 / 训练位空了）。
- **挡住谁**：既挡排班系统动房间，也挡 mower 自己开始训练——mower 想开始训练但房间受保护时**发邮件提醒用户**（新通知⑤），计划保持 idle。
- 已知风险：待收取+非专三+协助位逻各斯/艾丽妮+干员技能都不在计划时，若无新训练开始，房间会长期受保护（现读现判下条件不变则持续），见 §14。

### 16.6 恢复流程（待收取 + 干员+技能都在计划内 + 非专三）

1. 正常收取。
2. 该计划**优先级排前**（`update_plan_priority`）+ 置 `idle`。
3. 计划保持 idle 等续训（材料门控已按用户决定删除，§16.7：无开始前材料检查；续训由 dispatch 进房空房/待开始计划时自然触发）。
4. 期间：协助位不是逻各斯/艾丽妮 → 排班接管；是 → 排班不能接管（保护）。

> ✅ 实现注（2026-08-14 修正）：收取后训练位/协助位**仍保留原干员**（游戏机制：收取
> 只领成果、不挪人，除非手动换人），因此「排班不能接管」在恢复流程期间持续生效——
> 逻各斯/艾丽妮在协助位 → gate 整房跳过/冻结。§16.4「空闲 + 训练位没人 → 可排班」
> 只适用于真正没有干员的空闲房间（从头空），与「收取后」场景无关。

### 16.7 材料门控（开始训练前提）—— ❌ 2026-08-14 用户决定不实现，已删

> 定案原为「开始训练只在仓库扫描确认材料充足后进行；材料不足保持 idle，等下次扫描」。
> **实现后用户明确撤回**：不要材料门控（开始训练的触发/材料由仓库扫描 + 自动排程负责，
> 不做开始前的材料检查），相关代码（`mastery_materials_ready`/缓存/`_next_startable_plan`/
> reconcile 与重启恢复里的门控）已全部删除。材料不足走确认页 fail-fast 兜底（旧行为：
> `_start_new_training` 的 `TRAIN_SKILL_UPGRADE_ERROR` 分支置 failed）。

### 16.8 三态倒计时读取器

- 读取层实现「**有值 / 为0（00:00:00）/ 读失败**」三态，**不再把读失败和 00:00:00 都压成 now**（现状 `double_read_time` 三态缺失，base_mixin.py:399-405）。
- `RoomPanel.countdown` 携带三态；`classify_room_state` 按 16.2 矩阵消费。
- 修复点：完成房间（00:00:00）不再被当空房重置重开。

### 16.9 通知清单（新增类型实现时同步 §6）

- ① blocked（计划外训练占用，保留）
- ② fake_reset（保留）
- ③ m3_collect（专三收取，保留，带截图）
- ④ **帮收**：非专三收取 + 干员技能不在计划 / 干员在计划技能不在 → 通知「mower 帮忙收取」（新增）
- ⑤ **训练室受保护、mower 无法开始训练**（新增）
- ⑥ **已到target**：开始训练时发现已专三 → 邮件「已专三」+ DB 标完成（新增，草案要求）
- ⑦ **协助位纠错失败（#79，2026-08-15）**：run_swap_support 换人前确认协助位，陌生人纠错成 operator 失败 → 邮件「协助位 X 纠错失败，跳过减半换人」+ 不换人 + 排收取（key=plan id，WARNING）
- ⑧ **换人失败放弃（#81，2026-08-15）**：run_swap_support 减半换人失败，原地重试 SWAP_RETRY_LIMIT 次仍失败 / 剩余不足 5h → 放弃 + 邮件「换人失败已放弃，减半收益可能丢失」，**不置 swap_frozen=1**（reconcile 下次进房重新补排，暂时性失败可被救回；key=plan id，WARNING，与⑦ 并列）

### 16.10 开始训练术语流（草案 1-8，实现对齐）

1. 左下角读干员名+技能名+专精图标记下。
2. lit_zones 判当前等级：已专三 → 邮件⑥+标完成；非专三 → 记等级 → 点确认开始（对钩符号）。
3. 场景检测：确认页 → 技能选择页（开始成功自动退回）→ 再退出一次 → 回训练室主界面。
4. 打开进驻详情读协助位。
5. 按「当前等级+1」路线配置（= 当前步目标级；#76 2026-08-15：`_get_plan_route(plan, step_level)` 按 step_level 加载，不再用整体 target_level——专三计划专一/专二步用 level_1/2 路线减半换人）比对，非配置干员 → 换协助位。
6. 换人后回到进驻详情浮窗 → 关浮窗回主界面。
7. 重读左下角倒计时+干员名+技能名+图标，**以当前读取为准**（✅ #90 已实现：协助位
   安排后 `_re_read_train_countdown` 重读倒计时，换人判定/收取/`expires_at`/开始训练
   邮件完成时间都以重读值为准；读失败回退安排前值）。
8. 判断是否创建中途换人任务（减半）：是 → 排换人任务（路线 swap_target + 效率 + buffer + 倒计时，`calc_swap_threshold`）且**不排收取**，等 `SWAP_SUPPORT` 完成后重读倒计时再排收取；否（当前步路线无 swap_target，如专三）→ 直接排收取任务。

### 16.11 enable_mastery OFF（2026-08-14 定案）

- 自动收取 / 开始训练 / 换人 / 保护 / 通知 → 全停。
- 排班照常排训练室，**保留「被占用就不硬塞」防卡检查**（#59 gate，铁律 11 不变：排班永不写锁定训练位）——防排班硬写训练中的训练位卡到超时饿死其它任务。
- 与现状 §9 一致；本次定案补明确「防卡检查保留」语义。

### 16.12 开始训练邮件（#90，2026-08-16）

每级训练确认开始后发一封 INFO 邮件（`_confirm_training_started`，mastery.py）。改文案/时机前先读：
- **时机**：协助位安排（`_arrange_support`）之后、`_schedule_swap_if_needed` 判定之后才发
  （§16.10 第7步重读倒计时后，此时效率/倒计时已确定）。旧发送点在确认倒计时处、协助位安排之前。
- **档位 = 目标级** = 主界面左下角专精图标读数（`step_level`，亮 N 颗=专N，**不加 1**）；
  读不到显示「专精等级未知」（**不回退** `target_level`）。litzones/技能页星星 = 当前级、
  +1 才是目标级，是另一种来源。
- **真名**：`plan["skill_name"]`（如「二技能·破坏与滋养」），不用 `skill_index+1`。
- **完成时间两情况**：
  - 无减半换人 → 用重读的倒计时（`_re_read_train_countdown` 结果，读失败回退安排前值）；
  - 有减半换人 → SWAP_SUPPORT 任务触发时刻 + `(300 + mastery_swap_buffer)` 分钟
    （UI 文案「减半对象需在位时间 = 5小时 + 缓冲时间」；触发时刻 = remaining 降到
    `calc_swap_threshold` 阈值时，`_schedule_swap_if_needed` 的返回值），邮件附
    「将于 {触发时刻} 换入{路线 swap_target 干员}」（swap_target 读不到则省略该子句）。
- **`expires_at` 也用换协助位后的最终倒计时**：确认时先写安排前的倒计时（SM-03），
  重读后若与安排前不同则刷新 DB（同值跳过写，#82 同款）——安排前的倒计时基于旧效率，
  不是最终完成时间。
- 日志 INFO 用同一 msg 字符串（一起修正）。

