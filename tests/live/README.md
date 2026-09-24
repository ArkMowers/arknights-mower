# `tests/live/` — 实机脚本

本目录是 **S13 独占目录**（§10.3）。脚本**不参与离线门禁 G1**（`tests/live/**` 不被
`*_tests.py` 的 `discover` 收集），只在 S13 执行。

统一入口约定（§10.2 实机脚本规范）

| 项 | 约定 |
|---|---|
| 路径引导 | 文件头向上找 `tests/_bootstrap.py` 锚点，再用 `from tests._bootstrap import REPO_ROOT`；**不硬算 `parent.parent`** |
| 墙钟上限 | 每个脚本都有 `--seconds`（默认 ≤300），到点强制 `request_stop()` |
| 安全退出 | `finally` 里 `request_stop()`；`Ctrl+C` 可安全中断 |
| 日志 | 开头 `logger.setLevel(INFO)`（`utils/log.py:50` 把 level 硬编码为 DEBUG） |
| 读数可信度 | 关键判据连读 2~3 次取一致值 |

共享工具：`t1_common.py`（**文件名不以 `_tests.py` 结尾**，故不会被 G1 收集）。

---

## T1 — Wave 1 实机验收（零点击）

T1 是 **S13 的分片执行**，只覆盖与 Wave 1（S1–S5）相关的三项。
**不包含** S13 第 7 项（六个新 executor，属 S7–S12，尚未实现），因此**不是完整 S13**。

**T1 全程不得 tap / swipe，不得派发任何任务。**

| 顺序 | 脚本 | 对应 | 是否连真机 | 是否需游戏运行 | 副作用 | 回滚 |
|---|---|---|---|---|---|---|
| 1 | `t1_2_c5_regression.py` | S5（S13 item 6） | **否** | 否 | 无 | 无需回滚 |
| 2 | `t1_1_no_fake_task.py` | S1（S13 item 1） | **是**（只读截图） | 否 | 写 `tmp/mower.db` | 自动：`Copy-Item` 备份 → `finally` 还原 |
| 3 | `t1_3_pause_stop.py` | S13 item 9 | **是**（只读截图） | 否 | 无 | 无需回滚 |

> 顺序有理由：T1.2 最安全且价值最高；T1.1 会写 `mower.db`；T1.3 连真机设备。

### `t1_2_c5_regression.py` — C5 回归

**安全边界**：不连接任何设备、不 tap/swipe、不启动 `MainLoop`。
只读 `conf.yml` / `plan.json`；`config.conf.dorm_order` 的改动只存在于本进程内存，
`finally` 里还原。构造 `SchedulerState` 全程套 `no_save_conf()`，**绝不写用户的 `conf.yml`**。

**验什么**（三条硬性规约的落实）

| 规约 | 落实 |
|---|---|
| 正向 | 真实配置 + `backup_plans=[]` 构造 `SchedulerState`，不得抛 `宿舍优先级和当前宿舍不匹配`；断言 `plan` 非空、`config` 非 None |
| **规约 2 反向对照** | 故意设 `dorm_order = dormitory_9_9`（错配），**必须仍然抛** `ConfigError`；测完在内存里还原 |
| **规约 2 可证伪性** | 用子类复现 C5 修复前的分支（`_backup_plans` 为空时不调 `swap_plan`），该场景**必须**抛错 —— 证明判据真能变红 |
| **规约 3 只读** | 记录 `save_conf` 被拦截次数；并单独验证 `dorm_order == ""` 时该分支确实会命中 `save_conf`（>0），即该守卫**必要**而非摆设。跑前跑后比对 `conf.yml` SHA256 |

**用法**

```powershell
.venv\Scripts\python.exe tests\live\t1_2_c5_regression.py
.venv\Scripts\python.exe tests\live\t1_2_c5_regression.py --seconds 120
```

### `t1_1_no_fake_task.py` — 启动无假任务

**安全边界**：真机只做**只读** `screencap()`。`PCDevicePort.tap/swipe/swipe_path`
被**类级**替换成记录器 → 即使有任务意外产生也点不到屏幕，计数用于事后断言为 0。
**不派发任何任务**：`config.conf.workshop_settings == []` 使 `WorkshopPlanner.condition()`
为 False，`_build_planners` 只注册这一个 planner → 队列恒空。

**副作用与回滚**：`bootstrap.run()` 的 `finally` 会写 `tmp/mower.db`。
脚本用 `Copy-Item` 备份到 `mower.db.t1bak`，**在 `run()` 线程确认退出后**回写还原
（先还原再让写库线程继续会覆盖还原结果）。不使用 `git checkout`（会丢未提交成果）。

**验什么**（不靠"某行日志没出现"这种弱证据）

| 证据 | 采集方式 | 期望 |
|---|---|---|
| 任务推送计数 | 包 `TaskQueue.push` | **0**（任何类型都不该被推） |
| 日志行 | `LogCapture` 抓 `utils.log.logger` | `pushed SHIFT_ON` / `test: pushed` 各 **0** 行 |
| 点击计数 | 类级替换 `PCDevicePort.tap/swipe/swipe_path` | **0** |
| loop 存活 | 窗口内**逐秒连续采样** | 存活 ≥3 次且存活到窗口末尾 |
| 空转确实发生 | `no pending tasks, idling` 日志 ≥1 | 证明是"空转不崩"而非"没跑起来" |

> ⚠️ 存活判据**不得只看窗口末尾**。`--seconds` 同时是墙钟上限，窗口末尾恰好是
> `request_stop()` 的触发点，在那里读 `is_alive()` 只会读到"刚被停掉" —— 那是竞态，
> 会假红（本脚本首版实测踩到）。因此：窗口内连续采样 + 安全网定时器比观察窗口晚
> `CLOCK_GRACE_SECONDS` 触发，停止动作由观察者自己发出。

**用法**

```powershell
.venv\Scripts\python.exe tests\live\t1_1_no_fake_task.py --seconds 25
```

### `t1_3_pause_stop.py` — pause/stop 有效性

**安全边界**：真机只做**只读**探测（`Device()` + `screencap()` + `get_scene()`）。
`PCDevicePort.tap/swipe/swipe_path` 类级替换为记录器 → 零点击；
`TaskDispatch.execute` 被包一层记录器 → 断言**零任务派发**。
`SchedulerState` 构造套 `no_save_conf()`。等待全部走 `threading.Event.wait`
（既非 `pause.wait`，也非 `time.sleep`）。

**恒真陷阱与观察量的独立性（规约 1 / S13 规则 6）**

若观察者用 `pause.wait()` 观察"暂停后是否真的停住"，观察者会被**同一个 pause 挂起**，
于是根本没机会采样 —— 验证恒真。本脚本的做法：

- 观察量 = **`MainLoop._run_planners` 的计数器**。它每轮迭代都被调用、
  **本身不经过 pause**，所以 pause 后计数应停止增长。
- 观察者采样原语 = `threading.Event.wait`，**与 pause 协议无关**。

**必须先跑正向对照**：未 pause 时计数**必须**增长。若正向对照就不增长，说明观察量本身
失效 → 脚本判 `INVALID`（**不是 PASS**），不给出结论。这是 S4 flaky 的同类教训：
**先证明探针自己有效，再信它的结论**。

**验什么**

| 阶段 | 判据 |
|---|---|
| 正向对照 | 未 pause 时 ticks 增量 **> 0**（否则整次验证 INVALID） |
| pause | `is_paused=True`；线程仍存活（是被挂起不是崩了）；ticks 增量 **= 0** |
| resume | `is_paused=False`；ticks 增量 **> 0** |
| stop | `request_stop()` 后线程未存活，耗时 **≤10s** |
| 零副作用 | tap/swipe 计数 0、`TaskDispatch.execute` 计数 0、队列为空 |

**用法**

```powershell
.venv\Scripts\python.exe tests\live\t1_3_pause_stop.py
.venv\Scripts\python.exe tests\live\t1_3_pause_stop.py --seconds 90 --settle 3 --window 4
```

---

## T2 — S13 点击类分片（第 2/3/4/5/8 项）

T2 是 **S13 的第二个分片**，覆盖 Wave 1 遗留的**点击类**项。
**不包含** S13 第 7 项（六个新 executor，属 S7–S12 / Wave 3，**尚未实现**，无可测对象），
因此 **T2 完成 ≠ S13 结案**。

**T2 全程会点击游戏**，因此必须：MuMu 已启动、游戏已登录、`adb 127.0.0.1:16416` 在线。
每项跑完游戏可能停在 `INFRA_ARRANGE_ORDER(207)` / `INFRA_DETAILS_OPEN(230)`，
下一项开始前都会先做环境归一（`recover_if_stuck` / `dismiss_leave_infra_dialog` / `setup_to_infra_main`）。

| 项 | 脚本 | S13 | 需游戏运行 | 副作用 | 回滚 | 判定 |
|---|---|---|---|---|---|---|
| T2.1 | `t2_1_navigation.py` | item 2 | **是** | 写 `mower.db` | `Copy-Item` 备份 → `finally` 还原 | ❌ 失败（缺陷 A/C） |
| T2.2 | `t2_2_free_fill.py` | item 3 | **是** | **真实补位 3 人** + 写 `mower.db` | 游戏内手工调宿舍 | ✅ 15/15 |
| T2.3 | `t2_3_bug2_report.py` | item 4 | **是** | 写 `mower.db`（**不点任何干员**） | `Copy-Item` 备份 → `finally` 还原 | ❌ 失败（代码问题） |
| T2.4 | `t2_4_real_swap.py` | item 5 | **是** | **真实换人** + 写 `mower.db` | 游戏内手工调宿舍 | ✅ 12/12 |
| T2.5 | `t2_5_read_confidence.py` | item 8 | **是**（只读面板） | 写 `mower.db` | `Copy-Item` 备份 → `finally` 还原 | ❌ 失败 8/10（代码问题） |

共享工具（**文件名均不以 `_tests.py` 结尾**，故不进 G1）：
`t2_common.py`（设备/状态/备份）、`t2_nav.py`（导航腿 + 看门狗）、`t2_probe.py`（调用记账、
scene 采样、日志计数）、`t2_read.py`（稳定读数 + 滚动复位）、`t2_runner.py`（统一 `main()` 脚手架）、
`t2_task.py`（真实 `MainLoop` 驱动 + 房间读数）。

**每项脚本自带的统一保障**（`t2_runner.run_probe_script`）

- `--seconds` 墙钟上限 + `WallClockStop` 安全网（比观察窗口晚 `CLOCK_GRACE_SECONDS`）
- `mower.db` / `conf.yml` **前后 SHA256** 打印；`db_backup_t2` 用 `Copy-Item` 备份、
  `finally` 还原，并断言**无 `.t2bak` 残留**
- `finally: request_stop()`（正常结束 / `Ctrl+C` / 异常三条路径都收敛）
- `SchedulerState` 全程 `no_save_conf()`
- 证伪 / 正控对照（每项至少一条）

### `t2_1_navigation.py` — 导航全链路

**安全边界**：会点击（进房间、开详情、退首页）。**只进入并退出房间，不打开干员选择面板、
不点击任何干员、不提交任何变更**。

**为什么不得把「零点击」写成硬判据**：S13 要求"首页 → 基建 → 任意房间，scene 序列正确"，
而 `Navigator.enter_room()` 在 `navigator.py:134` **无条件**点一次房间中心，**没有任何
提前返回路径**。因此"零 tap/swipe"与"真的进入房间"**互斥**，脚本按**分腿点击预算**
下实质判据，并把字面零点击判据**如实记为 FAIL**（未放宽）。

**结果**：实质判据 **13/16**。全部房间腿通过；三项 FAIL（`到达首页 INDEX`、
`首页腿点击预算 ≤3`（实测 99）、`无任何腿被墙钟打断`）**同源于缺陷 A**。

### `t2_2_free_fill.py` — 自由位补位（A6 / BUG-1）

**安全边界**：真实补位（`Free` 位会真的被填上 3 人）→ 房间构成**会变**，需在游戏内手工回滚。
**证伪对照**：把补位判定静默化 → `free tap` 必须为 **0** 次。

**结果**：**15/15 通过**。`free tap` 3 次且互不相同、`swipe page` 0 次、
`uncheck slots=[2,3,4]`、终点 5 位全非空、保留位未被误动。

### `t2_3_bug2_report.py` — BUG-2 失败可上报

**安全边界**：进 `room_1_2` → 开选择面板 → 翻页扫描。`TARGET` 是一个**非真实干员名**
（`T2_不存在的干员_zzz`），因此**面板上永远不可能命中它** → **全程不点任何干员**，
无半成品排班。

**⚠️ 本项为何用"构造"而非"塞一个真不存在的干员名"**：S13 原方案实测**走不到**失败点。
名字不认识 ⇒ `DEFAULT_FILTER="ALL"` ⇒ 需翻 27+ 页，翻到第 5~20 页游戏切
`LOGIN_LOADING(104)`，`agent_swap_base.py:110` 直接 abort；换成职介明确的真实名字后，
面板职介筛选**实际没有收窄**列表（实测 `filter=MEDIC` 却扫出 `能天使`(SNIPER)、
`德克萨斯`(PIONEER)），同样要 27+ 页。故改用**产品自身**的翻页上限守卫：
把 `MAX_PAGE`（`constants.py`，**产品代码不改**）50 → 3，由 `_advance_page` 抛
`AgentSwapError("max page reached")` —— 与"目标扫不到"**同一语义**，只是更快到达。

**结果**：**11/11 预测成立 → 失败（代码问题）**。主臂：`AgentSwapError` 正常抛出，但被
`agent_swap_base.py:126-128` 的 `except Exception: return False` **吞掉** ⇒
`state.error` 恒为 `False`、任务悬挂。**正控臂**：仅把该处改成 `raise` ⇒ 立即
`executor failed for task` → `task failed` → `state.error=True` 且队列清空 ⇒
**下游 dispatch/loop 完好，缺陷位置唯一确定**。

### `t2_4_real_swap.py` — 拆分后唯一真实换人

**安全边界**：**真实换人**（会改房间构成）→ 需游戏内手工回滚。

**结果**：**12/12 通过**。真实点击换入 `流明`/`琴柳`，自由位按预期补 `Free`，
房间构成按预期变化、无残留。

### `t2_5_read_confidence.py` — 读数可信度

**安全边界**：会导航并点一次 `arrange_check_in` 打开详情面板，但**不打开干员选择面板、
不点击任何干员、不提交任何变更**。自证段用 `MockDevicePort` + 空存储，**不连真机、不碰数据库**。

**两件事**：① **自证**（把 `RoomReader._read_name` 猴补丁成交替返回两个值 → 必须判
`INVALID`；若工具恒绿，则 T2.2/T2.4 的读数结论**全部作废**）；② **实机连读 3 次**。

**结果**：**8/10 → 失败（代码问题）**。A 臂（不复位滚动）第 2/3 次读出
`缄默德克萨斯×3`（同屏重名**物理不可能**）⇒ 证明**一致性 ≠ 正确性**；
B 臂（每次读数前复位滚动）3 次完全一致。

---

## T2 实测发现的产品缺陷（**只上报，不修复**）

T2 是**验证方**，`arknights_mower/` 下**未改一行**。缺陷清单（详见报告）：

| 编号 | 类型 | 位置 | 要点 |
|---|---|---|---|
| A | 代码问题 | `constants.py:104` | `TapPosition.CONFIRM_YES=(1371,998)` 落在 `224 离开基建` 确认框外（实测框 `(835,683)-(1082,800)`，正确 ≈`(1080,741)`）⇒ 224 永不可关 ⇒ `navigate(INDEX)` 空转 |
| B | **识别问题** | `agent_swap_arrange.py:35-51` | `_detect_arrange` 先查降序窗口，`心情` 列静态字形恒命中 ⇒ 永远返回 `('心情', False)`，宿舍定向换人**挂死**（`StepRetry` 无 guard/超时） |
| C | 代码问题 | `navigator.py:99-136` | `enter_room` 先 `clip` 再判越界 ⇒ 两个 panic-swipe 分支是**死代码**；屏外房间永不可达，函数仍 `return True` |
| D | 代码问题 | `room_reader.py:52-59` | `scan_room` 上滑读 3-4 槽位后**不回滚** ⇒ 后续读数错行；`_read_name` 无分数下限 ⇒ 静默返回错名 |
| E | 代码问题 | `agent_swap_base.py:126-128` | 普通异常被降级为 `return False` ⇒ 业务失败不可上报（T2.3 主证） |
| 待定 | 识别/代码 | `agent_swap_arrange.py:_open_filter` | 职介筛选**未真正收窄**列表（T2.3 run3 实证），归因未定 |

**需主控裁定**：T2.1 的「零 tap/swipe」与「真的进入房间」互斥（见上）。

---

## 既有脚本（S0 从 `scripts/` 迁入）

### `verify_scheduler_live.py`

默认**只读探测**：`conf.yml` 的 adb 地址、`Device()` 连通性、`screencap()` 尺寸、
`get_scene()`、场景图可达性。加 `--run` 才启动真实 `MainLoop`。

⚠️ 该脚本的 pause/resume 验证用的是 `time.sleep`（第 143/147/151 行附近），
属 §10.2 **豁免清单**：观察者若改用 `pause.wait()` 会被同一个 pause 挂起导致验证恒真。
**不要以"清理 time.sleep"为名改这几处**（详见 §10.2 的豁免规则表）。

### `verify_shift_live.py`

⚠️ **会真的点击游戏**（跑一个 SHIFT_ON 任务）。需游戏已登录且你愿意让它操作。
硬性墙钟上限（默认 180s），`finally` 里 `request_stop()`。

### `probe_select_panel.py`

⚠️ **会点击游戏**，但**只点击「空位」打开选择面板，绝不点击任何干员**，随后原路退回
`INFRA_MAIN`，不提交任何变更。

用途：复现 `_do_scan` 的面板读数，判定 free 补位分支实际会点到哪个干员
（BUG-1 的推断来源）。

**S13 合规补齐（本次）**：原脚本缺 `--seconds` 与 `request_stop()`（违反 §10.3 规则 2），
且第 6 步构造 `SchedulerState` 未套 `save_conf` 守卫（违反规约 3）。现已补：

- 新增 `--seconds`（默认 300）
- 新增 `_AbortOnStop`：`request_stop()` 后 `wait_if_paused()` 抛 `MowerExit`，
  把控制流从 `Navigator` 内部**硬拽出来**（`Navigator` 已 `except MowerExit`），
  而不是等它自己走完
- `main()` 的 `finally` 调 `request_stop()`；`Ctrl+C` 可安全中断
- 第 6 步套 `no_save_conf()`

```powershell
.venv\Scripts\python.exe tests\live\probe_select_panel.py --room dormitory_2 --seconds 120
```

> 本次 T1 为**零点击**执行，因此 `probe_select_panel.py` 的真实点击路径**未被实机跑过**；
> 只离线验证了 `--seconds` 参数与 `MowerExit` 中断器生效。真正跑它属后续 S13 分片。

---

## 一次性临时脚本（**不进交付物**）

证伪用的 throwaway 脚本放在 `tmp/`（不是 `tests/live/`），因为它们不受
`tests/live` 规范约束，也不该被当成可复用资产：

| 文件 | 用途 |
|---|---|
| `tmp/s13_t1_falsify.py` | 注入假任务到真实 `bootstrap.run()`，证明 T1.1 判据会变红 |
| `tmp/s13_t1_falsify_pause.py` | 三实验证明 T1.3 判据会变红，并复现恒真陷阱 |