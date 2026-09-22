"""T2.1 — 导航全链路实机验收（S13 item 2；**点击类**）。

验收目标（§10.3「S13 分片执行」T2.1）
------------------------------------
从**任意**起点导航到 `Scene.INFRA_MAIN`(201)，再进入指定房间，最后回到 201；
`scene` 序列必须符合预期（参考 A2 记录：`首页 → 201 → 205 → 230`）。
判据落法：包 `Navigator._get_scene` 把**每次变化**记成序列；覆盖 2 个不同房间
（`dormitory_2` 宿舍 + `room_1_2` 生产房间）；所有 scene 引用
`scheduler/scene.py` 成员，不写字面量；证伪对照传不存在的房间名。

⚠️ 判据本身的自相矛盾（**如实上报，不放宽**）
--------------------------------------------
原文写「**零 tap/swipe**：把 `PCDevicePort.tap/swipe/swipe_path` 换成记录器，
断言计数 0」。但 `Navigator.enter_room()` **本身就是一次 tap**：它算出房间多边形
中心后调 `self._device.tap(...)`（`navigator.py:134`），没有提前返回路径。因此
「真的进入房间」与「全程 tap 计数 0」**不可能同时成立**。本脚本按**可执行且有意义**
的方式落实：不断言全程零点击，而按**腿**记账 —— `enter_room` 恰好 1 次 tap、
`return` 必须 0 次、`to_index` 预算 ≤3 次；字面判据（总数 0）记 FAIL。

用法：`.venv/Scripts/python.exe tests/live/t2_1_navigation.py [--seconds 300]`

安全边界：**会点击游戏**（每次点击在日志里标明属于哪条腿）；只走**导航**，不打开
干员选择面板、不提交任何换班；**不构造 `RoomReader`**（不写 `tmp/mower.db`）与
`SchedulerState`（不碰 `conf.yml`），仅按 T2 规约 7 备份/还原取 SHA256 证据；`finally` 里
`request_stop()`，`--seconds` 墙钟上限到时硬中断 `Navigator`。
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
    counts,
    recording_port,
)
from tests.live.t2_nav import (  # noqa: E402
    ENTER_LEG_MAX_SWIPE,
    NavLegs,
    falsify_ghost_room,
    scene_of,
)
from tests.live.t2_probe import (  # noqa: E402
    CALL_KINDS,
    CallMeter,
    SceneTracker,
    blank_leg,
    describe,
    names_of,
    print_legs,
    scene_name,
)
from tests.live.t2_runner import run_probe_script  # noqa: E402

# 至少覆盖两个不同房间：一个宿舍 + 一个生产房间（`room_*`）。
# ⚠️ 选房经实测修正（run9）：`room_1_1` 在当前视口是**屏外**的（`segment_base`
# 实测 x = -222..73），而 `enter_room()` 在 `navigator.py:117` 先 `np.clip` 再判
# 边界，"滑屏挪进视口"的分支（line 120/126）因此是死代码（min_x 被夹成 0，永不
# < 0）。故判据只用屏内房间，屏外房间另作缺陷证据。
ROOMS = ("dormitory_2", "room_1_2")

# 屏外房间（已知缺陷证据，不计入判据）：`enter_room` 应滑进视口后再进。
OFFSCREEN_ROOM = "room_1_1"

# 不存在的房间名（证伪对照用）：`segment_base` 的返回字典里绝不会有它。
GHOST_ROOM = "no_such_room_zzz"

# `201 -> INDEX` 腿的本腿墙钟预算（秒）。该腿已知会永久自旋，见 `_probe` 注释。
# 取值只需够它暴露"点击远超预算"即可，不必等它自然结束。
TO_INDEX_BUDGET = 60.0

# "打底腿"（把起点拨到 201）的预算。它同样可能在 224 上自旋。
SETUP_BUDGET = 45.0


def _probe(args, pause) -> dict:
    """取证：首页往返 + 两个房间往返 + 证伪对照。

    墙钟一旦到点（`MowerExit` 被 `NavLegs` 接住记为 `aborted`），立即停止后续取证
    —— 否则每条腿都会立刻抛 `MowerExit`，账单被无意义地拉长。
    """
    port, recog, infra = build_device(pause)
    nav = infra.navigator
    calls = recording_port(port)
    tracker = SceneTracker(nav)
    legs = NavLegs(nav, tracker, CallMeter(calls))

    start = int(nav._get_scene())
    print(f"[1] 起点 scene = {scene_name(start)}（任意起点，不要求是 201）")

    # 开跑前环境恢复：上一次跑若在 `to_index` 腿被预算中断，游戏会**停在 224**，
    # 此后连"打底腿"都从 224 自旋（run7 实测 527 次点击烧光窗口）。
    pre_recovery = legs.recover_if_stuck(nav, recog)
    start = int(nav._get_scene())

    # 先把起点拨到 201（打底腿，不计分）：否则若恰好从 INDEX 起步，`to_index`
    # 腿会退化成"原地不动 0 次点击"，把真正的缺陷掩盖掉。
    if start != int(scene_of("INFRA_MAIN")):
        print(f"    [打底] 先把起点拨到 201（当前 {scene_name(start)}）")
        # 打底腿也给预算：它同样可能在 224 上自旋。
        legs.navigate(
            scene_of("INFRA_MAIN"), "setup_to_infra_main", budget=SETUP_BUDGET
        )
        start = int(nav._get_scene())

    rooms: dict = {}
    falsify: dict = {}
    offscreen = None
    recovery = {"needed": False}
    to_index_leg = None

    # 取证顺序经实测调整（run8）：`to_index` 腿**必然**以卡在 224 收尾，之后任何腿
    # 都会从 224 继续自旋（run8 里 `index_to_infra` 烧掉 218.9s）。故放到最后。
    if not pause.is_stopped:
        print("\n[2] 逐房间往返（宿舍 + 生产房间）")
        rooms = {room: legs.round_trip(room) for room in ROOMS}
        # 屏外房间单独取证（不计入判据），证明 `enter_room` 的滑屏分支是死代码。
        print(f"\n[2b] 屏外房间 {OFFSCREEN_ROOM}（已知缺陷，不计入判据）")
        offscreen = legs.round_trip(OFFSCREEN_ROOM)
        print("\n[3] 证伪对照：不存在的房间名")
        falsify = falsify_ghost_room(legs, recog, GHOST_ROOM)
        print("\n[4] 首页腿（已知缺陷：本腿必然自旋，故放在最后并单独限额）")
        to_index_leg = legs.navigate(
            scene_of("INDEX"), "to_index", budget=TO_INDEX_BUDGET
        )
        # 收尾：把游戏从 224 救回。点掉确认框后 scene 可能落在 `LOADING`，必须等它
        # 稳定，否则紧接着的 `index_to_infra` 会在加载动画上乱点（run11 实测 68 次）。
        recovery = legs.recover_if_stuck(nav, recog)
        nav.wait_scene_stable(max_duration=12.0, min_stable=3)
        print(f"    [环境恢复] 稳定后 scene={scene_name(int(nav._get_scene()))}")
        legs.navigate(scene_of("INFRA_MAIN"), "index_to_infra", budget=SETUP_BUDGET)

    if not falsify:
        print("\n[!] 墙钟到点，部分段落未执行 —— 按已完成部分出账")
        falsify = {
            "leg": blank_leg(f"falsify:{GHOST_ROOM}"),
            "central_found": False,
            "recover": blank_leg("recover", after=None),
        }
    for room in ROOMS:
        rooms.setdefault(
            room, {"enter": blank_leg("enter_room"), "detail": None, "return": None}
        )

    return {
        "start": start,
        "recovery": recovery,
        "pre_recovery": pre_recovery,
        "legs": list(legs.legs),
        "rooms": rooms,
        "offscreen": offscreen,
        "falsify": falsify,
        "total": {k: counts(calls, k) for k in CALL_KINDS},
        "sequence": tracker.sequence,
    }


def _summarize(result: dict) -> bool:
    rooms = result["rooms"]
    offscreen = result.get("offscreen")
    falsify = result["falsify"]
    legs = result["legs"]
    seq_names = names_of(result["sequence"])

    print("\n[5] 场景序列（逐次变化，`<label>` 是腿边界）")
    print(f"    {describe(result['sequence'])}")
    print_legs(legs)
    if offscreen is not None:
        ent, det = offscreen["enter"], offscreen["detail"]
        # 缺陷 C 由**读源码**确证（`np.clip` 早于边界判断）；端到端影响看
        # 点按那刻该房间是否已滚出视口（run12 它恰在屏内），故只留观测值。
        print(f"\n[5b] 屏外房间 {OFFSCREEN_ROOM}: enter ok={ent['ok']}"
              f" {ent['before']}->{ent['after']} tap={ent['tap']}"
              f"  detected={det['detected'] if det else None}（缺陷 C 见报告）")

    # ⚠️ 不要求字面出现 205：`205` 是进房点击后极短暂的过渡态，
    # `SceneTracker` 只在 `_get_scene()` 被调用且值变化时采样，实测一次点击常直接
    # 落到 `230`（run11）。故按可观测的顺序性质判：先 201，再详情类场景。
    detail_states = ("INFRA_DETAILS", "INFRA_DETAILS_OPEN")
    detail_idx = next(
        (i for i, n in enumerate(seq_names) if n in detail_states), None
    )
    main_idx = seq_names.index("INFRA_MAIN") if "INFRA_MAIN" in seq_names else None
    order_ok = (
        main_idx is not None
        and detail_idx is not None
        and main_idx < detail_idx
        and "INFRA_DETAILS_OPEN" in seq_names
    )
    return_legs = [leg for leg in legs if leg["label"].startswith("return:")]
    to_index = next((leg for leg in legs if leg["label"] == "to_index"), None)
    index_legs = [leg for leg in legs if leg["label"] == "index_to_infra"]
    to_index_calls = (to_index["tap"] + to_index["swipe"]) if to_index else 0
    to_index_budget = 3  # `201 --back--> INDEX` + 一次 `224` 确认点击 ⇒ 正常 ≤3

    checks = {
        "到达首页 INDEX(1)": any(
            leg["label"] == "to_index" and leg["ok"] and leg["after"] == 1
            for leg in legs
        ),
        "首页 -> 201 完成": any(
            leg["label"] == "index_to_infra" and leg["ok"] and leg["after"] == 201
            for leg in legs
        ),
        "两个房间 enter_room 都成功": all(rooms[r]["enter"]["ok"] for r in ROOMS),
        "两个房间 _detect_room 均正确": all(
            rooms[r]["detail"] and rooms[r]["detail"]["detected"] == r for r in ROOMS
        ),
        "进入后 scene 是详情类(205/230)": all(
            rooms[r]["detail"] and rooms[r]["detail"]["after"] in {205, 230}
            for r in ROOMS
        ),
        "scene 序列 201 -> 详情类 且顺序正确": order_ok,
        "进入房间腿恰好 1 次 tap": all(rooms[r]["enter"]["tap"] == 1 for r in ROOMS),
        "进入房间腿 swipe ≤1（贴边兜底）": all(
            rooms[r]["enter"]["swipe"] <= ENTER_LEG_MAX_SWIPE for r in ROOMS
        ),
        "退回 201 的腿零点击（2 个房间）": len(return_legs) >= 2 and all(
            leg["tap"] == 0 and leg["swipe"] == 0 and leg["swipe_path"] == 0
            for leg in return_legs
        ),
        # `index_to_infra` → `_tap_element("infrastructure")`，本来就是一次点击
        # （实测 2 次：点击 + 稳定等待内的重取），预算 ≤3。
        "进入基建腿点击预算 ≤3": all(
            leg["tap"] <= 3 and leg["swipe"] == 0 for leg in index_legs
        ),
        # ⚠️ 2026-09-19 实机：`to_index` 实测 71 次点击（见报告「新发现缺陷」）。
        # 根因是 `TapPosition.CONFIRM_YES`(1371,998) 落在确认框外，
        # `224` 永远点不掉 ⇒ `navigate` 在 201/224 之间自旋。此处如实记为 FAIL。
        f"首页腿点击预算 ≤{to_index_budget}（实测 {to_index_calls}）": (
            to_index is not None and to_index_calls <= to_index_budget
        ),
        "无任何腿被墙钟打断": not any(leg.get("aborted") for leg in legs),
        "证伪: enter_room(不存在房间) == False": falsify["leg"]["ok"],
        "证伪: 该腿零点击": all(falsify["leg"][k] == 0 for k in CALL_KINDS),
        "证伪: control_central 确被找到（False 不是提前返回）": falsify["central_found"],
        "证伪后能安全退回 201": falsify["recover"]["ok"]
        and falsify["recover"]["after"] == 201,
    }
    print("\n[7] 判据逐条结果")
    passed = 0
    for name, good in checks.items():
        print(f"    -> {'PASS' if good else 'FAIL'}  {name}")
        passed += int(good)

    literal_zero = sum(result["total"].values()) == 0
    print("\n[8] 判据字面项「全程 tap/swipe 计数 = 0」（见文件头 ⚠️ 说明）")
    print(
        f"    tap={result['total']['tap']} swipe={result['total']['swipe']}"
        f" swipe_path={result['total']['swipe_path']}"
    )
    print(
        f"    -> {'PASS' if literal_zero else 'FAIL'}  "
        "全程零点击（enter_room 本身必然 tap，故字面判据不成立）"
    )
    enter_taps = sum(rooms[r]["enter"]["tap"] for r in ROOMS)
    print(f"    其中进入房间腿 tap 合计 = {enter_taps}（两房间各 1 次，属预期点击）")
    print(f"\n[T2.1] 实质判据 {passed}/{len(checks)} 项通过；"
          f"字面零点击={'PASS' if literal_zero else 'FAIL'}")
    print(
        "\n[需主控裁定] T2.1 的『零 tap/swipe』与『真的进入房间』互斥："
        "`Navigator.enter_room()` 无任何提前返回路径地执行一次 tap（`navigator.py:134`）；"
        "本脚本按实质判据执行，字面判据如实记为 FAIL，未放宽。"
    )
    if to_index is not None and (
        to_index_calls > to_index_budget or to_index.get("aborted")
    ):
        print(
            f"\n[新发现缺陷 · 需修复] `201 -> INDEX` 腿实测 {to_index_calls} 次设备调用"
            f"（预算 ≤{to_index_budget}）"
            + ("，且**被墙钟硬中断**（永久自旋）" if to_index.get("aborted") else "")
            + "。根因：`TapPosition.CONFIRM_YES` 归一化 → 像素 (1371, 998)，但 "
            "`224 离开基建` 确认框 `double_confirm/main` 实测落在 (835,683)-(1082,800)，"
            "该点**在框外**（dx=-289, dy=-257）→ 224 永远点不掉 → `navigate` 在 201/224 "
            "间自旋。正确坐标应为确认框右端中心 ≈(1080, 741)（v1 `utils/graph.py:57` 用 "
            "`tap_element('double_confirm/main', x_rate=1)`，实测有效）。"
            "归因：**代码问题**（`scheduler/constants.py:104`）；T2 不修改源码。"
        )
    return passed == len(checks)


def main() -> int:
    return run_probe_script(
        description="T2.1 导航全链路（点击类）",
        boundary="安全边界：只走导航，不进选择面板、不提交换班",
        probe=_probe,
        summarize=lambda result, lines: _summarize(result),
        default_seconds=240,
    )


if __name__ == "__main__":
    raise SystemExit(main())
