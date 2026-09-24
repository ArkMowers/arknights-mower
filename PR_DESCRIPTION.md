# PR：v2 Scheduler 重构（Wave 1 完整验收 + T2 分片实测）

> 分支：`redesign` → `main` ｜ 基准：`a45297c` ｜ 提交：101 个（重构主体 22 个） ｜ 文件：291 个｜ +49,135 / −10,118

## 摘要

将基建调度（Infra）从旧的 `solvers/`/`utils/` 单体逐步迁移到 `scheduler/` 新世界（scene-driven 状态机 + `Step` 队列模式 + DevicePort 抽象），按规范（`重构流程.md` §10.3，S1–S5）分阶段交付，每阶段跑绿 G1–G5 门禁；**Wave 1（T1）三项实测全过**，随后进入 **T2 分片实测**，覆盖 S13 遗留的点击类项（2/3/4/5/8），并如实上报所发现的**产品缺陷**（不修复、仅归因）。

**注意**：S13 第 7 项（六个新 executor，属 S7–S12 / Wave 3）**尚未实现**，本 PR 不声称完整 S13 结案。

---

## 背景：为什么重构

- `solvers/` 与 `utils/` 中基建逻辑耦合大量游戏专用坐标、`time.sleep()`、状态机不统一。
- AGENTS.md 新规：scene-driven 状态机、**tap-once**、异常隔离、**禁止 `time.sleep()`**、零硬编码坐标、文件 ≤300 行。
- 迁移节奏（S1→S5→Wave 3）：架构骨架 → Graph/导航 → 识别精简 → 业务迁移 → 全链路。

---

## 本 PR 包含什么

### 1. 重构主体（S1–S5，22 commits）

| 阶段 | 要点 | 提交代表 |
|---|---|---|
| S1 启动清理 | 启动路径去死代码、测试搬迁 `tests/`、harness fixtures | `834be8f1` `374e7fea` |
| S2 Step 下沉 | `Step`/`StepRetry`/`StepRestart` 沉入 `scheduler/steps.py`，常量收敛 | `c0954d2f` |
| S3 换班服务拆分 | `agent_swap_service` 619 → 113 行，拆分 5 个 Mixin；**修复 BUG-2/BUG-3** | `2255a632` |
| S4 导航拆分 | `navigator.py` 450 → 288 行 + `navigator_actions.py`；消除 11 处裸尺寸、锚点守卫 | `203d4d00` 等 |
| S5 状态层拆分 | `state.py` + `state_init.py` + `state_plan_load.py`，C5 回归 | `59ca3d46` |

涉及 `arknights_mower/scheduler/` 下 **73 个文件**（domain / services / infra / executors / database / copilot / device_port / graph / constants 等）。

### 2. Wave 1 实测（T1，全过）

| 项 | 结果 | 要点 |
|---|---|---|
| T1.1 启动无假任务 | ✅ 9/9 | 25s 内 TaskQueue.push=0、零点击 |
| T1.2 C5 回归 | ✅ 12/12 | 真实配置+backup_plans=[] 不抛错；反向对照仍抛 ConfigError；SHA256 前后一致 |
| T1.3 pause/stop | ✅ 12/12 | 观察量不经过 pause；stop 后线程 0.00s 退出 |

> 三项**零点击、零任务派发**，游戏全程停在 scene 201；并补齐 `probe_select_panel.py` 的 `--seconds`/`request_stop()`/`MowerExit` 硬中断/`no_save_conf` 合规项。

### 3. T2 分片实测（S13 第 2/3/4/5/8 项，点击类）

新增 12 个实机脚本（`tests/live/t2_*.py` + 共享模块），每个脚本独立 `--seconds` 墙钟上限、`mower.db`/`conf.yml` 前后 SHA256、`finally: request_stop()`、`.t2bak` 残留检查、证伪/正控对照。

| 项 | 判定 | 证据概要 |
|---|---|---|
| **T2.1 导航全链路** | ❌ 失败（产品缺陷，非测试问题） | 实质判据 13/16。确认 **缺陷 A**：`TapPosition.CONFIRM_YES=(1371,998)` 落在 224 离场确认框外（框实测 (835,683)-(1082,800)），正确点 ≈(1080,741) ⇒ 224 永远消不掉 → `navigate(INDEX)` 死循环（实测单次 99+ tap）。确认 **缺陷 C**：`enter_room` 在 clip 之后才判越界 ⇒ 两个 panic-swipe 分支是死代码；实测三房间均能进入、`open_detail` 终态判定正确、`return` 零 tap |
| **T2.2 自由位补位（A6/BUG-1）** | ✅ 15/15 | `Free×3` 只填 3 次、翻页 0 次、`uncheck slots=[2,3,4]`、房间构成不变；证伪对照（静默补位）0 次 |
| **T2.3 BUG-2 失败可上报** | ❌ 失败（**代码问题**） | 11/11 预测成立：构造 MAX_PAGE 3 ⇒ `AgentSwapError` 抛出，但被 `agent_swap_base.py:126-128` 的 `except Exception: return False` **吞掉** ⇒ `state.error` 恒 False、任务悬挂；**正控**（仅把该行改 `raise`）立即走通 `executor failed → task failed → error=True` ⇒ 下游链路完好，缺陷定位唯一 |
| **T2.4 拆分后唯一真实换人** | ✅ 12/12 | 真实点击换入 `流明/琴柳`、自由位补 `Free`，房间构成按预期变化、无残留 |
| **T2.5 读数可信度** | ❌ 失败（8/10） | 连读 3 次一致性：Arm A 出现 `缄默德克萨斯×3`（物理不可能重名）⇒ 证明**一致性 ≠ 正确性**；室内滚动不复位导致错行（缺陷 D：`scan_room` 上滑不恢复） |

**已归因的产品缺陷清单**（T2 只验证不修复，全部提交缺陷报告随 PR 附件/仓库 `tmp/` 日志）：

- **缺陷 A（代码问题）** `constants.py:104`：`TapPosition.CONFIRM_YES` 坐标越界，224 离场框永远关不掉（历史遗留，独立复现 `tmp/t2_recover_224.py`）。
- **缺陷 B（识别问题）** `agent_swap_arrange.py:35-51`：`_detect_arrange` 先查降序窗口，`心情` 列静态字形恒命中 ⇒ 宿舍定向换人挂死（`StepRetry` 无 guard/超时）。
- **缺陷 C（代码问题）** `navigator.py:99-136`：`enter_room` clip 先于越界判定 ⇒ panic 分支死代码，屏外房间永远滚不进视野。
- **缺陷 D（代码问题）** `room_reader.py:52-59`：`scan_room` 上滑读 3-4 槽位不恢复 ⇒ 后续读数错行。
- **缺陷（新增发现）** `agent_swap_base.py:126-128`：普通异常被降级为 `return False`，换班业务失败需等 10 分钟超时才上报（本 PR 的 T2.3 主证）。

> ⚠️ **T2.1 需主控裁定**：规范同时要求"零 tap/swipe（count 0）"与"真实进入房间"，而 `Navigator.enter_room()` **无条件**点房间中心（`navigator.py:134`），二者互斥 ⇒ T2.1 以**分腿预算**为实质判据，字面零点击判据如实判 FAIL 并上报，未放松。

---

## 门禁（全部在最后一轮复核过）

| 门禁 | 结果 |
|---|---|
| G1 离线测试收集 | ✅ 3× exit 0（≥127 用例） |
| G2 | ✅ exit 0 |
| G3 静态检查 | ✅ 13 errors（≤13 基线） |
| G4 | ✅ exit 0 |
| G5 | ✅ 13 tests OK / exit 0 |

---

## 如何验证

```bash
# 离线门禁
python -m pytest tests/ -q        # G1/G5
ruff check arknights_mower tests/ # G3

# T2 实机（需 MuMu/模拟器 + 游戏已登录 + adb 在线，见 tests/live/README.md）
.venv\Scripts\python.exe tests\live\t2_1_navigation.py  --seconds 300
.venv\Scripts\python.exe tests\live\t2_2_free_fill.py   --seconds 300
.venv\Scripts\python.exe tests\live\t2_3_bug2_report.py --seconds 300
.venv\Scripts\python.exe tests\live\t2_4_real_swap.py   --seconds 300
.venv\Scripts\python.exe tests\live\t2_5_read_confidence.py --seconds 300
```

每个脚本自带：墙钟硬中断、`mower.db`/`conf.yml` SHA256 前后对比、无 `.t2bak` 残留、证伪/正控对照、`finally: request_stop()`。

---

## 已知限制 / 后续

- **S13 第 7 项（六个新 executor）未实现**，属后续 Wave（S7–S12），本 PR 不结案 S13。
- Wave 2（S6）尚未开工：最后一次功能提交为 S5（`59ca3d46`），HEAD `6194b641` 只追加测试/文档。
- T1/T2 实机脚本全部在 `tests/live/`，**不参与** G1 收集（文件名不以 `_tests.py` 结尾），不污染离线门禁。
- `tmp/` 下留有待归档的实测日志（`tmp/t2_*_run*.log` 等），含上述缺陷的原始证据。

---

## 环境事实（实测基线，供复现）

- 模拟器 MuMu，adb `127.0.0.1:16416`（目标）+ `emulator-5556`；`touch_method=scrcpy`、`droidcast.enable=True`；游戏包 `com.hypergryph.arknights`，设备 `Xiaomi 2201123C (Android 15)`。
- 日志文件为 UTF-16（`*>` 重定向），读取需先嗅探 BOM。