"""共享 OCR 工作进程独立参与更新关闭，涵盖孤立模型与延迟启动。"""

import ctypes
import multiprocessing as mp
import os
import signal
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from arknights_mower.utils import ocr_service, ocr_shared
from arknights_mower.utils import software_update_worker as updater
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.device.owned import close_process


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not (result := predicate()):
        assert time.monotonic() < deadline, "fixture wait expired"
        time.sleep(0.01)
    return result


class NativeEngine:
    def __call__(self, image, **options):
        Path(os.environ["OCR_NATIVE_ENTERED"]).write_text(str(os.getpid()))
        # PyDLL 保持 GIL，模拟原生调用期间 EOF 线程无法立即执行。
        library = ctypes.PyDLL("kernel32" if sys.platform == "win32" else None)
        sleep = library.Sleep if sys.platform == "win32" else library.sleep
        sleep.argtypes = [ctypes.c_uint32]
        sleep.restype = None
        sleep(15000 if sys.platform == "win32" else 15)
        return None, None


def native_engine():
    return NativeEngine()


class EmptyEngine:
    def __call__(self, image, **options):
        return None, None


def empty_engine():
    return EmptyEngine()


def recording_engine():
    Path(os.environ["OCR_MODEL_CONSTRUCTED"]).write_text(str(os.getpid()))
    return EmptyEngine()


@contextmanager
def standalone_worker(directory, *, factory=empty_engine):
    state = directory / "updates"
    context = mp.get_context("spawn")
    parent, child = context.Pipe()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        token = "a" * 64
        process = context.Process(
            target=ocr_service._worker,
            args=(listener, child, token, directory, 10, factory, 256, state),
        )
        process.start()
        child.close()
        runtime.write_json(
            directory / "endpoint.json",
            {"version": 1, "port": listener.getsockname()[1], "token": token},
        )
        try:
            yield process, state
        finally:
            parent.close()
            child.close()
            close_process(process, os.getpid(), timeout=0.5)


def registered_instance(state):
    registration = runtime.RuntimeRegistration(
        "instance", directory=state, maintenance=False
    )
    try:
        wait_for(registration.shutdown_requested, timeout=20)
    finally:
        registration.close()


def test_orphan_native_worker_remains_in_update_shutdown_snapshot(
    tmp_path, monkeypatch
):
    state = tmp_path / "updates"
    entered = tmp_path / "native-entered"
    monkeypatch.setenv("OCR_NATIVE_ENTERED", str(entered))
    monkeypatch.setenv("MOWER_DATA_DIR", str(tmp_path))
    context = mp.get_context("spawn")
    application = context.Process(target=registered_instance, args=(state,))
    coordinator = context.Process(
        target=ocr_service.serve,
        args=(tmp_path,),
        kwargs={"factory": native_engine, "state_directory": state},
    )
    worker_pid = None
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        application.start()
        wait_for(lambda: runtime.instances(state))
        coordinator.start()
        wait_for(lambda: runtime.read_json(tmp_path / "endpoint.json"))
        request = pool.submit(
            ocr_shared.SharedOCREngine(directory=tmp_path),
            np.zeros((1, 1), np.uint8),
        )
        worker_pid = int(
            wait_for(lambda: entered.read_text() if entered.exists() else None)
        )
        coordinator.terminate()
        coordinator.join(3)
        assert not coordinator.is_alive()
        assert runtime.process_alive(worker_pid)
        with pytest.raises(RuntimeError):
            with runtime.supervision_lock(tmp_path / "model", timeout=0):
                pass

        worker = object.__new__(updater.Worker)
        worker.state = state
        worker.work = tmp_path / "job"
        worker.job = {"id": "fixture-update"}
        worker.report = Mock()
        # 保留真实登记扫描、进程活性与关闭流程，仅压缩 90 秒失败预算。
        clock = iter((0, 0, 1, 91))
        monkeypatch.setattr(
            updater,
            "time",
            SimpleNamespace(
                monotonic=lambda: next(clock),
                sleep=lambda seconds: application.join(3),
            ),
        )
        with pytest.raises(RuntimeError, match="90 秒"):
            worker.stop_instances()
        assert any(
            record["kind"] == "ocr-worker" and record["pid"] == worker_pid
            for record in worker.original
        )
        assert not application.is_alive()
        assert runtime.process_alive(worker_pid)
    finally:
        if worker_pid is not None and runtime.process_alive(worker_pid):
            os.kill(worker_pid, signal.SIGTERM)
        close_process(coordinator, os.getpid(), timeout=0.5)
        close_process(application, os.getpid(), timeout=0.5)
        pool.shutdown(wait=True)
        if "request" in locals():
            with pytest.raises((ConnectionError, OSError, TimeoutError)):
                request.result()
        # 取得真实模型锁确认原生进程已释放资源，不依赖孤儿 PID 的回收时机。
        with runtime.supervision_lock(tmp_path / "model", timeout=3):
            pass


def test_update_restart_excludes_coordinator_and_model_worker(tmp_path):
    worker = object.__new__(updater.Worker)
    worker.report = Mock()
    worker.job = {"background": False, "id": "fixture"}
    worker.work = tmp_path
    worker.root = tmp_path
    worker.command_for = Mock(return_value=["fixture-application"])
    records = [{"kind": "ocr-service"}, {"kind": "ocr-worker"}]
    with patch("subprocess.Popen") as launch:
        worker.restart(records, verify=False)
    launch.assert_not_called()


@pytest.mark.parametrize("gate", ["active-job", "submission-lock"])
def test_worker_start_after_update_snapshot_is_rejected_before_model_loading(
    tmp_path, monkeypatch, gate
):
    monkeypatch.delenv("MOWER_RESTART_JOB", raising=False)
    constructed = tmp_path / "model-constructed"
    monkeypatch.setenv("OCR_MODEL_CONSTRUCTED", str(constructed))
    state = tmp_path / "updates"
    if gate == "active-job":
        runtime.write_json(
            state / "active/owner.json", {"id": "fixture-update", "pid": os.getpid()}
        )
    # 模拟协调进程已死、更新已经拍下快照，但模型进程尚未完成启动。
    assert runtime.instances(state) == []
    admission = (
        runtime.submission_lock(state) if gate == "submission-lock" else nullcontext()
    )
    with (
        admission,
        standalone_worker(tmp_path, factory=recording_engine) as (process, state),
    ):
        with pytest.raises((OSError, RuntimeError)):
            ocr_shared.SharedOCREngine(directory=tmp_path, timeout=2)(
                np.zeros((1, 1), np.uint8)
            )
        process.join(3)
        assert not process.is_alive()
        assert not constructed.exists()
        assert runtime.instances(state) == []
        with runtime.supervision_lock(tmp_path / "model", timeout=0):
            pass


def test_worker_registration_responds_to_shutdown_without_coordinator(tmp_path):
    with standalone_worker(tmp_path) as (process, state):
        record = wait_for(lambda: runtime.instances(state))[0]
        assert record["kind"] == "ocr-worker"
        assert record["pid"] == process.pid
        runtime.write_json(state / "shutdown" / f"{record['id']}.json", {})
        process.join(3)
        assert not process.is_alive()
        assert runtime.instances(state) == []


def test_restarted_worker_may_start_for_matching_active_update(tmp_path, monkeypatch):
    monkeypatch.setenv("MOWER_RESTART_JOB", "fixture-update")
    state = tmp_path / "updates"
    runtime.write_json(
        state / "active/owner.json", {"id": "fixture-update", "pid": os.getpid()}
    )
    with standalone_worker(tmp_path) as (process, state):
        record = wait_for(lambda: runtime.instances(state))[0]
        assert record["kind"] == "ocr-worker"
        assert ocr_shared.SharedOCREngine(directory=tmp_path)(
            np.zeros((1, 1), np.uint8)
        ) == (None, None)
        assert process.is_alive()


@pytest.mark.parametrize("failure", [False, True])
def test_worker_registration_survives_until_process_exit(
    tmp_path, monkeypatch, failure
):
    observed = []
    registrations = []
    state = tmp_path / "updates"
    listener, control = Mock(), Mock()
    monkeypatch.setattr(ocr_service, "Thread", Mock())
    register = ocr_service._register

    def record_registration(*args):
        registration = register(*args)
        registrations.append(registration)
        return registration

    monkeypatch.setattr(ocr_service, "_register", record_registration)

    def exit_process(code):
        observed.append((code, runtime.instances(state)))
        raise SystemExit(code)

    monkeypatch.setattr(ocr_service.os, "_exit", exit_process)
    monkeypatch.setattr(
        ocr_service,
        "_serve",
        Mock(side_effect=ValueError("fixture") if failure else None),
    )
    try:
        with pytest.raises(SystemExit) as stopped:
            ocr_service._worker(
                listener, control, "token", tmp_path, 1, empty_engine, 256, state
            )
        assert stopped.value.code == int(failure)
        assert len(observed) == 1
        assert observed[0][0] == int(failure)
        assert [record["kind"] for record in observed[0][1]] == ["ocr-worker"]
        listener.close.assert_called_once()
        control.close.assert_called_once()
    finally:
        # 当前进程代替退出中的工作进程，需要关闭模拟登记的心跳线程。
        for registration in registrations:
            registration.close()


def test_dead_worker_scan_cleans_only_its_shutdown_request(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "process_alive", lambda pid: False)
    for kind in ("instance", "ocr-worker"):
        runtime.write_json(
            tmp_path / "instances" / f"{kind}.json", {"pid": 123, "kind": kind}
        )
        runtime.write_json(tmp_path / "shutdown" / f"{kind}.json", {})
    assert runtime.instances(tmp_path) == []
    assert not (tmp_path / "shutdown/ocr-worker.json").exists()
    assert (tmp_path / "shutdown/instance.json").exists()
