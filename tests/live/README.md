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