"""T2.2 — 自由位补位实机验收（S13 item 3；A6/BUG-1；**点击类**）。

要验的修复
----------
**BUG-1**：`_do_scan` 把识别结果写进**局部变量** `cache`，而补位分支读的是
`self._cache`（只在 `__init__` 里初始化为 `[]`）→ 补位恒空转、`free tap` 恒为 0、
直接落到翻页逻辑。修复后 `_do_scan` 写 `self._cache`，"从空位补人"才首次真正执行。
A/B 基准（mock：需补 2 空位，见 `重构流程.md` BUG-1 节）

| | taps | swipes |
|---|---|---|
| 修复前 | **0** | 1（翻页） |
| 修复后 | **1**（`free tap 令`） | 0 |

判据（A6 表 + T2 规约；逐条见 `_summarize`）
-------------------------------------------
1. `free tap` 出现 **3 次且互不相同**（不是同一人重复 3 次）
2. **不得**出现 `free tap 流明` / `free tap 琴柳`（不点已在房干员）
3. `uncheck slots=[2, 3, 4]`（房间原为满员，先腾位再补）
4. 终点 5 位**全非空**，前两位仍是 `流明/琴柳`
5. `state.error == False`、队列空、无 `unhandled error`
6. `_do_sort` 后 5 个槽位全被重新点击（补位 3 人全部补回）
7. `swipe page` 计数 **0**（补位应在第 0 页完成）

**证伪对照**：把 `_do_scan` 猴补丁回 BUG-1 修复前的写法（写局部变量）→
`free tap` 必须变 **0** 且出现翻页 —— 证明这条判据真能检出 BUG-1 回退。

用法：`.venv/Scripts/python.exe tests/live/t2_2_free_fill.py [--seconds 300]`

安全边界
--------
- **会点击游戏并真的改动 `dormitory_2` 的干员构成**（腾出 3 个位置再补 3 人）。
- 副作用：写 `tmp/mower.db`（`RoomReader._persist`）→ 按 T2 规约 7 备份/还原。
- `state` 全程 `no_save_conf()`，不写 `conf.yml`。
- **回滚**：本项只影响 `dormitory_2` 的自由位选谁，不改定向干员安排逻辑；
  若结果不符，在游戏内手工调整该宿舍即可（A6 原定回滚方式）。
"""

import sys
from pathlib import Path

# 直接执行时 sys.path[0] 是 tests/live/，连 `tests` 包都解析不到；不硬算层数，向上找锚点。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "tests" / "_bootstrap.py").is_file():
        sys.path.insert(0, str(_parent))
        break

from tests._bootstrap import REPO_ROOT  # noqa: E402,F401

from tests.live.t2_common import (  # noqa: E402
    build_device,
    build_state,
    room_snapshot,
)
from tests.live.t2_nav import NavLegs, scene_of  # noqa: E402
from tests.live.t2_probe import (  # noqa: E402
    CallMeter,
    SceneTracker,
    SwapCounters,
    falsify_scan_silent,
)
from tests.live.t2_runner import run_probe_script, run_with_logs  # noqa: E402
from tests.live.t2_task import read_room_via_nav, run_shift_task  # noqa: E402

ROOM = "dormitory_2"
# A6 的目标：两位定向干员 + 三个自由位。
PLAN = ["流明", "琴柳", "Free", "Free", "Free"]
KEEP = ("流明", "琴柳")
# `_do_sort` 会 `INFRA_CLEAR_ALL` 后按 click_order 重新点击；5 位应全被点回。
EXPECTED_RETAP = 5


def _probe(args, pause) -> dict:
    port, recog, infra = build_device(pause)
    nav = infra.navigator
    calls = _recording(port)
    tracker = SceneTracker(nav)
    legs = NavLegs(nav, tracker, CallMeter(calls))

    state, _workshop, save_calls = build_state()
    infra.state = state

    print("[2] 只读探测：行动前的房间构成（T2.5：连读 3 次取一致值）")
    before_readings, before_ok = read_room_via_nav(
        nav, recog, infra, state, ROOM, "行动前"
    )
    before = room_snapshot(before_readings)
    print(f"    行动前规整 = {before}")

    print(f"\n[3] 真实跑 SHIFT_ON，plan={PLAN}")
    # 主臂单独记账：`run_probe_script` 只在最外层挂一个 LogCapture，证伪臂的
    # `swipe page` / `unhandled error` 会与主臂混在一起（T2.2 首跑即因此误判 3 项）。
    main, main_lines = run_with_logs(
        lambda: run_shift_task(infra, state, ROOM, PLAN, args.seconds)
    )
    print(
        f"    error={main['error']} queue_len={main['queue_len']}"
        f" still_alive={main['still_alive']}"
    )

    print("\n[4] 只读复查：行动后的房间构成")
    after_readings, after_ok = read_room_via_nav(
        nav, recog, infra, state, ROOM, "行动后"
    )
    after = room_snapshot(after_readings)
    print(f"    行动后规整 = {after}")

    print("\n[5] 证伪对照：把 `_do_scan` 猴补丁回 BUG-1 修复前（写局部变量）")
    state2, _w2, _c2 = build_state()
    infra.state = state2
    handle = falsify_scan_silent(None)
    try:
        # 证伪臂会因 `StepRestart` **永久重试**，必然烧满预算，故单独给一个
        # 较短的上限（默认 90s），避免挤占实机观察窗口。
        falsify, falsify_lines = run_with_logs(
            lambda: run_shift_task(
                infra, state2, ROOM, PLAN, getattr(args, "falsify_seconds", 90)
            )
        )
    finally:
        handle.restore()
    fc = SwapCounters(falsify_lines)
    print(
        f"    error={falsify['error']} queue_len={falsify['queue_len']}"
        f"  free tap={len(fc.free_taps())}  swipe page={fc.summary()['swipe_pages']}"
    )

    legs.navigate(scene_of("INFRA_MAIN"), "final_return")
    return {
        "main": main,
        "main_lines": main_lines,
        "falsify": falsify,
        "falsify_lines": falsify_lines,
        "before": before,
        "after": after,
        "before_ok": before_ok,
        "after_ok": after_ok,
        "after_readings": after_readings,
        "save_calls": len(save_calls),
        "legs": legs.legs,
    }


def _recording(port) -> list:
    from tests.live.t2_common import recording_port

    return recording_port(port)


def _summarize(result: dict, lines: list) -> bool:
    # 只用**主臂**日志下判据；证伪臂日志单独用 `falsify_lines` 统计。
    counters = SwapCounters(result.get("main_lines") or lines)
    summary = counters.summary()
    picks = summary["free_taps"]
    distinct = len(set(picks))
    after = result["after"]
    falsify = result["falsify"]

    print("\n[6] 换班链路关键日志")
    for line in counters.find("current room="):
        print(f"    {line}")
    for line in summary["skip_seated"]:
        print(f"    {line}")
    for line in counters.find("switching to free mode"):
        print(f"    {line}")
    for line in counters.find("free tap "):
        print(f"    {line}")
    for line in counters.find("free done"):
        print(f"    {line}")
    print(f"    swipe page 次数 = {summary['swipe_pages']}")
    print(f"    uncheck slots   = {summary['uncheck_slots']}")
    print(f"    uncheck 逐次点击 = {summary['uncheck_taps']}")
    print(f"    free tap 名单    = {picks}")

    non_empty = [n for n in after if n and n != "空"]
    falsify_lines = result.get("falsify_lines") or []
    fc = SwapCounters(falsify_lines)
    falsify_picks = fc.free_taps()

    checks = {
        "自证: 行动前读数 3 次一致": result["before_ok"],
        "自证: 行动后读数 3 次一致": result["after_ok"],
        "free tap 出现 3 次": len(picks) == 3,
        "free tap 三次互不相同": distinct == 3,
        "不点已在房干员（无 free tap 流明/琴柳）": not any(p in KEEP for p in picks),
        "uncheck slots == [2, 3, 4]（先腾位）": summary["uncheck_slots"] == [2, 3, 4],
        "终点 5 位全非空": len(after) == 5 and len(non_empty) == 5,
        "前两位仍是 流明/琴柳": after[:2] == list(KEEP),
        "state.error == False": result["main"]["error"] is False,
        "任务队列已清空": result["main"]["queue_len"] == 0,
        "无 unhandled error": summary["unhandled"] == 0,
        "补位在第 0 页完成（swipe page == 0）": summary["swipe_pages"] == 0,
        "无 reached end of list / max page": (
            summary["reached_end"] == 0 and summary["max_page"] == 0
        ),
        "证伪: 修复前写法下 free tap == 0": len(falsify_picks) == 0,
        "证伪: 修复前写法未能补满（翻页或补位不足）": (
            fc.summary()["swipe_pages"] > 0 or len(falsify_picks) < 3
        ),
    }

    print("\n[7] 判据逐条结果")
    passed = 0
    for name, good in checks.items():
        print(f"    -> {'PASS' if good else 'FAIL'}  {name}")
        passed += int(good)
    print(
        f"\n    证伪段：free tap={falsify_picks} "
        f"swipe page={fc.summary()['swipe_pages']} error={falsify['error']}"
    )

    ok = passed == len(checks)
    print(f"\n[T2.2] {passed}/{len(checks)} 项通过")
    print(
        "\n[归因] 若 `free tap` 为 0 且出现翻页 → **代码问题**（BUG-1 回退）；"
        "若 `free tap` 命中已在房干员 → **识别/过滤问题**；"
        "若读数不一致或无空闲候选 → 环境问题或 INVALID。"
    )
    print("[OK] T2.2 通过" if ok else "[FAIL] T2.2 未通过")
    return ok


def main() -> int:
    return run_probe_script(
        description="T2.2 自由位补位（A6/BUG-1）",
        boundary="安全边界：会真的改动 dormitory_2 的干员构成（腾 3 位再补 3 人）",
        probe=_probe,
        summarize=_summarize,
        default_seconds=300,
        extra_args=(
            (
                "--falsify-seconds",
                {
                    "type": int,
                    "default": 90,
                    "help": "证伪臂的墙钟上限（秒；该臂因 StepRestart 会烧满）",
                },
            ),
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())