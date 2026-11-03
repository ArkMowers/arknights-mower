import asyncio
import threading
from contextlib import nullcontext
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from arknights_mower.agent import agent
from arknights_mower.agent import rank_activity_entries as ranking
from arknights_mower.solvers import base_schedule, manual_tasks
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.tests import maa_copilot_tests as helpers
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.io_budget import device_io_budget

files = helpers.files
scheduler = helpers.scheduler
CANDIDATES = [{"text": "进入活动", "score": 0.9, "center": (100, 200)}]


@pytest.fixture
def stalled_model(monkeypatch):
    state = SimpleNamespace(
        elapsed=0.0, cancelled=False, started=False, tick=lambda: None
    )
    response = SimpleNamespace(content='{"indices":[0]}')

    def sync_invoke(_):
        state.started = True
        state.elapsed += 90
        return response

    async def async_invoke(_):
        state.started = True
        try:
            await asyncio.Event().wait()
        finally:
            state.cancelled = True

    model = SimpleNamespace(invoke=sync_invoke, ainvoke=async_invoke)
    factory = MagicMock(return_value=model)
    monkeypatch.setattr(agent, "build_llm", factory)
    monkeypatch.setattr(
        ranking,
        "time",
        SimpleNamespace(
            monotonic=lambda: state.elapsed, perf_counter=lambda: state.elapsed
        ),
    )
    wait = asyncio.wait

    async def advance(tasks, *, timeout):
        await asyncio.sleep(0)
        state.elapsed = round(state.elapsed + timeout, 6)
        state.tick()
        return await wait(tasks, timeout=0)

    monkeypatch.setattr(asyncio, "wait", advance)
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

    if manual and remaining > 90:
        with pytest.raises(TimeoutError, match="导航超时"):
            scheduler.maa_plan_solver([], manual=manual, long_task="copilot")
    else:
        scheduler.maa_plan_solver([], manual=manual, long_task="copilot")

    budget = min(60, remaining - 30)
    assert state.elapsed <= budget
    assert state.cancelled
    assert factory.call_args.kwargs["timeout"] <= budget
    assert factory.call_args.kwargs["max_retries"] == 0
    assert factory.call_args.kwargs["http_async_client"].is_closed
    scheduler.MAA.append_task.assert_not_called()
    scheduler.MAA.start.assert_not_called()
    assert scheduler.tasks == [pending]
    assert scheduler.maa_copilot_progress["next"] == 0
    assert scheduler.maa_copilot_progress["failed"] is (remaining > 90)


@pytest.mark.parametrize(
    "outcome",
    ["success", "network_error", "invalid_json", "stop", "deadline", "late_success"],
)
def test_real_model_async_transport_is_closed_without_retries(monkeypatch, outcome):
    monkeypatch.setattr(config, "stop_mower", threading.Event())
    monkeypatch.setattr(
        config, "conf", Conf(ai_type="deepseek", ai_key="transport-test-key")
    )
    state = SimpleNamespace(expired=False, cancelled=False, requests=0)

    async def handle(request):
        state.requests += 1
        if outcome == "network_error":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        if outcome in {"stop", "deadline"}:
            if outcome == "stop":
                config.stop_mower.set()
            else:
                state.expired = True
            try:
                await asyncio.Event().wait()
            finally:
                state.cancelled = True
        if outcome == "late_success":
            state.expired = True
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
                        "message": {
                            "role": "assistant",
                            "content": "invalid JSON"
                            if outcome == "invalid_json"
                            else '{"indices":[1,0]}',
                        },
                    }
                ],
            },
        )

    clients = []

    def client_factory(**kwargs):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(ranking, "httpx", SimpleNamespace(AsyncClient=client_factory))

    def remaining():
        if state.expired:
            raise InterruptedError("fixture deadline")
        return 5

    expected = (
        pytest.raises(MowerExit if outcome == "stop" else InterruptedError)
        if outcome in {"stop", "deadline", "late_success"}
        else nullcontext()
    )
    with expected, device_io_budget(remaining):
        result = ranking.rank_activity_entries_with_agent("1-7", {}, CANDIDATES * 2)
        if outcome not in {"stop", "deadline", "late_success"}:
            assert result == ([1, 0] if outcome == "success" else [0, 1])
    assert state.requests == 1
    assert all(client.is_closed for client in clients)
    assert state.cancelled is (outcome in {"stop", "deadline"})


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
    assert factory.call_args.kwargs["http_async_client"].is_closed
    assert scheduler.tasks == [pending]
    scheduler.MAA.start.assert_not_called()
    scheduler.MAA.append_task.assert_not_called()
