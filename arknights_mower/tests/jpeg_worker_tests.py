"""JPEG worker input allocation and mapping lifetime with isolated transport."""

import tracemalloc
from unittest.mock import MagicMock, Mock

import pytest

from arknights_mower.utils import jpeg_codec, jpeg_worker


def serve_frames(tmp_path, monkeypatch, pixels, shape, encode, *, count=1):
    path = tmp_path / "frame.bin"
    path.write_bytes(pixels)
    with path.open("r+b") as stream:
        stream.truncate(jpeg_worker.MAPPING_BYTES)
    views = []
    mappings = []
    replies = []

    def consume(width, height, channels, packed):
        assert isinstance(packed, memoryview)
        views.append(packed)
        mappings.append(packed.obj)
        return encode(width, height, channels, packed)

    def send(data):
        if data == b"token":
            return
        # Each response must release its input before the next request can arrive.
        for view in views:
            with pytest.raises(ValueError, match="released memoryview"):
                view.tobytes()
        status, size = jpeg_worker.RESPONSE.unpack(data[: jpeg_worker.RESPONSE.size])
        payload = (
            data[jpeg_worker.RESPONSE.size :]
            if status
            else mappings[-1][
                jpeg_worker.MAX_RAW_BYTES : jpeg_worker.MAX_RAW_BYTES + size
            ]
        )
        replies.append((status, payload))

    channel = MagicMock()
    channel.__enter__.return_value = channel
    channel.sendall.side_effect = send
    requests = Mock()
    requests.get.side_effect = [(*shape, 0)] * count + [EOFError("requests complete")]
    monkeypatch.setattr(jpeg_worker, "Queue", Mock(return_value=requests))
    monkeypatch.setattr(jpeg_worker, "Thread", Mock())
    monkeypatch.setattr(
        jpeg_worker.socket, "create_connection", Mock(return_value=channel)
    )
    monkeypatch.setattr(jpeg_worker, "encode_packed", consume)
    with pytest.raises(EOFError, match="requests complete"):
        jpeg_worker._serve(path, 0, "token")
    assert len(views) == count
    assert all(mapping.closed for mapping in mappings)
    return replies


@pytest.mark.parametrize("channels", (1, 3))
def test_worker_encodes_mapping_views_without_changing_jpeg(
    tmp_path, monkeypatch, channels
):
    pixels = bytes(range(256)) * (48 * 32 * channels // 256)
    expected = jpeg_codec.encode_packed(48, 32, channels, pixels)
    replies = serve_frames(
        tmp_path,
        monkeypatch,
        pixels,
        (48, 32, channels),
        jpeg_codec.encode_packed,
        count=2,
    )
    assert replies == [(0, expected), (0, expected)]


def test_worker_releases_input_even_when_encoder_traceback_is_retained(
    tmp_path, monkeypatch
):
    pixels = b"\x7f" * (48 * 32 * 3)
    expected = jpeg_codec.encode_packed(48, 32, 3, pixels)
    save = jpeg_codec._save
    errors = []

    def fail_once(image):
        if not errors:
            try:
                raise MemoryError("offline allocation failure")
            except MemoryError as error:
                errors.append(error)
                raise
        return save(image)

    monkeypatch.setattr(jpeg_codec, "_save", fail_once)
    replies = serve_frames(
        tmp_path, monkeypatch, pixels, (48, 32, 3), jpeg_codec.encode_packed, count=2
    )
    assert replies == [(1, b"offline allocation failure"), (0, expected)]
    assert errors[0].__traceback__ is not None


def test_full_frame_worker_does_not_allocate_an_extra_rgb_copy(tmp_path, monkeypatch):
    pixels = b"\xdc\x1e\x0a" * (1920 * 1080)
    expected = jpeg_codec.encode_packed(1920, 1080, 3, pixels)
    tracemalloc.start()
    try:
        replies = serve_frames(
            tmp_path, monkeypatch, pixels, (1920, 1080, 3), jpeg_codec.encode_packed
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert replies == [(0, expected)]
    assert peak < jpeg_worker.MAX_RAW_BYTES // 2
