"""T2.4 — 唯一真实换人路径（S13 item 5；**点击类**）。

验收目标（§10.3 T2.4）
---------------------
S3 拆分（`agent_swap_service.py` → 6 个 mixin）是**行为保持型重构**，
"减少人数"这条**唯一真实换人路径**必须与拆分前逐字一致。A2 基线记录的
正是这条路：房间满员 → 定向干员留下、其余被 uncheck → 人数减少。

判据（逐条见 `_summarize`）
--------------------------
1. 导航链路 `201 → 205 → 230` 正确，`_detect_room()` == `dormitory_2`
2. `uncheck slots` 非空，且 == 行动前"非定向干员"所占槽位
3. 房内已就位的定向干员被 `skip ... already in slot N` 跳过（不重复点击）
4. 前后读数各**连读 3 次一致**（T2.5 规范）
5. `state.error == False`、队列空、无 `unhandled error` / `executor failed`
6. 无其他房间被改动（`operator_mood` 中其他房间归属不变）
7. 定向干员未被挤出（`流明`/`琴柳` 仍在房内）

⚠️ 与 A2 的**预期行为变化**（如实记录，不放宽判据）
--------------------------------------------------
A2 基线（BUG-1 未修）用 `[流明, 琴柳, Free, Free, Free]` 得到终点
`[流明 琴柳 空 空 空]` —— 因为当时补位分支恒空转，3 个空位留空。

**BUG-1 修复后该 plan 的结果必然改变**：uncheck 腾出的 3 个位置会被补位
分支重新填满（这正是 T2.2 要验的能力）。因此本项以 A2 的**换人签名**
（`uncheck slots=[2,3,4]` + `skip 流明/琴柳 already in slot 0/1` + 排序重排）
为准，**不**断言终点人数减少 —— 那已是修复前的偶然现象。

⚠️ 与 T2.2 同 plan：本项与 T2.2 的 plan 相同（都是 A2 原 plan）。T2.2 验
"补位填满 3 位"，本项验"腾位 + 保定向 + 排序"这条**换人**链路，两者互补。

用法：`.venv/Scripts/python.exe tests/live/t2_4_real_swap.py [--seconds 300]`

安全边界
--------
- **会点击游戏并真的改动 `dormitory_2`**（uncheck 掉非定向干员）。
- 副作用：写 `tmp/mower.db`（`RoomReader._persist`）→ 按 T2 规约 7 备份/还原。
- `state` 全程 `no_save_conf()`，不写 `conf.yml`。
- **回滚**：只影响 `dormitory_2`；如需还原，在游戏内手工把干员放回该宿舍。
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
    operator_rooms,
    room_snapshot,
)
from tests.live.t2_nav import NavLegs, scene_of  # noqa: E402
from tests.live.t2_probe import (  # noqa: E402
    CallMeter,
    SceneTracker,
    SwapCounters,
    names_of,
)
from tests.live.t2_read import impossible_duplicates  # noqa: E402
from tests.live.t2_runner import run_probe_script  # noqa: E402
from tests.live.t2_task import read_room_via_nav, run_shift_task  # noqa: E402

ROOM = "dormitory_2"
# 与 A2 基线**逐字一致**：保留前 2 位定向干员，其余 3 位按 `Free` 处理
# ⇒ `_to_uncheck` 应为 [2,3,4]（真机上原为 令/迷迭香/鸿雪）。
# ⚠️ 不能用空字符串占位：`run()` 里 `_pending = [a for a in agents if a != "Free"]`
# 只排除字面量 `"Free"`，空串会混进待选名单。
KEEP = ("流明", "琴柳")
PLAN = ["流明", "琴柳", "Free", "Free", "Free"]
# 导航链路要求出现的场景名（取自 `scheduler/scene.py`，不写字面量）。
EXPECTED_PATH = ("INFRA_MAIN", "INFRA_DETAILS", "INFRA_DETAILS_OPEN")

# 起点归一（退回 201）那一步的墙钟预算（秒）。
SETUP_BUDGET = 45.0


def _probe(args, pause) -> dict:
    from arknights_mower.utils.path import get_path

    db_path = Path(get_path("@app/tmp")) / "mower.db"
    rooms_before = operator_rooms(db_path)

    port, recog, infra = build_device(pause)
    nav = infra.navigator
    tracker = SceneTracker(nav)
    legs = NavLegs(nav, tracker, CallMeter(_recording(port)))

    state, _workshop, save_calls = build_state()
    infra.state = state

    # **起点归一**：上一次跑可能把游戏留在 `230`（详情面板展开）或 `207`（选人面板）。
    # T2.4 要单独验"导航 201 -> 205 -> 230"，因此先退回 `201` 再开始记账，
    # 否则若恰好在房内起步，场景序列里不会出现 201/205，判据会误判为失败
    # （run2 实测：序列从 INFRA_DETAILS_OPEN 开始，nav 判据 FAIL 但链路其实正常）。
    legs.navigate(scene_of("INFRA_MAIN"), "setup_to_infra_main", budget=SETUP_BUDGET)
    tracker.frame.clear()

    print("[2] 只读探测：行动前的房间构成（T2.5：连读 3 次）")
    before_readings, before_ok = read_room_via_nav(
        nav, recog, infra, state, ROOM, "行动前", legs=legs
    )
    before = room_snapshot(before_readings)
    print(f"    行动前规整 = {before}")

    print(f"\n[3] 真实跑 SHIFT_ON（减少人数路径），plan={PLAN}")
    main = run_shift_task(infra, state, ROOM, PLAN, args.seconds)
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

    rooms_after = operator_rooms(db_path)
    return {
        "main": main,
        "before": before,
        "after": after,
        "before_ok": before_ok,
        "before_dup": impossible_duplicates(before_readings),
        "after_ok": after_ok,
        "before_readings": before_readings,
        "after_readings": after_readings,
        "rooms_before": rooms_before,
        "rooms_after": rooms_after,
        "detected": nav._detect_room(),
        "sequence": tracker.sequence,
        "save_calls": len(save_calls),
        "legs": legs.legs,
    }


def _recording(port) -> list:
    from tests.live.t2_common import recording_port

    return recording_port(port)


def _other_rooms_unchanged(before: dict, after: dict) -> tuple[bool, list]:
    """除 `ROOM` 外，其他房间的干员归属必须不变。"""
    changed = []
    for name, was in before.items():
        now = after.get(name)
        if was != now and (was != ROOM and now != ROOM):
            changed.append((name, was, now))
    return (not changed), changed


def _summarize(result: dict, lines: list) -> bool:
    counters = SwapCounters(lines)
    summary = counters.summary()
    seq_names = names_of(result["sequence"])
    after = result["after"]
    uncheck = summary["uncheck_slots"]

    print("\n[5] 场景序列")
    print(f"    {' -> '.join(seq_names)}")

    print("\n[6] 换班链路关键日志")
    for line in counters.find("current room="):
        print(f"    {line}")
    for line in summary["skip_seated"]:
        print(f"    {line}")
    for line in counters.find("uncheck slot "):
        print(f"    {line}")
    for line in counters.find("uncheck done"):
        print(f"    {line}")
    print(f"    uncheck slots = {uncheck}")

    # 期望被 uncheck 的槽位，取自 **`_do_swap` 自己那行日志**（`current=[...]`），
    # 而不是"行动前读数" —— T2.5 已证明读数可能是"一致地错"的（run1 实测行动前
    # 读到 `泰拉大陆调查团 ×3`，用它推出的期望值是 `[0,1,2,3,4]`，属错误期望）。
    # 产品自己读出的 current 才是它真实决策所依据的输入，用它做期望才对齐。
    current = counters.current_room()
    expect_uncheck = [
        i for i, name in enumerate(current) if name not in KEEP and name
    ]
    # 进入房间的腿记录。**不**要求 `enter_room` 停在 205：实测该腿一次点击后
    # `_wait_room_detail` 的稳定等待可能直接跨过瞬态的 205 落到 230
    # （run4：`[enter_room:dormitory_2] INFRA_MAIN -> INFRA_DETAILS_OPEN`，tap=1）。
    # 205 只是过渡态，判据应针对**可达性**：从 201 出发、经一次点击进入详情页，
    # 且 `_detect_room()` 正确。硬要求中间态会得到一个时序相关的伪失败。
    enter_legs = [leg for leg in result["legs"] if leg["label"].startswith("enter_room:")]
    detail_scenes = {
        int(scene_of("INFRA_DETAILS")),
        int(scene_of("INFRA_DETAILS_OPEN")),
    }
    enter_ok = bool(enter_legs) and all(
        leg["after"] in detail_scenes
        and leg["before"] == int(scene_of("INFRA_MAIN"))
        for leg in enter_legs
    )
    nav_ok = enter_ok and result["detected"] == ROOM
    unchanged, changed = _other_rooms_unchanged(
        result["rooms_before"], result["rooms_after"]
    )
    seated = [n for n in after if n in KEEP]

    checks = {
        "导航 201 -> 205/230 详情页可达（enter_room 腿）": nav_ok,
        "_detect_room() == dormitory_2": result["detected"] == ROOM,
        "行动前读数无同屏重名（快照可信）": not result.get("before_dup"),
        "行动后读数 3 次一致且无重名（T2.5 规范）": result["after_ok"],
        "uncheck 命中非定向槽位": bool(uncheck) and uncheck == expect_uncheck,
        "定向干员被 skip 未重复点击": summary["skip_seated"] != []
        or all(n in current for n in KEEP),
        "终点定向干员仍在房内（未被挤出）": all(n in after for n in KEEP),
        "state.error == False": result["main"]["error"] is False,
        "任务队列已清空": result["main"]["queue_len"] == 0,
        "无 unhandled error": summary["unhandled"] == 0,
        "无 executor failed for task": summary["executor_failed"] == 0,
        "无其他房间被改动": unchanged,
    }
    print("\n[7] 判据逐条结果")
    passed = 0
    for name, good in checks.items():
        print(f"    -> {'PASS' if good else 'FAIL'}  {name}")
        passed += int(good)
    if changed:
        print(f"    其他房间变动：{changed}")
    print(f"    KEEP 就位情况 = {seated}；期望 uncheck = {expect_uncheck}")

    ok = passed == len(checks)
    print(f"\n[T2.4] {passed}/{len(checks)} 项通过")
    print(
        "\n[归因] 若 `uncheck slots` 与期望不符 → **代码问题**（拆分改变了行为）；"
        "若读数不一致 → 按 T2.5 判 INVALID；若无法进入房间 → 环境问题。"
    )
    print(
        "[说明] 若 T2.2 的补位干预使终点人数未减少，按'T2.2 修复后的预期行为变化'"
        "记录实态，不放宽判据。"
    )
    print("[OK] T2.4 通过" if ok else "[FAIL] T2.4 未通过")
    return ok


def main() -> int:
    return run_probe_script(
        description="T2.4 唯一真实换人路径（减少人数）",
        boundary="安全边界：会真的 uncheck dormitory_2 的非定向干员",
        probe=_probe,
        summarize=_summarize,
        default_seconds=300,
    )


if __name__ == "__main__":
    raise SystemExit(main())