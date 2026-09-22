"""T2.5 — 读数可信度（S13 item 8；**横切规范**）。

S13 item 8 的原文是「关键判据**连读 2~3 次取一致值**后才下结论」。它不是某一项
功能，而是 T2.1/T2.2/T2.3/T2.4 都必须遵守的规范，因此本脚本做两件事：

1. **自证**：`t2_common.read_room_stable` 必须能**检出人造的不一致**。
   把 `RoomReader._read_name` 猴补丁成交替返回两个值 → 必须判 `INVALID`。
   若自证失败（工具恒绿），则 T2.2/T2.4 的读数结论**全部作废**，本项判 INVALID。
2. **实机连读**：进 `dormitory_2` 并打开详情面板（230），用 `read_room_stable`
   连读 3 次；一致才下结论，不一致 → `INVALID`（**不是 PASS**）并列出各次读数。

用法（项目根目录）
------------------
    .venv\\Scripts\\python.exe tests\\live\\t2_5_read_confidence.py
    .venv\\Scripts\\python.exe tests\\live\\t2_5_read_confidence.py --seconds 240

安全边界
--------
- **会点击游戏**（导航 + 点一次 `arrange_check_in` 打开详情面板），但**不打开
  干员选择面板、不点击任何干员、不提交任何变更**。
- 副作用：`RoomReader.scan_room` 的 `_persist()` 会写 `tmp/mower.db` →
  按 T2 规约 7 用 `Copy-Item` 备份到 `.t2bak` 并在**读库动作结束后**还原。
- `SchedulerState` 构造全程套 `no_save_conf()`，绝不写用户的 `conf.yml`。
- 自证段用 `MockDevicePort` + `MockRecognizer` + 空存储，**不连真机、不碰数据库**。
- `finally` 里 `request_stop()`；`--seconds` 墙钟上限到时硬中断 `Navigator`。
"""

import argparse
import sys
from pathlib import Path

# 直接执行（python tests/live/xxx.py）时 sys.path[0] 是 tests/live/，仓库根不在其中，
# 连 `tests` 这个包都还解析不到。这里**不硬算层数**，改为向上找 tests/_bootstrap.py 锚点；
# 真正的路径引导一律由 tests._bootstrap 负责。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "tests" / "_bootstrap.py").is_file():
        sys.path.insert(0, str(_parent))
        break

# 副作用：把仓库根写入 sys.path
from tests._bootstrap import REPO_ROOT  # noqa: E402,F401

from tests.live.t2_common import (  # noqa: E402
    DEFAULT_STABLE_READS,
    build_device,
    build_state,
    recording_port,
)
from tests.live.t2_read import (  # noqa: E402
    impossible_duplicates,
    read_room_stable,
    reset_room_scroll,
    room_snapshot,
    vary_slot,
)
from tests.live.t2_nav import NavLegs, scene_of  # noqa: E402
from tests.live.t2_probe import CallMeter, SceneTracker  # noqa: E402
from tests.live.t2_runner import run_probe_script  # noqa: E402

# 本项读的目标房间（与 T2.2/T2.4 一致，便于横向比对）。
ROOM = "dormitory_2"

# 自证段至少要真正调用 `_read_name` 这么多次，否则"变异检测"没被跑到。
MIN_SELFCHECK_CALLS = DEFAULT_STABLE_READS


class _NullStorage:
    """吞掉 `_persist()` 的假存储：自证段**绝不**碰 `tmp/mower.db`。"""

    def save(self, key, data) -> None:
        return None


def _selfcheck(times: int) -> dict:
    """自证：人造不一致必须被 `read_room_stable` 判为 INVALID。

    两个场景共用**同一张**全黑画面（不连真机）：

    | 场景 | `_read_name` | 期望 |
    |---|---|---|
    | `base` | 固定返回「人造甲」 | 3 次一致 → `base_consistency=True` |
    | `patched` | **交替**返回「人造甲」/「人造乙」 | 必不一致 → `patched_consistency=False` |

    `base` 段证明工具**不会无故报不一致**（不恒红）；`patched` 段证明工具
    **真能变红**。只有两者同时成立，T2.2/T2.4 的读数结论才有效。
    """
    import numpy as np

    from arknights_mower.scheduler.infra.room_reader import RoomReader
    from tests.harness.mock_device import MockDevicePort
    from tests.harness.mock_recognizer import MockRecognizer

    state, _, _ = build_state()
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    device = MockDevicePort(screencap_factory=lambda n: frame)
    recog = MockRecognizer(scenes=[], finds={"infra_no_operator": None})
    reader = RoomReader(device, recog, None)
    reader._storage = _NullStorage()

    original_name = RoomReader._read_name
    original_time = RoomReader._read_time
    RoomReader._read_time = lambda self, img: None
    try:
        RoomReader._read_name = lambda self, img: "人造甲"
        base_readings, base_ok = read_room_stable(reader, ROOM, state, times)

        counter = {"n": 0}

        def _alternating(self, img):
            counter["n"] += 1
            return "人造甲" if counter["n"] % 2 else "人造乙"

        RoomReader._read_name = _alternating
        try:
            patched_readings, patched_ok = read_room_stable(reader, ROOM, state, times)
        finally:
            RoomReader._read_name = original_name
    finally:
        RoomReader._read_time = original_time

    return {
        "base_ok": base_ok,
        "patched_ok": patched_ok,
        "base_readings": base_readings,
        "patched_readings": patched_readings,
        "patched_calls": counter["n"],
        "patched_vary": vary_slot(patched_readings),
    }


def _live_read(args, pause, state) -> dict:
    """实机：两臂对照 —— A) 不复位连读（T2.5 原口径）；B) 每次复位后连读。

    T2.5 实测发现 A 臂会**一致地错**：连读 3 次得到逐字相同的
    `缄默德克萨斯 ×3`（同宿舍不可能有三个同名干员）。因此本项同时给出
    A 臂的"一致性"与**合理性**两条结论，并加 B 臂验证"复位后是否恢复可信"。
    """
    from arknights_mower.scheduler.infra.room_reader import RoomReader

    port, recog, infra = build_device(pause)
    nav = infra.navigator
    tracker = SceneTracker(nav)
    # 本项是**只读**项，只需记录导航腿的场景序列用于取证，不必统计点击预算。
    legs = NavLegs(nav, tracker, CallMeter(recording_port(port)))

    print(f"[2] 导航到 201 并进入 {ROOM}")
    legs.navigate(scene_of("INFRA_MAIN"), "to_infra_main")
    enter = legs.enter_room(ROOM)
    detail = legs.open_detail(ROOM) if enter["ok"] else None
    if detail is None:
        return {"ok": False, "reason": "无法进入房间或打开详情面板", "legs": legs.legs}

    scene_now = int(nav._get_scene())
    print(f"[3] 当前 scene = {scene_now}，预期 {int(scene_of('INFRA_DETAILS_OPEN'))}(230)")
    reader = RoomReader(infra.device, recog, nav)

    print(f"\n[4a] A 臂（不复位，T2.5 原口径）连读 {args.times} 次")
    raw, raw_ok = read_room_stable(reader, ROOM, state, args.times)
    for i, reading in enumerate(raw, 1):
        print(f"    第 {i} 次: {reading}")
    raw_dup = impossible_duplicates(raw)
    print(f"    一致 = {raw_ok}  重名（物理不可能）= {raw_dup}")
    print(f"    规整后 = {room_snapshot(raw)}")

    print(f"\n[4b] B 臂（每次读数前滑回顶部）连读 {args.times} 次")
    fixed, fixed_ok = read_room_stable(
        reader,
        ROOM,
        state,
        args.times,
        reset=lambda: reset_room_scroll(nav, recog),
    )
    for i, reading in enumerate(fixed, 1):
        print(f"    第 {i} 次: {reading}")
    fixed_dup = impossible_duplicates(fixed)
    print(f"    一致 = {fixed_ok}  重名 = {fixed_dup}")
    print(f"    规整后 = {room_snapshot(fixed)}")

    legs.navigate(scene_of("INFRA_MAIN"), "return")
    return {
        "ok": True,
        "scene": scene_now,
        "readings": raw,
        "consistent": raw_ok,
        "snapshot": room_snapshot(raw),
        "vary": vary_slot(raw),
        "dup": raw_dup,
        "fixed": fixed,
        "fixed_consistent": fixed_ok,
        "fixed_snapshot": room_snapshot(fixed),
        "fixed_vary": vary_slot(fixed),
        "fixed_dup": fixed_dup,
        "legs": legs.legs,
    }


def _probe(args, pause) -> dict:
    """把自证段与实机段一起跑：自证失败则实机读数结论作废。"""
    print("\n[1] 自证：人造不一致必须被判 INVALID（离线，不连真机）")
    selfcheck = _selfcheck(args.times)
    print(
        f"    base    consistent={selfcheck['base_ok']}  "
        f"readings={selfcheck['base_readings']}"
    )
    print(
        f"    patched consistent={selfcheck['patched_ok']}  "
        f"calls={selfcheck['patched_calls']}  vary={selfcheck['patched_vary']}"
    )
    for i, reading in enumerate(selfcheck["patched_readings"], 1):
        print(f"      patched 第 {i} 次: {reading}")

    state, workshop, save_calls = build_state()
    print(f"\n[0] workshop_settings = {workshop}；save_conf 被拦截 {len(save_calls)} 次")
    live = _live_read(args, pause, state)
    return {
        "selfcheck": selfcheck,
        "live": live,
        "save_calls": len(save_calls),
    }


def _summarize(result: dict, lines: list) -> bool:
    selfcheck = result["selfcheck"]
    live = result["live"]
    live_consistent = bool(live.get("consistent"))
    checks = {
        "自证: base 段 3 次一致（工具不恒红）": selfcheck["base_ok"],
        "自证: patched 段被判不一致（工具真能变红）": not selfcheck["patched_ok"],
        "自证: patched 段确实被调用了 ≥times 次": selfcheck["patched_calls"] >= MIN_SELFCHECK_CALLS,
        "实机: 成功进入房间并打开详情面板": bool(live.get("ok")),
        "实机 A 臂: 不复位连读的读数**合理**（无同屏重名）": not live.get("dup"),
        "实机 A 臂: 不复位连读 3 次读数一致（T2.5 原口径）": live_consistent,
        "实机 B 臂: 复位后连读一致": bool(live.get("fixed_consistent")),
        "实机 B 臂: 复位后读数合理（无同屏重名）": not live.get("fixed_dup"),
        "实机: 读数跨 5 个槽位": len(live.get("snapshot", [])) == 5,
        "两臂结论可比（都有 5 槽读数）": len(live.get("fixed_snapshot", [])) == 5,
    }
    print("\n[6] 判据逐条结果")
    passed = 0
    for name, good in checks.items():
        print(f"    -> {'PASS' if good else 'FAIL'}  {name}")
        passed += int(good)

    raw_dup = live.get("dup") or []
    print("\n[6] 两臂对照")
    print(f"    A 臂（不复位） 一致={live_consistent}  合理={not raw_dup}  "
          f"读数={live.get('readings')}")
    print(f"    B 臂（复位）   一致={live.get('fixed_consistent')}  "
          f"合理={not live.get('fixed_dup')}  读数={live.get('fixed')}")

    if raw_dup:
        print(
            "\n    [关键发现] A 臂读数**逐字一致但物理不可能**"
            f"（同屏重名 {raw_dup}）——"
        )
        print("               `RoomReader.scan_room` 为读第 4~5 槽位向上滑屏却不复位，")
        print("               第 2 次起槽位 0~2 读到已滚动的帧。")
        print("               ⇒ 仅靠'连读一致'**无法**保证读数可信，必须并用合理性检查。")
        if live.get("fixed_consistent") and not live.get("fixed_dup"):
            print("               B 臂（每次滑回顶部）恢复了可信读数 ⇒ 复位是充分修复口径。")
    elif not live_consistent:
        print("    [INVALID] A 臂读数不一致 —— 按 T2.5 规范判 INVALID（不是 PASS）")
        print(f"              不一致槽位：{live.get('vary')}")

    ok = passed == len(checks)
    verdict = "通过" if ok else "失败"
    print(f"\n[T2.5] {passed}/{len(checks)} 项通过；结论：{verdict}")
    print(f"[T2.5] save_conf 被拦截 {result['save_calls']} 次（>0 表示该守卫确有必要）")
    print(
        "[归因] `scan_room` 滚动后不复位 + `_read_name` 无分数下限 ⇒ **代码问题**"
        "（`infra/room_reader.py`），非环境问题。"
    )
    print("[OK] T2.5 通过" if ok else "[FAIL] T2.5 未通过")
    return ok


def main() -> int:
    return run_probe_script(
        description="T2.5 读数可信度（横切规范）",
        boundary="安全边界：只读房间构成，不开选择面板、不点干员、不提交变更",
        probe=_probe,
        summarize=_summarize,
        default_seconds=240,
        extra_args=(
            (
                "--times",
                {
                    "type": int,
                    "default": DEFAULT_STABLE_READS,
                    "help": "连读次数（默认 3）",
                },
            ),
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
