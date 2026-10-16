"""跨实例 OCR 客户端与有界本机传输，不在调用方加载模型。"""

import hashlib
import json
import math
import os
import socket
import struct
import subprocess
import sys
from pathlib import Path
from threading import Lock, Thread
from time import monotonic, sleep

REQUEST_TIMEOUT = 60.0
START_TIMEOUT = 10.0
IDLE_TIMEOUT = 60.0
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_HEADER_BYTES = 4096
BACKLOG = 32
VERSION = 1
_LENGTH = struct.Struct("!I")


def remaining(deadline):
    value = deadline - monotonic()
    if value <= 0:
        raise TimeoutError("共享 OCR 请求超过执行预算")
    return value


def receive(channel, size, deadline):
    data = bytearray()
    while len(data) < size:
        channel.settimeout(remaining(deadline))
        part = channel.recv(size - len(data))
        if not part:
            raise ConnectionError("共享 OCR 连接已关闭")
        data.extend(part)
    return data


def send(channel, data, deadline):
    channel.settimeout(remaining(deadline))
    channel.sendall(data)


def send_json(channel, value, deadline, limit=MAX_RESULT_BYTES):
    def native(value):
        if hasattr(value, "tolist"):
            return value.tolist()
        raise TypeError("OCR 结果不是可传输的数据")

    data = json.dumps(value, default=native, allow_nan=False).encode("utf-8")
    if len(data) > limit:
        raise ValueError("共享 OCR 消息超过容量上限")
    send(channel, _LENGTH.pack(len(data)) + data, deadline)


def read_json(channel, deadline, limit=MAX_RESULT_BYTES):
    size = _LENGTH.unpack(receive(channel, _LENGTH.size, deadline))[0]
    if size > limit:
        raise ValueError("共享 OCR 消息超过容量上限")
    return json.loads(receive(channel, size, deadline))


def shared_directory():
    from arknights_mower.utils import update_runtime as runtime
    from arknights_mower.utils.path import get_path

    identity = [str(runtime.installation_root()), socket.gethostname()]
    if sys.platform == "linux":
        namespace = Path("/proc/self/ns/net").stat()
        identity.append(f"{namespace.st_dev}:{namespace.st_ino}")
    key = hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()[:20]
    return get_path("@app/tmp/shared-ocr", space="") / key


def service_command(directory):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--shared-ocr-service", str(directory)]
    return [
        sys.executable,
        "-m",
        "arknights_mower.utils.ocr_service",
        str(directory),
    ]


def start_service(directory):
    from arknights_mower.utils import update_runtime as runtime

    options = (
        {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        }
        if sys.platform == "win32"
        else {"start_new_session": True}
    )
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    process = subprocess.Popen(
        service_command(directory),
        cwd=runtime.installation_root(),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **options,
    )
    # 服务独立存活；创建它的实例只负责回收退出状态，不终止共享进程。
    Thread(target=process.wait, name="ocr-service-reaper", daemon=True).start()
    return process


def _connect(directory, deadline):
    from arknights_mower.utils import update_runtime as runtime

    endpoint = runtime.read_json(directory / "endpoint.json", {})
    if (
        not isinstance(endpoint, dict)
        or endpoint.get("version") != VERSION
        or type(endpoint.get("port")) is not int
        or not 0 < endpoint["port"] <= 65535
        or not isinstance(endpoint.get("token"), str)
        or len(endpoint["token"]) != 64
    ):
        return None
    try:
        channel = socket.create_connection(
            ("127.0.0.1", endpoint["port"]), timeout=min(1.0, remaining(deadline))
        )
    except ConnectionRefusedError:
        return None
    return channel, endpoint["token"]


def open_service(directory, deadline):
    from arknights_mower.utils import update_runtime as runtime

    if connection := _connect(directory, deadline):
        return connection
    # 仅在尚未发送请求时协调冷启动；发送后的错误不自动重放。
    with runtime.supervision_lock(directory / "startup", timeout=remaining(deadline)):
        if connection := _connect(directory, deadline):
            return connection
        startup_deadline = min(deadline, monotonic() + START_TIMEOUT)
        process = start_service(directory)
        while True:
            if connection := _connect(directory, startup_deadline):
                return connection
            if process.poll() is not None:
                raise RuntimeError("共享 OCR 服务启动失败")
            sleep(min(0.02, remaining(startup_deadline)))


def image_size(shape):
    if (
        not isinstance(shape, (list, tuple))
        or len(shape) not in (2, 3)
        or any(type(size) is not int or not 0 < size <= 8192 for size in shape)
        or (len(shape) == 3 and shape[2] not in (1, 3, 4))
    ):
        raise ValueError("共享 OCR 需要有效的灰度或彩色图像")
    size = math.prod(shape)
    if size > MAX_IMAGE_BYTES:
        raise ValueError("共享 OCR 图像超过容量上限")
    return size


def checked_options(options):
    if not isinstance(options, dict) or options.keys() - {
        "use_det",
        "use_cls",
        "use_rec",
        "text_score",
        "box_thresh",
        "unclip_ratio",
    }:
        raise ValueError("共享 OCR 参数无效")
    for name, value in options.items():
        if name.startswith("use_"):
            if value is not None and type(value) is not bool:
                raise ValueError("共享 OCR 开关必须是布尔值")
        elif (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= (10 if name == "unclip_ratio" else 1)
        ):
            raise ValueError("共享 OCR 阈值无效")
    return options


class SharedOCREngine:
    """同一调用方串行提交，排队期间只发送小型请求头。"""

    def __init__(self, score=0.3, *, directory=None, timeout=REQUEST_TIMEOUT):
        self.score = checked_options({"text_score": score})["text_score"]
        self.directory = (
            Path(directory) if directory is not None else shared_directory()
        )
        self.timeout = min(REQUEST_TIMEOUT, timeout)
        self._lock = Lock()

    def __call__(self, image, use_det=None, use_cls=None, use_rec=None, **kwargs):
        import numpy as np

        if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
            raise ValueError("共享 OCR 只接收 uint8 图像数组")
        shape = list(image.shape)
        image_size(shape)
        options = checked_options(
            {
                "use_det": use_det,
                "use_cls": use_cls,
                "use_rec": use_rec,
                "text_score": self.score,
                **kwargs,
            }
        )
        deadline = monotonic() + self.timeout
        if not self._lock.acquire(timeout=remaining(deadline)):
            raise TimeoutError("共享 OCR 等待前一请求超时")
        try:
            channel, token = open_service(self.directory, deadline)
            with channel:
                send_json(
                    channel,
                    dict(
                        version=VERSION,
                        token=token,
                        shape=shape,
                        options=options,
                        deadline=deadline,
                    ),
                    deadline,
                    MAX_HEADER_BYTES,
                )
                ready = read_json(channel, deadline)
                if ready != {"status": "ready"}:
                    raise RuntimeError("共享 OCR 拒绝请求")
                # 只对已获准执行的请求生成连续传输副本。
                send(
                    channel, memoryview(np.ascontiguousarray(image)).cast("B"), deadline
                )
                response = read_json(channel, deadline)
                if not isinstance(response, dict) or response.get("status") != "ok":
                    raise RuntimeError(
                        f"共享 OCR 执行失败：{response.get('error', '无有效结果') if isinstance(response, dict) else '响应无效'}"
                    )
                return tuple(response["result"])
        finally:
            self._lock.release()
