"""Lean JPEG child entry; no device, configuration or logging imports."""

import hmac
import mmap
import os
import socket
import sys
import time
from queue import Queue
from threading import Thread

from arknights_mower.utils.jpeg_protocol import (
    MAPPING_BYTES,
    MAX_ERROR_BYTES,
    MAX_JPEG_BYTES,
    MAX_RAW_BYTES,
    REQUEST,
    RESPONSE,
    TOKEN_BYTES,
)


def encode_packed(*args):
    # Establish the EOF watcher before importing or calling native Pillow code.
    from arknights_mower.utils.jpeg_codec import encode_packed as encode

    return encode(*args)


def receive_exact(channel, size, *, deadline=None):
    data = bytearray()
    while len(data) < size:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("截图编码超过执行预算")
            channel.settimeout(remaining)
        part = channel.recv(size - len(data))
        if not part:
            raise EOFError("截图编码工作进程通道已关闭")
        data.extend(part)
    return bytes(data)


def authenticate(channel, token, *, deadline=None):
    if not hmac.compare_digest(
        receive_exact(channel, TOKEN_BYTES, deadline=deadline), token.encode("ascii")
    ):
        raise RuntimeError("截图编码工作进程身份校验失败")


def _remove_mapping(mapping_path):
    try:
        os.unlink(mapping_path)
    except OSError:
        # Windows deletes the mapping after the last kernel handle closes.
        pass


def _serve(mapping_path, port, token):
    descriptor = os.open(
        mapping_path,
        os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_TEMPORARY", 0),
    )
    with (
        os.fdopen(descriptor, "r+b") as source,
        mmap.mmap(source.fileno(), MAPPING_BYTES) as shared,
        socket.create_connection(("127.0.0.1", int(port)), timeout=5) as channel,
    ):
        channel.sendall(token.encode("ascii"))
        channel.settimeout(None)
        requests = Queue(maxsize=1)

        def watch_channel():
            try:
                while True:
                    requests.put_nowait(
                        REQUEST.unpack(receive_exact(channel, REQUEST.size))
                    )
            except (EOFError, OSError):
                # Portable EOF cleanup needs the GIL; Windows has kernel Job ownership.
                try:
                    shared.close()
                    source.close()
                finally:
                    _remove_mapping(mapping_path)
                    os._exit(0)
            except Exception:
                os._exit(1)

        Thread(target=watch_channel, name="jpeg-parent-channel", daemon=True).start()
        while True:
            width, height, channels = requests.get()
            try:
                size = width * height * channels
                if not 0 < size <= MAX_RAW_BYTES:
                    raise ValueError("截图共享输入超过单帧上限")
                with memoryview(shared) as mapped, mapped[:size] as pixels:
                    data = encode_packed(width, height, channels, pixels)
                if not 0 < len(data) <= MAX_JPEG_BYTES:
                    raise ValueError("JPEG 编码结果为空或超过单帧上限")
                shared[MAX_RAW_BYTES : MAX_RAW_BYTES + len(data)] = data
                channel.sendall(RESPONSE.pack(0, len(data)))
                del data
            except Exception as exc:
                message = str(exc).encode("utf-8", errors="replace")[:MAX_ERROR_BYTES]
                channel.sendall(RESPONSE.pack(1, len(message)) + message)


def worker_main(mapping_path, port, token):
    try:
        _serve(mapping_path, port, token)
    finally:
        _remove_mapping(mapping_path)


if __name__ == "__main__":
    worker_main(*sys.argv[1:])
