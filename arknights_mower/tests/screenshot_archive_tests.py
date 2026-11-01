"""报错归档的 JPEG 编码、历史格式兼容及单条容量限制的离线验证。"""

import json
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import numpy as np
import pytest
from PIL import Image

from arknights_mower.tests.screenshot_pipeline_tests import wait_until
from arknights_mower.utils import diagnostics, screenshot


@pytest.mark.parametrize("retention", [0, 1])
@pytest.mark.parametrize("gray", [False, True])
def test_archived_frames_use_shared_jpeg_encoding_and_export(tmp_path, retention, gray):
    now = [time.time_ns()]
    store = screenshot.ScreenshotStore(
        tmp_path, lambda: retention, logger=Mock(), wall_time_ns=lambda: now[0]
    )
    pixels = np.random.default_rng(7).integers(0, 256, (64, 96, 3), dtype=np.uint8)
    if gray:
        pixels = pixels[:, :, 0]
    expected = pixels.copy()
    store.start()
    try:
        before = store.submit_frame(pixels)
        pixels[:] = 0
        wait_until(lambda: store.stats()["pending_count"] == 0)
        wait_until(lambda: store.latest() is not None)
        assert store.latest().data.startswith(b"\xff\xd8")
        now[0] += 10**9
        archive_id = store.mark_error(now[0], "识别失败")
        now[0] += 10**9
        after = store.submit_frame(expected)
        archive = tmp_path / "errors" / archive_id
        wait_until(
            lambda: all((archive / Path(n).name).exists() for n in (before, after))
        )
        for name in (before, after):
            assert name.endswith(".jpg")
            with Image.open(archive / Path(name).name) as image:
                assert image.format == "JPEG"
        events = diagnostics.error_events(tmp_path)
        assert len(events[0]["screenshots"]) == 2
        with (
            diagnostics.export_bundle(
                tmp_path / "log",
                tmp_path,
                datetime.fromtimestamp(int(archive_id) / 10**9),
                archive_id,
            ) as data,
            ZipFile(data) as bundle,
        ):
            names = [name for name in bundle.namelist() if name.endswith(".jpg")]
            assert len(names) == 2
    finally:
        store.close()


def archive_store(tmp_path, **options):
    store = screenshot.ScreenshotStore(tmp_path, lambda: 0, logger=Mock(), **options)
    archive_id = store.mark_error(time.time_ns(), "识别失败")
    archive = tmp_path / "errors" / archive_id
    archive.mkdir(parents=True)
    (archive / "event.json").write_text(json.dumps({"time_ns": int(archive_id)}))
    return store, archive_id, archive


def test_archive_does_not_limit_image_count_when_bytes_under_cap(tmp_path):
    assert screenshot.MAX_ARCHIVE_BYTES == 512 * 1024**2
    store, archive_id, archive = archive_store(tmp_path, archive_limit_mb=lambda: 0)
    try:
        for number in range(260):
            (archive / f"{int(archive_id) - number}.jpg").write_bytes(b"x")
        filename = store.submit(b"new image")
        assert store._archive_frame(store._queue[-1])
        source = tmp_path / f"{int(archive_id) + 1}.png"
        source.write_bytes(b"legacy image")
        store._copy_to_archive(source, archive / source.name)
        assert len(list(store._images(archive))) == 262
        assert (archive / Path(filename).name).exists()
        assert (archive / source.name).exists()
        assert not json.loads((archive / "event.json").read_text()).get("truncated")
    finally:
        store.close()


def test_archive_byte_cap_counts_existing_files_and_leaves_metadata_space(tmp_path):
    store, archive_id, archive = archive_store(tmp_path, archive_limit_mb=lambda: 0)
    try:
        # 稀疏文件验证真实 512 MiB 边界，不分配同等大小的内存。
        with (archive / "1.jpg").open("wb") as stream:
            stream.truncate(
                screenshot.MAX_ARCHIVE_BYTES - screenshot.ARCHIVE_METADATA_RESERVE - 128
            )
        store.submit(b"x" * 256)
        assert not store._archive_frame(store._queue[-1])
        source = tmp_path / "2.jpg"
        source.write_bytes(b"x" * 256)
        store._copy_to_archive(source, archive / source.name)
        assert not (archive / source.name).exists()
        assert (
            screenshot.ScreenshotStore._archive_size(archive)
            <= screenshot.MAX_ARCHIVE_BYTES
        )
        assert json.loads((archive / "event.json").read_text())["truncated"]
    finally:
        store.close()


@pytest.mark.parametrize("plan", [None, {"description": "x" * 1500}])
def test_archive_export_bounds_legacy_images_and_log_and_reports_omission(
    tmp_path, monkeypatch, plan
):
    monkeypatch.setattr(diagnostics, "MAX_ARCHIVE_BYTES", 4096)
    monkeypatch.setattr(diagnostics, "ARCHIVE_METADATA_RESERVE", 1024)
    center = datetime.now()
    archive_id = str(int(center.timestamp() * 10**9))
    archive = tmp_path / "errors" / archive_id
    archive.mkdir(parents=True)
    for number in range(3):
        (archive / f"{int(archive_id) + number}.jpg").write_bytes(b"x" * 1500)
    (archive / "logs.json").write_text(json.dumps([{"message": "x" * 3000}]))
    with diagnostics.export_bundle(
        tmp_path / "log", tmp_path, center, archive_id, scheduling_plan=plan
    ) as data:
        data.seek(0, 2)
        assert data.tell() <= 4096
        data.seek(0)
        with ZipFile(data) as bundle:
            assert len([n for n in bundle.namelist() if n.endswith(".jpg")]) == (
                2 if plan is None else 1
            )
            if plan is not None:
                assert json.loads(bundle.read("plan.json")) == plan
            assert "部分截图或日志已省略" in bundle.read("说明.txt").decode()


def test_log_snapshot_truncation_preserves_valid_json_and_manifest(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(screenshot, "MAX_ARCHIVE_LOG_BYTES", 512)
    store, archive_id, archive = archive_store(tmp_path / "screenshot")
    try:
        logs = tmp_path / "log"
        logs.mkdir()
        stamp = datetime.fromtimestamp(int(archive_id) / 10**9).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        (logs / "runtime.log").write_text(f"{stamp} task.py:1 INFO reading\n" * 50)
        store._save_error_logs(archive_id)
        contents = (archive / "logs.json").read_bytes()
        assert len(contents) <= 512
        assert 0 < len(json.loads(contents)) < 50
        assert json.loads((archive / "event.json").read_text())["truncated"]
    finally:
        store.close()
