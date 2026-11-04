import json
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from arknights_mower.agent import agent
from arknights_mower.agent import navigation_process as worker
from arknights_mower.solvers import base_schedule, manual_tasks
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.tests import maa_copilot_tests as helpers
from arknights_mower.utils import config, path
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit

files = helpers.files
scheduler = helpers.scheduler
CANDIDATES = [{"text": "进入活动", "score": 0.9, "center": (100, 200)}]


@pytest.fixture
def stalled_model(monkeypatch):
    monkeypatch.setattr(
        agent,
        "build_llm",
        MagicMock(side_effect=AssertionError("model requests belong in the worker")),
    )
    state = SimpleNamespace(elapsed=0.0, cancelled=False, tick=lambda: None)
    process = MagicMock(pid=123)
    process.is_alive.side_effect = lambda: not state.cancelled
    process.kill.side_effect = lambda: setattr(state, "cancelled", True)

    def join(timeout):
        if not state.cancelled:
            state.elapsed = round(state.elapsed + timeout, 6)
            state.tick()

    process.join.side_effect = join
    channel = MagicMock()
    factory = MagicMock(return_value=(process, channel))
    monkeypatch.setattr(worker, "_start_worker", factory)
    monkeypatch.setattr(worker, "_unreaped", [])
    monkeypatch.setattr(
        worker, "time", SimpleNamespace(monotonic=lambda: state.elapsed)
    )
    return state, factory


@pytest.mark.parametrize("remaining", [45, 75, 150])
@pytest.mark.parametrize("manual", [False, True])
def test_copilot_model_wait_consumes_navigation_budget(
    scheduler, monkeypatch, stalled_model, remaining, manual
):
    state, factory = stalled_model
    start = datetime.now()

    class Clock(datetime):
        @classmethod
        def now(cls):
            return start + timedelta(seconds=state.elapsed)

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(manual_tasks, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "monotonic", lambda: state.elapsed)
    base_schedule.config.conf.ai_type = "deepseek"
    base_schedule.config.conf.ai_key = "navigation-test-key"
    scheduler.tasks[0].time = start + timedelta(seconds=remaining)
    scheduler.task = SimpleNamespace(type=None)
    pending = scheduler.tasks[0]
    nav = object.__new__(NavigationSolver)
    nav.name, nav.stage_meta = "1-7", {}
    base_schedule.NavigationSolver.return_value.run.side_effect = lambda _: bool(
        nav.rank_activity_candidates(CANDIDATES)
    )

    def start_when_allowed():
        assert remaining - state.elapsed > 30
        return True

    scheduler.MAA.start.side_effect = start_when_allowed
    scheduler.maa_plan_solver([], manual=manual, long_task="copilot")

    budget = min(60, remaining - 30)
    assert state.elapsed <= budget
    assert state.cancelled
    assert factory.call_args.args[3] <= budget
    factory.return_value[0].close.assert_called_once()
    factory.return_value[1].close.assert_called_once()
    scheduler.MAA.append_task.assert_called_once()
    scheduler.MAA.start.assert_called_once()
    assert scheduler.tasks == [pending]
    assert scheduler.maa_copilot_progress["next"] == 0
    assert scheduler.maa_copilot_progress["failed"] is False


@pytest.mark.parametrize("outcome", ["success", "network_error", "oversized"])
def test_model_worker_closes_client_and_disables_retries(monkeypatch, outcome):
    monkeypatch.setattr(config, "conf", Conf(ai_type="deepseek"))
    calls = []

    def handle(request):
        calls.append(request)
        if outcome == "network_error":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        content = "x" * 5000 if outcome == "oversized" else '{"indices":[1,0]}'
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-fixture",
                "object": "chat.completion",
                "created": 0,
                "model": "fixture",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handle))
    model_class = agent.ChatOpenAI

    def model_factory(**kwargs):
        assert kwargs["timeout"] == 5
        assert kwargs["max_retries"] == 0
        return model_class(**kwargs, http_client=client)

    monkeypatch.setattr(agent, "ChatOpenAI", model_factory)
    channel = MagicMock()
    settings = {
        key: getattr(config.conf, key)
        for key in ("ai_type", "ai_deepseek_model", "ai_model", "ai_base_url")
    }
    worker._model_worker(
        channel,
        settings,
        "transport-test-key",
        [{"role": "user", "content": "rank"}],
        5,
        {name: getattr(path, name) for name in worker._PATH_FIELDS},
    )
    response = json.loads(channel.send_bytes.call_args.args[0])
    assert ("text" in response) is (outcome == "success")
    assert len(calls) == 1
    assert client.is_closed
    channel.close.assert_called_once()


@pytest.mark.parametrize("stop", ["stop_maa", "stop_mower"])
def test_stop_during_model_wait_cancels_request_and_preserves_task(
    scheduler, monkeypatch, stalled_model, stop
):
    state, factory = stalled_model
    base_schedule.config.conf.ai_type = "deepseek"
    base_schedule.config.conf.ai_key = "navigation-test-key"
    state.tick = lambda: getattr(base_schedule.config, stop).set()
    nav = object.__new__(NavigationSolver)
    nav.name, nav.stage_meta = "1-7", {}
    base_schedule.NavigationSolver.return_value.run.side_effect = lambda _: bool(
        nav.rank_activity_candidates(CANDIDATES)
    )
    pending = scheduler.tasks[0]

    if stop == "stop_mower":
        with pytest.raises(MowerExit):
            scheduler.maa_plan_solver([])
        scheduler.device.exit_after_task_stop.assert_called_once()
    else:
        scheduler.maa_plan_solver([])
        assert scheduler.maa_copilot_progress["failed"] is False
    assert state.elapsed <= 0.1
    assert state.cancelled
    factory.return_value[0].close.assert_called_once()
    factory.return_value[1].close.assert_called_once()
    assert scheduler.tasks == [pending]
    scheduler.MAA.start.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()


@pytest.mark.parametrize(
    "outcome", ["success", "network_error", "invalid_json", "late"]
)
def test_worker_response_preserves_budget_checked_rule_fallback(monkeypatch, outcome):
    from arknights_mower.agent import rank_activity_entries as ranking
    from arknights_mower.utils.device.io_budget import device_io_budget

    monkeypatch.setattr(
        config, "conf", Conf(ai_type="deepseek", ai_key="offline-test-key")
    )
    monkeypatch.setattr(config, "stop_mower", threading.Event())
    monkeypatch.setattr(
        agent,
        "build_llm",
        MagicMock(side_effect=AssertionError("model requests belong in the worker")),
    )
    process = MagicMock(pid=123)
    process.is_alive.return_value = False
    channel = MagicMock()
    factory = MagicMock(return_value=(process, channel))
    monkeypatch.setattr(worker, "_start_worker", factory)
    state = SimpleNamespace(expired=False)

    def response(_):
        state.expired = outcome == "late"
        payload = {
            "text": "invalid JSON" if outcome == "invalid_json" else '{"indices":[1,0]}'
        }
        if outcome == "network_error":
            payload = {"error": "APITimeoutError"}
        return json.dumps(payload).encode()

    channel.recv_bytes.side_effect = response

    def remaining():
        if state.expired:
            raise InterruptedError("offline preemption")
        return 5

    if outcome == "late":
        with pytest.raises(InterruptedError), device_io_budget(remaining):
            ranking.rank_activity_entries_with_agent("1-7", {}, CANDIDATES * 2)
    else:
        with device_io_budget(remaining):
            result = ranking.rank_activity_entries_with_agent("1-7", {}, CANDIDATES * 2)
        assert result == ([1, 0] if outcome == "success" else [0, 1])
    factory.assert_called_once()
    process.close.assert_called_once()
    channel.close.assert_called_once()


def test_failed_worker_cleanup_blocks_replacement_until_reaped(monkeypatch):
    monkeypatch.setattr(config, "conf", Conf())
    monkeypatch.setattr(config, "stop_mower", threading.Event())
    process = MagicMock(pid=123)
    process.is_alive.return_value = True
    channel = MagicMock()
    monkeypatch.setattr(worker, "_unreaped", [])
    with pytest.raises(RuntimeError, match="工作进程"):
        worker._close_worker(process, channel, worker.os.getpid())
    channel.close.assert_not_called()
    factory = MagicMock()
    monkeypatch.setattr(worker, "_start_worker", factory)
    with pytest.raises(RuntimeError, match="工作进程"):
        worker.invoke_navigation_model("offline-test-key", [])
    factory.assert_not_called()
    assert len(worker._unreaped) == 1
    process.is_alive.return_value = False
    completed = MagicMock(pid=456)
    completed.is_alive.return_value = False
    result_channel = MagicMock()
    result_channel.recv_bytes.return_value = b'{"text":"ok"}'
    factory.return_value = (completed, result_channel)
    assert worker.invoke_navigation_model("offline-test-key", []).content == "ok"
    assert worker._unreaped == []


def test_failed_start_releases_shared_reply(monkeypatch):
    process = MagicMock(pid=None)
    process.start.side_effect = OSError("offline spawn failure")
    reply = MagicMock()
    monkeypatch.setattr(worker, "_ReplySlot", MagicMock(return_value=reply))
    context = SimpleNamespace(
        RawArray=MagicMock(return_value=bytearray(4004)),
        Process=MagicMock(return_value=process),
    )
    monkeypatch.setattr(
        worker.multiprocessing, "get_context", MagicMock(return_value=context)
    )
    with pytest.raises(OSError, match="spawn failure"):
        worker._start_worker({}, "offline-test-key", [], 1)
    process.close.assert_called_once()
    reply.close.assert_called_once()


@pytest.mark.parametrize("size", [1, 512, 4000])
def test_shared_reply_accepts_bounded_payload_without_pipe_backpressure(size):
    reply = worker._ReplySlot(worker.multiprocessing.RawArray("B", 4004))
    payload = b"x" * size
    reply.send_bytes(payload)
    assert reply.recv_bytes(4000) == payload
    reply.close()
    assert reply.closed


def test_unfinished_shared_reply_is_not_returned():
    buffer = worker.multiprocessing.RawArray("B", 4004)
    buffer[4:7] = b"bad"
    reply = worker._ReplySlot(buffer)
    with pytest.raises(EOFError):
        reply.recv_bytes(4000)
    reply.close()


def test_oversized_shared_reply_does_not_publish_length():
    reply = worker._ReplySlot(worker.multiprocessing.RawArray("B", 4004))
    with pytest.raises(ValueError):
        reply.send_bytes(b"x" * 4001)
    with pytest.raises(EOFError):
        reply.recv_bytes(4000)
    reply.close()


def test_closed_worker_releases_its_retained_reply():
    process = worker.multiprocessing.get_context("spawn").Process()
    process.close()
    reply = worker._ReplySlot(worker.multiprocessing.RawArray("B", 4004))
    worker._close_worker(process, reply, worker.os.getpid())
    assert reply.closed
