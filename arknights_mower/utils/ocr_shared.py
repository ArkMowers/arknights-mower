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

from arknights_mower.utils.rapidocr import DEFAULT_TEXT_SCORE

REQUEST_TIMEOUT = 60.0
START_TIMEOUT = 10.0
IDLE_TIMEOUT = 60.0
# 认证 preamble 之后的请求头接收预算；保持文档中的五秒值。
HEADER_TIMEOUT = 5.0
# 未认证连接只允许占用固定长度 preamble 的接收时间。
PREAUTH_TIMEOUT = 1.0
CONNECT_TIMEOUT = 1.0
RECYCLE_GRACE = 3.0
ACCEPT_POLL = 0.05
CLOSE_TIMEOUT = 0.5
STARTUP_RETRY = 0.02
CONNECT_RETRY = 0.05
ERROR_TEXT_LIMIT = 512
SERVICE_LOG_NAME = "service.log"
SERVICE_LOG_ROTATED = "service.log.1"
SERVICE_LOG_BYTES = 64 * 1024
SERVICE_LOG_TAIL = 2048
SERVICE_DEADLINE_ENV = "MOWER_OCR_SERVICE_DEADLINE"
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_HEADER_BYTES = 4096
BACKLOG = 32
# 前置认证改变了首帧顺序；端点中的版本号让旧服务的端点按失效端点处理。
VERSION = 2
PREAMBLE_MAGIC = b"MOWR"
PREAMBLE = struct.Struct("!4sB64s")
AUTH_FAILED = "共享 OCR 身份校验失败"
VERSION_MISMATCH = "共享 OCR 协议版本不一致"
INVALID_REQUEST = "共享 OCR 请求无效"
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


def prepare_directory(directory):
    """以 0700 创建共享目录；Windows 无 POSIX 权限位，跳过 chmod。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if sys.platform != "win32":
        try:
            directory.chmod(0o700)
        except OSError:
            pass


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


def _open_service_log(directory):
    path = Path(directory) / SERVICE_LOG_NAME
    try:
        if path.stat().st_size >= SERVICE_LOG_BYTES:
            rotated = Path(directory) / SERVICE_LOG_ROTATED
            rotated.unlink(missing_ok=True)
            path.replace(rotated)
    except OSError:
        pass
    return path.open("ab", buffering=0)


def read_service_log(directory):
    """读取协调进程日志尾部，供客户端附带启动失败原因。"""
    try:
        text = (Path(directory) / SERVICE_LOG_NAME).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return ""
    return text[-SERVICE_LOG_TAIL:].strip()


def _startup_failure(directory):
    detail = read_service_log(directory)
    message = "共享 OCR 服务启动失败"
    if detail:
        message = f"{message}：{detail}"
    return RuntimeError(message)


def start_service(directory, deadline=None):
    from arknights_mower.utils import update_runtime as runtime
    from arknights_mower.utils.path import get_path

    directory = Path(directory)
    prepare_directory(directory)
    environment = os.environ.copy()
    environment["MOWER_DATA_DIR"] = str(get_path("@app", space="").resolve())
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if deadline is not None:
        # 两个解释器共享同一系统单调时钟，协调进程据此限定注册等待预算。
        environment[SERVICE_DEADLINE_ENV] = repr(float(deadline))
    try:
        log = _open_service_log(directory)
    except OSError:
        log = None
    try:
        process = subprocess.Popen(
            service_command(directory),
            cwd=runtime.installation_root(),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=log if log is not None else subprocess.DEVNULL,
            **runtime.detached_options(),
        )
    finally:
        if log is not None:
            log.close()
    # 服务独立存活；创建它的实例只负责回收退出状态，不终止共享进程。
    Thread(target=process.wait, name="ocr-service-reaper", daemon=True).start()
    return process


def send_preamble(channel, token, deadline):
    send(
        channel, PREAMBLE.pack(PREAMBLE_MAGIC, VERSION, token.encode("ascii")), deadline
    )


def _endpoint(directory):
    from arknights_mower.utils import update_runtime as runtime

    endpoint = runtime.read_json(Path(directory) / "endpoint.json", {})
    token = endpoint.get("token") if isinstance(endpoint, dict) else None
    if (
        not isinstance(endpoint, dict)
        or endpoint.get("version") != VERSION
        or type(endpoint.get("port")) is not int
        or not 0 < endpoint["port"] <= 65535
        or type(endpoint.get("pid")) is not int
        or endpoint["pid"] <= 0
        or not isinstance(token, str)
        or len(token) != 64
        or any(char not in "0123456789abcdef" for char in token)
    ):
        return None
    if not runtime.process_alive(endpoint["pid"]):
        # 协调进程已消失：删除残留端点，让下一次请求直接冷启动。删除前
        # 重新读取并比对，避免把并发冷启动刚发布的新端点当成残留删掉。
        path = Path(directory) / "endpoint.json"
        if runtime.read_json(path, {}) == endpoint:
            path.unlink(missing_ok=True)
        return None
    return endpoint


def _connect_endpoint(endpoint, deadline):
    timeout = min(CONNECT_TIMEOUT, remaining(deadline))
    try:
        return socket.create_connection(
            ("127.0.0.1", endpoint["port"]), timeout=timeout
        )
    except OSError:
        # 连接被拒绝、超时或端口尚未监听都只表示本次未能连接。
        return None


def _wait_for_service(directory, deadline):
    """等待存活协调进程释放连接名额，而不是启动第二个协调进程。"""
    while True:
        endpoint = _endpoint(directory)
        if endpoint is None:
            return None
        channel = _connect_endpoint(endpoint, deadline)
        if channel is not None:
            return channel, endpoint["token"]
        sleep(min(CONNECT_RETRY, remaining(deadline)))


def open_service(directory, deadline):
    from arknights_mower.utils import update_runtime as runtime

    directory = Path(directory)
    prepare_directory(directory)
    if connection := _wait_for_service(directory, deadline):
        return connection
    # 仅在尚未发送请求时协调冷启动；发送后的错误不自动重放。
    with runtime.supervision_lock(directory / "startup", timeout=remaining(deadline)):
        if connection := _wait_for_service(directory, deadline):
            return connection
        startup_deadline = min(deadline, monotonic() + START_TIMEOUT)
        try:
            process = start_service(directory, deadline)
        except OSError as exc:
            raise RuntimeError(f"共享 OCR 服务启动失败：{exc}") from exc
        while True:
            if connection := _wait_for_service(directory, startup_deadline):
                return connection
            if process.poll() is not None or monotonic() >= startup_deadline:
                raise _startup_failure(directory)
            sleep(min(STARTUP_RETRY, remaining(startup_deadline)))


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
    """校验协议选项白名单。

    协议保留三个推理开关（use_det/use_cls/use_rec）与三个阈值；生产调用方只发送
    三个布尔开关，阈值由服务端的默认值补齐。
    """
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


def _refusal(response):
    if isinstance(response, dict):
        error = response.get("error")
        if isinstance(error, str) and error:
            return f"共享 OCR 拒绝请求：{error}"
    return "共享 OCR 拒绝请求"


class SharedOCREngine:
    """同一调用方串行提交，排队期间只发送小型请求头。"""

    def __init__(
        self, score=DEFAULT_TEXT_SCORE, *, directory=None, timeout=REQUEST_TIMEOUT
    ):
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
                send_preamble(channel, token, deadline)
                authenticated = read_json(channel, deadline)
                if (
                    not isinstance(authenticated, dict)
                    or authenticated.get("status") != "authenticated"
                ):
                    raise RuntimeError(_refusal(authenticated))
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
                if not isinstance(ready, dict) or ready.get("status") != "ready":
                    raise RuntimeError(_refusal(ready))
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
