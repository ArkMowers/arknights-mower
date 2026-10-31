"""离线复现后台消费停滞时的内存保留，并固定日志、截图归档与 OCR 预处理边界。"""

import logging
from unittest.mock import Mock

import pytest

from arknights_mower.utils import log
from arknights_mower.utils.screenshot import ScreenshotStore


@pytest.fixture(scope="module")
def production_ocr_engine():
    """生产模型工厂；本模块的预处理与坐标空间断言共用一次模型加载。"""
    from arknights_mower.utils.rapidocr import create_engine

    return create_engine()


def _detector_input(engine, height, width):
    """返回检测包装器对原始图像算出的张量长宽。

    这里直接调用 _BoundedDetectionInput（生产工厂安装的包装器），测的是包装器对
    传入图像的行为。生产 RapidOCR.__call__ 在进入该包装器前会先做内置 letterbox
    （宽度/高度比 8、最小高度 30），因此实际检测输入可能与包装器层不同。
    """
    import numpy as np

    preprocess = engine._sdk.text_det.get_preprocess()
    tensor = preprocess(np.zeros((height, width, 3), dtype=np.uint8))
    assert tensor.shape[:2] == (1, 3)
    return tuple(tensor.shape[2:])


def test_frontend_log_without_consumer_keeps_only_recent_messages(monkeypatch):
    queue = log.LatestLogQueue(drop_warning_interval=None)
    monkeypatch.setattr(log, "frontend_log_queue", queue)
    for index in range(1024):
        record = logging.LogRecord(
            "memory-test", logging.INFO, __file__, 1, "message %s", (index,), None
        )
        record.asctime = "2026-10-16 12:00:00"
        log.whlr.emit(record)
    assert queue.qsize() <= 256
    messages = [queue.get_nowait() for _ in range(queue.qsize())]
    assert messages[-1].endswith("message 1023")


def test_slow_archive_cannot_retain_a_recent_cache_per_error(tmp_path):
    now = [10**18]
    store = ScreenshotStore(
        tmp_path,
        lambda: 0,
        logger=Mock(),
        max_recent_bytes=32,
        wall_time_ns=lambda: now[0],
    )
    try:
        for index in range(20):
            now[0] += 601 * 10**9
            store.submit(bytes([index]) * 16)
            store.mark_error(now[0], "画面异常")
        retained = sum(frame.size for task in store._archive_queue for frame in task[5])
        assert retained <= 32
    finally:
        store.close(timeout=0)


def test_live_backlog_bounds_messages_without_truncating_file_log(tmp_path):
    from logging.handlers import QueueListener

    queue = log.LatestLogQueue(maxsize=2, drop_warning_interval=None)
    asynchronous = log.LiveQueueHandler(queue)
    path = tmp_path / "runtime.log"
    disk = logging.FileHandler(path, encoding="utf-8")
    logger = logging.Logger("bounded-live-log")
    logger.addHandler(asynchronous)
    logger.addHandler(disk)
    try:
        oversized = "长" * (2 * log.LIVE_LOG_MESSAGE_LIMIT)
        for index in range(10):
            logger.info("%s %s", index, oversized)
        assert queue.qsize() == 2
        assert queue.dropped == 8
        record = queue.get_nowait()
        assert record.getMessage().startswith("8 ")
        assert len(record.getMessage()) <= log.LIVE_LOG_MESSAGE_LIMIT
        assert record.args is None
        assert record.exc_info is None
        queue.task_done()
        # 满队列仍可提交退出标记，监听器不因容量限制无法关闭。
        logger.info("last")
        listener = QueueListener(queue)
        listener.enqueue_sentinel()
        assert queue.get_nowait().getMessage() == "last"
        queue.task_done()
        assert queue.get_nowait() is listener._sentinel
        queue.task_done()
        assert queue.unfinished_tasks == 0
    finally:
        disk.close()
    assert path.read_text(encoding="utf-8").count(oversized) == 10


def test_log_producers_share_capacity_and_release_evicted_records():
    import weakref
    from concurrent.futures import ThreadPoolExecutor

    queue = log.LatestLogQueue(maxsize=8, drop_warning_interval=None)
    handler = log.LiveQueueHandler(queue)
    references = []

    def emit(index):
        record = logging.LogRecord(
            "memory-test", logging.INFO, __file__, 1, "message %s", (index,), None
        )
        prepared = handler.prepare(record)
        references.append(weakref.ref(prepared))
        handler.enqueue(prepared)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(emit, range(1000)))
    assert queue.qsize() == 8
    assert queue.dropped == 992
    assert sum(ref() is not None for ref in references) == 8
    for _ in range(8):
        queue.get_nowait()
        queue.task_done()
    assert all(ref() is None for ref in references)
    assert queue.unfinished_tasks == 0


def test_live_log_default_queue_capacity_keeps_latest_256_messages():
    # 生产默认容量：队列满后只保留最新 256 条，淘汰条数可从队列状态读取。
    queue = log.LatestLogQueue(drop_warning_interval=None)
    for index in range(300):
        queue.put(f"message {index}")
    assert queue.qsize() == 256
    assert queue.dropped == 44
    assert queue.dropped_since_warning == 44
    assert queue.get_nowait() == "message 44"


def test_live_log_default_message_limit_is_16384_characters():
    # 生产默认单条上限：超长消息截到 16,384 字符并附截断标记，边界值不截断。
    handler = log.LiveQueueHandler(log.LatestLogQueue(drop_warning_interval=None))
    oversized = "长" * 20000
    record = logging.LogRecord(
        "memory-test", logging.INFO, __file__, 1, "%s", (oversized,), None
    )
    prepared = handler.prepare(record)
    assert len(prepared.message) == 16_384
    assert prepared.message.startswith("长" * 100)
    assert prepared.message != oversized
    boundary = "短" * 16_384
    record = logging.LogRecord(
        "memory-test", logging.INFO, __file__, 1, "%s", (boundary,), None
    )
    assert handler.prepare(record).message == boundary


def test_truncated_live_log_line_keeps_screenshot_archive_id(monkeypatch):
    # 生产链路：入队前已截到上限的消息，归档说明在最终整行截断后仍留在行尾。
    queue = log.LatestLogQueue(drop_warning_interval=None)
    monkeypatch.setattr(log, "frontend_log_queue", queue)
    store = Mock()
    store.mark_error.return_value = "456"
    monkeypatch.setattr(log, "get_screenshot_store", lambda: store)
    record = logging.LogRecord(
        "memory-test",
        logging.ERROR,
        "/project/arknights_mower/solvers/base_schedule.py",
        12,
        "%s",
        ("长" * 20000,),
        None,
    )
    record.asctime = "2026-10-17 12:00:00"
    prepared = log.LiveQueueHandler(log.logger).prepare(record)
    assert len(prepared.message) == 16_384
    log.whlr.emit(prepared)
    assert store.mark_error.call_count == 1
    line = queue.get_nowait()
    assert len(line) <= 16_384
    assert line.startswith("2026-10-17 12:00:00 ERROR ")
    assert "记录编号 456" in line
    assert line.count(log.LIVE_LOG_TRUNCATION_SUFFIX) == 1
    assert line.endswith("（已保存前后截图，记录编号 456）")


def test_live_log_drop_warning_is_rate_limited_and_observable(monkeypatch):
    # 首次淘汰立即告警，同一 60 秒间隔内不再告警；累计与待告警条数都可读。
    now = [1000.0]
    monkeypatch.setattr(log, "monotonic", lambda: now[0])
    warning = Mock()
    monkeypatch.setattr(log.logger, "warning", warning)
    queue = log.LatestLogQueue(maxsize=2)
    for index in range(3):
        queue.put(str(index))
    assert queue.dropped == 1
    assert warning.call_count == 1
    assert warning.call_args.args[1:] == (1, 1)
    # 告警发出后“自上次告警以来”清零，累计条数继续增长。
    assert queue.dropped_since_warning == 0
    now[0] += 30
    for index in range(10):
        queue.put(str(index))
    assert queue.dropped == 11
    assert warning.call_count == 1
    assert queue.dropped_since_warning == 10
    now[0] += 31
    queue.put("last")
    assert warning.call_count == 2
    assert warning.call_args.args[1:] == (12, 11)
    assert queue.dropped_since_warning == 0


def test_archive_budget_covers_active_work_and_releases_on_failure(tmp_path):
    import time
    import weakref
    from threading import Event, Thread

    from arknights_mower.tests.screenshot_pipeline_tests import wait_until

    now = [time.time_ns()]
    entered, release = Event(), Event()
    store = ScreenshotStore(
        tmp_path,
        lambda: 0,
        logger=Mock(),
        max_recent_bytes=16,
        wall_time_ns=lambda: now[0],
    )
    store.logger = logging.Logger("archive-memory-test")
    store.logger.addHandler(logging.NullHandler())
    original_archive = store._archive_frame

    def blocked(frame):
        entered.set()
        if not release.wait(3):
            raise TimeoutError("test archive stuck")
        raise OSError("disk failure")

    store._archive_frame = blocked
    store.submit(b"a" * 16)
    previous = weakref.ref(store._recent_frames[0])
    store.mark_error(now[0], "first")
    worker = Thread(target=store._archiver, daemon=True)
    worker.start()
    try:
        assert entered.wait(2)
        now[0] += 601 * 10**9
        store.submit(b"b" * 16)
        store.mark_error(now[0], "second")
        assert store.stats()["archive_buffer_bytes"] == 16
        assert store.stats()["archive_buffer_dropped"] == 1
        # 归档线程已取走第一个任务：在途任务的保留引用仍计入预算，但不在排队队列中；
        # 第二个任务已入队，其缓冲被省略，因此排队引用为 0。
        assert store.stats()["archive_pending_count"] == 1
        assert (
            sum(frame.size for task in store._archive_queue for frame in task[5]) == 0
        )
        release.set()
        wait_until(lambda: store.stats()["archive_buffer_bytes"] == 0)
        wait_until(lambda: previous() is None)
        store._archive_frame = original_archive
        now[0] += 601 * 10**9
        filename = store.submit(b"c" * 16)
        archive_id = store.mark_error(now[0], "third")
        destination = tmp_path / "errors" / archive_id / filename.split("/")[-1]
        wait_until(destination.exists)
        assert destination.read_bytes() == b"c" * 16
        wait_until(lambda: store.stats()["archive_buffer_bytes"] == 0)
    finally:
        release.set()
        store.close(timeout=0)
        worker.join(3)
        assert not worker.is_alive()


def test_archive_delete_and_close_release_queued_buffers(tmp_path):
    import time

    store = ScreenshotStore(tmp_path, lambda: 0, logger=Mock())
    try:
        store.submit(b"frame")
        archive_id = store.mark_error(time.time_ns(), "first")
        archive = tmp_path / "errors" / archive_id
        archive.mkdir(parents=True)
        (archive / "event.json").write_text("{}", encoding="utf-8")
        assert store.stats()["archive_buffer_bytes"] == 5
        assert store.delete_error_archive(archive_id)
        assert store.stats()["archive_buffer_bytes"] == 0
        # 重复删除不再扣减已释放的任务引用。
        assert not store.delete_error_archive(archive_id)
        assert store.stats()["archive_buffer_bytes"] == 0
        store.mark_error(time.time_ns(), "second")
        assert store.stats()["archive_buffer_bytes"] == 5
        store.close(timeout=0)
        assert store.stats()["archive_buffer_bytes"] == 0
        store.close(timeout=0)
        assert store.stats()["archive_buffer_bytes"] == 0
        assert store.stats()["archive_buffer_dropped"] == 0
        with store._lock:
            store._assert_archive_buffer_locked()
    finally:
        store.close(timeout=0)


def test_archive_buffer_counts_omitted_references_per_task(tmp_path):
    # archive_buffer_dropped 按“被省略的归档任务帧引用数”累加：两个任务各省略
    # 两个引用时累计 4，而不是按去重帧数只计 2。已接受任务的保留引用不被新任务挤掉。
    now = [10**18]
    store = ScreenshotStore(
        tmp_path,
        lambda: 0,
        logger=Mock(),
        max_recent_bytes=8,
        wall_time_ns=lambda: now[0],
    )
    try:
        for payload in (b"aaaa", b"bbbb"):
            store.submit(payload)
        store.mark_error(now[0], "first")
        assert store.stats()["archive_buffer_bytes"] == 8
        now[0] += 601 * 10**9
        for payload in (b"cccc", b"dddd"):
            store.submit(payload)
        store.mark_error(now[0], "second")
        stats = store.stats()
        queued = sum(frame.size for task in store._archive_queue for frame in task[5])
        assert stats["archive_buffer_bytes"] == queued == 8
        assert stats["archive_buffer_dropped"] == 2
        now[0] += 601 * 10**9
        for payload in (b"eeee", b"ffff"):
            store.submit(payload)
        store.mark_error(now[0], "third")
        stats = store.stats()
        assert stats["archive_buffer_dropped"] == 4
        assert stats["archive_buffer_bytes"] == 8
        assert stats["archive_buffer_bytes"] <= store.max_recent_bytes
        with store._lock:
            store._assert_archive_buffer_locked()
    finally:
        store.close(timeout=0)
    assert store.stats()["archive_buffer_bytes"] == 0
    assert store.stats()["archive_buffer_dropped"] == 4


def test_concurrent_ocr_initialization_loads_one_engine(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from arknights_mower.utils import ocr_shared, rapidocr

    # 引擎门控默认按存活实例数选择，而测试进程没有实例登记；固定共享模式保留
    # “共享客户端在并发首次调用中只构造一次”的原意。
    monkeypatch.setenv("MOWER_OCR_MODE", "shared")
    entered, release = Event(), Event()
    created = []

    # 用真实类而不是 Mock 工厂：门控按引擎类型判断当前模式，只有类实例才能确认
    # 已发布的共享客户端，避免并发调用被误判为需要重建。
    class SharedEngine:
        def __init__(self, score):
            created.append(score)
            entered.set()
            assert release.wait(3)

    monkeypatch.setattr(rapidocr, "engine", None)
    monkeypatch.setattr(ocr_shared, "SharedOCREngine", SharedEngine)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(rapidocr.initialize_ocr) for _ in range(8)]
        try:
            assert entered.wait(2)
        finally:
            release.set()
        for future in futures:
            future.result(timeout=3)
    assert created == [0.3]
    assert isinstance(rapidocr.engine, SharedEngine)


def test_failed_ocr_initialization_can_retry(monkeypatch):
    from arknights_mower.utils import ocr_shared, rapidocr

    # 固定共享模式，避免实例登记缺失时退回本地引擎而绕过本用例注入的构造失败。
    monkeypatch.setenv("MOWER_OCR_MODE", "shared")
    instance = object()
    factory = Mock(side_effect=[RuntimeError("model unavailable"), instance])
    monkeypatch.setattr(rapidocr, "engine", None)
    monkeypatch.setattr(ocr_shared, "SharedOCREngine", factory)
    with pytest.raises(RuntimeError, match="model unavailable"):
        rapidocr.initialize_ocr()
    assert rapidocr.engine is None
    rapidocr.initialize_ocr()
    assert rapidocr.engine is instance


@pytest.mark.parametrize(
    "height,width,expected",
    [
        # 以下基准是 _BoundedDetectionInput 对传入图像的行为（包装器层）：生产调用中
        # RapidOCR.__call__ 会先做 letterbox（宽度/高度比 8、最小高度 30），实际检测
        # 输入可能不同；本用例固定的是包装器对原始裁剪的尺寸约束。
        # 整帧 1080x1920：长边已到 1920，只做 32 对齐（1080/32=33.75 → 34*32）。
        # 旧实现短边 736 项不生效、同样对齐为 1088x1920，整帧检测输入与旧行为一致。
        (1080, 1920, (1088, 1920)),
        # 1920x100 宽横带：长边上限 1920 优先，短边 100 只对齐到 96，不再放大到 736。
        # 旧实现会生成 736x14144。
        (100, 1920, (96, 1920)),
        # 441x48 家具名称窄裁剪：长边先定 1920，短边按同一比例落到 224。
        # 旧实现会生成 736x6752。
        (48, 441, (224, 1920)),
        # 100x80 小图：短边放大到 736，长边 920 对齐到 928，仍在 1920 以内。
        (80, 100, (736, 928)),
        # 1919：长边 59.97 个 32 单位，对齐后恰为 1920。
        (1080, 1919, (1088, 1920)),
        # 737 与 735：短边已接近 736，只做 32 对齐；737 向下、735 向上都落到 736。
        (737, 1920, (736, 1920)),
        (735, 1920, (736, 1920)),
        # 33 高文字带：长边 1920 优先，短边 1.03 个 32 单位向下取到 32。
        (33, 1920, (32, 1920)),
        # 2560x1080：长边上限 1920 生效，比例 0.75，短边 1080 落到 800。
        (1080, 2560, (800, 1920)),
    ],
)
def test_detector_input_follows_long_edge_first_geometry(
    production_ocr_engine, height, width, expected
):
    assert _detector_input(production_ocr_engine, height, width) == expected


@pytest.mark.parametrize(
    "height,width,expected",
    [
        # 同为包装器层基准；生产调用先经过 RapidOCR 内置 letterbox，实际检测输入可能不同。
        # 旧实现先按短边放大到 736（短边 ≥736 时比例为 1），再对齐到 32，无长边上限。
        # 以下输入的两种公式落点相同，用于固定标准裁剪的检测输入没有随新公式变化。
        (1080, 1920, (1088, 1920)),
        (80, 100, (736, 928)),
        (720, 1280, (736, 1312)),
        (1080, 1919, (1088, 1920)),
        (737, 1920, (736, 1920)),
        (735, 1920, (736, 1920)),
    ],
)
def test_legacy_detector_geometry_is_preserved_where_edge_caps_do_not_apply(
    production_ocr_engine, height, width, expected
):
    assert _detector_input(production_ocr_engine, height, width) == expected


def test_detector_returns_caller_coordinate_space_for_wide_crop(production_ocr_engine):
    # 先取包装器对原始裁剪的尺寸（包装器层；生产 RapidOCR.__call__ 会先做 letterbox，
    # 实际检测输入可能不同），再跑真实引擎：返回框必须仍按调用方原始图像尺寸回映射，
    # 而不是落在检测张量坐标空间（否则 x 可超过原图宽度）。
    from pathlib import Path

    from arknights_mower.solvers import furniture
    from arknights_mower.utils.image import bytes2img

    fixture = Path(__file__).parent / "fixtures/furniture/panel_on.png"
    image = bytes2img(fixture.read_bytes())
    crop = furniture.crop_relative(image, furniture.NAME_SCOPE)
    height, width = crop.shape[:2]
    detector_height, detector_width = _detector_input(
        production_ocr_engine, height, width
    )
    assert max(detector_height, detector_width) == 1920
    assert max(detector_height, detector_width) > max(height, width)
    result, _ = production_ocr_engine(crop, use_det=True, use_cls=False, use_rec=True)
    assert result
    for box, text, _score in result:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        assert text
        assert 0 <= min(xs) <= max(xs) <= width
        assert 0 <= min(ys) <= max(ys) <= height


def test_shared_ocr_rejects_single_side_above_8192():
    # 识别子系统说明同时限制单边 ≤8192 与 32 MiB 总量：10000x1000x3 只有约 30 MB，
    # 仍按单边上限以形状错误拒绝，而不是容量错误。
    from arknights_mower.utils import ocr_shared

    assert 10000 * 1000 * 3 < 32 * 1024**2
    for shape in ([10000, 1000, 3], [8193, 100, 1], [100, 8193, 1]):
        with pytest.raises(ValueError, match="需要有效的灰度或彩色图像"):
            ocr_shared.image_size(shape)
    assert ocr_shared.image_size([8192, 1, 3]) == 8192 * 3
    assert ocr_shared.image_size([1, 8192, 3]) == 8192 * 3
    # 总量上限仍是独立错误类别。
    with pytest.raises(ValueError, match="图像超过容量上限"):
        ocr_shared.image_size([8192, 8192, 1])


def test_shared_client_rejects_oversized_side_before_starting_service(
    monkeypatch, tmp_path
):
    import numpy as np

    from arknights_mower.utils import ocr_shared

    engine = ocr_shared.SharedOCREngine(directory=tmp_path)
    started = Mock(side_effect=AssertionError("不得为被拒绝的图像启动服务"))
    monkeypatch.setattr(ocr_shared, "open_service", started)
    with pytest.raises(ValueError, match="需要有效的灰度或彩色图像"):
        engine(np.zeros((10000, 1000, 3), dtype=np.uint8))
    started.assert_not_called()


def test_production_ocr_bounds_detector_tensor(production_ocr_engine):
    # 直接调用包装器，固定的是包装器层张量边界；生产调用会先经过 RapidOCR 内置
    # letterbox（宽度/高度比 8、最小高度 30），实际检测输入可能不同。
    for height, width in ((48, 440), (1080, 1920), (1920, 1080), (100, 100)):
        actual_height, actual_width = _detector_input(
            production_ocr_engine, height, width
        )
        assert max(actual_height, actual_width) <= 1920
        assert actual_height % 32 == 0
        assert actual_width % 32 == 0
    # 小字仍放大，宽文字带不会生成 736 × 6752 的检测输入。
    assert _detector_input(production_ocr_engine, 48, 440) == (224, 1920)


def test_actual_detector_rebuilds_bounded_preprocess_each_call(
    production_ocr_engine, monkeypatch
):
    import numpy as np

    detector = production_ocr_engine._sdk.text_det
    original_session = detector.session
    shapes = []

    def capture(tensor):
        shapes.append(tensor.shape)
        return original_session(tensor)

    monkeypatch.setattr(detector, "session", capture)
    for height, width in ((48, 441), (65, 1920)):
        production_ocr_engine(
            np.zeros((height, width, 3), dtype=np.uint8),
            use_cls=False,
            use_rec=False,
        )
    assert shapes == [(1, 3, 480, 1920), (1, 3, 480, 1920)]
