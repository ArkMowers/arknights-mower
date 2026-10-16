"""共享 OCR 的真实本机传输、并发准入和自有进程生命周期。"""

import multiprocessing as mp
import os
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier, Event, Thread

import numpy as np
import pytest

from arknights_mower.utils import ocr_service, ocr_shared, rapidocr
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.device.owned import close_process


class RecordingEngine:
    def __init__(self):
        self.calls = 0

    def __call__(self, image, **options):
        self.calls += 1
        marker = int(image.flat[0])
        if marker == 253:
            raise ValueError("fixture inference failure")
        if marker == 254:
            os._exit(12)
        if marker == 255:
            time.sleep(30)
        time.sleep(0.01)
        return [[os.getpid(), marker, self.calls, image.shape, options]], None


def fake_engine():
    return RecordingEngine()


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while not (result := predicate()):
        assert time.monotonic() < deadline, "fixture wait expired"
        time.sleep(0.01)
    return result


@contextmanager
def service(directory, *, idle=3, factory=fake_engine, max_requests=256):
    context = mp.get_context("spawn")
    process = context.Process(
        target=ocr_service.serve,
        args=(directory,),
        kwargs={
            "idle_timeout": idle,
            "factory": factory,
            "state_directory": directory / "updates",
            "max_requests": max_requests,
        },
    )
    process.start()
    try:
        wait_for(lambda: runtime.read_json(directory / "endpoint.json"))
        yield process
    finally:
        # 正常空闲退出覆盖整个服务；测试失败时先杀自有协调进程，EOF 清理模型。
        process.join(idle + 3)
        close_process(process, os.getpid(), timeout=0.5)


def test_eighteen_clients_share_one_model_and_preserve_independent_results(tmp_path):
    with service(tmp_path):
        barrier = Barrier(18)

        def identify(index):
            client = ocr_shared.SharedOCREngine(directory=tmp_path)
            barrier.wait(timeout=5)
            # 非连续灰度图也必须原样传输。
            image = np.full((8, 16), index, np.uint8)[:, ::2]
            return client(image, use_det=False, text_score=index / 20)[0][0]

        with ThreadPoolExecutor(max_workers=18) as pool:
            results = list(pool.map(identify, range(18)))
        assert len({row[0] for row in results}) == 1
        assert [row[1] for row in results] == list(range(18))
        assert sorted(row[2] for row in results) == list(range(1, 19))
        assert all(row[3] == [8, 8] for row in results)
        assert [row[4]["text_score"] for row in results] == [i / 20 for i in range(18)]
        assert all(row[4]["box_thresh"] == 0.5 for row in results)


def test_waiting_client_sends_no_image_before_admission(tmp_path, monkeypatch):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    runtime.write_json(
        tmp_path / "endpoint.json",
        {
            "version": 1,
            "port": listener.getsockname()[1],
            "token": "a" * 64,
        },
    )
    seen = Event()
    release = Event()
    outcomes = []

    def inspect():
        with listener, listener.accept()[0] as channel:
            header = ocr_shared.read_json(channel, time.monotonic() + 3)
            assert header["shape"] == [1080, 1920, 3]
            channel.settimeout(0.15)
            try:
                outcomes.append(channel.recv(1))
            except TimeoutError:
                outcomes.append("no image")
            seen.set()
            assert release.wait(3)

    worker = Thread(target=inspect)
    worker.start()
    client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client, np.zeros((1080, 1920, 3), np.uint8))
        try:
            assert seen.wait(2)
            assert outcomes == ["no image"]
        finally:
            release.set()
        with pytest.raises(ConnectionError):
            future.result(timeout=3)
    worker.join(3)
    assert not worker.is_alive()


def test_authentication_and_input_bounds_do_not_construct_or_poison_model(tmp_path):
    with service(tmp_path):
        endpoint = runtime.read_json(tmp_path / "endpoint.json")
        for extra in (
            {"token": "wrong"},
            {"shape": [8192, 8192, 3]},
            {"options": {"use_det": "yes"}},
        ):
            with socket.create_connection(("127.0.0.1", endpoint["port"])) as channel:
                deadline = time.monotonic() + 2
                header = dict(
                    version=1,
                    token=endpoint["token"],
                    shape=[1, 1],
                    options={},
                    deadline=deadline,
                )
                header.update(extra)
                ocr_shared.send_json(channel, header, deadline)
                assert ocr_shared.read_json(channel, deadline)["status"] == "error"
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        row = client(np.ones((1, 1), np.uint8))[0][0]
        assert row[2] == 1
        with pytest.raises(ValueError):
            client(np.ones((1, 1), np.float32))


def test_request_failure_is_not_replayed_and_next_request_remains_usable(tmp_path):
    with service(tmp_path):
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        with pytest.raises(RuntimeError, match="fixture inference failure"):
            client(np.full((1, 1), 253, np.uint8))
        assert client(np.zeros((1, 1), np.uint8))[0][0][2] == 2


@pytest.mark.parametrize("marker", [254, 255])
def test_native_exit_or_timeout_ends_owned_worker_without_fallback(
    tmp_path, monkeypatch, marker
):
    monkeypatch.setattr(
        rapidocr, "create_engine", lambda *a, **k: pytest.fail("client loaded a model")
    )
    with service(tmp_path, idle=1) as process:
        endpoint = runtime.read_json(tmp_path / "endpoint.json")
        client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=1.5)
        started = time.monotonic()
        with pytest.raises((ConnectionError, TimeoutError)):
            client(np.full((1, 1), marker, np.uint8))
        process.join(4)
        assert not process.is_alive()
        assert time.monotonic() - started < 5
        assert not runtime.process_alive(endpoint["worker_pid"])
        assert not (tmp_path / "endpoint.json").exists()


def test_idle_exit_releases_model_and_directory_can_be_reused(tmp_path):
    with service(tmp_path, idle=0.3) as process:
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        first = client(np.zeros((1, 1), np.uint8))[0][0][0]
        process.join(3)
        assert not process.is_alive()
        assert not runtime.process_alive(first)
    with service(tmp_path, idle=0.3):
        second = client(np.ones((1, 1), np.uint8))[0][0]
        assert second[0] != first
        assert second[2] == 1


def test_concurrent_cold_start_constructs_one_service(tmp_path, monkeypatch):
    processes = []

    def start(directory):
        p = mp.get_context("spawn").Process(
            target=ocr_service.serve,
            args=(directory,),
            kwargs={
                "idle_timeout": 0.5,
                "factory": fake_engine,
                "state_directory": directory / "updates",
            },
        )
        p.start()
        processes.append(p)
        return p

    # multiprocessing.Process 对应 Popen.poll 的轻量适配。
    class Started:
        def __init__(self, process):
            self.process = process

        def poll(self):
            return self.process.exitcode

    monkeypatch.setattr(
        ocr_shared, "start_service", lambda directory: Started(start(directory))
    )
    try:
        with ThreadPoolExecutor(max_workers=18) as pool:
            results = list(
                pool.map(
                    lambda i: ocr_shared.SharedOCREngine(directory=tmp_path)(
                        np.full((1, 1), i, np.uint8)
                    ),
                    range(18),
                )
            )
        assert len(processes) == 1
        assert len({r[0][0][0] for r in results}) == 1
    finally:
        for p in processes:
            p.join(4)
            close_process(p, os.getpid(), timeout=0.5)


def test_initialize_ocr_is_lightweight_and_does_not_load_local_model(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(rapidocr, "engine", None)
    monkeypatch.setattr(ocr_shared, "shared_directory", lambda: tmp_path)
    monkeypatch.setattr(
        rapidocr, "create_engine", lambda *a, **k: pytest.fail("loaded model")
    )
    rapidocr.initialize_ocr()
    assert isinstance(rapidocr.engine, ocr_shared.SharedOCREngine)
    assert not list(tmp_path.iterdir())


def test_real_ocr_through_service_matches_local_engine(tmp_path):
    from arknights_mower.solvers import furniture
    from arknights_mower.utils.image import bytes2img

    local = rapidocr.create_engine(threads=2)
    with service(tmp_path, factory=ocr_service._engine):
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        source = Path(__file__).parent / "fixtures/furniture/stock_3_2.png"
        fixture = tmp_path / "中文目录" / "家具截图.png"
        fixture.parent.mkdir()
        fixture.write_bytes(source.read_bytes())
        image = bytes2img(fixture.read_bytes())
        # 直接比较原图局部文字的坐标、文本和分数；耗时独立统计。
        crop = furniture.crop_relative(image, furniture.NAME_SCOPE)
        shared_result = client(crop, use_cls=False)[0]
        local_result = local(crop, use_cls=False)[0]
        assert shared_result == local_result
        assert shared_result and "洗衣间地毯" in "".join(
            row[1] for row in shared_result
        )


def test_frozen_command_and_early_entry_do_not_launch_gui(monkeypatch, tmp_path):
    import builtins
    import runpy
    from types import ModuleType
    from unittest.mock import Mock

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command = ocr_shared.service_command(tmp_path)
    assert command == [sys.executable, "--shared-ocr-service", str(tmp_path)]
    entry = Path(__file__).parents[2] / "webview_ui.py"
    stub = ModuleType("arknights_mower.utils.ocr_service")
    stub.main = Mock()
    monkeypatch.setitem(sys.modules, stub.__name__, stub)
    monkeypatch.setattr(sys, "argv", [str(entry), *command[1:]])
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in ("webview", "flask", "arknights_mower.utils.config"):
            pytest.fail(f"service imported application UI: {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(entry), run_name="__main__")
    assert stopped.value.code is None
    stub.main.assert_called_once_with()


def test_update_shutdown_releases_worker_before_service_registration(tmp_path):
    with service(tmp_path, idle=10) as process:
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        pid = client(np.zeros((1, 1), np.uint8))[0][0][0]
        records = runtime.instances(tmp_path / "updates")
        assert len(records) == 1 and records[0]["kind"] == "ocr-service"
        record = records[0]
        runtime.write_json(tmp_path / "updates/shutdown" / f"{record['id']}.json", {})
        process.join(4)
        assert not process.is_alive()
        assert not runtime.process_alive(pid)
        assert runtime.instances(tmp_path / "updates") == []
        with runtime.supervision_lock(record["supervision_directory"], timeout=0):
            pass


def test_active_update_prevents_unrelated_service_start(tmp_path):
    state = tmp_path / "updates"
    runtime.write_json(
        state / "active/owner.json", {"pid": os.getpid(), "id": "fixture-update"}
    )
    with pytest.raises(RuntimeError, match="更新或进程操作"):
        ocr_service.serve(tmp_path, state_directory=state)
    assert not (tmp_path / "endpoint.json").exists()
    assert runtime.instances(state) == []


def test_model_lock_rejects_replacement_while_old_worker_ownership_remains(tmp_path):
    # 模拟协调进程消失、但旧原生工作进程尚未退出。
    with runtime.supervision_lock(tmp_path / "model", timeout=0):
        with service(tmp_path, idle=0.5) as process:
            client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=1)
            with pytest.raises((ConnectionError, TimeoutError)):
                client(np.zeros((1, 1), np.uint8))
            process.join(3)
            assert not process.is_alive()


def test_update_restart_does_not_launch_on_demand_service(tmp_path):
    from unittest.mock import Mock, patch

    from arknights_mower.utils.software_update_worker import Worker

    worker = object.__new__(Worker)
    worker.report = Mock()
    worker.job = {"background": False, "id": "fixture"}
    worker.work = tmp_path
    with patch("subprocess.Popen") as launch:
        worker.restart([{"kind": "ocr-service"}], verify=False)
    launch.assert_not_called()


def test_source_service_survives_first_instance_exit_and_reuses_model(tmp_path):
    import subprocess

    directory = tmp_path / "service"
    data_root = tmp_path / "data"
    source = (
        "import sys, numpy as np\n"
        "from arknights_mower.utils.ocr_shared import SharedOCREngine\n"
        "client = SharedOCREngine(directory=sys.argv[1])\n"
        "assert client(np.zeros((32, 64, 3), np.uint8))[0] is None\n"
    )
    environment = {**os.environ, "MOWER_DATA_DIR": str(data_root)}
    endpoint = None
    try:
        subprocess.run(
            [sys.executable, "-c", source, str(directory)],
            env=environment,
            check=True,
            timeout=20,
            capture_output=True,
        )
        endpoint = runtime.read_json(directory / "endpoint.json")
        assert endpoint and runtime.process_alive(endpoint["pid"])
        client = ocr_shared.SharedOCREngine(directory=directory)
        assert client(np.zeros((32, 64, 3), np.uint8))[0] is None
        assert runtime.read_json(directory / "endpoint.json") == endpoint
    finally:
        # 此测试数据根目录内的服务登记只来自上面创建的子进程。
        import hashlib

        key = hashlib.sha256(os.fsencode(runtime.installation_root())).hexdigest()[:20]
        state = data_root / "tmp/updates" / key
        for record in runtime.instances(state):
            runtime.write_json(state / "shutdown" / f"{record['id']}.json", {})
        if endpoint:
            wait_for(lambda: not runtime.process_alive(endpoint["worker_pid"]))
            wait_for(lambda: not (directory / "endpoint.json").exists())


def test_recycling_preserves_waiting_requests_and_never_overlaps_models(tmp_path):
    with service(tmp_path, idle=2, max_requests=2):
        first = runtime.read_json(tmp_path / "endpoint.json")
        with ThreadPoolExecutor(max_workers=18) as pool:
            results = list(
                pool.map(
                    lambda i: ocr_shared.SharedOCREngine(directory=tmp_path)(
                        np.full((1, 1), i, np.uint8)
                    )[0][0],
                    range(18),
                )
            )
        assert [row[1] for row in results] == list(range(18))
        pids = {row[0] for row in results}
        assert len(pids) == 9
        assert all(row[2] in (1, 2) for row in results)
        current = runtime.read_json(tmp_path / "endpoint.json")
        assert current["port"] == first["port"] and current["token"] == first["token"]
        assert all(
            not runtime.process_alive(pid)
            for pid in pids
            if pid != current["worker_pid"]
        )


def failed_factory():
    raise RuntimeError("fixture model unavailable")


def test_failed_model_construction_releases_service_for_a_later_new_request(tmp_path):
    with service(tmp_path, factory=failed_factory, idle=0.5) as process:
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        with pytest.raises(RuntimeError, match="fixture model unavailable"):
            client(np.zeros((1, 1), np.uint8))
        process.join(3)
        assert not process.is_alive()
    with service(tmp_path, idle=0.5):
        assert client(np.ones((1, 1), np.uint8))[0][0][1] == 1


def test_default_endpoint_scope_separates_installations_and_network_namespaces(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace

    from arknights_mower.utils import path as mower_path

    monkeypatch.setattr(mower_path, "_data_dir", tmp_path)
    monkeypatch.setattr(runtime, "installation_root", lambda: Path("/install/mower"))
    monkeypatch.setattr(ocr_shared.socket, "gethostname", lambda: "fixture-host")
    monkeypatch.setattr(sys, "platform", "linux")
    real_stat = Path.stat
    namespace = [123]

    def stat(path, *args, **kwargs):
        if path == Path("/proc/self/ns/net"):
            return SimpleNamespace(st_dev=1, st_ino=namespace[0])
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    first = ocr_shared.shared_directory()
    assert ocr_shared.shared_directory() == first
    assert first.parent == tmp_path / "tmp/shared-ocr"
    namespace[0] = 124
    assert ocr_shared.shared_directory() != first
    namespace[0] = 123
    monkeypatch.setattr(runtime, "installation_root", lambda: Path("/install/other"))
    assert ocr_shared.shared_directory() != first


@pytest.mark.parametrize("failure_site", ["poll", "recv", "drain"])
@pytest.mark.parametrize("error", [EOFError, BrokenPipeError])
@pytest.mark.parametrize("recycle", [False, True])
def test_generation_channel_close_preserves_recycle_and_cleans_worker(
    monkeypatch, tmp_path, failure_site, error, recycle
):
    from unittest.mock import Mock

    from arknights_mower.utils.device import owned

    parent, child = Mock(), Mock()
    process = Mock(pid=123)
    context = Mock()
    context.Pipe.return_value = (parent, child)
    context.Process.return_value = process
    monkeypatch.setattr(ocr_service.mp, "get_context", lambda method: context)
    cleanup = Mock()
    monkeypatch.setattr(owned, "close_process", cleanup)
    registration = Mock()
    registration.shutdown_requested.return_value = False
    listener = Mock()
    listener.getsockname.return_value = ("127.0.0.1", 12345)

    # Windows 管道关闭可能在任一 poll 或 recv 报错；已经收到的回收通知仍有效。
    parent.recv.side_effect = ["recycle" if recycle else None, error()]
    parent.poll.side_effect = (
        [True, True] if failure_site == "recv" else [True, error()]
    )
    process.is_alive.return_value = failure_site != "drain"

    assert (
        ocr_service._generation(
            listener,
            "token",
            tmp_path,
            tmp_path / "endpoint.json",
            registration,
            60,
            fake_engine,
            256,
        )
        is recycle
    )
    cleanup.assert_called_once_with(process, os.getpid(), timeout=0.5)
    parent.close.assert_called_once()
    assert child.close.called
    listener.close.assert_not_called()
