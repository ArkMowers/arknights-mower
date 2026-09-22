"""T2 导航腿原语（实机脚本，不参与门禁 G1 收集）。

从 `t2_1_navigation.py` 抽出：T2.1 要走"201 → 房间 → 201"的**往返腿**，
T2.2/T2.4 也要先到 `dormitory_2` 并复核 `_detect_room()`。把腿的取证原语
收敛到一处，既满足 AGENTS.md「每个文件 ≤300 行」，也保证三个脚本用**同一套**
点击记账，判据口径一致。

| 原语 | 用途 |
|---|---|
| `scene_of` | 按名字取 `scheduler.scene.Scene` 成员（不写字面量） |
| `NavLegs.navigate` | 一条 `navigate(target)` 腿：前后 scene + 该腿点击计数 |
| `NavLegs.enter_room` | 一条 `enter_room(room)` 腿（**不含**打开详情面板那一步） |
| `NavLegs.open_detail` | 205 → 230 腿：`_wait_room_detail()` + `_detect_room()` 复核 |
| `NavLegs.round_trip` | `201 → 房间(205/230) → 201` 的组合腿 |

⚠️ 本文件名**不以 `_tests.py` 结尾**，因此不会被 G1 的 `discover` 收集。
"""

from __future__ import annotations

# 进入房间腿最多允许的滑动次数：房间贴边时 `enter_room` 会先平移一次再点中心。
ENTER_LEG_MAX_SWIPE = 1

# 详情类场景（205 详情页 / 230 详情页已展开）。
DETAIL_SCENES = ("INFRA_DETAILS", "INFRA_DETAILS_OPEN")


def scene_of(name: str):
    """按名字取 `scheduler/scene.py` 的 `Scene` 成员（AGENTS.md 规则 4：不写字面量）。"""
    from arknights_mower.scheduler.scene import Scene

    return getattr(Scene, name)


def scene_name_of(scene) -> str:
    """场景号 -> 可读名（仅用于打印；`t2_probe.scene_name` 的同义包装）。"""
    from tests.live.t2_probe import scene_name

    return scene_name(int(scene))


def _record(tracker, label, ok, before, after, calls, extra="", seconds=None) -> dict:
    from tests.live.t2_probe import scene_name

    record = {
        "label": label,
        "ok": bool(ok),
        "before": before,
        "after": after,
        "seconds": seconds,
        **calls,
    }
    elapsed = f" t={seconds:.1f}s" if seconds is not None else ""
    print(
        f"    [{label}] ok={record['ok']}  {scene_name(before)} -> {scene_name(after)}"
        f"   tap={calls['tap']} swipe={calls['swipe']} path={calls['swipe_path']}"
        f"{elapsed}{extra}"
    )
    tracker.mark(label)
    return record


class NavLegs:
    """把每次导航/进房动作记成一条**带点击账的腿**。

    `meter` 是 `t2_probe.CallMeter`，`tracker` 是 `t2_probe.SceneTracker`。
    两者都由调用方创建 —— 脚本需要按自己的判据决定哪条腿参与断言。

    ⚠️ 每条腿都被 `MowerExit` 包住并记为 `aborted=True`：T2.1 实测发现
    `201 -> INDEX` 腿可能因 `TapPosition.CONFIRM_YES` 点不中确认框而**永久自旋**，
    墙钟到点会从腿内部硬拽出 `MowerExit`。若不接住它，脚本会丢光整份点击账。
    """

    def __init__(self, nav, tracker, meter) -> None:
        self.nav = nav
        self.tracker = tracker
        self.meter = meter
        self.legs: list[dict] = []

    # ─ 单条腿 ──

    def navigate(self, target, label: str, budget: float | None = None) -> dict:
        """跑一次 `navigate(target)` 并取证。`budget` 见 `_leg`。"""
        return self._leg(label, lambda: self.nav.navigate(target), budget=budget)

    def enter_room(self, room: str) -> dict:
        """只跑 `enter_room(room)`（不含打开详情面板那一步）。"""
        return self._leg(f"enter_room:{room}", lambda: self.nav.enter_room(room))

    def open_detail(self, room: str) -> dict:
        """205 -> 230 腿：`_wait_room_detail()` 可能点一次 `arrange_check_in`。

        判 `ok` 的依据是**终态落在详情类场景且房间认对**，而不是"是否调用了
        `_wait_room_detail`"：实测 `enter_room` 的一次点击可能**直接**把面板开到
        `230`（`205` 未被子采样捕获），此时 `before == 230`、`opened is None`，
        但这一步事实上已经完成，不应记为失败。
        """
        before = int(self.nav._get_scene())
        self.meter.phase()
        opened = None
        if before == int(scene_of("INFRA_DETAILS")):
            opened = self.nav._wait_room_detail()
        self.nav.wait_scene_stable(max_duration=3.0, min_stable=2)
        after = int(self.nav._get_scene())
        detected = self.nav._detect_room()
        ok = after in {int(scene_of("INFRA_DETAILS")), int(scene_of("INFRA_DETAILS_OPEN"))}
        record = self._push(
            f"detail:{room}",
            ok and detected == room,
            before,
            after,
            extra=f"  _detect_room={detected!r} opened={opened}",
        )
        record["detected"] = detected
        return record

    def round_trip(self, room: str) -> dict:
        """`当前 → room(205/230) → 201`。房间进不去时如实返回 `None` 子项。

        ⚠️ 进房前**先等画面稳定**：`enter_room` 用 `self._recognizer.img` 这份
        可能**过期的截图**算 `segment_base` 房间多边形，且 `navigator.py:136`
        **无条件 `return True`**，不做任何"场景真的变了吗"的后置校验。上一条腿
        刚把画面从 230 拉回 201 时若立刻进房，点击会落在仍在平移的旧坐标上
        （run10 实测 `room_1_2` 因此点空、scene 仍 201，却报 True）。等画面稳定
        属于测试侧取证纪律，**不是放宽判据**；产品缺失的后置校验另行上报。
        """
        print(f"\n    --- {room} ---")
        self.nav.wait_scene_stable(max_duration=6.0, min_stable=3)
        enter = self.enter_room(room)
        if not enter["ok"]:
            return {"enter": enter, "detail": None, "return": None}
        detail = self.open_detail(room)
        back = self.navigate(scene_of("INFRA_MAIN"), f"return:{room}")
        return {"enter": enter, "detail": detail, "return": back}

    def recover_if_stuck(self, nav, recog) -> dict:
        """若游戏停在 `224`（上一条腿被预算中断的遗留态）就点掉确认框救回。

        返回 `dismiss_leave_infra_dialog` 的结果；不在 224 时 `needed=False`。
        """
        if int(nav._get_scene()) != int(scene_of("LEAVE_INFRASTRUCTURE")):
            return {"needed": False}
        result = dismiss_leave_infra_dialog(nav, recog)
        print(
            f"    [环境恢复] 撤离 224：{scene_name_of(result['before'])}"
            f" -> {scene_name_of(result['after'])} px={result.get('px')}"
        )
        return result

    # ─ 内部 ──

    def _leg(self, label: str, action, budget: float | None = None) -> dict:
        """跑 `action()`，把结果、点击账、耗时与是否被墙钟打断记成一条腿。

        `budget`：该腿的**独立**墙钟上限（秒）。T2.1 实测 `201 -> INDEX` 腿会因
        `CONFIRM_YES` 点不中确认框而**永久自旋**；若只靠最外层墙钟，这一条腿就会
        吃掉整个观察窗口，后面的 `[3]/[4]` 段落全部拿不到证据。给了 `budget`
        就用一个看门狗线程到点 `request_stop()`，让该腿尽快以 `aborted=True` 收尾，
        把剩余时间留给其他腿。
        """
        import threading
        import time as _time

        from arknights_mower.utils.csleep import MowerExit

        before = int(self.nav._get_scene())
        self.meter.phase()
        t0 = _time.monotonic()
        aborted = False
        timed_out = False
        watchdog_stop = threading.Event()
        watchdog = None
        if budget is not None:
            pause = getattr(self.nav, "_pause", None)

            def _watch() -> None:
                nonlocal timed_out
                if watchdog_stop.wait(budget):
                    return
                timed_out = True
                if pause is not None:
                    pause.request_stop()

            watchdog = threading.Thread(target=_watch, daemon=True)
            watchdog.start()
        try:
            ok = action()
            self.nav.wait_scene_stable(max_duration=3.0, min_stable=2)
        except MowerExit:
            # 墙钟到点：腿没走完。如实记为失败，保留已发生的点击账。
            ok = False
            aborted = True
        finally:
            watchdog_stop.set()
            if watchdog is not None:
                watchdog.join(timeout=2)
            # 本腿预算触发的是**任务级** stop；只有带 `resume_run` 的控制器
            # 才能解除（墙钟真到点时 `resume_run` 会拒绝）。
            resume = getattr(pause, "resume_run", None) if budget is not None else None
            if timed_out and resume is not None:
                resume()
        seconds = _time.monotonic() - t0
        after = int(self.nav._get_scene())
        if aborted and timed_out:
            extra = f"  [ABORTED 本腿预算 {budget:.0f}s 到点]"
        elif aborted:
            extra = "  [ABORTED 墙钟到点]"
        else:
            extra = ""
        record = self._push(label, ok, before, after, extra=extra, seconds=seconds)
        record["aborted"] = aborted
        record["timed_out"] = timed_out
        return record

    def _push(self, label, ok, before, after, extra="", seconds=None) -> dict:
        calls = self.meter.phase()
        record = _record(
            self.tracker, label, ok, before, after, calls, extra, seconds
        )
        self.legs.append(record)
        return record


def dismiss_leave_infra_dialog(nav, recog) -> dict:
    """环境恢复：点掉 `224 离开基建` 确认框，把卡住的游戏救回首页/基建。

    为什么需要：T2.1 实测 `201 -> INDEX` 腿因 `TapPosition.CONFIRM_YES`
    →(1371,998) 落在确认框外而**永久自旋**；该腿被本腿预算中断时，游戏就**停在
    224**。此后每一条腿（`index_to_infra` 等）都会从 224 出发继续自旋，把整个
    观察窗口烧光。因此中断后必须先做一次环境恢复，后续腿才有意义。

    这里按 **v1 已验证的写法**（`utils/graph.py:57` 的
    `tap_element("double_confirm/main", x_rate=1)`）点确认框右端中心 ——
    这是**测试脚本的环境恢复**，不修改任何产品源码。

    返回 `{"needed","before","after","box","px"}`。
    """
    from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W

    before = int(nav._get_scene())
    if before != int(scene_of("LEAVE_INFRASTRUCTURE")):
        return {"needed": False, "before": before, "after": before}

    recog.update()
    box = recog.find("double_confirm/main")
    if isinstance(box, tuple) and len(box) == 2 and isinstance(box[0], (list, tuple)):
        (x1, y1), (x2, y2) = box
        px = (int(x2) - 2, int((y1 + y2) / 2))
    else:
        # 模板没找到时退回实测定标（确认框实测 (835,683)-(1082,800)）。
        px = (1080, 741)
    nav._device.tap(px[0] / SCREEN_W, px[1] / SCREEN_H)
    nav.wait_scene_stable(max_duration=3.0, min_stable=2)
    for _ in range(4):
        nav.wait_scene_stable(max_duration=2.0, min_stable=2)
        if int(nav._get_scene()) != int(scene_of("LEAVE_INFRASTRUCTURE")):
            break
    after = int(nav._get_scene())
    return {"needed": True, "before": before, "after": after, "box": box, "px": px}


def falsify_ghost_room(nav_legs: NavLegs, recog, ghost_room: str) -> dict:
    """T2.1 证伪对照：传**不存在**的房间名，必须 `False`、零点击、且能退回 201。

    同时记录 `control_central` 是否被找到 —— 否则 `False` 可能只是
    "识别没找到中枢"的提前返回，而不是"房间名查不到"这条判据在起作用。
    """
    nav = nav_legs.nav
    central = recog.find("control_central")
    before = int(nav._get_scene())
    nav_legs.meter.phase()
    result = nav.enter_room(ghost_room)
    calls = nav_legs.meter.phase()
    after = int(nav._get_scene())
    leg = _record(
        nav_legs.tracker,
        f"falsify:{ghost_room}",
        result is False,
        before,
        after,
        calls,
        f"  control_central={'找到' if central is not None else '未找到'}",
    )
    nav_legs.legs.append(leg)
    recover = nav_legs.navigate(scene_of("INFRA_MAIN"), "recover")
    return {"leg": leg, "central_found": central is not None, "recover": recover}