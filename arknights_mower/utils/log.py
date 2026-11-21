import atexit
import json
import logging
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from logging.handlers import QueueHandler, QueueListener, TimedRotatingFileHandler
from pathlib import Path
from queue import Queue
from threading import Lock, Thread
from time import monotonic
from typing import TYPE_CHECKING

import colorlog

from arknights_mower.utils.log_groups import group_for_pathname
from arknights_mower.utils.log_history import ID_ONLY_LOG_PARENT_TYPES
from arknights_mower.utils.log_retention import RUNTIME_LOG_RETENTION_HOURS
from arknights_mower.utils.path import get_path

if TYPE_CHECKING:
    from arknights_mower.utils.screenshot import ScreenshotStore

BASIC_FORMAT = "%(asctime)s %(log_group_prefix)s%(relativepath)s:%(lineno)d %(levelname)s %(funcName)s: %(message)s"
COLOR_FORMAT = f"%(log_color)s{BASIC_FORMAT}"
DATE_FORMAT = None
basic_formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)
color_formatter = colorlog.ColoredFormatter(COLOR_FORMAT, DATE_FORMAT)
LIVE_LOG_CAPACITY = 256
LIVE_LOG_MESSAGE_LIMIT = 16 * 1024
LIVE_LOG_RECRUITMENT_LIMIT = 4096
LIVE_LOG_TRUNCATION_SUFFIX = "\n[实时日志已截断，完整内容见 runtime.log]"
LIVE_LOG_DROP_WARNING_INTERVAL = 60.0
LIVE_LOG_DROP_WARNING_FORMAT = (
    "部分日志未能及时显示，已跳过较早记录以显示最新内容。"
    "需要查看这些记录时，请打开 runtime.log。"
)


def _live_message(message, keep_tail=""):
    """把实时日志整行限制在 LIVE_LOG_MESSAGE_LIMIT 字符内。

    ``keep_tail`` 由调用方拼在 ``message`` 末尾（例如截图归档说明）。超长时保留
    正文前缀，并在截断标记后重新接上 ``keep_tail``，因此行尾的归档编号不会被截掉；
    ``runtime.log`` 仍保存完整原文。
    """
    if len(message) <= LIVE_LOG_MESSAGE_LIMIT:
        return message
    suffix = LIVE_LOG_TRUNCATION_SUFFIX + keep_tail
    budget = LIVE_LOG_MESSAGE_LIMIT - len(suffix)
    if budget <= 0:
        return suffix[-LIVE_LOG_MESSAGE_LIMIT:]
    return message[:budget] + suffix


def _task_snapshot(value, message):
    """任务预告与正文共用实时长度预算；无效或超限时退回完整文本的既有处理。"""
    if not isinstance(value, dict):
        return None
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        if len(message) + len(encoded) > LIVE_LOG_MESSAGE_LIMIT:
            return None
        return json.loads(encoded)
    except (TypeError, ValueError, OverflowError, RecursionError, RuntimeError):
        return None


def _recruitment_snapshot(value, message, task=None):
    """公招标签独立快照，并与正文、任务预告共用实时长度预算。"""
    if not isinstance(value, dict):
        return None
    event = value.get("event")
    rarity = value.get("rarity")
    if not isinstance(event, str) or event not in ("tags", "start", "rare"):
        return None
    if rarity is not None and (type(rarity) is not int or not 1 <= rarity <= 6):
        return None
    if "combinations" in value:
        if event != "rare" or "tags" in value or rarity is None:
            return None
        combinations = value["combinations"]
        if not isinstance(combinations, list) or not 1 <= len(combinations) <= 25:
            return None
        groups = []
        for combination in combinations:
            if not isinstance(combination, dict):
                return None
            tags = combination.get("tags")
            level = combination.get("rarity")
            if not isinstance(tags, list) or not 1 <= len(tags) <= 3:
                return None
            if any(
                not isinstance(tag, str) or not tag.strip() or len(tag) > 32
                for tag in tags
            ):
                return None
            if type(level) is not int or not 1 <= level <= 6:
                return None
            groups.append({"tags": list(tags), "rarity": level})
        snapshot = {"event": event, "rarity": rarity, "combinations": groups}
    else:
        tags = value.get("tags")
        if not isinstance(tags, list) or not 1 <= len(tags) <= 5:
            return None
        if any(
            not isinstance(tag, str) or not tag.strip() or len(tag) > 32 for tag in tags
        ):
            return None
        snapshot = {"event": event, "tags": list(tags), "rarity": rarity}
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > LIVE_LOG_RECRUITMENT_LIMIT:
        return None
    task_size = (
        len(json.dumps(task, ensure_ascii=False, separators=(",", ":")))
        if task is not None
        else 0
    )
    if len(message) + task_size + len(encoded) > LIVE_LOG_MESSAGE_LIMIT:
        return None
    return snapshot


def _backups_snapshot(value, message, task=None, recruitment=None):
    """保存副表完整名称，与其他实时字段共用长度预算。"""
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        return None
    result = []
    for item in value:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        active = item.get("active")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 128
            or type(active) is not bool
        ):
            return None
        result.append({"name": name, "active": active})
    size = len(message)
    for snapshot in (task, recruitment, result):
        if snapshot is not None:
            size += len(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
    return result if size <= LIVE_LOG_MESSAGE_LIMIT else None


def _training_positions(value):
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 2
        or any(
            not isinstance(item, dict)
            or type(item.get("index")) is not int
            or item["index"] not in (0, 1)
            or not isinstance(item.get("agent"), str)
            or not item["agent"].strip()
            or len(item["agent"]) > 256
            for item in value
        )
        or len({item["index"] for item in value}) != len(value)
    ):
        return None
    return [{"agent": item["agent"], "index": item["index"]} for item in value]


def _parent_snapshot(value):
    """保留日志记录明确关联的任务。"""
    if not isinstance(value, dict):
        return None

    def identifier(key):
        item = value.get(key)
        return isinstance(item, str) and bool(item.strip()) and len(item) <= 128

    if not identifier("id"):
        return None
    if value.get("type") in ID_ONLY_LOG_PARENT_TYPES:
        return {key: value[key] for key in ("type", "id")}
    if value.get("type") == "recruitment-slot":
        slot = value.get("slot")
        if type(slot) is not int or not 1 <= slot <= 4:
            return None
        return {key: value[key] for key in ("type", "id", "slot")}
    if value.get("type") == "facility-arrangement":
        if not identifier("room"):
            return None
        return {key: value[key] for key in ("type", "id", "room")}
    if value.get("type") != "rescue-staffing":
        return None
    scoped = "room" in value or "attempt" in value
    if scoped and not (identifier("room") and identifier("attempt")):
        return None
    keys = ("type", "id", "room", "attempt") if scoped else ("type", "id")
    return {key: value[key] for key in keys}


_parent_log_scope = ContextVar("mower_parent_log_scope", default=None)


@contextmanager
def log_parent_context(parent):
    """在来源上下文绑定任务明细，退出或中断时恢复先前归属。"""
    token = _parent_log_scope.set(_parent_snapshot(parent))
    try:
        yield
    finally:
        _parent_log_scope.reset(token)


def _display_snapshots(record, message, *existing):
    """库存和动作提示保留独立快照，与既有字段共用实时长度预算。"""
    remaining = (
        LIVE_LOG_MESSAGE_LIMIT
        - len(message)
        - sum(
            len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            for value in existing
            if value is not None
        )
    )
    result = {}

    def include(key, value):
        nonlocal remaining
        size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        if size <= remaining:
            result[key] = value
            remaining -= size

    inventory = getattr(record, "log_inventory", None)
    items = inventory.get("items") if isinstance(inventory, dict) else None
    if isinstance(items, list) and 1 <= len(items) <= 512:
        valid = all(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and bool(item["name"].strip())
            and len(item["name"]) <= 256
            and type(item.get("count")) is int
            and 0 <= item["count"] <= 9_007_199_254_740_991
            for item in items
        )
        if valid:
            include(
                "inventory",
                {
                    "items": [
                        {"name": item["name"], "count": item["count"]} for item in items
                    ]
                },
            )
    event = getattr(record, "log_event", None)

    def text_field(value, limit=256):
        return isinstance(value, str) and bool(value.strip()) and len(value) <= limit

    def count_field(value):
        return type(value) is int and 0 <= value <= 9_007_199_254_740_991

    def workshop_material(value):
        if (
            isinstance(value, dict)
            and text_field(value.get("name"))
            and text_field(value.get("item"))
        ):
            return {"name": value["name"], "item": value["item"]}

    if isinstance(event, dict) and event.get("type") == "operator-reset-idle":
        include("event", {"type": "operator-reset-idle"})
    elif isinstance(event, dict) and event.get("type") == "recruitment-slot":
        phase = event.get("phase")
        if (slot := _parent_snapshot(event)) is not None and (
            "phase" not in event
            or phase in ("started", "completed", "failed", "stopped")
        ):
            if "phase" in event:
                slot["phase"] = phase
            include("event", slot)
    elif isinstance(event, dict) and event.get("type") == "facility-idle":
        agents = event.get("agents")
        if (
            text_field(event.get("id"), 128)
            and text_field(event.get("room"), 128)
            and isinstance(agents, list)
            and 1 <= len(agents) <= 5
            and all(
                text_field(name) and name not in ("Current", "Free", "_")
                for name in agents
            )
            and len(set(agents)) == len(agents)
        ):
            include(
                "event",
                {
                    "type": "facility-idle",
                    "id": event["id"],
                    "room": event["room"],
                    "agents": list(agents),
                },
            )
    elif isinstance(event, dict) and event.get("type") == "workshop-material":
        if (material := workshop_material(event)) is not None:
            include("event", {"type": "workshop-material", **material})
    elif isinstance(event, dict) and event.get("type") == "workshop-result":
        changes = event.get("changes")
        if (
            isinstance(changes, list)
            and 1 <= len(changes) <= 512
            and all(
                isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and bool(item["name"].strip())
                and len(item["name"]) <= 256
                and type(item.get("delta")) is int
                and 0 < abs(item["delta"]) <= 9_007_199_254_740_991
                for item in changes
            )
        ):
            workshop_result = {
                "type": "workshop-result",
                "changes": [
                    {"name": item["name"], "delta": item["delta"]} for item in changes
                ],
            }
            if (product := workshop_material(event.get("product"))) is not None:
                workshop_result["product"] = product
            include("event", workshop_result)
    elif isinstance(event, dict) and event.get("type") == "rescue-staffing":
        rooms = event.get("rooms")
        phase = event.get("phase")
        if (
            text_field(event.get("id"), 128)
            and phase in ("queued", "started", "completed", "failed")
            and type(event.get("anchor")) is bool
            and event["anchor"] == (phase == "queued")
            and isinstance(rooms, list)
            and 1 <= len(rooms) <= 32
            and all(
                isinstance(item, dict)
                and text_field(item.get("room"), 128)
                and text_field(item.get("label"), 128)
                and isinstance(item.get("agents"), list)
                and len(item["agents"]) <= 5
                and all(
                    isinstance(name, str) and len(name) <= 256
                    for name in item["agents"]
                )
                and item.get("status")
                in ("pending", "active", "completed", "unconfirmed")
                for item in rooms
            )
            and len({item["room"] for item in rooms}) == len(rooms)
            and (
                phase != "completed"
                or all(item["status"] == "completed" for item in rooms)
            )
            and (
                "detail" not in event
                or (phase == "failed" and text_field(event["detail"], 2048))
            )
        ):
            include(
                "event",
                {
                    "type": "rescue-staffing",
                    **{key: event[key] for key in ("id", "phase", "anchor")},
                    "rooms": [
                        {
                            "room": item["room"],
                            "label": item["label"],
                            "agents": list(item["agents"]),
                            "status": item["status"],
                        }
                        for item in rooms
                    ],
                    **({"detail": event["detail"]} if "detail" in event else {}),
                },
            )
    elif isinstance(event, dict) and event.get("type") == "facility-arrangement":
        agents = event.get("agents")
        positions = _training_positions(event.get("positions"))
        summary = event.get("summary")
        if (
            all(
                isinstance(event.get(key), str)
                and bool(event[key].strip())
                and len(event[key]) <= 128
                for key in ("id", "room", "label")
            )
            and event.get("phase") in ("started", "updated", "completed", "failed")
            and (event["phase"] != "updated" or event.get("anchor") is False)
            and (
                "anchor" not in event
                or (
                    type(event["anchor"]) is bool
                    and event["anchor"] == (event["phase"] == "started")
                )
            )
            and isinstance(agents, list)
            and len(agents) <= 5
            and all(
                isinstance(name, str) and name.strip() and len(name) <= 256
                for name in agents
            )
            and (
                "positions" not in event
                or (
                    event["room"] == "train"
                    and positions is not None
                    and all(item["agent"] in agents for item in positions)
                )
            )
        ):
            include(
                "event",
                {
                    "type": "facility-arrangement",
                    **{key: event[key] for key in ("id", "phase", "room", "label")},
                    "agents": list(agents),
                    **({"anchor": event["anchor"]} if "anchor" in event else {}),
                    **({"positions": positions} if positions is not None else {}),
                    **(
                        {"summary": summary}
                        if summary == message
                        and text_field(summary, 1024)
                        and "\n" not in summary
                        and "\r" not in summary
                        else {}
                    ),
                },
            )
    elif isinstance(event, dict) and event.get("type") == "facility-observation":
        phase = event.get("phase")
        summary = event.get("summary")
        agents = event.get("agents")
        if (
            all(text_field(event.get(key), 128) for key in ("id", "room", "label"))
            and phase in ("started", "completed", "failed")
            and type(event.get("anchor")) is bool
            and event["anchor"] == (phase == "started")
            and text_field(summary, 1024)
            and summary == message
            and "\n" not in summary
            and "\r" not in summary
            and isinstance(agents, list)
            and len(agents) <= 5
            and all(text_field(name) for name in agents)
        ):
            include(
                "event",
                {
                    **{
                        key: event[key]
                        for key in (
                            "type",
                            "id",
                            "room",
                            "label",
                            "phase",
                            "anchor",
                            "summary",
                        )
                    },
                    "agents": list(agents),
                },
            )
    elif isinstance(event, dict) and event.get("type") in (
        "mood-calculation",
        "depot-scan",
    ):
        mood = event["type"] == "mood-calculation"
        phase = event.get("phase")
        summary = event.get("summary")
        if (
            text_field(event.get("id"), 128)
            and (not mood or text_field(event.get("label"), 128))
            and (
                phase in ("started", "updated", "completed", "failed")
                or (not mood and phase == "stopped")
            )
            and type(event.get("anchor")) is bool
            and event["anchor"] == (phase == "started")
            and text_field(summary, 1024)
            and summary == message
            and "\n" not in summary
            and "\r" not in summary
        ):
            include(
                "event",
                {
                    **{
                        key: event[key]
                        for key in ("type", "id", "phase", "anchor", "summary")
                    },
                    **({"label": event["label"]} if mood else {}),
                },
            )
    elif isinstance(event, dict) and event.get("type") == "production-switch":
        phase = event.get("phase")
        if (
            all(text_field(event.get(key), 128) for key in ("id", "room", "label"))
            and text_field(event.get("product"))
            and event.get("facility") in ("manufacture", "trade")
            and phase in ("started", "waiting", "completed", "failed")
            and type(event.get("anchor")) is bool
            and event["anchor"] == (phase == "started")
            and ("previous" not in event or text_field(event["previous"]))
            and (
                "detail" not in event
                or (
                    phase in ("waiting", "failed") and text_field(event["detail"], 2048)
                )
            )
            and (phase != "waiting" or "detail" in event)
        ):
            include(
                "event",
                {
                    "type": "production-switch",
                    **{
                        key: event[key]
                        for key in (
                            "id",
                            "phase",
                            "anchor",
                            "room",
                            "label",
                            "facility",
                            "product",
                        )
                    },
                    **({"previous": event["previous"]} if "previous" in event else {}),
                    **({"detail": event["detail"]} if "detail" in event else {}),
                },
            )
    elif isinstance(event, dict) and event.get("type") == "order-read":
        rooms = event.get("rooms")
        phase = event.get("phase")
        if (
            text_field(event.get("id"), 128)
            and phase in ("started", "updated", "completed", "failed")
            and type(event.get("anchor")) is bool
            and event["anchor"] == (phase == "started")
            and type(event.get("after_switch")) is bool
            and isinstance(rooms, list)
            and 1 <= len(rooms) <= 32
            and all(
                isinstance(item, dict)
                and text_field(item.get("room"), 128)
                and text_field(item.get("label"), 128)
                and item.get("status") in ("pending", "read", "paused")
                for item in rooms
            )
            and len({item["room"] for item in rooms}) == len(rooms)
            and (
                phase not in ("started", "updated")
                or any(item["status"] == "pending" for item in rooms)
            )
            and (
                phase != "completed"
                or all(item["status"] != "pending" for item in rooms)
            )
            and (
                "detail" not in event
                or (phase == "failed" and text_field(event["detail"], 2048))
            )
        ):
            include(
                "event",
                {
                    "type": "order-read",
                    **{
                        key: event[key]
                        for key in ("id", "phase", "anchor", "after_switch")
                    },
                    "rooms": [
                        {key: item[key] for key in ("room", "label", "status")}
                        for item in rooms
                    ],
                    **({"detail": event["detail"]} if "detail" in event else {}),
                },
            )
    elif isinstance(event, dict) and event.get("type") == "training-selection":
        positions = _training_positions(event.get("positions"))
        if positions is not None:
            include("event", {"type": "training-selection", "positions": positions})
    elif isinstance(event, dict) and event.get("type") in (
        "stage-inventory-limit",
        "stage-inventory-ratio",
    ):
        stage = event.get("stage")
        if (
            isinstance(stage, dict)
            and text_field(stage.get("code"), 64)
            and isinstance(stage.get("drops"), list)
            and len(stage["drops"]) <= 64
            and all(text_field(name) for name in stage["drops"])
        ):
            include(
                "event",
                {
                    "type": event["type"],
                    "stage": {"code": stage["code"], "drops": list(stage["drops"])},
                },
            )
    elif isinstance(event, dict) and event.get("type") == "stage-inventory-plan":
        stages = event.get("stages")
        aliases = {"Annihilation": "当期剿灭", "": "上次作战"}
        if (
            isinstance(stages, list)
            and len(stages) <= 128
            and all(
                isinstance(item, dict)
                and isinstance(item.get("code"), str)
                and (item["code"] == "" or text_field(item["code"], 64))
                and text_field(item.get("label"), 64)
                and item["label"] == aliases.get(item["code"], item["code"])
                and isinstance(item.get("drops"), list)
                and len(item["drops"]) <= 64
                and all(text_field(name) for name in item["drops"])
                and (item["code"] not in aliases or not item["drops"])
                for item in stages
            )
        ):
            include(
                "event",
                {
                    "type": "stage-inventory-plan",
                    "stages": [
                        {
                            "code": item["code"],
                            "label": item["label"],
                            "drops": list(item["drops"]),
                        }
                        for item in stages
                    ],
                },
            )
    elif isinstance(event, dict) and event.get("type") == "operation-drops":
        items = event.get("items")
        if (
            isinstance(items, list)
            and 1 <= len(items) <= 512
            and all(
                isinstance(item, dict)
                and text_field(item.get("name"))
                and count_field(item.get("count"))
                and item["count"] > 0
                for item in items
            )
        ):
            include(
                "event",
                {
                    "type": "operation-drops",
                    "items": [
                        {"name": item["name"], "count": item["count"]} for item in items
                    ],
                },
            )
    elif isinstance(event, dict) and event.get("type") == "base-report":
        items = event.get("items")
        if (
            text_field(event.get("date"), 32)
            and isinstance(items, list)
            and 1 <= len(items) <= 64
            and all(
                isinstance(item, dict)
                and text_field(item.get("name"))
                and "value" in item
                and (item.get("value") is None or count_field(item["value"]))
                and text_field(item.get("unit"), 32)
                and text_field(item.get("item"))
                for item in items
            )
        ):
            include(
                "event",
                {
                    "type": "base-report",
                    "date": event["date"],
                    "items": [
                        {key: item[key] for key in ("name", "value", "unit", "item")}
                        for item in items
                    ],
                },
            )
    parent = _parent_snapshot(getattr(record, "log_parent", None))
    if parent is not None:
        include("parent", parent)
    return result


class LatestLogQueue(Queue):
    """消费停滞时淘汰最旧记录，生产者和退出标记不等待空位。

    ``put(item)`` 没有 ``block``/``timeout`` 参数：队列满时先淘汰最旧一条再入队，
    不会抛 ``queue.Full``。淘汰条数累计在 ``dropped``，“自上次告警以来的条数”见
    ``dropped_since_warning``；两者都是线程安全的可读状态。淘汰用户可见的普通
    记录时，按 ``drop_warning_interval`` 限频提示日志显示不完整。调试记录、
    退出标记及此提示本身不触发警告；传入 ``None`` 可关闭警告（测试用）。
    """

    def __init__(
        self,
        maxsize=LIVE_LOG_CAPACITY,
        *,
        drop_warning_interval=LIVE_LOG_DROP_WARNING_INTERVAL,
    ):
        if maxsize <= 0:
            raise ValueError("日志队列容量必须大于 0")
        super().__init__(maxsize=maxsize)
        self.dropped = 0
        self.dropped_since_warning = 0
        self._drop_warning_interval = drop_warning_interval
        self._last_drop_warning = None
        self._drop_lock = Lock()

    def put(self, item):
        """入队一条记录或消息；不等待空位，队列满时淘汰最旧一条。"""
        if isinstance(item, str):
            item = _live_message(item)
        dropped = False
        previous = None
        with self.not_full:
            if self._qsize() >= self.maxsize:
                previous = self._get()
                self.unfinished_tasks -= 1
                dropped = True
            self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()
        if dropped:
            self._report_dropped(previous, notify=item is not None)

    def put_nowait(self, item):
        """QueueHandler 与 QueueListener 使用的非阻塞入口。"""
        self.put(item)

    @staticmethod
    def _needs_warning(item):
        if isinstance(item, logging.LogRecord):
            return item.levelno >= logging.INFO and not getattr(
                item, "log_drop_notice", False
            )
        if isinstance(item, dict):
            return item.get("level", "INFO") not in ("DEBUG", "NOTSET") and not (
                item.get("group") == "runtime-log"
                and item.get("msg") == LIVE_LOG_DROP_WARNING_FORMAT
            )
        return isinstance(item, str) and item != LIVE_LOG_DROP_WARNING_FORMAT

    def _report_dropped(self, item, *, notify=True):
        with self._drop_lock:
            self.dropped += 1
            self.dropped_since_warning += 1
            interval = self._drop_warning_interval
            if interval is None or not notify or not self._needs_warning(item):
                return
            now = monotonic()
            if (
                self._last_drop_warning is not None
                and now - self._last_drop_warning < interval
            ):
                return
            self.dropped_since_warning = 0
            self._last_drop_warning = now
        logger.warning(
            LIVE_LOG_DROP_WARNING_FORMAT,
            extra={
                "log_group": "runtime-log",
                "log_drop_notice": True,
                "log_parent": None,
            },
        )


class LiveQueueHandler(QueueHandler):
    def prepare(self, record):
        """限制入队记录的消息长度，作为队列内容的第一道内存界限。

        整行（时间、级别、消息和截图归档说明）的最终截断在 Handler.emit 完成；
        文件日志 handler 直接接收原始记录，不受这里影响。
        """
        prepared = super().prepare(record)
        prepared.msg = prepared.message = _live_message(prepared.message)
        task = _task_snapshot(getattr(prepared, "log_task", None), prepared.message)
        if task is None:
            prepared.__dict__.pop("log_task", None)
        else:
            prepared.log_task = task
        recruitment = _recruitment_snapshot(
            getattr(prepared, "log_recruitment", None), prepared.message, task
        )
        if recruitment is None:
            prepared.__dict__.pop("log_recruitment", None)
        else:
            prepared.log_recruitment = recruitment
        backups = _backups_snapshot(
            getattr(prepared, "log_backups", None), prepared.message, task, recruitment
        )
        if backups is None:
            prepared.__dict__.pop("log_backups", None)
        else:
            prepared.log_backups = backups
        display = _display_snapshots(
            prepared, prepared.message, task, recruitment, backups
        )
        for key in ("inventory", "event", "parent"):
            attr = f"log_{key}"
            if key in display:
                setattr(prepared, attr, display[key])
            else:
                prepared.__dict__.pop(attr, None)
        return prepared


class PackagePathFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        relativepath = Path(record.pathname)
        try:
            relativepath = relativepath.relative_to(get_path("@install"))
        except ValueError:
            pass
        record.relativepath = relativepath
        # 文件日志和终端输出携带 group 前缀，使 runtime.log 可按子系统 grep；
        # group 缺失时跳过，不产生额外空格。这里只写独立的格式化属性，
        # record.log_group 保持调用方原始值，结构化记录不受前缀空格影响。
        group = getattr(record, "log_group", None)
        record.log_group_prefix = f"{group} " if group else ""
        return True


filter = PackagePathFilter()


class _ParentContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        parent = _parent_log_scope.get()
        if parent is not None and not hasattr(record, "log_parent"):
            record.log_parent = dict(parent)
        return True


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addFilter(_ParentContextFilter())

# 只有画面能帮助定位的运行路径才自动归档；其他 ERROR 仍进入运行日志和实时日志。
_VISUAL_ERROR_FILES = {
    "utils/device/device.py",
    "utils/graph.py",
    "utils/matcher.py",
    "utils/scheduler_task.py",
    "utils/segment.py",
    "utils/solver.py",
}
_VISUAL_SOLVER_FILES = {
    "base_mixin.py",
    "base_schedule.py",
    "captcha_solver.py",
    "operation.py",
    "player_info.py",
    "recruit.py",
    "secret_front.py",
}


def should_archive_record(record: logging.LogRecord) -> bool:
    if record.levelno < logging.WARNING:
        return False
    override = getattr(record, "archive_screenshots", None)
    if override is not None:
        return bool(override)
    if record.levelno < logging.ERROR:
        return False
    source = record.pathname.replace("\\", "/").partition("arknights_mower/")[2]
    if source.startswith("solvers/"):
        return source.removeprefix("solvers/") in _VISUAL_SOLVER_FILES
    return source in _VISUAL_ERROR_FILES


# d(ebug)hlr: 终端输出
dhlr = logging.StreamHandler(stream=sys.stdout)
dhlr.setFormatter(color_formatter)
dhlr.setLevel(logging.DEBUG)
dhlr.addFilter(filter)


class Handler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord):
        detail = record.getMessage()
        summary = detail.split("\nTraceback (most recent call last):", 1)[0]
        if record.levelno >= logging.ERROR:
            if summary.startswith(("Error", "Exception")) or summary == str(record.msg):
                summary = f"运行时发生错误：{summary}"
        archive_notice = ""
        if should_archive_record(record):
            try:
                store = get_screenshot_store() or (
                    _store() if fhlr is not None else None
                )
                if store is not None:
                    archive_summary = (
                        f"警告：{summary}"
                        if record.levelno < logging.ERROR
                        else summary
                    )
                    archive_id = store.mark_error(
                        int(record.created * 10**9), archive_summary
                    )
                    archive_notice = f"（已保存前后截图，记录编号 {archive_id}）"
            except Exception:
                pass  # 日志输出不能因归档失败而中断。
        if record.exc_info and record.levelno < logging.ERROR:
            summary += "\n" + "".join(traceback.format_exception(*record.exc_info))
        rec = _build_log_record(record, summary, archive_notice)
        frontend_log_queue.put(rec)


def _build_log_record(record, summary, archive_notice=""):
    """把 LogRecord 组装成推送给前端的结构化记录字典。

    必填字段：``t``（asctime 字符串）、``level``、``msg``。
    ``at`` 保留记录产生时的 Unix 毫秒时间，供跨时区的客户端计算经过时长。
    ``msg`` 由 ``summary`` 与 ``archive_notice`` 合并后按实时日志上限截断，
    保留与原文本行相同的显示格式（截断标记和归档编号留在尾部）。
    可选字段由调用方通过 ``logger.*(msg, extra={"log_group": ...})`` 注入：
    ``group``、``room``、``agents``、``duration_ms``、``error_code``、``task``、
    ``recruitment``、``backups``、``inventory``、``event``、``parent``。
    ``group`` 在调用方未指定时按 ``record.pathname`` 从来源模块派生；显式值
    与派生值都去掉首尾空白，两者都没有时记录不含 ``group`` 键。
    """
    full_msg = _live_message(summary + archive_notice, archive_notice)
    rec = {
        "t": record.asctime,
        "at": round(record.created * 1000),
        "level": record.levelname,
        "msg": full_msg,
    }
    # 调用方显式取值优先；没有时按来源模块派生。过滤器只给文件日志写
    # log_group_prefix，因此这里的原始值不带前缀空格，仍须去掉首尾空白。
    group = getattr(record, "log_group", None)
    if group is None:
        group = group_for_pathname(record.pathname)
    if group is not None:
        group = str(group).strip()
        if group:
            rec["group"] = group
    for attr, key in (
        ("log_room", "room"),
        ("log_agents", "agents"),
        ("log_duration_ms", "duration_ms"),
        ("log_error_code", "error_code"),
    ):
        value = getattr(record, attr, None)
        if value is not None:
            rec[key] = value
    task = _task_snapshot(getattr(record, "log_task", None), full_msg)
    if task is not None:
        rec["task"] = task
    recruitment = _recruitment_snapshot(
        getattr(record, "log_recruitment", None), full_msg, task
    )
    if recruitment is not None:
        rec["recruitment"] = recruitment
    backups = _backups_snapshot(
        getattr(record, "log_backups", None), full_msg, task, recruitment
    )
    if backups is not None:
        rec["backups"] = backups
    rec.update(_display_snapshots(record, full_msg, task, recruitment, backups))
    return rec


# w(ebsocket)hlr: WebSocket
frontend_log_queue = LatestLogQueue()
whlr = Handler()
whlr.setLevel(logging.INFO)

log_queue = LatestLogQueue()
queue_handler = LiveQueueHandler(log_queue)
logger.addHandler(queue_handler)
listener = QueueListener(log_queue, dhlr, whlr, respect_handler_level=True)
listener.start()

# f(ile)hlr: 文件记录（整点滚转）。不在导入时建立，避免 GUI 子进程（webview_window
# 等）import 本模块时也各建一个指向同一 runtime.log 的文件句柄。Windows 的 os.rename
# 需要独占移动文件，两个进程都持有该文件时，任一进程整点滚转都会因另一进程仍占用而
# 抛 PermissionError [WinError 32]，且失败后该进程之后所有日志都会重复失败、全部丢失。
# 因此文件日志交由主进程显式 init_file_logging() 建立，子进程不调用。
fhlr = None
_stderr_handler = None
_stderr_handler_lock = Lock()


def init_stderr_logging(stream=None) -> None:
    """同步保存独立服务的诊断，不建立实例文件日志或读取配置。

    服务工作进程可能通过 os._exit 退出，不能依赖异步队列完成输出。
    调用方可以传入自己的 stderr；重复初始化复用同一个 handler。
    """
    global _stderr_handler
    stream = sys.stderr if stream is None else stream
    if stream is None:
        return
    with _stderr_handler_lock:
        if _stderr_handler is None:
            _stderr_handler = logging.StreamHandler(stream)
            _stderr_handler.setFormatter(basic_formatter)
            _stderr_handler.addFilter(filter)
            logger.addHandler(_stderr_handler)
        elif _stderr_handler.stream is not stream:
            _stderr_handler.setStream(stream)


def init_file_logging() -> None:
    global fhlr
    if fhlr is not None:
        return
    folder = Path(get_path("@app/log"))
    folder.mkdir(exist_ok=True, parents=True)
    fhlr = TimedRotatingFileHandler(
        folder.joinpath("runtime.log"),
        when="h",
        interval=1,
        encoding="utf8",
        backupCount=RUNTIME_LOG_RETENTION_HOURS,
    )
    fhlr.setFormatter(basic_formatter)
    fhlr.setLevel("DEBUG")
    fhlr.addFilter(filter)
    logger.addHandler(fhlr)
    # 已有报错归档时，即使本次启动尚未截图，也要继续定期清理过期记录。
    if (Path(get_path("@app/screenshot")) / "errors").is_dir():
        _store()


# 多进程集中式日志：mower 主进程独占 runtime.log 文件句柄（init_file_logging），
# mp.Process 子进程（如 webview_window）经 title_version→resource_version import log.py 时
# 不建 fhlr，而是用 QueueHandler 把 LogRecord 经共享的 multiprocessing.Queue 上行到主进程，
# 由主进程的 start_mp_listener 消费后写入 fhlr。这样既保留子进程日志落盘，又避免多个进程
# 各自持有 runtime.log 导致 Windows 整点滚转（os.rename 需独占）抛 PermissionError
# [WinError 32]。两个通过 subprocess.Popen 拉起的 worker（进程控制 / 软件更新）与主进程
# 之间没有共享的 mp.Queue，走不进这条路，它们各自把输出写进 process.log / update.log。
mp_queue_handler = None  # 子进程侧：把本进程的 logger 记录送上共享队列
mp_listener = None  # 主进程侧：把共享队列里的记录写入 fhlr


def bind_mp_queue(queue) -> None:
    """mp.Process 子进程使用：把本进程日志上行到主进程的共享队列。

    子进程不调用 init_file_logging（不建 fhlr），只把 logger 挂到 QueueHandler(queue)，
    记录由主进程的 start_mp_listener 消费后写入 runtime.log。
    """
    global mp_queue_handler
    if mp_queue_handler is not None:
        return
    mp_queue_handler = QueueHandler(queue)
    logger.addHandler(mp_queue_handler)


def start_mp_listener(queue) -> None:
    """主进程使用：消费共享队列，把子进程上行的记录写入 runtime.log。

    QueueHandler.prepare 会把 message 连同异常栈一起格式化进 record.message，随后清空
    args / exc_info / exc_text，因此跨进程 pickle 安全，子进程的异常栈会随 message 落盘。
    须在能取得 fhlr 之后调用（内部会兜底 init_file_logging）。
    """
    global mp_listener
    if mp_listener is not None:
        return
    init_file_logging()
    mp_listener = QueueListener(queue, fhlr, respect_handler_level=True)
    mp_listener.start()


def _stop_listener(bounded_listener, timeout=2):
    if bounded_listener is None:
        return

    # QueueListener.stop has an unbounded join (and a pipe sentinel may block).
    # The daemon sender and bounded reader join keep shutdown finite.
    def notify():
        try:
            bounded_listener.enqueue_sentinel()
        except (EOFError, OSError, ValueError):
            pass

    sender = Thread(target=notify, daemon=True)
    sender.start()
    sender.join(timeout)
    worker = bounded_listener._thread
    if worker is not None:
        worker.join(timeout)


def close_mp_logging():
    global mp_listener
    current, mp_listener = mp_listener, None
    _stop_listener(current)


def close_logging():
    """Release only mower's listeners and file handler, after other resources."""
    global fhlr, _stderr_handler
    close_mp_logging()
    logger.removeHandler(queue_handler)
    if mp_queue_handler is not None:
        logger.removeHandler(mp_queue_handler)
    _stop_listener(listener)
    current, fhlr = fhlr, None
    if current is not None:
        logger.removeHandler(current)
        current.close()
    with _stderr_handler_lock:
        current, _stderr_handler = _stderr_handler, None
        if current is not None:
            logger.removeHandler(current)
            current.close()


_store_instance: "ScreenshotStore | None" = None
_store_lock = Lock()
_store_closed = False


def _store() -> "ScreenshotStore | None":
    """返回本进程的截图存储，第一次提交截图时才建立后台线程。

    与 fhlr 同样不在导入时建立：导入本模块的进程（测试、开发服务器、各种抓图
    脚本）不应顺带拿到写盘与过期清理线程。清理线程启动时会先扫一遍历史截图，
    多份清理线程并发删除同一批文件时，Windows 会让其中一次以 WinError 5 失败
    并记一条清理错误。
    """
    from arknights_mower.utils import config

    global _store_instance
    with _store_lock:
        if _store_closed:
            return _store_instance
        if _store_instance is None:
            from arknights_mower.utils.screenshot import ScreenshotStore

            store = ScreenshotStore(
                get_path("@app/screenshot"),
                lambda: config.conf.screenshot,
                logger,
                archive_limit_mb=lambda: config.conf.screenshot_archive_limit_mb,
            )
            store.start()
            atexit.register(close_screenshot_store)
            _store_instance = store
        return _store_instance


def get_screenshot_store() -> "ScreenshotStore | None":
    """本进程已建立的截图存储；还没提交过截图时返回 None。"""
    return _store_instance


def close_screenshot_store(timeout=5) -> dict:
    """Close at process exit, retaining the final snapshot for diagnostics."""
    global _store_closed
    with _store_lock:
        _store_closed = True
        store = _store_instance
    if store is None:
        return {"remaining_threads": []}
    result = store.close(timeout=timeout)
    if result["remaining_threads"] or result.get("remaining_encoding_workers"):
        logger.warning("截图关闭超过等待预算，剩余后台操作：%s", result)
    return result


def save_screenshot(img: bytes, sub_folder=None) -> None:
    store = _store()
    if store is None:
        return
    store.submit(img, sub_folder)


def save_screenshot_frame(
    img,
    sub_folder=None,
    *,
    capture_ms=None,
    capture_owner=None,
    configuration_ref=None,
    capture_started_at=None,
    capture_wall_ns=None,
) -> None:
    """Submit RGB without waiting for the background encoder or filesystem."""
    store = _store()
    if store is None:
        return
    try:
        store.submit_frame(
            img,
            sub_folder,
            capture_ms=capture_ms,
            capture_owner=capture_owner,
            configuration_ref=configuration_ref,
            capture_started_at=capture_started_at,
            capture_wall_ns=capture_wall_ns,
        )
    except MemoryError as exc:
        store._report_error("截图快照内存不足，本帧不保存", str(exc))
        return


def get_log_by_time(target_time, time_range=1):
    folder = Path(get_path("@app/log"))
    time_points = [
        target_time - timedelta(hours=time_range),
        target_time,
        target_time + timedelta(hours=time_range),
    ]
    valid_suffixes = [tp.strftime("%Y-%m-%d_%H") for tp in time_points]
    matching_files = []
    for file_path in folder.iterdir():
        if file_path.is_file():
            try:
                if any(suffix in file_path.name for suffix in valid_suffixes):
                    matching_files.append(file_path)
                elif (
                    file_path.name == "runtime.log"
                    and (datetime.now() - target_time).total_seconds() <= 3600
                ):
                    matching_files.append(file_path)
            except Exception as e:
                logger.exception(f"Error processing file {file_path}: {e}")
    return matching_files
