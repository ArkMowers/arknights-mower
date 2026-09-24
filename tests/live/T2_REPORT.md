## Session S13-T2 报告（点击类分片：第 2/3/4/5/8 项）

- **状态**：完成（测试指标已跑完并收口；**含 3 项失败，均归因到产品代码**）
- **变更文件**：
  - 新增 `tests/live/t2_1_navigation.py`(300)、`t2_2_free_fill.py`(244)、`t2_3_bug2_report.py`(287)、
    `t2_4_real_swap.py`(260)、`t2_5_read_confidence.py`(298)
  - 新增共享模块 `tests/live/t2_common.py`(230)、`t2_nav.py`(286)、`t2_probe.py`(272)、
    `t2_read.py`(170)、`t2_runner.py`(127)、`t2_task.py`(169)
  - 改 `tests/live/README.md`（补 T2 小节：安全边界/须运行游戏/副作用/回滚/缺陷清单）
  - 改 `重构流程.md` §10.3（**只追加** T2 结果小节）
  - **`arknights_mower/` 下改动 = 0 行**（T2 是验证方，不修复）
- **门禁**（T2.3 重写后复跑）：G1=**Ran 127 tests OK / exit 0（连跑 3 次全绿）** G2=exit 0
  G3=**13 errors（≤13 基线）** G4=exit 0 G5=**Ran 13 tests OK / exit 0**
- **新增测试**：`tests/live/` 20 个文件（含既有），**不参与 G1 收集**（文件名不以 `_tests.py` 结尾）→ G1 计数仍为 **127**，未污染业务基线
- **基线数字变化**：`scheduler/` 行数/文件数**未变**（本次未改产品代码）；`>300 行文件` 仍为 **0**
  （`tests/live` 全部 ≤300，最大 `t2_1_navigation.py`=300）
- **遗留/未做**：
  - **S13 第 7 项（六个新 executor，属 S7–S12 / Wave 3）尚未实现，无可测对象 ⇒ T2 完成 ≠ S13 结案**
  - Wave 2（S6）尚未开工（最后一次功能提交为 S5 `59ca3d46`），T2 只覆盖 Wave 1 遗留点击类项
  - `_open_filter` 职介筛选未真正收窄列表，**归因未定**（识别问题 or 代码问题）
- **需要主控裁定**：**有（1 项）** —— T2.1 的「零 tap/swipe」与「真的进入房间」**互斥**
  （`Navigator.enter_room()` 在 `navigator.py:134` 无提前返回路径地执行一次 tap）。
  本分片按分腿点击预算下实质判据，字面零点击判据**如实记 FAIL，未放宽**。

---

### 逐项结论

| 项 | S13 | 判定 | 实机证据 |
|---|---|---|---|
| T2.1 导航全链路 | item 2 | ❌ **失败**（代码问题） | 实质 13/16；`to_index … tap=99 … [ABORTED 本腿预算 60s 到点]` |
| T2.2 自由位补位 A6/BUG-1 | item 3 | ✅ **通过 15/15** | `free tap` 3 次互不相同、`swipe page == 0`、`uncheck slots=[2,3,4]` |
| T2.3 BUG-2 失败可上报 | item 4 | ❌ **失败**（代码问题） | 11/11 预测成立；`max page reached` 抛出后被 `_run_steps` 吞掉 |
| T2.4 拆分后唯一真实换人 | item 5 | ✅ **通过 12/12** | 真实换入 `流明/琴柳`、房间构成按预期变化 |
| T2.5 读数可信度 | item 8 | ❌ **失败 8/10**（代码问题） | A 臂读出 `缄默德克萨斯×3`（同屏重名物理不可能） |

---

### T2.1 导航全链路 —— 失败（代码问题，缺陷 A/C）

**实机日志片段**

```
[环境恢复] 撤离 224：LEAVE_INFRASTRUCTURE -> INDEX px=(1080, 741)
[to_index] ok=False  INFRA_MAIN -> LEAVE_INFRASTRUCTURE   tap=99 swipe=0 path=0 t=60.1s  [ABORTED 本腿预算 60s 到点]
[5b] 屏外房间 room_1_1: enter ok=True 201->205  detected=room_1_1（未滑进视口 ⇒ clip 早于边界判断）
```

**逐条判据（实质 13/16）**

| 判据 | 结果 |
|---|---|
| 到达首页 INDEX(1) | ❌ FAIL |
| 首页 → 201 完成 | ✅ |
| 两个房间 `enter_room` 都成功 | ✅ |
| 两个房间 `_detect_room` 均正确 | ✅ |
| 进入后 scene 是详情类(205/230) | ✅ |
| scene 序列 201 → 详情类 且顺序正确 | ✅ |
| 进入房间腿恰好 1 次 tap | ✅ |
| 进入房间腿 swipe ≤1（贴边兜底） | ✅ |
| 退回 201 的腿零点击（2 个房间） | ✅ |
| 进入基建腿点击预算 ≤3 | ✅ |
| **首页腿点击预算 ≤3（实测 99）** | ❌ FAIL |
| **无任何腿被墙钟打断** | ❌ FAIL |
| 证伪: `enter_room(不存在房间) == False` | ✅ |
| 证伪: 该腿零点击 | ✅ |
| 证伪: `control_central` 确被找到（False 不是提前返回） | ✅ |
| 证伪后能安全退回 201 | ✅ |
| 字面项「全程 tap/swipe = 0」 | ❌ FAIL（与"真进房"互斥） |

**归因：代码问题（缺陷 A + C）**

- **缺陷 A** `constants.py:104`：`TapPosition.CONFIRM_YES` 归一化 → 像素 `(1371, 998)`，
  但 `224 离开基建` 确认框 `double_confirm/main` 实测落在 `(835,683)-(1082,800)`，
  该点**在框外** ⇒ 224 永不可关 ⇒ `navigate(INDEX)` 永久自旋。有效点 ≈`(1080,741)`
  （独立复现：`tmp/t2_recover_224.py`，点 1 次即离开 224）。
- **缺陷 C** `navigator.py:99-136`：`enter_room` 先 `np.clip`（117 行）再判越界（120/126 行）
  ⇒ 两个 panic-swipe 分支是**死代码**；屏外房间 `room_1_1` 永远滑不进视口，
  函数仍 `return True`。
- **三项 FAIL 同源**：全部由缺陷 A 导致（该腿自旋 + 被墙钟打断）。

**需主控裁定**：S13 要求"首页 → 基建 → 任意房间，scene 序列正确"与"零 tap/swipe"，
而真进房必然 tap ⇒ 二者互斥。**未放宽**，如实记 FAIL。

---

### T2.2 自由位补位（A6/BUG-1）—— 通过 15/15

**实机日志片段**

```
[0] mower.db  = 898b4c97…979213
[0] conf.yml  = 417bb224…7b1b
[0] mower.db 已备份 -> mower.db.t2bak
-> PASS  free tap 出现 3 次 / 三次互不相同
-> PASS  uncheck slots == [2, 3, 4]（先腾位）
-> PASS  补位在第 0 页完成（swipe page == 0）
-> PASS  证伪: 修复前写法下 free tap == 0
[9] 无 .t2bak 残留 = True
[T2.2] 15/15 项通过
```

**副作用与回滚**：真实补位 3 人 ⇒ `dormitory_2` 构成**已变**，需在游戏内手工回滚。
`mower.db`/`conf.yml` SHA256 前后一致、无 `.t2bak` 残留。
**证伪对照**：静默化补位判定 → `free tap == 0` 且补不满 ⇒ 判据可证伪。

---

### T2.3 BUG-2 失败可上报 —— 失败（代码问题，缺陷 E）

**构造方式说明（重要）**：S13 原方案"塞一个真不存在的干员名"**实测走不到失败点**：

- 名字不认识 ⇒ `_get_target_filter` 回落 `DEFAULT_FILTER="ALL"` ⇒ 需翻 27+ 页；
  实测翻到第 5~20 页游戏切 `LOGIN_LOADING(104)`，`agent_swap_base.py:110`
  `unexpected scene 104, abort` ⇒ **末尾守卫永不触发**。
- 换成职介明确的真实名字（`末药`=MEDIC）后，面板职介筛选**实际没有收窄**列表：
  `filter=MEDIC` 却扫出 `能天使`(SNIPER)、`德克萨斯`(PIONEER) ⇒ 同样要 27+ 页。

故改用**产品自身**的翻页上限守卫（`MAX_PAGE` 50→3，**产品代码不改**），由 `_advance_page`
抛 `AgentSwapError("max page reached")` —— 与"目标扫不到"**同一语义**，只是更快到达。

**实机日志片段（主臂，未修复）**

```
AgentSwap: max page reached
AgentSwap step select: unhandled error
_do_swap: swap_service failed, restart
...  （12 次循环，240s 内未结束）
[2] error=False queue_len=1 still_alive=False
```

**实机日志片段（正控臂，仅把 `return False` 改 `raise`）**

```
executor failed for task: SchedulerTask(…task_plan={'room_1_2': ['T2_不存在的干员_zzz']}…)
task failed: SchedulerTask(…)
[2] error=True  queue_len=0  still_alive=False
```

**逐条判据（11/11 预测成立）**

| 判据 | 结果 |
|---|---|
| [主] 到达翻页上限并抛出 `AgentSwapError` | ✅ PASS |
| [主] 异常被 `_run_steps` 吞掉（记录 unhandled error） | ✅ PASS |
| [主] 未到达 dispatch（无 `executor failed for task`） | ✅ PASS |
| [主] 主循环未记 `task failed` | ✅ PASS |
| [主] `state.error` 未被置位（BUG-2 现象） | ✅ PASS |
| [主] 任务未结束、仍挂在队列里 | ✅ PASS |
| [主] 无半成品排班（房间构成未变） | ✅ PASS |
| [正控] 守卫仍触发 `AgentSwapError` | ✅ PASS |
| [正控] dispatch 记 `executor failed for task` | ✅ PASS |
| [正控] 主循环记 `task failed` | ✅ PASS |
| [正控] `state.error == True` 且任务已清空 | ✅ PASS |

**归因：代码问题（缺陷 E）** —— `agent_swap_base.py:126-128` 的
`except Exception: logger.exception(...); return False` 把业务失败**降级为"正常结束"**。
`AgentSwapError` 已按约定是**普通异常**；正控臂证明**下游 dispatch/loop 完好**，
缺陷位置唯一确定。后果：失败不靠 10 分钟 `_timeout` 兜底就无法上报。

**副作用**：`mower.db` `46a41bd2…`、`conf.yml` `417bb224…` 前后一致、无 `.t2bak` 残留；
`save_conf` 调用 **0** 次；**全程未点任何干员**。

---

### T2.4 拆分后唯一真实换人 —— 通过 12/12

**实机日志片段**

```
[0] 安全边界：会真的 uncheck dormitory_2 的非定向干员
-> PASS  _detect_room() == dormitory_2
-> PASS  uncheck 命中非定向槽位
-> PASS  定向干员被 skip 未重复点击
-> PASS  终点定向干员仍在房内（未被挤出）
-> PASS  无其他房间被改动
[T2.4] 12/12 项通过
```

**副作用与回滚**：真实换人 ⇒ 构成**已变**，需游戏内手工回滚；
`mower.db`/`conf.yml` SHA256 前后一致、无 `.t2bak` 残留。

---

### T2.5 读数可信度 —— 失败 8/10（代码问题，缺陷 D）

**实机日志片段（两次读数逐字对比）**

```
[4a] A 臂（不复位，T2.5 原口径）连读 3 次
   第 1 次: ['流明(24)', '琴柳(24)', '清流(24)', '但书(24)', '摩根(24)']
   第 2 次: ['缄默德克萨斯(19)', '缄默德克萨斯(19)', '缄默德克萨斯(19)', '但书(24)', '摩根(24)']
   第 3 次: ['缄默德克萨斯(19)', '缄默德克萨斯(19)', '缄默德克萨斯(19)', '但书(24)', '摩根(24)']
[4b] B 臂（每次读数前滑回顶部）连读 3 次
   第 1/2/3 次: ['流明(24)', '琴柳(24)', '清流(24)', '但书(24)', '摩根(24)']  （三次一致）
   第 1/2/3 次: 一致=True  合理=True
[关键发现] A 臂读数逐字一致但物理不可能（同屏重名 ['缄默德克萨斯']）
```

**逐条判据（8/10）**

| 判据 | 结果 |
|---|---|
| 自证: base 段 3 次一致（工具不恒红） | ✅ |
| 自证: patched 段被判不一致（工具真能变红） | ✅ |
| 自证: patched 段确实被调用了 ≥times 次 | ✅ |
| 实机: 成功进入房间并打开详情面板 | ✅ |
| **实机 A 臂: 不复位连读的读数合理（无同屏重名）** | ❌ FAIL |
| **实机 A 臂: 不复位连读 3 次读数一致** | ❌ FAIL |
| 实机 B 臂: 复位后连读一致 | ✅ |
| 实机 B 臂: 复位后读数合理（无同屏重名） | ✅ |
| 实机: 读数跨 5 个槽位 | ✅ |
| 两臂结论可比（都有 5 槽读数） | ✅ |

**归因：代码问题（缺陷 D）** —— `room_reader.py:52-59` 的 `scan_room` 读第 3-4 槽位时
向上滑屏却**不滑回**（实测 `pre=176 → post=49`），且 `_read_name` 用
`TM_CCORR_NORMED` argmax **无分数下限** ⇒ 静默返回错名。
**结论：一致性 ≠ 正确性** —— 只靠"连读 2~3 次一致"不足以保证读数正确，
必须**每次读数前复位滚动**。

---

### 缺陷汇总（**只上报，不修复**）

| 编号 | 类型 | 位置 | 要点 |
|---|---|---|---|
| A | **代码问题** | `scheduler/constants.py:104` | `CONFIRM_YES=(1371,998)` 在 224 确认框外（框 `(835,683)-(1082,800)`，有效 ≈`(1080,741)`）⇒ 224 永不可关 ⇒ 首页腿永久自旋 |
| B | **识别问题** | `services/agent_swap_arrange.py:35-51` | `_detect_arrange` 先查降序窗口，`心情` 列静态字形恒命中 ⇒ 永远返回 `('心情', False)`；宿舍定向换人挂死（`StepRetry` 无 guard/超时） |
| C | **代码问题** | `scheduler/navigator.py:99-136` | `enter_room` 先 `clip` 再判越界 ⇒ panic-swipe 为死代码；屏外房间不可达且仍 `return True` |
| D | **代码问题** | `infra/room_reader.py:52-59` | `scan_room` 上滑不复位 + `_read_name` 无分数下限 ⇒ 静默返回错名 |
| E | **代码问题** | `services/agent_swap_base.py:126-128` | 普通异常降级为 `return False` ⇒ 业务失败不可上报 |
| 待定 | 识别/代码 | `services/agent_swap_arrange.py:_open_filter` | 职介筛选未真正收窄列表（T2.3 实证） |

---

### 无游戏数据破坏（S13 验收标准 3）

除 T2.2（补位 3 人）与 T2.4（真实换人）这两项**预期内**的房间改动外，无其他房间被改动。
每项跑前后 `mower.db` / `conf.yml` SHA256 一致、无 `.t2bak` 残留。

**⚠️ 自曝（必须记录）**：T2 期间有三个一次性诊断脚本调用了 `RoomReader.scan_room()`
却**未套 `db_backup_t2`**，覆写了 `tmp/mower.db`（含物理不可能的 `缄默德克萨斯`）。
SQLite freelist = 0 ⇒ **无法字节还原**；已按语义还原：
`A10C3B0F…87346F`（原）→ `BEAC7FFE…BD6F`（污染）→
`898B4C973200C30B38A1CED91A1950E6B148026F46E99DE629E321A24E979213`（还原）。
**性质：语义还原、非字节还原。**
另：初版环境恢复脚本无上限连按返回键，曾按到 `EXIT_GAME` **把游戏退出**；
已删除并改为有上限的 `recover_to_index(max_back=2)`，用 `monkey` 重新拉起游戏。

---

### 明确排除（不得当作 S13 结案）

- **S13 第 7 项（六个新 executor，S7–S12 / Wave 3）尚未实现**，无可测对象。
- T2 只覆盖 S13 第 2/3/4/5/8 项，**不是完整 S13**。
