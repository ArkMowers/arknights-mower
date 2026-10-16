"""离线复现后台消费停滞时的内存保留。"""

import logging
from unittest.mock import Mock

from arknights_mower.utils import log
from arknights_mower.utils.screenshot import ScreenshotStore


def test_frontend_log_without_consumer_keeps_only_recent_messages(monkeypatch):
    queue = type(log.frontend_log_queue)()
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

    queue = log.LatestLogQueue(maxsize=2)
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

    queue = log.LatestLogQueue(maxsize=8)
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
        store.mark_error(time.time_ns(), "second")
        assert store.stats()["archive_buffer_bytes"] == 5
        store.close(timeout=0)
        assert store.stats()["archive_buffer_bytes"] == 0
        store.close(timeout=0)
        assert store.stats()["archive_buffer_bytes"] == 0
    finally:
        store.close(timeout=0)


def test_concurrent_ocr_initialization_loads_one_engine(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from arknights_mower.utils import rapidocr

    entered, release = Event(), Event()
    instance = object()

    def construct(score):
        entered.set()
        assert release.wait(3)
        return instance

    factory = Mock(side_effect=construct)
    monkeypatch.setattr(rapidocr, "engine", None)
    monkeypatch.setattr(rapidocr, "create_engine", factory)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(rapidocr.initialize_ocr) for _ in range(8)]
        try:
            assert entered.wait(2)
        finally:
            release.set()
        for future in futures:
            future.result(timeout=3)
    assert rapidocr.engine is instance
    factory.assert_called_once_with(0.3)


def test_failed_ocr_initialization_can_retry(monkeypatch):
    import pytest

    from arknights_mower.utils import rapidocr

    instance = object()
    factory = Mock(side_effect=[RuntimeError("model unavailable"), instance])
    monkeypatch.setattr(rapidocr, "engine", None)
    monkeypatch.setattr(rapidocr, "create_engine", factory)
    with pytest.raises(RuntimeError, match="model unavailable"):
        rapidocr.initialize_ocr()
    assert rapidocr.engine is None
    rapidocr.initialize_ocr()
    assert rapidocr.engine is instance


def test_production_ocr_bounds_detector_tensor():
    import numpy as np

    from arknights_mower.utils.rapidocr import create_engine

    engine = create_engine()
    preprocess = engine.text_det.preprocess_op
    for height, width in ((48, 440), (1080, 1920), (1920, 1080), (100, 100)):
        tensor = preprocess(np.zeros((height, width, 3), dtype=np.uint8))
        assert tensor.shape[:2] == (1, 3)
        assert max(tensor.shape[2:]) <= 1920
        assert all(size % 32 == 0 for size in tensor.shape[2:])
    # 小字仍放大，宽文字带不会生成 736 × 6752 的检测输入。
    tensor = preprocess(np.zeros((48, 440, 3), dtype=np.uint8))
    assert tensor.shape[2] > 48
    assert tensor.shape[3] == 1920
