"""共享 OCR 的真实本机传输、并发准入和自有进程生命周期。"""

import multiprocessing as mp
import os
import select
import signal
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Thread

import numpy as np
import pytest

from arknights_mower.tests.ocr_test_support import (
    endpoint_path,
    read_endpoint,
    service,
    state_directory,
    wait_for,
)
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


def serve_with_late_update(directory):
    """在回收获准后、替代工作进程登记前开始更新，确定性拒绝替代登记。"""
    directory = Path(directory)
    state = directory / "updates"
    start_worker = ocr_service._start_worker

    def start_after_update(*args, **kwargs):
        if kwargs.get("wait_for_start"):
            runtime.write_json(
                state / "active/owner.json",
                {"id": "fixture-update", "pid": os.getpid()},
            )
        return start_worker(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ocr_service, "_start_worker", start_after_update)
        ocr_service.serve(
            directory,
            state_directory=state,
            factory=fake_engine,
            idle_timeout=10,
            max_requests=1,
        )


def recording_factory():
    """记录模型构造，并记下构造时仍存活的旧工作进程数。

    工厂在工作进程内运行，构造日志路径经环境变量继承。``alive`` 为构造
    时刻仍存活的既有工作进程数，用于断言回收不重叠模型。
    """
    log = Path(os.environ["OCR_TEST_FACTORY_LOG"])
    previous = (
        [
            int(line.split()[0])
            for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if log.exists()
        else []
    )
    alive = sum(runtime.process_alive(pid) for pid in previous)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"{os.getpid()} {alive}\n")
    return RecordingEngine()


def shutdown_service(directory, *state_directories, timeout=10):
    """通过登记请求关闭测试启动的独立服务，并等待端点消失。"""
    endpoint = read_endpoint(directory)
    for state in state_directories:
        state = Path(state)
        if not state.exists():
            continue
        for record in runtime.instances(state):
            runtime.write_json(state / "shutdown" / f"{record['id']}.json", {})
    if endpoint:
        try:
            wait_for(lambda: not endpoint_path(directory).exists(), timeout=timeout)
        finally:
            for pid in (endpoint.get("worker_pid"), endpoint.get("pid")):
                if runtime.process_alive(pid):
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except OSError:
                        # 进程已在等待期间退出；PID 复用不是测试可清理的对象。
                        pass


def test_eighteen_clients_share_one_model_and_preserve_independent_results(tmp_path):
    with service(tmp_path, factory=fake_engine):
        barrier = Barrier(18)
        started = time.monotonic()

        def identify(index):
            client = ocr_shared.SharedOCREngine(directory=tmp_path)
            barrier.wait(timeout=5)
            # 非连续灰度图也必须原样传输。
            image = np.full((8, 16), index, np.uint8)[:, ::2]
            return client(image, use_det=False, text_score=index / 20)[0][0]

        with ThreadPoolExecutor(max_workers=18) as pool:
            results = list(pool.map(identify, range(18)))
        elapsed = time.monotonic() - started
        assert len({row[0] for row in results}) == 1
        assert [row[1] for row in results] == list(range(18))
        assert sorted(row[2] for row in results) == list(range(1, 19))
        assert all(row[3] == [8, 8] for row in results)
        assert [row[4]["text_score"] for row in results] == [i / 20 for i in range(18)]
        assert all(row[4]["box_thresh"] == 0.5 for row in results)
        # 每请求只有 10 ms 推理；30 秒时排队耗尽的宽松上界，60 秒是请求预算。
        assert elapsed < 30
        assert elapsed < ocr_shared.REQUEST_TIMEOUT


def test_same_instance_serializes_concurrent_calls_before_transport(
    tmp_path, monkeypatch
):
    with service(tmp_path, factory=fake_engine):
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        barrier = Barrier(2)
        original = ocr_shared.open_service
        state = {"active": 0, "maximum": 0}

        def observed(directory, deadline):
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            try:
                # 给另一线程足够时间进入同一客户端；若实例锁缺失，
                # 两个请求会同时开始解析端点并并发进入传输。
                time.sleep(0.2)
                return original(directory, deadline)
            finally:
                state["active"] -= 1

        monkeypatch.setattr(ocr_shared, "open_service", observed)

        def identify(marker):
            barrier.wait(5)
            return client(np.full((1, 1), marker, np.uint8))[0][0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(identify, (7, 9)))
        assert state["maximum"] == 1
        assert sorted(row[1] for row in rows) == [7, 9]
        assert sorted(row[2] for row in rows) == [1, 2]


def test_production_defaults_bound_shared_ocr_and_model_threads(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import cv2

    assert ocr_shared.REQUEST_TIMEOUT == 60.0
    assert ocr_shared.START_TIMEOUT == 10.0
    assert ocr_shared.HEADER_TIMEOUT == 5.0
    assert ocr_shared.IDLE_TIMEOUT == 60.0
    assert ocr_shared.MAX_IMAGE_BYTES == 32 * 1024 * 1024
    assert ocr_shared.MAX_HEADER_BYTES == 4096
    assert ocr_shared.MAX_RESULT_BYTES == 2 * 1024 * 1024
    assert ocr_shared.BACKLOG == 32
    assert ocr_service.IDLE_TIMEOUT == ocr_shared.IDLE_TIMEOUT
    assert ocr_service.REQUEST_TIMEOUT == ocr_shared.REQUEST_TIMEOUT
    assert ocr_service.MAX_REQUESTS == 256
    assert rapidocr.DEFAULT_TEXT_SCORE == 0.3
    assert rapidocr.DEFAULT_BOX_THRESH == 0.5
    assert rapidocr.DEFAULT_UNCLIP_RATIO == 1.6
    assert ocr_shared.image_size([8192, 4096, 1]) == 32 * 1024 * 1024
    with pytest.raises(ValueError, match="容量"):
        ocr_shared.image_size([8192, 4097, 1])
    client = ocr_shared.SharedOCREngine()
    assert client.timeout == ocr_shared.REQUEST_TIMEOUT
    assert client.score == rapidocr.DEFAULT_TEXT_SCORE

    original = rapidocr.create_engine
    factory = {}
    monkeypatch.setattr(cv2, "setNumThreads", lambda count: factory.update(cv2=count))
    monkeypatch.setattr(
        rapidocr,
        "create_engine",
        lambda **kwargs: factory.update(engine=kwargs) or object(),
    )
    assert ocr_service._engine() is not None
    assert factory["cv2"] == 2
    assert factory["engine"] == {"threads": 2}

    created = {}
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    for name in (
        "PP-OCRv6_det_tiny.onnx",
        "PP-OCRv6_rec_tiny.onnx",
        "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    ):
        (model_dir / name).touch()
    monkeypatch.setattr(rapidocr, "_MODEL_DIR", model_dir)

    class FakeDetector:
        def get_preprocess(self):
            return lambda image: image

    class FakeRapidOCR:
        def __init__(self, *, params):
            created.update(params)
            self.text_det = FakeDetector()

        def _load_det_model(self):
            return self.text_det

        def _load_cls_model(self):
            pass

        def _load_rec_model(self):
            pass

    monkeypatch.setitem(
        sys.modules,
        "rapidocr",
        SimpleNamespace(
            RapidOCR=FakeRapidOCR,
            ModelType=SimpleNamespace(TINY="tiny"),
            __file__=str(tmp_path / "__init__.py"),
        ),
    )
    engine = original(threads=2)
    assert created["EngineConfig.onnxruntime.intra_op_num_threads"] == 2
    assert created["EngineConfig.onnxruntime.inter_op_num_threads"] == 1
    assert created["Det.limit_type"] == "max"
    assert created["Det.limit_side_len"] == 1920
    assert created["Global.text_score"] == rapidocr.DEFAULT_TEXT_SCORE
    assert created["Global.use_preprocess_img"] is False
    assert created["Det.box_thresh"] == rapidocr.DEFAULT_BOX_THRESH
    assert created["Det.unclip_ratio"] == rapidocr.DEFAULT_UNCLIP_RATIO
    assert created["Det.model_type"] == "tiny"
    assert created["Rec.model_type"] == "tiny"
    assert isinstance(
        engine._sdk.text_det.get_preprocess(), rapidocr._BoundedDetectionInput
    )


def test_waiting_client_sends_no_image_before_admission(tmp_path):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    runtime.write_json(
        endpoint_path(tmp_path),
        {
            "version": ocr_shared.VERSION,
            "port": listener.getsockname()[1],
            "token": "a" * 64,
            "pid": os.getpid(),
            "worker_pid": 0,
        },
    )
    accepted = Event()
    finished = Event()
    received = bytearray()

    def inspect():
        # 认证后、ready 前是客户端唯一允许发送小请求头的窗口。假服务端读完
        # 认证 preamble 后不回复 authenticated，并在整个等待窗口持续观察；
        # 客户端若提前上传请求头或像素，任何时刻的入站字节都会被发现。
        with listener:
            listener.settimeout(5)
            channel, _ = listener.accept()
            with channel:
                preamble = ocr_shared.receive(
                    channel, ocr_shared.PREAMBLE.size, time.monotonic() + 3
                )
                magic, version, token = ocr_shared.PREAMBLE.unpack(preamble)
                assert magic == ocr_shared.PREAMBLE_MAGIC
                assert version == ocr_shared.VERSION
                assert token.decode("ascii") == "a" * 64
                accepted.set()
                channel.setblocking(False)
                deadline = time.monotonic() + 5
                while not finished.is_set() and time.monotonic() < deadline:
                    readable, _, _ = select.select([channel], [], [], 0.02)
                    if not readable:
                        continue
                    try:
                        part = channel.recv(65536)
                    except (BlockingIOError, InterruptedError):
                        continue
                    if not part:
                        break
                    received.extend(part)

    worker = Thread(target=inspect, daemon=True)
    worker.start()
    client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=1)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            client(np.zeros((1080, 1920, 3), np.uint8))
        assert 0.8 <= time.monotonic() - started < 3
        assert accepted.wait(0)
    finally:
        finished.set()
        worker.join(5)
    assert not worker.is_alive()
    assert received == b""


def test_authentication_and_input_bounds_do_not_construct_or_poison_model(
    tmp_path, monkeypatch
):
    log = tmp_path / "constructions.log"
    monkeypatch.setenv("OCR_TEST_FACTORY_LOG", str(log))
    with service(tmp_path, factory=recording_factory):
        endpoint = read_endpoint(tmp_path)
        assert not log.exists()
        token = endpoint["token"]

        def exchange(*, magic=None, version=None, candidate=None, extra=None):
            with socket.create_connection(
                ("127.0.0.1", endpoint["port"]), timeout=3
            ) as channel:
                deadline = time.monotonic() + 3
                channel.sendall(
                    ocr_shared.PREAMBLE.pack(
                        ocr_shared.PREAMBLE_MAGIC if magic is None else magic,
                        ocr_shared.VERSION if version is None else version,
                        (token if candidate is None else candidate).encode("ascii"),
                    )
                )
                response = ocr_shared.read_json(channel, deadline)
                if extra is not None:
                    assert response == {"status": "authenticated"}
                    header = dict(
                        version=ocr_shared.VERSION,
                        shape=[1, 1],
                        options={},
                        deadline=deadline,
                    )
                    header.update(extra)
                    ocr_shared.send_json(channel, header, deadline)
                    response = ocr_shared.read_json(channel, deadline)
                return response

        # 认证前失败：错误、版本、令牌；认证后失败：请求头版本、形状、选项。
        for case in (
            {"magic": b"MOWX"},
            {"version": ocr_shared.VERSION + 1},
            {"candidate": "0" * 64},
            {"extra": {"version": ocr_shared.VERSION + 1}},
            {"extra": {"shape": [8192, 8192, 3]}},
            {"extra": {"shape": [10000, 1000, 3]}},
            {"extra": {"options": {"use_det": "yes"}}},
            {"extra": {"options": {"unclip_ratio": 11}}},
        ):
            response = exchange(**case)
            assert response["status"] == "error"
            assert response["error"]
            # 校验失败若先构造模型，工厂日志会在这里出现。
            assert not log.exists(), f"invalid request constructed a model: {case}"
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        row = client(np.ones((1, 1), np.uint8))[0][0]
        assert row[2] == 1
        assert row[4]["text_score"] == 0.3
        assert [line.split()[1] for line in log.read_text().splitlines()] == ["0"]
        # 非法客户端输入不进服务，也不影响已构造实例的调用计数。
        with pytest.raises(ValueError):
            client(np.ones((1, 1), np.float32))
        assert client(np.zeros((1, 1), np.uint8))[0][0][2] == 2
        assert len(log.read_text().splitlines()) == 1


def test_request_failure_is_not_replayed_and_next_request_remains_usable(tmp_path):
    with service(tmp_path, factory=fake_engine):
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
    with service(tmp_path, factory=fake_engine, idle=1) as process:
        endpoint = read_endpoint(tmp_path)
        client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=1.5)
        started = time.monotonic()
        with pytest.raises((ConnectionError, TimeoutError)):
            client(np.full((1, 1), marker, np.uint8))
        process.join(4)
        assert not process.is_alive()
        assert time.monotonic() - started < 5
        assert not runtime.process_alive(endpoint["worker_pid"])
        assert not endpoint_path(tmp_path).exists()


def test_idle_exit_releases_model_and_directory_can_be_reused(tmp_path):
    with service(
        tmp_path, factory=fake_engine, idle=0.3, wait_for_idle=True
    ) as process:
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        first = client(np.zeros((1, 1), np.uint8))[0][0][0]
        process.join(3)
        assert not process.is_alive()
        assert not runtime.process_alive(first)
    with service(tmp_path, factory=fake_engine, idle=0.3, wait_for_idle=True):
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
        ocr_shared,
        "start_service",
        lambda directory, deadline=None: Started(start(directory)),
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
    # 固定共享模式：发布轻量客户端不依赖存活实例数，也不触碰共享目录。
    monkeypatch.setenv("MOWER_OCR_MODE", "shared")
    monkeypatch.setattr(rapidocr, "engine", None)
    monkeypatch.setattr(ocr_shared, "shared_directory", lambda: tmp_path)
    monkeypatch.setattr(
        rapidocr, "create_engine", lambda *a, **k: pytest.fail("loaded model")
    )
    rapidocr.initialize_ocr()
    assert isinstance(rapidocr.engine, ocr_shared.SharedOCREngine)
    assert not list(tmp_path.iterdir())


def test_initialize_ocr_cold_starts_default_shared_service(tmp_path, monkeypatch):
    from arknights_mower.solvers import furniture
    from arknights_mower.utils import path as mower_path
    from arknights_mower.utils.image import bytes2img

    monkeypatch.setattr(mower_path, "_data_dir", tmp_path)
    monkeypatch.delenv("MOWER_OCR_MODE", raising=False)
    monkeypatch.setenv("MOWER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rapidocr, "engine", None)
    directory = ocr_shared.shared_directory()
    state = runtime.state_dir()
    assert directory.is_relative_to(tmp_path / "tmp/shared-ocr")
    assert state.is_relative_to(tmp_path / "tmp/updates")
    registrations = [
        runtime.RuntimeRegistration("instance", directory=state, maintenance=False)
        for _ in range(2)
    ]
    try:
        # 默认 auto 路径：两个存活实例选择共享客户端，首次识别才冷启动服务。
        rapidocr.initialize_ocr()
        client = rapidocr.engine
        assert isinstance(client, ocr_shared.SharedOCREngine)
        assert client.directory == directory
        assert client.score == rapidocr.DEFAULT_TEXT_SCORE
        assert not endpoint_path(directory).exists()
        for registration in registrations:
            registration.close()
        source = Path(__file__).parent / "fixtures/furniture/stock_3_2.png"
        image = bytes2img(source.read_bytes())
        crop = furniture.crop_relative(image, furniture.NAME_SCOPE)
        result = client(crop, use_cls=False)[0]
        assert "洗衣间地毯" in "".join(row[1] for row in result)
        endpoint = read_endpoint(directory)
        assert endpoint and runtime.process_alive(endpoint["pid"])
        assert runtime.process_alive(endpoint["worker_pid"])
        assert {record["kind"] for record in runtime.instances(state)} == {
            "ocr-service",
            "ocr-worker",
        }
    finally:
        rapidocr.engine = None
        for registration in registrations:
            if not registration.closed.is_set():
                registration.close()
        shutdown_service(directory, state)


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
    with service(tmp_path, factory=fake_engine, idle=10) as process:
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        pid = client(np.zeros((1, 1), np.uint8))[0][0][0]
        records = runtime.instances(tmp_path / "updates")
        by_kind = {record["kind"]: record for record in records}
        assert set(by_kind) == {"ocr-service", "ocr-worker"}
        assert by_kind["ocr-worker"]["pid"] == pid
        record = by_kind["ocr-service"]
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
    assert not endpoint_path(tmp_path).exists()
    assert runtime.instances(state) == []


def test_model_lock_rejects_replacement_while_old_worker_ownership_remains(tmp_path):
    # 模拟协调进程消失、但旧原生工作进程尚未退出。
    with runtime.supervision_lock(tmp_path / "model", timeout=0):
        with service(tmp_path, factory=fake_engine, idle=0.5) as process:
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
        endpoint = read_endpoint(directory)
        assert endpoint and runtime.process_alive(endpoint["pid"])
        client = ocr_shared.SharedOCREngine(directory=directory)
        assert client(np.zeros((32, 64, 3), np.uint8))[0] is None
        assert read_endpoint(directory) == endpoint
    finally:
        # 此数据根内的服务登记只来自上面创建的子进程；共享夹具只替换数据根，
        # 不复制 state_dir 的哈希算法。
        state = state_directory(data_root)
        assert state.is_relative_to(data_root)
        for record in runtime.instances(state):
            runtime.write_json(state / "shutdown" / f"{record['id']}.json", {})
        if endpoint:
            wait_for(lambda: not runtime.process_alive(endpoint["worker_pid"]))
            wait_for(lambda: not endpoint_path(directory).exists())


@pytest.mark.parametrize("active_update", [False, True])
def test_source_cold_start_preserves_resolved_data_root_and_update_admission(
    tmp_path, active_update
):
    import subprocess

    installation = runtime.installation_root()
    try:
        relative_data = Path(os.path.relpath(tmp_path / "service-data", installation))
    except ValueError:
        pytest.skip("相对数据根目录检查需要源码与临时目录位于同一磁盘")
    # 将调用目录与安装目录解析出的数据根都限制在此测试的临时目录内。
    levels = next(
        (index for index, part in enumerate(relative_data.parts) if part != ".."),
        0,
    )
    caller = tmp_path.joinpath(*(["caller"] * max(1, levels)))
    caller.mkdir(parents=True)
    expected_data = (caller / relative_data).resolve()
    assert expected_data.is_relative_to(tmp_path)
    assert expected_data != tmp_path / "service-data"
    environment = {
        **os.environ,
        "MOWER_DATA_DIR": str(relative_data),
        "PYTHONPATH": os.pathsep.join(
            filter(None, (str(installation), os.environ.get("PYTHONPATH")))
        ),
    }
    environment.pop("MOWER_RESTART_JOB", None)
    source = """
import os, sys, time
from pathlib import Path
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.ocr_shared import open_service, shared_directory

expected_data, wrong_data = map(Path, sys.argv[1:3])
active_update = sys.argv[3] == "True"
state = runtime.state_dir()
assert state.is_relative_to(expected_data)
directory = shared_directory()
if active_update:
    runtime.write_json(state / "active/owner.json", {"pid": os.getpid(), "id": "fixture"})
try:
    try:
        channel, token = open_service(directory, time.monotonic() + 10)
    except RuntimeError:
        assert active_update, "cold start failed without an active update"
    else:
        channel.close()
        assert not active_update, "shared OCR ignored the caller's active update"
        records = runtime.instances(state)
        assert any(record["kind"] == "ocr-service" for record in records), (
            "shared OCR registration escaped the caller's resolved data root"
        )
    if active_update:
        assert not (directory / "endpoint.json").exists()
        assert runtime.instances(state) == []
finally:
    # 断言失败时也关闭意外数据根内由此测试创建的服务。
    for data_root in (expected_data, wrong_data):
        for service_state in (data_root / "tmp/updates").glob("*"):
            for record in runtime.instances(service_state):
                runtime.write_json(service_state / "shutdown" / f"{record['id']}.json", {})
    deadline = time.monotonic() + 5
    while (directory / "endpoint.json").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not (directory / "endpoint.json").exists(), "test service did not stop"
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            source,
            str(expected_data),
            str(tmp_path / "service-data"),
            str(active_update),
        ],
        cwd=caller,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_recycling_preserves_waiting_requests_and_never_overlaps_models(
    tmp_path, monkeypatch
):
    log = tmp_path / "constructions.log"
    monkeypatch.setenv("OCR_TEST_FACTORY_LOG", str(log))
    with service(tmp_path, factory=recording_factory, idle=2, max_requests=2):
        first = read_endpoint(tmp_path)
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
        assert sorted(row[2] for row in results) == [1] * 9 + [2] * 9
        # 每次构造模型时，此前所有工作进程都必须已经退出；日志第二列
        # 是构造时刻仍存活的旧进程数，重叠回收会让它为 1。
        constructions = [
            (int(pid), int(alive))
            for pid, alive in (
                line.split() for line in log.read_text(encoding="utf-8").splitlines()
            )
        ]
        assert len(constructions) == 9
        assert all(alive == 0 for _, alive in constructions), (
            "recycling constructed a model before the previous worker exited"
        )
        assert {pid for pid, _ in constructions} == pids
        current = read_endpoint(tmp_path)
        assert current["port"] == first["port"] and current["token"] == first["token"]
        assert all(
            not runtime.process_alive(pid)
            for pid in pids
            if pid != current["worker_pid"]
        )


def test_silent_connection_does_not_end_service_generation(tmp_path):
    with service(tmp_path, factory=fake_engine, idle=8) as process:
        endpoint = read_endpoint(tmp_path)
        channel = socket.create_connection(("127.0.0.1", endpoint["port"]), timeout=3)
        started = time.monotonic()
        try:
            # 静默连接只占用认证 preamble 的 1 秒预算；旧实现读取 5 秒请求头，
            # 同一代工作进程会被它独占，后续请求在 5 秒后才得到服务。
            row = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=10)(
                np.zeros((1, 1), np.uint8)
            )[0][0]
            elapsed = time.monotonic() - started
            assert row[2] == 1
            assert elapsed < 4, (
                f"silent connection delayed the next request by {elapsed:.2f}s"
            )
            # 越过旧实现的 5 秒请求头预算后，整代服务仍必须存活且端点不变。
            time.sleep(max(0.0, ocr_shared.HEADER_TIMEOUT + 0.5 - elapsed))
            assert process.is_alive()
            assert read_endpoint(tmp_path) == endpoint
        finally:
            channel.close()
            shutdown_service(tmp_path, tmp_path / "updates")


def test_stale_endpoint_after_coordinator_kill_self_heals(tmp_path, monkeypatch):
    from arknights_mower.utils import path as mower_path

    monkeypatch.setattr(mower_path, "_data_dir", tmp_path)
    directory = tmp_path / "shared"
    state = runtime.state_dir()
    with service(directory, factory=fake_engine, idle=10) as process:
        try:
            client = ocr_shared.SharedOCREngine(directory=directory, timeout=15)
            client(np.zeros((32, 64, 3), np.uint8))
            stale = read_endpoint(directory)
            process.kill()
            process.join(5)
            assert not process.is_alive()
            wait_for(lambda: not runtime.process_alive(stale["worker_pid"]), timeout=10)
            # 协调进程被硬杀后端点文件残留，下一次请求必须冷启动而不是超时。
            assert endpoint_path(directory).exists()
            result = client(np.zeros((32, 64, 3), np.uint8))
            assert result[0] is None
            current = read_endpoint(directory)
            assert current["pid"] != stale["pid"]
            assert current["worker_pid"] != stale["worker_pid"]
            assert runtime.process_alive(current["pid"])
        finally:
            shutdown_service(directory, state)


def test_recycle_counts_only_inferred_requests(tmp_path):
    with service(tmp_path, factory=fake_engine, idle=5, max_requests=2):
        try:
            client = ocr_shared.SharedOCREngine(directory=tmp_path)
            first = client(np.zeros((1, 1), np.uint8))[0][0]
            assert first[2] == 1
            endpoint = read_endpoint(tmp_path)
            # 空连接和认证后未准入的连接都没有进入推理，不能消耗回收额度。
            socket.create_connection(("127.0.0.1", endpoint["port"]), timeout=3).close()
            with socket.create_connection(
                ("127.0.0.1", endpoint["port"]), timeout=3
            ) as channel:
                deadline = time.monotonic() + 3
                channel.sendall(
                    ocr_shared.PREAMBLE.pack(
                        ocr_shared.PREAMBLE_MAGIC,
                        ocr_shared.VERSION,
                        endpoint["token"].encode("ascii"),
                    )
                )
                assert ocr_shared.read_json(channel, deadline) == {
                    "status": "authenticated"
                }
                ocr_shared.send_json(
                    channel,
                    dict(
                        version=ocr_shared.VERSION,
                        shape=[10000, 1000, 3],
                        options={},
                        deadline=deadline,
                    ),
                    deadline,
                )
                assert ocr_shared.read_json(channel, deadline)["status"] == "error"
            second = client(np.ones((1, 1), np.uint8))[0][0]
            assert second[0] == first[0]
            assert second[2] == 2
            third = client(np.full((1, 1), 2, np.uint8))[0][0]
            assert third[0] != first[0]
            assert third[2] == 1
        finally:
            shutdown_service(tmp_path, tmp_path / "updates")


def test_update_preparation_resumes_recycle_and_keeps_worker(tmp_path):
    state = tmp_path / "updates"
    with service(tmp_path, factory=fake_engine, idle=10, max_requests=1) as process:
        try:
            wait_for(
                lambda: (
                    {record["kind"] for record in runtime.instances(state)}
                    >= {"ocr-service", "ocr-worker"}
                ),
                timeout=10,
            )
            # 更新准备期：active owner 已写，但安装尚未开始。此时回收必须被
            # 协调进程改判为 resume，而不是结束包含可用工作进程的服务代际。
            runtime.write_json(
                state / "active/owner.json",
                {"id": "fixture-update", "pid": os.getpid()},
            )
            endpoint = read_endpoint(tmp_path)
            client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=10)
            first = client(np.zeros((1, 1), np.uint8))[0][0]
            # max_requests=1：首个请求已触发回收；准备期拒绝回收后，第二个
            # 请求必须仍由同一工作进程服务，端点与协调进程保持不变。
            second = client(np.ones((1, 1), np.uint8))[0][0]
            assert second[0] == first[0]
            assert second[2] == 2
            assert process.is_alive()
            assert read_endpoint(tmp_path) == endpoint
            assert endpoint["worker_pid"] == first[0]
            assert runtime.process_alive(first[0])
        finally:
            shutdown_service(tmp_path, state)


def test_replacement_registration_failure_keeps_worker_and_endpoint(tmp_path):
    state = tmp_path / "updates"
    process = mp.get_context("spawn").Process(
        target=serve_with_late_update, args=(tmp_path,)
    )
    process.start()
    try:
        try:
            wait_for(
                lambda: (
                    {record["kind"] for record in runtime.instances(state)}
                    >= {"ocr-service", "ocr-worker"}
                ),
                timeout=10,
            )
            endpoint = wait_for(lambda: read_endpoint(tmp_path))
            client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=10)
            first = client(np.zeros((1, 1), np.uint8))[0][0]
            # 交接失败后协调进程必须 resume 旧工作进程，而不是结束整代服务。
            second = client(np.ones((1, 1), np.uint8))[0][0]
            assert second[0] == first[0]
            assert second[2] == 2
            assert process.is_alive()
            assert read_endpoint(tmp_path) == endpoint
            assert endpoint["worker_pid"] == first[0]
            assert runtime.process_alive(first[0])
            assert runtime.read_json(state / "active/owner.json")["pid"] == process.pid
            # active owner 只在替代启动入口写入，证明本次经过登记失败后的
            # 恢复分支，而不只是回收前就发现更新并跳过交接。
            workers = [
                record["pid"]
                for record in runtime.instances(state)
                if record["kind"] == "ocr-worker"
            ]
            assert workers == [first[0]]
        finally:
            shutdown_service(tmp_path, state)
    finally:
        close_process(process, os.getpid(), timeout=0.5)


def test_immediate_recycle_resume_serves_the_next_request_without_waiting(monkeypatch):
    from unittest.mock import MagicMock, Mock

    granted, resumed = Event(), Event()
    control = Mock()
    requests = []

    def decide(message):
        if message == ocr_service.CONTROL_RECYCLE:
            requests.append(message)
            if len(requests) == 1:
                # 控制线程可以在 send 返回前收到协调进程的决定。
                resumed.set()
            else:
                granted.set()

    control.send.side_effect = decide
    listener = Mock()
    listener.accept.side_effect = [(MagicMock(), None), (MagicMock(), None)]
    monkeypatch.setattr(ocr_service, "_authenticate", lambda *args: None)
    monkeypatch.setattr(
        ocr_service,
        "read_json",
        lambda *args: {
            "version": ocr_shared.VERSION,
            "deadline": time.monotonic() + 5,
            "shape": [1, 1],
            "options": {},
        },
    )
    monkeypatch.setattr(ocr_service, "receive", lambda *args: b"\0")
    monkeypatch.setattr(ocr_service, "send_json", lambda *args: None)
    monkeypatch.setattr(
        ocr_service,
        "sleep",
        lambda seconds: pytest.fail("已收到 resume，不应再等待回收决定"),
    )
    ocr_service._serve(listener, control, "token", 5, fake_engine, 1, granted, resumed)
    assert listener.accept.call_count == 2
    assert len(requests) == 2


def test_client_reports_server_refusal_text(tmp_path):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    runtime.write_json(
        endpoint_path(tmp_path),
        {
            "version": ocr_shared.VERSION,
            "port": listener.getsockname()[1],
            "token": "a" * 64,
            "pid": os.getpid(),
            "worker_pid": 0,
        },
    )

    def refuse():
        with listener:
            listener.settimeout(3)
            channel, _ = listener.accept()
            with channel:
                ocr_shared.receive(
                    channel, ocr_shared.PREAMBLE.size, time.monotonic() + 3
                )
                ocr_shared.send_json(
                    channel,
                    {"status": "error", "error": "fixture protocol refusal"},
                    time.monotonic() + 3,
                )

    worker = Thread(target=refuse, daemon=True)
    worker.start()
    client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=3)
    with pytest.raises(RuntimeError, match="fixture protocol refusal"):
        client(np.zeros((1, 1), np.uint8))
    worker.join(3)
    assert not worker.is_alive()


def test_connection_refusal_waits_for_live_service_within_budget(tmp_path, monkeypatch):
    with service(tmp_path, factory=fake_engine, idle=5):
        try:
            original = ocr_shared._connect_endpoint
            attempts = []

            def refused_once(endpoint, deadline):
                attempts.append(time.monotonic())
                if len(attempts) == 1:
                    return None
                return original(endpoint, deadline)

            monkeypatch.setattr(ocr_shared, "_connect_endpoint", refused_once)
            monkeypatch.setattr(
                ocr_shared,
                "start_service",
                lambda *args, **kwargs: pytest.fail(
                    "connection refusal started a duplicate service"
                ),
            )
            client = ocr_shared.SharedOCREngine(directory=tmp_path, timeout=3)
            row = client(np.zeros((1, 1), np.uint8))[0][0]
            assert row[2] == 1
            assert len(attempts) >= 2
        finally:
            shutdown_service(tmp_path, tmp_path / "updates")


def test_startup_failure_writes_reason_to_service_log(tmp_path, monkeypatch):
    from arknights_mower.utils import path as mower_path

    monkeypatch.setattr(mower_path, "_data_dir", tmp_path)
    monkeypatch.delenv("MOWER_RESTART_JOB", raising=False)
    state = runtime.state_dir()
    runtime.write_json(
        state / "active/owner.json", {"id": "fixture-update", "pid": os.getpid()}
    )
    directory = tmp_path / "service"
    with pytest.raises(RuntimeError, match="共享 OCR 服务启动失败"):
        ocr_shared.open_service(directory, time.monotonic() + 1.5)
    wait_for(
        lambda: "更新或进程操作" in ocr_shared.read_service_log(directory), timeout=5
    )


def test_cold_start_waits_for_busy_submission_lock(tmp_path, monkeypatch):
    from arknights_mower.utils import path as mower_path

    monkeypatch.setattr(mower_path, "_data_dir", tmp_path)
    state = runtime.state_dir()
    directory = tmp_path / "service"
    held = Event()
    release = Event()

    def hold():
        with runtime.submission_lock(state):
            held.set()
            release.wait(5)

    holder = Thread(target=hold, daemon=True)
    holder.start()
    try:
        assert held.wait(2)
        releaser = Thread(target=lambda: (time.sleep(0.5), release.set()))
        releaser.start()
        started = time.monotonic()
        channel, _ = ocr_shared.open_service(directory, time.monotonic() + 10)
        elapsed = time.monotonic() - started
        channel.close()
        assert elapsed >= 0.4
        assert any(
            record["kind"] == "ocr-service" for record in runtime.instances(state)
        )
    finally:
        release.set()
        holder.join(5)
        shutdown_service(directory, state)


def failed_factory():
    raise RuntimeError("fixture model unavailable")


def test_failed_model_construction_releases_service_for_a_later_new_request(tmp_path):
    with service(tmp_path, factory=failed_factory, idle=0.5) as process:
        client = ocr_shared.SharedOCREngine(directory=tmp_path)
        with pytest.raises(RuntimeError, match="fixture model unavailable"):
            client(np.zeros((1, 1), np.uint8))
        process.join(3)
        assert not process.is_alive()
    with service(tmp_path, factory=fake_engine, idle=0.5):
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
def test_generation_channel_close_preserves_handoff_and_cleans_worker(
    monkeypatch, tmp_path, failure_site, error, recycle
):
    from unittest.mock import Mock

    from arknights_mower.utils.device import owned

    old_process = Mock(pid=123)
    replacement = Mock(pid=456)
    parent, child = Mock(), Mock()
    replaced_control = Mock()
    context = Mock()
    context.Pipe.return_value = (parent, child)
    context.Process.return_value = old_process
    monkeypatch.setattr(ocr_service.mp, "get_context", lambda method: context)
    cleanup = Mock()
    monkeypatch.setattr(owned, "close_process", cleanup)
    handoff = Mock(return_value=(replacement, replaced_control))
    monkeypatch.setattr(ocr_service, "_handoff", handoff)
    registration = Mock()
    registration.directory = tmp_path / "updates"
    registration.shutdown_requested.return_value = False
    listener = Mock()
    listener.getsockname.return_value = ("127.0.0.1", 12345)

    # Windows 管道关闭可能在任一 poll 或 recv 报错；已经收到的回收通知仍有效。
    control = replaced_control if recycle else parent
    control.recv.side_effect = [None, error()]
    control.poll.side_effect = (
        [True, True] if failure_site == "recv" else [True, error()]
    )
    active_process = replacement if recycle else old_process
    active_process.is_alive.return_value = failure_site != "drain"
    if recycle:
        parent.poll.return_value = True
        parent.recv.return_value = ocr_service.CONTROL_RECYCLE

    assert (
        ocr_service._generation(
            listener,
            "token",
            tmp_path,
            endpoint_path(tmp_path),
            registration,
            60,
            fake_engine,
            256,
        )
        is None
    )
    if recycle:
        handoff.assert_called_once()
        cleanup.assert_any_call(
            old_process, os.getpid(), timeout=ocr_service.CLOSE_TIMEOUT
        )
        cleanup.assert_any_call(
            replacement, os.getpid(), timeout=ocr_service.CLOSE_TIMEOUT
        )
        replaced_control.send.assert_called_once_with(ocr_service.CONTROL_START)
        assert read_endpoint(tmp_path)["worker_pid"] == replacement.pid
        replaced_control.close.assert_called_once()
    else:
        handoff.assert_not_called()
        cleanup.assert_called_once_with(
            old_process, os.getpid(), timeout=ocr_service.CLOSE_TIMEOUT
        )
    parent.close.assert_called_once()
    child.close.assert_called_once()
    listener.close.assert_not_called()
