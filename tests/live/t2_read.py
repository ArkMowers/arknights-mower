"""T2 房间读数层：`RoomReader` 的**可信**读取与一致性/合理性检查。

为什么单独一个模块
------------------
T2.5 实测证明 `RoomReader.scan_room` 会为读第 4~5 槽位向上滑屏却**从不复位**
（`scheduler/infra/room_reader.py:50-59`），于是**第 2 次**调用读槽位 0~2 时用的
是已滚动的帧，读出物理不可能的结果（同宿舍三个 `缄默德克萨斯`）。

更危险的是：**不复位时连读 3 次会得到逐字相同的读数**，单看"一致性"会误判为
可信 —— 因此一致性必须与**合理性检查**（`impossible_duplicates`）并用。

| 原语 | 作用 |
|---|---|
| `read_room_stable` | 连读 N 次；可传 `reset` 在每次读数前复位滚动 |
| `reset_room_scroll` | 把面板滑回顶部 |
| `impossible_duplicates` | 检出"一致但错误"（同读数内重名） |
| `room_snapshot` / `vary_slot` | 规整与逐槽位差异 |

⚠️ 文件名不以 `_tests.py` 结尾，不会被 G1 的 `discover` 收集。
"""

from __future__ import annotations

# 稳定读数的默认连读次数（S13 item 8：连读 2~3 次取一致值后才下判断）。
DEFAULT_STABLE_READS = 3

# 连读之间的间隔（秒）。走 `threading.Event.wait`，不是 `time.sleep`。
READ_GAP_SECONDS = 1.0

# `RoomReader.scan_room` 唯一汇总日志的前缀。
ROOM_LOG_PREFIX = "RoomReader: "

# 房间面板"下方还有内容"的探针点，与 `room_reader.py:54` 的判断同源。
# 该行像素 > `ROOM_SCROLL_NEEDED` 时 `scan_room` 会向上滑屏。
ROOM_SCROLL_PROBE = (1800, 930)
ROOM_SCROLL_NEEDED = 51


def capture_slots(call, room: str) -> list[str]:
    """执行 `call()` 并返回本次 `RoomReader` 汇总日志解析出的槽位列表。

    `RoomReader.scan_room` **不返回值**，唯一的读数出口是它自己那行
    `RoomReader: <room> [a b c]` 日志。因此在**同一线程内**临时挂一个
    handler 截获它，再按空白切分槽位文本（干员名不含空格）。

    参数 `call` 是 `reader.scan_room(room, state)` 的 thunk。
    """
    import logging

    from arknights_mower.utils.log import logger

    captured: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                message = record.getMessage()
            except Exception:
                return
            if message.startswith(ROOM_LOG_PREFIX):
                captured.append(message)

    handler = _Handler()
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        call()
    finally:
        logger.removeHandler(handler)

    for message in reversed(captured):
        body = message[len(ROOM_LOG_PREFIX):]
        if not body.startswith(room + " "):
            continue
        _, _, tail = body.partition("[")
        tail = tail.rstrip("]").strip()
        return tail.split() if tail else []
    return []


def reset_room_scroll(nav, recog) -> bool:
    """把房间面板滑回**顶部**（`scan_room` 自己不会做这件事），返回是否滑动过。

    探针语义（与 `room_reader.py:54` 同源）：`recog.img[930, 1800, 0]`
    - `> ROOM_SCROLL_NEEDED` ⇒ 下方还有内容 ⇒ 面板在**顶部/偏上**
    - `<= ROOM_SCROLL_NEEDED` ⇒ 下方已无内容 ⇒ 面板在**底部**（需复位）

    ⚠️ 初版把条件写反了（在底部时提前 return），导致 B 臂第一次读数仍是错的
    —— 这正是"仅看一致性会误判"的又一例证：写反时读数照样"一致"。
    """
    recog.update()
    probe = (recog.img[ROOM_SCROLL_PROBE[1], ROOM_SCROLL_PROBE[0], 0])
    if int(probe) > ROOM_SCROLL_NEEDED:
        return False  # 已在顶部，无需复位
    # 向下滑（y 0.2 -> 0.75）：内容下移，露出上面的行 ⇒ 回到顶部
    nav._device.swipe(0.8, 0.2, 0.8, 0.75, duration=500)
    nav.wait_scene_stable(max_duration=1.0, min_stable=2)
    recog.update()
    return True


def read_room_stable(
    reader, room: str, state, times: int = DEFAULT_STABLE_READS, reset=None
):
    """连读 `times` 次 `RoomReader.scan_room`，返回 `(读数列表, 是否一致)`。

    这是 T2 约定的**唯一**下判断入口：任何基于 `RoomReader` 的结论都必须经此
    函数，一次读数**不得**作为结论（S13 规则 3）。

    - 返回值 2：所有读数**逐槽位完全一致**才为 `True`；否则 `False` → 判 INVALID
    - `reset`：可选无参回调，在**每次**读数前调用（如
      `lambda: reset_room_scroll(nav, recog)`）。实测必须复位才能拿到可信读数。
    - ️ 不传 `reset` 时的"一致"可能只是**一致地错**，务必并用
      `impossible_duplicates`。
    """
    from tests.live.t1_common import idle_wait

    readings: list[list[str]] = []
    for i in range(times):
        if i:
            idle_wait(READ_GAP_SECONDS)
        if reset is not None:
            reset()
        readings.append(capture_slots(lambda: reader.scan_room(room, state), room))
    if not readings:
        return [], False
    consistent = all(r == readings[0] for r in readings[1:])
    return readings, consistent


def impossible_duplicates(readings: list[list[str]]) -> list[str]:
    """返回**同一读数内重复出现**的干员名 —— 同一宿舍不可能有两个同名干员。

    这是"一致但错误"的检出器：T2.5 实测不复位连读 3 次得到逐字相同的
    `缄默德克萨斯 ×3`，只看一致性会误判为可信，合理性检查才能拆穿。
    """
    bad: list[str] = []
    for slots in readings:
        names = [s.partition("(")[0] for s in slots if s and s != "空" and "(" in s]
        seen: set[str] = set()
        for name in names:
            if name in seen and name not in bad:
                bad.append(name)
            seen.add(name)
    return bad


def room_snapshot(readings: list[list[str]]) -> list[str]:
    """把稳定读数规整成 `[干员名或"空"]`（取第一次读数）。"""
    if not readings:
        return []
    names: list[str] = []
    for text in readings[0]:
        if text == "空" or "(" not in text:
            names.append(text)
            continue
        names.append(text.partition("(")[0])
    return names


def vary_slot(readings: list[list[str]]) -> list[int]:
    """返回"多次读数不一致"的槽位下标（空列表 = 完全一致）。"""
    if len(readings) < 2:
        return []
    bad: list[int] = []
    width = max(len(r) for r in readings)
    for i in range(width):
        if len({(r[i] if i < len(r) else None) for r in readings}) > 1:
            bad.append(i)
    return bad