---
title: 组内床位接管中断高优先恢复
status: implemented
category: bug-fix
date: 2026-10-08
---

# 组内床位接管中断高优先恢复

## 范围

本修改使用 10 月 8 日捕获的[排班表](../../../../arknights_mower/tests/fixtures/scheduler_incident_plan_20261008.json)和[观测状态](../../../../arknights_mower/tests/fixtures/scheduler_incident_20261008.json)，实现 [INV-SCHED-37]。捕获问题在基线 `87b9d3aa` 及独立修复基点 `31709700` 上复现。相关契约为[编码标准](../../../../CODING_STANDARDS.md)中的 [INV-SCHED-05]、[INV-SCHED-20] 和 [INV-SCHED-21]。

## 证据

| 时间 | 观测 |
| --- | --- |
| 11:05:55.813 | 完整换班收敛将歌蕾蒂娅安排到宿舍 1 的槽位 4，深海组休息。 |
| 11:07:47.603 | 房间读数记录她的心情为 0；保存的床位恢复完成时间为 18:44:53.645。 |
| 11:09:22.723 | `restore_displaced_resting` 报告床位接管触发深海整组回班。 |
| 11:09:23.534 | 完整换班收敛将歌蕾蒂娅安排回中枢。 |
| 11:12:35.126 | 下一次在岗实测心情仍为 0。 |
| 11:12:39.505 | 完整换班收敛再次将她安排到宿舍 1 的槽位 4。 |

配置给歌蕾蒂娅设置集中恢复优先级，将乌尔比安、斯卡蒂、安哲拉、幽灵鲨列为休息低优先成员。红松组接管这些较低优先成员的床位。`11:09` 的执行前队列只有一份新生成的 SHIFT_OFF；完整收敛之前，该任务的具体安排已经包含整组回班。

## 原因

[`_get_resting_plan`](../../../../arknights_mower/solvers/base_schedule.py)为等待组分配床位，再调用 [`restore_displaced_resting`](../../../../arknights_mower/utils/scheduler_task.py)。一名尚未完成恢复的必需主班失去床位时，函数将其同组全部成员加入工作安排，并清空被召回成员的床位记录。召回过程不逐一检查其他成员的心情或集中恢复优先级。

单个床位的接管因此中断整个恢复组，连恢复完成时间仍在七小时后的高优先成员也被召回。她回岗后的零心情读数又生成用尽下班任务。以薇薇安娜和歌蕾蒂娅休息状态为条件的副表跟随这些变化，再次切换工作驻员。

完整换班收敛完成当前任务的内存推演。局部 `returning` 集合只阻止刚回班成员在同一轮再次尝试下班；该保护随本轮结束，不保证后续观测和任务之间的恢复稳定性。

## 准入契约

[INV-SCHED-37] 要求申请者的层级严格高于所有受整组召回影响、尚未完成恢复的非宿舍固定岗、非工作狂成员，包括当前无床及心情未知的成员。已完成恢复的成员不保护尚未完成的较低层级组员。已恢复成员或待命成员让床后仍保留必需恢复成员时，整组继续恢复并保留回班任务。

恢复完成须有有效心情读数，排除倒计时到期后生成的预测值。床位截止时间已过，不能在实测未完成或心情未知时单独授权接管。Current 和未指定位置仅在最终安排没有将该姓名明确移走时保留原入住者。固定组恢复床位也提供留宿锚点，但不因此成为普通动态床位。

完整组准入先按待提交安排过滤每张候选床位，再在写入任何床位预约之前复核最终安排。最终安排撤走必需恢复成员时，接管采用完整的整组召回规则。不合法的候选床位不会阻止继续选择另一张合法较低层级床位。被拒绝的安排保留原床位、恢复截止时间和调用者的排班。严格更高层级的恢复申请者仍可合法接管整组床位；被召回组随后以相同或更低层级申请这些床位时不能立即重新接管。个人上限、预约、排除名单及明确任务执行保持现有边界。

## 实现与简化预检

`Operators.resting_recall_members` 为准入与失床补偿提供同一份召回成员。`resting_recovery_complete` 为召回、分床、空闲补床和执行时的 Free 选人共用恢复完成证据。`_resting_residents` 解析最终槽位身份，包含明确移动和本轮新增预约；`_retained_resting_members` 从中取出 `_resting_preemption_allowed` 使用的留宿姓名。`restore_displaced_resting` 使用同一份槽位解析，在写入补偿目标前用 Current 将工作设施或宿舍的短目标行补齐至配置长度。候选过滤和 `assign_dorm_group` 最终验证均在写入床位预约之前执行。空闲补床和 Free 选人在消耗恢复候选之前拒绝不合法床位，因此仍可使用另一张合法床位。

自动具名执行在重建改变安排或类型后、写入心情兜底状态或实际补偿前，再次进行共用关键任务准入。[INV-SCHED-36] 可以延期或调整这份安排；[INV-SCHED-37] 继续保护已观测的恢复状态。[执行记录](2026-10-08-named-bed-preemption-revalidation.zh.md#共用规划器实现)拥有这一生产边界。

[`emergency_dorm_plan`](../../../../arknights_mower/utils/emergency_recovery.py) 在预演对象上保留完整床位池。预约、保护和本轮已分配的位置通过索引排除，其驻员仍对整组召回判断可见。床位缓存缺名时，身份从实际干员位置补齐。紧急重排只清空可分配的床位副本，保留观测状态。修改沿用现有推演和分配边界，不新增持久调度状态或任务类型。

## 验证与边界

[离线事件回归](../../../../arknights_mower/tests/scheduler_incident_20261008_tests.py)恢复捕获的干员状态、有效副表条件和九个床位记录，执行真实 `resting`、`_plan_primary_recovery`、空闲补床和整组召回逻辑。测试通过 `update_detail` 重复观测零心情，分别以主班规划后补床、补床后主班规划的顺序执行三轮，将新生成且到期的安排投影为下一轮状态，歌蕾蒂娅始终留宿。原床位保护实验保留为对照用例。

[专用准入测试](../../../../arknights_mower/tests/group_preemption_stability_tests.py)覆盖同层级和较低层级中断拒绝、未知或预测心情、无床成员、合法更高层级整组召回、已恢复高优成员、分床失败的原子性和合法替代床位。执行测试让 `agent_arrange` 经过 Free 解析和失床补偿，在设备边界停止，检查真实 `update_detail` 后仍保留过期截止时间、锚点明确回班而宿舍行使用 Current、遗漏或短行、最终工作位置及旧回班任务撤销。紧急保护锚点分别覆盖有床位缓存姓名和缺名的情况。修补前，审查提交上的 11 个边界用例失败。

[固定组恢复覆盖](../../../../arknights_mower/tests/same_group_dorm_replacement_tests.py)执行分床和宿舍安排合并，再检查最终投影。邻近的待命、已恢复成员离宿、紧急预约、单回准入、菲亚梅塔、分散偏好及换班收敛用例通过。治理门检查文档结构、链接和术语，功能断言验证排班行为；编码标准和需求结论还包含对生产调用及状态修改顺序的人工检查。

```text
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/scheduler_incident_20261008_tests.py -k 'preemption or priority_recall' -q
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/group_preemption_stability_tests.py arknights_mower/tests/resting_preemption_tests.py arknights_mower/tests/completed_group_departure_tests.py arknights_mower/tests/emergency_group_beds_tests.py arknights_mower/tests/shift_cycle_convergence_tests.py arknights_mower/tests/fiammetta_dorm_isolation_tests.py arknights_mower/tests/dorm_admission_priority_tests.py -q
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/same_group_dorm_replacement_tests.py -k 'complete_shift_uses or fixed_alternative or normal_rotation_uses or fixed_target_is_preserved or reserved_fixed_slot or yields_with_required_anchor' -q
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/automatic_rescue_tests.py -k 'entry_reallocat or entry_dorm_plan' -q
python -B -X utf8 -m pytest -p no:cacheprovider arknights_mower/tests/dorm_isolation_tests.py -k 'emergency_' -q
python -B -X utf8 scripts/verify_governance.py
```

快照使用日志中的观测与捕获配置重建规划，不执行设备输入，也不回放整个游戏过程。运行日志中的源码行号与本提交基线不同，但同一错误规划行为在基线上复现。初次验证对象为审查提交 `42bf3467` 加准入与 Free 修补，比较基准为 `31709700`。这些测试在准入前更新观测，或执行 Free 占位符；跨任务事故测试直接投影生成的安排。它们不证明自动生成的具名接管在观测或入住者变化后仍可安全执行。[自动具名接管记录](2026-10-08-named-bed-preemption-revalidation.zh.md)定义后续补齐的执行边界。全部测试、无关事故用例及与更新 alpha 提交的兼容性不在这次 rebase 前验证范围内。当时的治理脚本提供三个结构检查门，不接受比较基准参数；rebase 目标的当前治理入口接受 `--base`，用于检查变更引用。

[延期任务重复生成记录](2026-10-08-deferred-exhaust-task-duplication.zh.md)保存这段反复换班之前的独立队列堆积问题。

## 编码标准评审

初次审查覆盖共用召回成员和最终槽位身份、床位和组遍历有界、独立推演、预约归属、规范领域用词及针对性离线测试。其治理检查和 Ruff 结果涉及文档结构及 Python 风格。这些检查不证明自动具名接管的准入证据变化后，执行仍符合 [INV-SCHED-37]。领域概念沿用现有定义。

## 规格评审

初次通过用例覆盖普通分床、准入证据未变化时的空闲补床、Free 执行、最终组准入拒绝、保留最终留宿锚点的已恢复成员或待命成员离宿、明确回班、更高层级准入及保留保护锚点的紧急补床。事故测试的重复观测及两种任务顺序，通过直接投影新生成安排保留高优恢复。自动具名接管在观测或入住者身份变化后的执行不在这些通过用例内，其契约由关联执行记录定义。

## Rebase 合并

首次 alpha rebase 的目标为 `9028fd00b123e610d1db50aa8f88e53c96878543`。完整的 rebase 前修复保存在 `85f69f66ea63bbda44419956933fde29f3c090bb`，包含初始 HEAD `42bf34678418af88a2bf2dfc879b538320aa4fe2` 之后保存的工作树修补。当次独立复审以该目标 SHA 至当时最终工作树（含未提交修改）为范围，并对照 `3170970051c8b4204c65260aa449aaf81fe130f0` 之后的完整修复检查保留情况。

首次合并保留本准入记录与独立的[自动具名执行记录](2026-10-08-named-bed-preemption-revalidation.zh.md)，包含双语镜像和元数据。当次合并将上游回收站保证从冲突的 [INV-SCHED-37] 迁移至 [INV-SCHED-40]，保留其完整保证及引用。现有待执行用尽下班、空闲观测、共用调度游标和右侧设施驻员契约继续生效。既有 implemented 用尽下班及空闲观测记录拥有各自决策；重放的诊断提案没有独立契约，其有效证据保留在这些所有者及已保存的 Git 历史中。

整组优先级、恢复锚点、自动执行复核和补偿隔离改变宿舍分床优先级、完整换班收敛及实际驻员与投影驻员现有概念下的执行规则。概念名称、含义、边界及关系不变，因此 [INV-06] 无需词汇表修改。上文测试和审查声明描述 rebase 前的历史证据。

### 首次 alpha 离线检查

首次 rebase 后 HEAD 为 `ef99a0daab457048e76706e8a87f18cadffb23c8`。下列检查保存针对首次目标 `9028fd00b123e610d1db50aa8f88e53c96878543` 及当时工作树中后续短行修复、夹具调整、关键任务窗口修复、回归测试、文档及格式调整的验证。结果属于首次合并的历史证据。

首次针对性执行有四个失败：三个参数化用例依赖旧床位顺序，一例暴露补偿写入宿舍短行时的 IndexError。夹具现选取宿舍 2、槽位 2 的实际组员，并检查其属于 `DEEP[1:]`；单回重排后的自动具名入住者仍不同于原恢复申请者。明确离宿夹具选择与锚点不同宿舍的让床成员，使锚点短行赋值保留合法接管安排。床位、截止时间、回班任务及拒绝断言均保留。当前补齐逻辑通过既有回归用例修复正式代码的短行失败。

```text
python -X utf8 -m pytest -q arknights_mower/tests/group_preemption_stability_tests.py arknights_mower/tests/scheduler_incident_20261008_tests.py -k 'preemption or priority_recall'
```

随后独立需求复审复现与 [INV-SCHED-36] 的 P2 交互：自动重建将安排预算从 100 秒增至 460 秒，原准入仍允许执行越过下一关键任务窗口。实际写入前重新调用共用优先级保护，修复这一执行路径。新增 RUN_ORDER 和已启用 SWAP_SUPPORT 两例，修复前失败、修复后通过；[执行记录](2026-10-08-named-bed-preemption-revalidation.zh.md#首次-alpha-执行修复证据)保存独立回放的时间及状态证据。

最终修复后的执行通过 52 条用例：全部 48 条稳定性用例和 4 条选中的事故用例；另 4 条事故用例未执行。最终邻近离线验证通过 406 条用例，涉及 `arknights_mower/tests/` 下的 `resting_preemption_tests.py`、`completed_group_departure_tests.py`、`same_group_dorm_replacement_tests.py`、`fixed_dorm_cover_admission_tests.py`、`dorm_priority_refresh_tests.py`、`emergency_group_beds_tests.py`、`dorm_admission_priority_tests.py`、`fiammetta_dorm_isolation_tests.py`、`shift_cycle_convergence_tests.py`、`dorm_isolation_tests.py`、`dorm_run_order_guard_tests.py`、`priority_admission_tests.py` 和 `mastery_scheduling_tests.py`。该轮报告相同的两条 Pydantic 序列化警告。

```text
python -X utf8 scripts/verify_governance.py --base 9028fd00b123e610d1db50aa8f88e53c96878543
python -X utf8 -m pytest -q arknights_mower/tests/verify_governance_tests.py
```

三个治理门均通过；两份未改动的 archived ADB 记录产生测试引用兼容性警告。针对性治理测试通过 25 条测试和 21 条子测试。四个生产文件和三个测试文件通过 Ruff 静态及格式检查。治理结果证明结构有效；行为、语义审查及词汇表批准仍是独立检查。

这些首次合并验证使用离线替身，并在设备输入前停止调度，不启动游戏、不连接设备、不运行全部测试。当次标准轴和需求轴独立复审的范围为首次目标 SHA 至当时最终工作树，包含未提交修改。对应复审报告分别记录结论以及这些行为和结构检查结果。

## PR 的最新 alpha 合并

最新实际 alpha 目标为 `4edfb1a57f715d284376d1473056649253ec0ed1`，比首次目标多十九个提交。再次合并提交并 rebase 前，完整的首次合并修复及工作树改动保存在 `backup/group-bed-preemption-complete-pr-20261009` 的 `76e3df9aded0481e709fb3a89b6637806a8f83aa`。本次独立复审范围为新目标 SHA 至最终工作树，包含未提交修改。保留情况对照原修复基准 `3170970051c8b4204c65260aa449aaf81fe130f0` 及已完整保存的修复检查。

新目标使用 [INV-SCHED-40] 登记加工确认后的专精派发保证。回收站的完整保证保留在 [INV-SCHED-41]，整组接管优先级继续使用 [INV-SCHED-37]。本次合并保留整组优先级、最终恢复锚点、合法替代床位、自动具名执行复核、规划期补偿隔离、实际入住者快照、短行补偿及重新进行关键任务准入，同时保留既有特殊任务边界。

上文首次目标下通过的 52 条针对性用例及 406 条邻近用例仍是历史结果。最新目标的针对性验证在测试隔离修正后通过 52 条用例，另 4 条事故用例未执行。守卫拦截 `requests.Session.request`、socket 连接及 `sqlite3.connect`；该轮报告零次尝试。既有领域概念评估不变，两份词汇表均未修改。

最新目标的邻近验证通过 512 条用例，范围为首次合并的十三份测试，加上 `arknights_mower/tests/` 下的 `mastery_maintenance_tests.py`、`maintenance_run_order_tests.py` 和 `workshop_mastery_dispatch_tests.py`。两条 Pydantic 序列化警告来自 `dorm_priority_refresh_tests.py` 中旧格式的 Task/Trigger 字典。后续带守卫的邻近审计首次捕获已启用 SWAP_SUPPORT 的初始菲亚梅塔用例触发公告请求；该既有测试现使用 `offline_maintenance`，行为断言保持不变。修正后的带守卫重跑通过相同的 512 条用例，保留相同的两条警告，request、socket 及工作区 SQLite 尝试均为零。该轮使用独立的 `MOWER_DATA_DIR`，仅允许临时测试数据库。八个改动的 Python 文件通过 Ruff 静态及格式检查；`git diff --check` 通过。

本次结构检查命令为 `python -X utf8 scripts/verify_governance.py --base 4edfb1a57f715d284376d1473056649253ec0ed1`。实际结果及独立复审结论由最终复审报告记录，与这些行为结果分别呈现。当前复审以新固定目标至最终工作树（含全部未提交修改）为范围，旧目标结果不证明本次范围。

## CI 回归对齐

`56c27c477aba19e5bbafe7d52daf1a27b9a03605` 的 CI 报告八个失败，本地针对性执行复现全部八个：六条旧用例在心情未恢复或未知时仍将床位倒计时到期当成恢复完成，两份简化 `SimpleNamespace` 夹具缺少共用召回策略调用的接口。跑单失败夹具现使用 `Operators`，产物预约床位夹具使用 `Operator`，保留原有任务留存及预约断言。

[清退测试](../../../../arknights_mower/tests/dorm_release_tests.py)使用 `update_detail` 记录实测完成，覆盖个人上限 12、20、24。截止时间缺失、未到期或已到期时，未恢复住客均保留床位。[未知心情选人测试](../../../../arknights_mower/tests/dorm_unknown_selection_tests.py)在各类截止时间下检查未知、无效及预测读数，保留原心情与床位状态，并验证实测完成后规划和选人允许相同接管。针对性 CI 复现及完成对照共通过 41 条用例。

[自动执行测试](../../../../arknights_mower/tests/group_preemption_stability_tests.py)新增三条合法准入后的配置变化用例：申请者失去优先级、原有成员提高优先级、新绑入组员具有相同优先级。执行在设备输入前拒绝失效召回，保留床位、截止时间及队列中的整组回班任务。三条均通过。测试扩展现有排班概念下的 [INV-SCHED-37] 证据；[INV-06] 无需词汇表修改。

最终离线验证基于相同 HEAD 及上述测试修复，22 份针对性排班测试共通过 956 条用例，报告三条警告。守卫禁止 socket 连接及工作区 SQLite 访问，两项尝试次数均为零。`MOWER_DATA_DIR` 指向独立临时目录。复审对照 `4edfb1a57f715d284376d1473056649253ec0ed1`，覆盖完整 PR 及本次修复，包括分床、普通及自动执行、补偿、救急准入、预约和关键任务保护。该范围没有剩余已确认的标准或需求缺陷。离线执行在设备输入前停止；真实设备行为不在本次验证范围内。
