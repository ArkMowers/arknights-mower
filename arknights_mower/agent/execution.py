"""Confirmed tool execution, evidence and cooperative cancellation for stored chat."""

import copy
import hashlib
import inspect
import json
import time
from contextlib import contextmanager
from datetime import datetime
from threading import Condition, RLock
from uuid import uuid4

from arknights_mower.utils.ai_history import MAX_TRACE_CHARS, HistoryError

WRITE_TOOLS = {"add_mastery_plan", "set_route", "retry_plan_tool", "submit_issue"}
READ_TOOLS = {
    "get_faq",
    "inspect_feedback",
    "call_db",
    "extract_stack_paths",
    "get_source_snippet",
    "analyze_missed_order",
    "list_plans",
    "get_route_info",
    "get_riic_context",
    "get_riic_knowledge",
    "try_riic_plan",
}
APPROVAL_SECONDS = 180
MAX_CALLS = 24
MAX_ARGUMENT_CHARS = 8000
MAX_RESULT_CHARS = 32000
MAX_ACTIVE_RUNS = 8
MAX_OBSERVERS = 4
_registry_lock = RLock()
_running = {}


class ModelCallError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class ChatTurnError(RuntimeError):
    def __init__(self, message, turn):
        super().__init__(message)
        self.turn_status = turn.status
        self.code = turn.failure.get(
            "code",
            "execution_stopped" if turn.status == "cancelled" else "execution_error",
        )


class ExecutionStopped(Exception):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def legacy_tool(name, args, functions):
    if name in WRITE_TOOLS:
        return "未执行：此操作需要在支持操作确认的会话中核对具体内容后确认。"
    if name not in READ_TOOLS or name not in functions:
        return f"未知工具: {name}"
    return functions[name](**args)


def control(store, conversation_id, turn_id, action, approval_id=None, digest=None):
    # Ownership is checked even if the caller happens to know another turn ID.
    store.read(conversation_id)
    with _registry_lock:
        run = _running.get((str(store.path), conversation_id, turn_id))
    if run is None or run.store.profile_id != store.profile_id:
        raise HistoryError("本轮已结束或连接已重启，请刷新历史查看结果")
    return run.control(action, approval_id, digest)


def observe(store, conversation_id, turn_id=None):
    saved = store.read(conversation_id)
    if turn_id is not None and (type(turn_id) is not int or turn_id <= 0):
        raise HistoryError("轮次标识无效", 400)
    if not saved["turns"]:
        raise HistoryError("会话暂无执行记录", 404)
    if turn_id is None:
        turn_id = saved["turns"][-1]["id"]
    with _registry_lock:
        run = _running.get((str(store.path), conversation_id, turn_id))
        if run is not None and run.store.profile_id != store.profile_id:
            raise HistoryError("会话不属于当前配置档案", 404)
    if run is None:
        saved = store.read(conversation_id)
        turn = next((item for item in saved["turns"] if item["id"] == turn_id), None)
        if turn is None:
            raise HistoryError("此轮记录已被清理", 404)
        if saved["busy"] and saved["turns"][-1]["id"] == turn_id:
            raise HistoryError("本轮正在准备，请重新连接查看进度")
        yield {
            "snapshot": {
                "conversation_id": conversation_id,
                "turn_id": turn["id"],
                "assistant": turn["assistant"],
                "draft": "",
                "events": turn["events"],
                "mode": turn["mode"],
                "status": turn["status"],
                "failure": turn["failure"],
            }
        }
        return
    with run.condition:
        if run.observers >= MAX_OBSERVERS:
            raise HistoryError("查看本轮进度的连接过多，请关闭其他会话窗口")
        run.observers += 1
    try:
        revision = -1
        while True:
            with run.condition:
                run.condition.wait_for(lambda: run.revision != revision, timeout=15)
                revision = run.revision
                snapshot = copy.deepcopy(run.snapshot)
            yield {"snapshot": snapshot}
            if snapshot["status"] != "running":
                return
    finally:
        with run.condition:
            run.observers -= 1


class Execution:
    def __init__(self, store, turn, send):
        self.store, self.turn, self._send = store, turn, send
        self.condition = Condition()
        self.stopped = False
        self.pending = None
        self.calls = 0
        self.draft = ""
        self.observers = 0
        self.revision = 0
        self.snapshot = {
            "conversation_id": turn.conversation_id,
            "turn_id": turn.turn_id,
            "context": turn.context_info,
            "mode": turn.mode,
            "assistant": "",
            "draft": "",
            "events": [],
            "status": "running",
        }

    def send(self, frame):
        with self.condition:
            event = frame.get("event", {})
            kind = event.get("type")
            if kind == "answer_delta":
                self.snapshot["draft"] = (self.snapshot["draft"] + event["text"])[
                    :32768
                ]
            elif kind in {"answer_reset", "model"} or "reply" in frame:
                self.snapshot["draft"] = ""
            if kind in {"tool", "approval"}:
                self.snapshot["events"] = copy.deepcopy(self.turn.events)
            if "reply" in frame:
                self.snapshot["assistant"] = self.turn.reply
            self.revision += 1
            self.condition.notify_all()
        self._send(frame)

    def finish(self, error=None):
        # Publish completion only after the history transaction has finished.
        with self.condition:
            self.snapshot.update(
                assistant=self.turn.reply,
                draft="",
                status="complete"
                if self.turn.complete and error is None
                else self.turn.status,
                error=error[:2000] if error else None,
                failure=copy.deepcopy(self.turn.failure),
            )
            self.revision += 1
            self.condition.notify_all()

    @contextmanager
    def registered(self):
        key = (str(self.store.path), self.turn.conversation_id, self.turn.turn_id)
        with _registry_lock:
            if sum(item[0] == key[0] for item in _running) >= MAX_ACTIVE_RUNS:
                raise HistoryError("AI 正在处理的会话过多，请等待已有请求结束")
            _running[key] = self
        try:
            yield self
        finally:
            with _registry_lock:
                _running.pop(key, None)
            with self.condition:
                self.pending = None
                self.condition.notify_all()

    def check(self):
        if self.stopped:
            raise ExecutionStopped(
                "已停止后续调用；已开始的操作可能已执行，请查看执行记录。"
            )

    def control(self, action, approval_id=None, digest=None):
        if not isinstance(action, str):
            raise HistoryError("控制操作无效", 400)
        with self.condition:
            if action == "stop":
                self.stopped = True
            elif action in {"approve", "reject"}:
                pending = self.pending
                if (
                    self.stopped
                    or not pending
                    or pending["id"] != approval_id
                    or pending["digest"] != digest
                    or pending["decision"] is not None
                    or time.monotonic() >= pending["deadline"]
                ):
                    raise HistoryError("确认已失效，请核对当前待确认操作")
                pending["decision"] = action == "approve"
            else:
                raise HistoryError("控制操作无效", 400)
            self.condition.notify_all()
        return {"ok": True}

    def emit(self, event, *, persist=True):
        event = dict(event, turn_id=self.turn.turn_id)
        if persist:
            identifier = event.get("id")
            if identifier:
                self.turn.events[:] = [
                    item for item in self.turn.events if item.get("id") != identifier
                ]
            self.turn.events.append(event)
            while (
                len(self.turn.events) > 32
                or len(canonical(self.turn.events))
                + len(canonical(self.turn.operations))
                > MAX_TRACE_CHARS - 1024
            ):
                if len(self.turn.events) <= 1:
                    raise HistoryError("本轮执行记录达到上限，请核实结果后开始新对话")
                self.turn.events.pop(0)
            self.store.save_progress(self.turn)
        self.send({"event": event})

    def approve(self, operation):
        pending = {
            "id": uuid4().hex,
            "digest": operation["digest"],
            "decision": None,
            "deadline": time.monotonic() + APPROVAL_SECONDS,
        }
        with self.condition:
            self.pending = pending
        try:
            self.emit(
                {
                    "type": "approval",
                    "id": operation["id"],
                    "approval_id": pending["id"],
                    "digest": pending["digest"],
                    "name": operation["name"],
                    "arguments": operation["arguments"],
                    "preview": operation["preview"],
                    "status": "awaiting_approval",
                    "expires_in": APPROVAL_SECONDS,
                    "expires_at": time.time() + APPROVAL_SECONDS,
                }
            )
            with self.condition:
                self.condition.wait_for(
                    lambda: self.stopped or pending["decision"] is not None,
                    timeout=max(0, pending["deadline"] - time.monotonic()),
                )
                self.check()
                return (
                    pending["decision"] is True
                    and time.monotonic() < pending["deadline"]
                )
        finally:
            with self.condition:
                self.pending = None

    def execute(self, name, args, functions, labels, *, raw=False):
        self.check()
        self.calls += 1
        if self.calls > MAX_CALLS:
            raise HistoryError("本轮工具调用达到上限，请根据已有结果缩小问题范围")
        if name not in READ_TOOLS | WRITE_TOOLS or name not in functions:
            return f"未知工具: {name}"
        if not isinstance(args, dict) or len(canonical(args)) > MAX_ARGUMENT_CHARS:
            return "未执行：工具参数过长或格式无效"
        try:
            signature_owner = functions[name]
            if name == "submit_issue":
                from arknights_mower.agent.tools.submit_issue import submit_issue

                signature_owner = submit_issue
            bound = inspect.signature(signature_owner).bind(**args)
            bound.apply_defaults()
        except TypeError as exc:
            return f"未执行：工具参数无效（{exc}）"
        # Named defaults make equivalent model calls share the same retry identity.
        normalized = dict(bound.arguments)
        if set(normalized) == {"kwargs"}:
            normalized = normalized["kwargs"]
        if name == "set_route":
            try:
                normalized["supports_json"] = canonical(
                    json.loads(normalized["supports_json"])
                )
            except (ValueError, KeyError, TypeError):
                return "未执行：路线 JSON 无效"
        if name == "retry_plan_tool":
            normalized = {"char_id": "", "skill_index": 0}
        identifier = f"T{self.turn.turn_id}-{self.calls}"
        digest = hashlib.sha256(canonical([name, normalized]).encode()).hexdigest()
        operation = None
        if name in WRITE_TOOLS:
            previous = next(
                (item for item in self.turn.operations if item["digest"] == digest),
                None,
            )
            if previous and previous["status"] not in {"proposed", "not_executed"}:
                result = f"未重复执行：此前操作状态为 {previous['status']}。{previous.get('result', '结果尚未确认，请核实实际状态。')}"
                self.emit(
                    {
                        "type": "tool",
                        "id": identifier,
                        "name": name,
                        "status": "not_repeated",
                        "result": result,
                        "previous_id": previous["id"],
                    }
                )
                return result
            if previous:
                self.turn.operations.remove(previous)
            if len(self.turn.operations) >= 12:
                raise HistoryError(
                    "本轮写入操作记录达到上限，请核实已有操作后开始新对话"
                )
            from arknights_mower.agent.operation_preview import prepare_operation

            preview, perform = prepare_operation(name, normalized, functions[name])
            operation = {
                "id": identifier,
                "digest": digest,
                "name": name,
                "arguments": normalized,
                "preview": preview,
                "status": "proposed",
            }
            self.turn.operations.append(operation)
            self.store.save_progress(self.turn)
            try:
                approved = self.approve(operation)
            except ExecutionStopped:
                operation.update(status="not_executed", result="已停止，未执行此操作。")
                self.emit(
                    {
                        "type": "tool",
                        **{
                            key: operation[key]
                            for key in ("id", "name", "status", "result")
                        },
                    }
                )
                raise
            if not approved:
                operation["status"] = "not_executed"
                operation["result"] = "用户未确认或确认已过期，未执行。"
                self.emit(
                    {
                        "type": "tool",
                        **{
                            key: operation[key]
                            for key in ("id", "name", "status", "result")
                        },
                    }
                )
                return operation["result"]
            self.check()
            operation["status"] = "attempted"
            self.store.save_progress(self.turn)
        self.emit(
            {
                "type": "tool",
                "id": identifier,
                "name": name,
                "label": labels.get(name, name),
                "status": "running",
                "arguments": normalized,
                "observed_at": datetime.now().astimezone().isoformat(),
            }
        )
        try:
            self.check()
            result = perform() if operation else functions[name](**args)
            text = result if isinstance(result, str) else canonical(result)
            status = result_status(name, text)
        except ExecutionStopped:
            raise
        except Exception as exc:
            text = f"执行未能确认：{exc}"
            status = "unknown" if operation else "failed"
        original_text = text
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + "\n[工具结果已截断，不能据此判断完整覆盖]"
        if operation:
            operation.update(status=status, result=text[:2000])
        source = {
            "call_db": "本地历史记录，查询范围见参数",
            "get_source_snippet": "当前安装的源代码，非故障发生时版本",
            "get_faq": "当前内置使用说明",
            "analyze_missed_order": "历史订单与任务记录的分析",
            "inspect_feedback": "本次收集的原始记录与源码引用",
        }.get(name, "本次工具读取或操作结果，后续状态可能变化")
        observed_at = datetime.now().astimezone().isoformat()
        self.emit(
            {
                "type": "tool",
                "id": identifier,
                "name": name,
                "label": labels.get(name, name),
                "status": status,
                "arguments": normalized,
                "result": text[:3000],
                "truncated": len(text) > 3000,
                "source": source,
                "observed_at": observed_at,
            }
        )
        self.check()
        return (
            original_text
            if raw
            else f"[证据 {identifier}] 状态：{status}；观测时间：{observed_at}；{source}\n{text}"
        )


def result_status(name, text):
    if name == "submit_issue":
        return "accepted" if text == "邮件发送成功！" else "unknown"
    if name in WRITE_TOOLS:
        return (
            "verified"
            if text.startswith(("已添加专精计划", "已保存", "已核对重置"))
            else "failed"
        )
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        value = None
    if isinstance(value, dict) and (
        value.get("error")
        or value.get("valid") is False
        or str(value.get("source_code", "")).startswith("读取失败")
    ):
        return "failed"
    if text.startswith(("SQL 执行失败", "读取失败", "未执行", "未知工具")):
        return "failed"
    return "succeeded"
