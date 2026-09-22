"""T2 点击类验收的**共享探针原语**（实机脚本，不参与门禁 G1 收集）。

从 `t2_1_navigation.py` 抽出 —— AGENTS.md 要求每个文件 ≤300 行，且这些原语
被 T2.1/T2.2/T2.3/T2.4 共同使用（`CallMeter` 数点击、`SceneTracker` 记 scene 序列、
`SwapCounters` 数换班日志）：

| 原语 | 用途 |
|---|---|
| `CallMeter` | 围绕 `recording_port` 的**增量**读数器：`phase()` 给出某条腿的 tap/swipe/swipe_path 数 |
| `SceneTracker` | 包 `Navigator._get_scene`，把每次**变化**记成序列，并支持插入腿边界标记 |
| `scene_name` / `describe` | 把 scene 值渲染成 `scheduler/scene.py` 里的**常量名**（判据要求引用常量） |
| `SwapCounters` | 从 `LogCapture.lines` 统计换班链路的关键日志计数 |
| `falsify_scan_silent` | T2.2 证伪：把 `_do_scan` 猴补丁回 **BUG-1 修复前**的写法 |

⚠️ 本文件名**不以 `_tests.py` 结尾**，因此不会被 G1 的 `discover` 收集。
"""

from __future__ import annotations

CALL_KINDS = ("tap", "swipe", "swipe_path")


def scene_name(value: int) -> str:
    """把 scene 数值渲染成 `scheduler/scene.py` 的常量名（未知则 `?N`）。"""
    from arknights_mower.scheduler.scene import Scene

    try:
        return Scene(value).name
    except ValueError:
        return f"?{value}"


def describe(values) -> str:
    """把 scene 序列（含 `("mark", label)` 边界）渲染成可读串。"""
    out = []
    for value in values:
        if isinstance(value, tuple):
            out.append(f"<{value[1]}>")
        else:
            out.append(scene_name(value))
    return " -> ".join(out)


def names_of(values) -> list[str]:
    """`describe` 的列表版：供 `in` / `index` 断言使用。"""
    return [
        f"<{v[1]}>" if isinstance(v, tuple) else scene_name(v) for v in values
    ]


def blank_leg(label: str, **extra) -> dict:
    """"未执行/被打断"的腿占位：**如实记为未通过**，绝不伪造成功。

    T2.1 的 `201 -> INDEX` 腿会因确认框点不中而永久自旋，墙钟到点后
    后续腿根本没跑。此时用本函数占位，让判据照常判 FAIL。
    """
    return {
        "label": label,
        "ok": False,
        "tap": 0,
        "swipe": 0,
        "swipe_path": 0,
        **extra,
    }


def print_legs(legs: list) -> None:
    """打印逐腿点击账（含耗时与是否被墙钟打断）。"""
    print("\n[6] 点击账（每条腿）")
    for leg in legs:
        aborted = "  [ABORTED]" if leg.get("aborted") else ""
        seconds = leg.get("seconds")
        elapsed = f" t={seconds:.1f}s" if seconds is not None else ""
        print(
            f"    {leg['label']:24} tap={leg['tap']} swipe={leg['swipe']}"
            f" path={leg['swipe_path']}{elapsed}{aborted}"
        )


class CallMeter:
    """`recording_port` 记录列表上的**增量**读数器。

    `phase()` 返回**自上次调用以来**的 tap/swipe/swipe_path 计数，因此可以按
    "腿"（一次 navigate / 一次 enter_room）分别记账 —— 这是 T2.1 判据的核心
    取证方式：非要断言全程零点击（`enter_room` 必然 tap），而是断言**每条腿**的
    点击数等于该腿在图/实现里的预期值。
    """

    def __init__(self, calls: list) -> None:
        self._calls = calls
        self._marks = self._snapshot()

    def _snapshot(self) -> dict:
        from tests.live.t2_common import counts

        return {kind: counts(self._calls, kind) for kind in CALL_KINDS}

    def phase(self) -> dict:
        now = self._snapshot()
        delta = {kind: now[kind] - self._marks[kind] for kind in CALL_KINDS}
        self._marks = now
        return delta

    def discard(self) -> None:
        """丢弃当前累计（不返回），用于"这一段不算"的场景。"""
        self._marks = self._snapshot()


class SceneTracker:
    """包 `Navigator._get_scene`，把**每次变化**记成序列，并支持插入腿边界标记。

    `Navigator.navigate()` 用 `self._get_scene()` 读场景，因此包实例属性即可
    捕获导航过程中的全部采样点，且不需要改动任何源码（T2 是验收方，不改 `arknights_mower/`）。
    """

    def __init__(self, navigator) -> None:
        self.frame: list = []
        self._last = object()
        self._original = navigator._get_scene

        def _tracked():
            value = int(self._original())
            if value != self._last:
                self._last = value
                self.frame.append(value)
            return value

        navigator._get_scene = _tracked

    @property
    def sequence(self) -> list:
        return list(self.frame)

    def names(self) -> list[str]:
        return names_of(self.frame)

    def mark(self, label: str) -> None:
        """在序列里插一个**腿边界**标记（渲染为 `<label>`）。"""
        self.frame.append(("mark", label))


class SwapCounters:
    """从 `LogCapture.lines` 统计换班链路的关键日志计数（T2.2/T2.3/T2.4 共用）。

    判据以**日志**为准（不以中间态为准）—— 例如 `free tap` 必须出现 3 次、
    `swipe page` 必须为 0、`uncheck slots=[2,3,4]` 必须出现。
    """

    def __init__(self, lines: list) -> None:
        self.lines = list(lines)

    def count(self, needle: str) -> int:
        return sum(1 for line in self.lines if needle in line)

    def find(self, needle: str) -> list[str]:
        return [line for line in self.lines if needle in line]

    def free_taps(self) -> list[str]:
        """`free tap <名字>` 里的名字列表（按出现顺序）。"""
        picked = []
        for line in self.find("AgentSwap: free tap "):
            picked.append(line.split("AgentSwap: free tap ", 1)[1].strip())
        return picked

    def uncheck_slots(self) -> list[int]:
        """`uncheck slots=[...]` 里的槽位下标（取最后一次出现）。"""
        hits = self.find("uncheck slots=[")
        if not hits:
            return []
        tail = hits[-1].split("uncheck slots=[", 1)[1].split("]", 1)[0]
        out = []
        for token in tail.split(","):
            token = token.strip()
            if token.lstrip("-").isdigit():
                out.append(int(token))
        return out

    def uncheck_taps(self) -> list[int]:
        """`uncheck slot N` 逐次点击记录里的槽位下标。"""
        out = []
        for line in self.find("AgentSwap: uncheck slot "):
            token = line.split("AgentSwap: uncheck slot ", 1)[1].strip()
            if token.isdigit():
                out.append(int(token))
        return out

    def swipe_pages(self) -> list[str]:
        """`swipe page=N` 日志行。"""
        return self.find("AgentSwap: swipe page=")

    def current_room(self) -> list[str]:
        """`current room=[...]` 里**产品自己读出**的干员名（取最后一次出现）。

        T2.4 用它推导"期望被 uncheck 的槽位"：`_do_swap` 就是按这份名单做决策的，
        因此用它与 `uncheck slots` 比对才是同口径。对比之下，"行动前读数"可能
        是**一致地错**的（T2.5 实测同屏重名），拿它当期望会得出错误的期望值。
        """
        hits = self.find("current room=[")
        if not hits:
            return []
        tail = hits[-1].split("current room=[", 1)[1].split("]", 1)[0]
        return [t.strip().strip("'\"") for t in tail.split(",") if t.strip()]

    def summary(self) -> dict:
        return {
            "free_taps": self.free_taps(),
            "uncheck_slots": self.uncheck_slots(),
            "uncheck_taps": self.uncheck_taps(),
            "swipe_pages": len(self.swipe_pages()),
            "reached_end": self.count("reached end of list"),
            "max_page": self.count("max page reached"),
            "executor_failed": self.count("executor failed for task"),
            "task_failed": self.count("task failed"),
            "unhandled": self.count("unhandled error"),
            "skip_seated": self.find("already in slot"),
        }


def falsify_scan_silent(monkeypatch_target) -> None:
    """T2.2 证伪对照：把 `_do_scan` 换回 **BUG-1 修复前**的写法。

    修复前的 `_do_scan` 把识别结果写进**局部变量** `cache`，而补位分支读的是
    `self._cache`（只在 `__init__` 里初始化为 `[]`，此后从未赋值）→ 补位恒空转，
    `free tap` 恒为 0，直接落到翻页逻辑。

    本函数把 `AgentSwapScanMixin._do_scan` 换成等价于修复前的实现，用于证明
    "`free tap` 计数"这条判据**真能变红**（检出 BUG-1 回退）。

    返回一个 `restore()` 可调用的句柄；调用方负责在 `finally` 里还原。
    """
    from arknights_mower.scheduler.services.agent_swap_scan import AgentSwapScanMixin
    from arknights_mower.scheduler.steps import Step, StepRetry
    from arknights_mower.utils.log import logger

    original = AgentSwapScanMixin._do_scan

    def _do_scan_bug1(self):
        self._recog.update()
        # ← BUG-1：写**局部变量**，不写 self._cache
        cache = self._operator_list_fn(
            self._recog.img, full_scan=(self._last_filter == "ALL")
        )
        names = [r[0] if isinstance(r, tuple) else r for r in cache]
        logger.info(
            f"AgentSwap: scan page={self._page_count} "
            f"filter={self._last_filter} names={names}"
        )
        if not cache:
            raise StepRetry

        target = self._pending[0] if self._pending else None
        self._found_target = False
        for name, box in cache:
            if name not in self._pending:
                continue
            logger.info(f"AgentSwap: tap {name} at {box}")
            self._tap_center(box)
            self._pending.remove(name)
            self._selected.append(name)
            if name == target:
                self._found_target = True

        return [Step("select", self._scene_check, self._do_select)]

    AgentSwapScanMixin._do_scan = _do_scan_bug1

    class _Handle:
        @staticmethod
        def restore() -> None:
            AgentSwapScanMixin._do_scan = original

    return _Handle()