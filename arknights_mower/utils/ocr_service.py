"""按需启动的共享 OCR 服务，与启动器和各账号实例独立存活。"""

import hmac
import math
import multiprocessing as mp
import os
import secrets
import socket
import sys
from pathlib import Path
from threading import Thread
from time import monotonic

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.ocr_shared import (
    BACKLOG,
    IDLE_TIMEOUT,
    MAX_HEADER_BYTES,
    REQUEST_TIMEOUT,
    VERSION,
    checked_options,
    image_size,
    read_json,
    receive,
    remaining,
    send_json,
)


def _engine():
    import cv2

    from arknights_mower.utils.rapidocr import create_engine

    cv2.setNumThreads(2)
    return create_engine(threads=2)


MAX_REQUESTS = 256


def _serve(listener, control, token, idle_timeout, factory, max_requests):
    import numpy as np

    engine = None
    completed = 0
    listener.settimeout(idle_timeout)
    while True:
        try:
            channel, _ = listener.accept()
        except TimeoutError:
            return
        with channel:
            deadline = monotonic() + 5
            control.send(deadline)
            try:
                header = read_json(channel, deadline, MAX_HEADER_BYTES)
                if (
                    not isinstance(header, dict)
                    or header.get("version") != VERSION
                    or not isinstance(header.get("token"), str)
                    or not hmac.compare_digest(header["token"], token)
                ):
                    raise ValueError("共享 OCR 身份校验失败")
                requested_deadline = header.get("deadline")
                if type(requested_deadline) not in (int, float) or not math.isfinite(
                    requested_deadline
                ):
                    raise ValueError("共享 OCR 截止时间无效")
                deadline = min(requested_deadline, monotonic() + REQUEST_TIMEOUT)
                remaining(deadline)
                size = image_size(header.get("shape"))
                options = checked_options(header.get("options"))
                control.send(deadline)
                send_json(channel, {"status": "ready"}, deadline)
                image = np.frombuffer(
                    receive(channel, size, deadline), np.uint8
                ).reshape(header["shape"])
                try:
                    if engine is None:
                        try:
                            engine = factory()
                        except Exception as exc:
                            send_json(
                                channel,
                                {"status": "error", "error": str(exc)[:512]},
                                deadline,
                            )
                            return
                    # RapidOCR 的 kwargs 会改变内部阈值，每次请求重置以隔离实例。
                    options = {
                        "text_score": 0.3,
                        "box_thresh": 0.5,
                        "unclip_ratio": 1.6,
                        **options,
                    }
                    result = engine(image, **options)
                    remaining(deadline)
                    send_json(channel, {"status": "ok", "result": result}, deadline)
                    del result
                finally:
                    del image
            except Exception as exc:
                try:
                    send_json(
                        channel, {"status": "error", "error": str(exc)[:512]}, deadline
                    )
                except (OSError, ValueError, TimeoutError):
                    pass
            finally:
                control.send(None)
        if engine is not None:
            completed += 1
            if completed >= max_requests:
                control.send("recycle")
                return


def _register(kind, state, model_directory):
    state = Path(state).resolve()
    with runtime.submission_lock(state):
        owner = runtime.read_json(state / "active/owner.json", {})
        if runtime.active_job(state) and owner.get("id") != os.environ.get(
            "MOWER_RESTART_JOB"
        ):
            raise RuntimeError("更新或进程操作期间不能启动共享 OCR")
        registration = runtime.RuntimeRegistration(
            kind, directory=state, maintenance=False
        )
        registration.record["supervision_directory"] = str(model_directory)
        registration.publish()
    return registration


def _worker(
    listener,
    control,
    token,
    directory,
    idle_timeout,
    factory,
    max_requests,
    state_directory,
):
    def parent_eof():
        try:
            control.recv()
        except (EOFError, OSError):
            os._exit(0)

    exitcode = 1
    try:
        Thread(target=parent_eof, name="ocr-parent-channel", daemon=True).start()
        # 独立登记先于模型加载，并与更新提交共用准入锁。
        registration = _register(
            "ocr-worker", Path(state_directory), Path(directory) / "model"
        )

        def shutdown():
            while not registration.closed.wait(0.05):
                if registration.shutdown_requested():
                    os._exit(0)

        Thread(target=shutdown, name="ocr-worker-shutdown", daemon=True).start()
        # 协调进程突然退出后，旧模型未释放前不允许构造替代模型。
        with runtime.supervision_lock(Path(directory) / "model", timeout=0):
            _serve(listener, control, token, idle_timeout, factory, max_requests)
        exitcode = 0
    finally:
        try:
            listener.close()
        finally:
            try:
                control.close()
            finally:
                # 保留登记直至进程退出，原生会话也随进程释放。
                os._exit(exitcode)


def serve(
    directory,
    *,
    idle_timeout=IDLE_TIMEOUT,
    factory=_engine,
    state_directory=None,
    max_requests=MAX_REQUESTS,
):
    directory = Path(directory)
    with runtime.supervision_lock(directory / "service", timeout=0):
        state = (
            Path(state_directory)
            if state_directory is not None
            else runtime.state_dir()
        )
        registration = _register("ocr-service", state, directory / "model")
        try:
            _coordinate(directory, registration, idle_timeout, factory, max_requests)
        finally:
            registration.close()


def _coordinate(directory, registration, idle_timeout, factory, max_requests):
    endpoint = directory / "endpoint.json"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(BACKLOG)
        token = secrets.token_hex(32)
        try:
            while not registration.shutdown_requested():
                recycle = _generation(
                    listener,
                    token,
                    directory,
                    endpoint,
                    registration,
                    idle_timeout,
                    factory,
                    max_requests,
                )
                if not recycle:
                    break
        finally:
            endpoint.unlink(missing_ok=True)


def _generation(
    listener,
    token,
    directory,
    endpoint,
    registration,
    idle_timeout,
    factory,
    max_requests,
):
    from arknights_mower.utils.device.owned import close_process

    context = mp.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_worker,
        args=(
            listener,
            child,
            token,
            directory,
            idle_timeout,
            factory,
            max_requests,
            registration.directory,
        ),
        daemon=True,
    )
    recycle = False
    try:
        process.start()
        child.close()
        runtime.write_json(
            endpoint,
            {
                "version": VERSION,
                "port": listener.getsockname()[1],
                "token": token,
                "pid": os.getpid(),
                "worker_pid": process.pid,
            },
        )
        deadline = monotonic() + REQUEST_TIMEOUT
        while not registration.shutdown_requested():
            try:
                if parent.poll(0.05):
                    message = parent.recv()
                    if message == "recycle":
                        recycle = True
                        deadline = monotonic() + 3
                    else:
                        deadline = message
                if not process.is_alive():
                    # 即使工作进程已退出，也先读完它在退出前发送的回收通知。
                    if parent.poll():
                        continue
                    break
            except (EOFError, OSError):
                # Windows 的 poll 也会报告管道关闭；保留已收到的回收通知。
                break
            if deadline is not None and monotonic() >= deadline:
                break
    finally:
        parent.close()
        child.close()
        close_process(process, os.getpid(), timeout=0.5)
        runtime.instances(registration.directory, timeout=0, strict=False)
    return recycle


def main():
    mp.freeze_support()
    serve(sys.argv[-1])


if __name__ == "__main__":
    main()
