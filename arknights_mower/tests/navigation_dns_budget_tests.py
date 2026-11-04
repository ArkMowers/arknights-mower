import asyncio
import multiprocessing
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from arknights_mower.agent import agent, navigation_process
from arknights_mower.agent import rank_activity_entries as ranking
from arknights_mower.tests.fixtures.navigation.dns_worker import slow_dns
from arknights_mower.utils import config, path
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.io_budget import device_io_budget


@pytest.mark.parametrize("stop", [False, True])
def test_slow_dns_does_not_extend_model_deadline_or_stop(
    monkeypatch, record_property, stop
):
    monkeypatch.setattr(config, "stop_mower", threading.Event())

    def resolve(*args, **kwargs):
        if stop:
            config.stop_mower.set()
        time.sleep(1.65)
        return []

    async def invoke(_):
        await asyncio.get_running_loop().getaddrinfo("offline.invalid", 443)
        return SimpleNamespace(content='{"indices":[0]}')

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(
        agent, "build_llm", lambda *args, **kwargs: SimpleNamespace(ainvoke=invoke)
    )
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=slow_dns, args=(child,), daemon=True)
    process.start()
    child.close()
    pid = process.pid
    try:
        assert parent.poll(10), "offline DNS worker did not start"
        assert parent.recv_bytes() == b"dns-started"

        def started(*args):
            if stop:
                config.stop_mower.set()
            return process, parent

        monkeypatch.setattr(navigation_process, "_start_worker", started)
        start = time.monotonic()
        deadline = start + (5 if stop else 0.5)

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise TimeoutError("offline deadline")
            return seconds

        with (
            pytest.raises(MowerExit if stop else TimeoutError),
            device_io_budget(remaining),
        ):
            ranking._invoke_with_budget("offline-test-key", [])
        elapsed = time.monotonic() - start
        record_property("dns_wait_return_seconds", elapsed)
        assert elapsed < 1.1, f"DNS cleanup retained control for {elapsed:.2f}s"
        assert not any(p.pid == pid for p in multiprocessing.active_children())
        assert parent.closed
    finally:
        if not process._closed:
            if process.is_alive():
                process.kill()
            process.join(timeout=1)
            process.close()
        parent.close()


def test_spawned_production_worker_returns_bounded_error_without_network(
    monkeypatch, tmp_path
):
    from arknights_mower.utils.config.conf import Conf

    monkeypatch.setattr(config, "conf", Conf())
    monkeypatch.setattr(config, "stop_mower", threading.Event())
    monkeypatch.setattr(path, "_data_dir", tmp_path)
    monkeypatch.setattr(path, "global_space", "worker")
    current = tmp_path / "worker/config"
    current.mkdir(parents=True)
    (current / "conf.yml").write_text("{}", encoding="utf-8")
    for name in ("plan.json", "rescue_plan.json"):
        (current / name).write_text('{"plan1": {}}', encoding="utf-8")
    original = {p.pid for p in multiprocessing.active_children()}
    start = time.monotonic()

    def remaining():
        seconds = 2 - (time.monotonic() - start)
        if seconds <= 0:
            raise TimeoutError("offline startup deadline")
        return seconds

    with pytest.raises((RuntimeError, TimeoutError)), device_io_budget(remaining):
        ranking._invoke_with_budget("offline-test-key", [])
    assert time.monotonic() - start < 3
    assert {p.pid for p in multiprocessing.active_children()} == original
