"""按需启动的共享 OCR 服务，与启动器和各账号实例独立存活。"""

import hmac
import math
import multiprocessing as mp
import os
import secrets
import socket
import sys
import traceback
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.ocr_shared import (
    ACCEPT_POLL,
    AUTH_FAILED,
    BACKLOG,
    CLOSE_TIMEOUT,
    ERROR_TEXT_LIMIT,
    HEADER_TIMEOUT,
    IDLE_TIMEOUT,
    INVALID_REQUEST,
    MAX_HEADER_BYTES,
    PREAMBLE,
    PREAMBLE_MAGIC,
    PREAUTH_TIMEOUT,
    RECYCLE_GRACE,
    REQUEST_TIMEOUT,
    SERVICE_DEADLINE_ENV,
    VERSION,
    VERSION_MISMATCH,
    checked_options,
    image_size,
    prepare_directory,
    read_json,
    receive,
    remaining,
    send_json,
)
from arknights_mower.utils.rapidocr import DEFAULT_OCR_OPTIONS


def _engine():
    import cv2

    from arknights_mower.utils.rapidocr import create_engine

    cv2.setNumThreads(2)
    return create_engine(threads=2)


MAX_REQUESTS = 256

# 协调进程与模型工作进程之间的控制消息。工作进程达到回收阈值后先暂停并
# 等待协调进程决定，不再自行退出，从而避免在更新准备期失去可用的工作进程。
CONTROL_RECYCLE = "recycle"
CONTROL_REGISTERED = "registered"
CONTROL_RESUME = "resume"
CONTROL_START = "start"
# 替代工作进程完成更新准入登记的等待上限。超过后保留旧工作进程。
HANDOFF_TIMEOUT = 10.0
# 替代工作进程在旧模型释放前等待模型监督锁的上限。
HANDOFF_MODEL_TIMEOUT = 15.0
# 协调进程无响应时恢复服务的上限，避免回收决定丢失后永久停摆。
RECYCLE_DECISION_TIMEOUT = 30.0


def _log(message):
    """诊断写协调进程 stderr；启动器已把它重定向到 service.log。"""
    if sys.stderr is not None:
        print(message, file=sys.stderr, flush=True)


class _Refusal(Exception):
    """可直接回给未认证对端的固定文案。"""


def _authenticate(channel, token, deadline):
    magic, version, candidate = PREAMBLE.unpack(
        receive(channel, PREAMBLE.size, deadline)
    )
    if magic != PREAMBLE_MAGIC:
        raise _Refusal(INVALID_REQUEST)
    if version != VERSION:
        raise _Refusal(VERSION_MISMATCH)
    try:
        valid = hmac.compare_digest(candidate.decode("ascii"), token)
    except (UnicodeDecodeError, TypeError):
        valid = False
    if not valid:
        raise _Refusal(AUTH_FAILED)


def _notify(control, message):
    try:
        control.send(message)
        return True
    except (EOFError, OSError):
        return False


def _serve(
    listener,
    control,
    token,
    idle_timeout,
    factory,
    max_requests,
    recycle_granted,
    recycle_resumed,
):
    import numpy as np

    engine = None
    completed = 0
    idle_deadline = monotonic() + idle_timeout
    pending = False
    decision_deadline = None
    while True:
        if recycle_granted.is_set():
            return
        if pending:
            if recycle_resumed.is_set():
                recycle_resumed.clear()
                pending = False
            elif decision_deadline is not None and monotonic() >= decision_deadline:
                _log("共享 OCR 工作进程等待回收决定超时，继续服务")
                recycle_resumed.clear()
                pending = False
            else:
                sleep(ACCEPT_POLL)
                continue
        wait = idle_deadline - monotonic()
        if wait <= 0:
            return
        listener.settimeout(min(ACCEPT_POLL, wait))
        try:
            channel, _ = listener.accept()
        except TimeoutError:
            continue
        idle_deadline = monotonic() + idle_timeout
        with channel:
            authenticated = False
            inferred = False
            deadline = monotonic() + PREAUTH_TIMEOUT
            try:
                _authenticate(channel, token, deadline)
                authenticated = True
                deadline = monotonic() + HEADER_TIMEOUT
                send_json(channel, {"status": "authenticated"}, deadline)
                header = read_json(channel, deadline, MAX_HEADER_BYTES)
                if not isinstance(header, dict) or header.get("version") != VERSION:
                    raise ValueError(VERSION_MISMATCH)
                requested_deadline = header.get("deadline")
                if type(requested_deadline) not in (int, float) or not math.isfinite(
                    requested_deadline
                ):
                    raise ValueError("共享 OCR 截止时间无效")
                deadline = min(requested_deadline, monotonic() + REQUEST_TIMEOUT)
                remaining(deadline)
                size = image_size(header.get("shape"))
                options = checked_options(header.get("options"))
                # 只有通过认证与准入的请求才上报协调进程执行截止时间；请求头
                # 接收与认证阶段不得决定整代服务的生命周期。
                _notify(control, deadline)
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
                                {
                                    "status": "error",
                                    "error": str(exc)[:ERROR_TEXT_LIMIT],
                                },
                                deadline,
                            )
                            return
                    # RapidOCR 的 kwargs 会改变内部阈值，每次请求重置以隔离实例。
                    options = {**DEFAULT_OCR_OPTIONS, **options}
                    inferred = True
                    result = engine(image, **options)
                    remaining(deadline)
                    send_json(channel, {"status": "ok", "result": result}, deadline)
                    del result
                finally:
                    del image
            except Exception as exc:
                if isinstance(exc, _Refusal):
                    message = str(exc)
                elif authenticated:
                    message = str(exc)[:ERROR_TEXT_LIMIT]
                else:
                    # 未认证对端只看到固定文案，不读取内部异常原文。
                    message = INVALID_REQUEST
                try:
                    send_json(
                        channel,
                        {"status": "error", "error": message},
                        deadline,
                    )
                except (OSError, ValueError, TimeoutError):
                    pass
            finally:
                _notify(control, None)
        # 只有真正进入推理的请求才计入回收；静默、非法与未认证连接不计。
        if inferred:
            completed += 1
            if completed >= max_requests:
                # 先请求协调进程判定，收到 resume 后继续用当前工作进程服务；
                # 只有协调进程完成替代登记后才发送授权并退出。
                if not _notify(control, CONTROL_RECYCLE):
                    return
                pending = True
                recycle_resumed.clear()
                decision_deadline = monotonic() + RECYCLE_DECISION_TIMEOUT


def _register(kind, state, model_directory, timeout=0.0):
    state = Path(state).resolve()
    deadline = monotonic() + timeout
    announced = False
    while True:
        try:
            with runtime.submission_lock(state):
                owner = runtime.read_json(state / "active/owner.json", {})
                busy = runtime.active_job(state) and owner.get("id") != os.environ.get(
                    "MOWER_RESTART_JOB"
                )
                if not busy:
                    registration = runtime.RuntimeRegistration(
                        kind, directory=state, maintenance=False
                    )
                    registration.record["supervision_directory"] = str(model_directory)
                    registration.publish()
                    return registration
        except runtime.LockBusyError:
            pass
        if timeout > 0 and kind == "ocr-service" and not announced:
            # 客户端先于协调进程耗尽启动子预算；把等待原因写进 service.log，
            # 客户端读取日志尾部时仍能区分"更新准备期"与普通启动失败。
            print("共享 OCR 协调进程等待更新准入", file=sys.stderr, flush=True)
            announced = True
        if monotonic() >= deadline:
            raise RuntimeError("更新或进程操作期间不能启动共享 OCR") from None
        sleep(min(0.05, max(0.0, deadline - monotonic())))


def _watch_control(
    control, recycle_granted, recycle_resumed, handoff_started, finished
):
    """持续读取协调进程消息；父进程退出时工作进程不再独立存活。"""
    while True:
        try:
            message = control.recv()
        except (EOFError, OSError):
            if finished.is_set():
                # 工作进程自己正在关闭通道，退出码由主路径决定。
                return
            os._exit(0)
        if message == CONTROL_RECYCLE:
            recycle_granted.set()
        elif message == CONTROL_RESUME:
            recycle_resumed.set()
        elif message == CONTROL_START:
            handoff_started.set()


def _worker(
    listener,
    control,
    token,
    directory,
    idle_timeout,
    factory,
    max_requests,
    state_directory,
    model_lock_timeout=0.0,
    wait_for_start=False,
):
    recycle_granted = Event()
    recycle_resumed = Event()
    handoff_started = Event()
    finished = Event()
    exitcode = 1
    try:
        Thread(
            target=_watch_control,
            args=(
                control,
                recycle_granted,
                recycle_resumed,
                handoff_started,
                finished,
            ),
            name="ocr-parent-channel",
            daemon=True,
        ).start()
        # 独立登记先于模型加载，并与更新提交共用准入锁。
        registration = _register(
            "ocr-worker", Path(state_directory), Path(directory) / "model"
        )
        # 协调进程据此在释放旧模型前确认替代工作进程已进入更新快照。
        _notify(control, CONTROL_REGISTERED)

        def shutdown():
            while not registration.closed.wait(0.05):
                if registration.shutdown_requested():
                    os._exit(0)

        Thread(target=shutdown, name="ocr-worker-shutdown", daemon=True).start()
        # 协调进程突然退出后，旧模型未释放前不允许构造替代模型；回收交接
        # 允许替代进程在旧工作进程退出前等待有限时间。
        with runtime.supervision_lock(
            Path(directory) / "model", timeout=model_lock_timeout
        ):
            if wait_for_start and not handoff_started.wait(HANDOFF_MODEL_TIMEOUT):
                # 协调进程在旧进程确认退出前不会放行替代进程，避免模型重叠。
                raise TimeoutError("共享 OCR 替代工作进程未收到交接完成通知")
            _serve(
                listener,
                control,
                token,
                idle_timeout,
                factory,
                max_requests,
                recycle_granted,
                recycle_resumed,
            )
        exitcode = 0
    except BaseException:
        # 协调进程 stderr 已重定向到 service.log；准入与模型锁失败必须可诊断，
        # 不能像旧实现那样在 finally 中静默 os._exit(1)。
        _log("共享 OCR 工作进程无法服务：" + traceback.format_exc())
    finally:
        finished.set()
        try:
            listener.close()
        finally:
            try:
                control.close()
            finally:
                # 保留登记直至进程退出，原生会话也随进程释放。
                os._exit(exitcode)


def _registration_timeout():
    value = os.environ.get(SERVICE_DEADLINE_ENV)
    try:
        deadline = float(value) if value else None
    except ValueError:
        return 0.0
    if deadline is None:
        return 0.0
    return max(0.0, min(deadline - monotonic(), REQUEST_TIMEOUT))


def serve(
    directory,
    *,
    idle_timeout=IDLE_TIMEOUT,
    factory=_engine,
    state_directory=None,
    max_requests=MAX_REQUESTS,
    registration_timeout=None,
):
    directory = Path(directory)
    prepare_directory(directory)
    if registration_timeout is None:
        registration_timeout = _registration_timeout()
    with runtime.supervision_lock(directory / "service", timeout=0):
        state = (
            Path(state_directory)
            if state_directory is not None
            else runtime.state_dir()
        )
        registration = _register(
            "ocr-service", state, directory / "model", registration_timeout
        )
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
            _generation(
                listener,
                token,
                directory,
                endpoint,
                registration,
                idle_timeout,
                factory,
                max_requests,
            )
        finally:
            endpoint.unlink(missing_ok=True)


def _send_control(control, message):
    try:
        control.send(message)
        return True
    except (EOFError, OSError):
        return False


def _start_worker(
    context,
    listener,
    token,
    directory,
    idle_timeout,
    factory,
    max_requests,
    state,
    model_lock_timeout=0.0,
    wait_for_start=False,
):
    """启动一个模型工作进程；交接时允许它先登记再等待旧模型释放。"""
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
            state,
        ),
        kwargs={
            "model_lock_timeout": model_lock_timeout,
            "wait_for_start": wait_for_start,
        },
        daemon=True,
    )
    try:
        process.start()
    except BaseException:
        parent.close()
        raise
    finally:
        child.close()
    return process, parent


def _endpoint_record(listener, token, worker_pid):
    return {
        "version": VERSION,
        "port": listener.getsockname()[1],
        "token": token,
        "pid": os.getpid(),
        "worker_pid": worker_pid,
    }


def _recycle_allowed(state):
    """回收前确认更新或进程操作没有占用准入，与工作进程登记共用提交锁。"""
    try:
        with runtime.submission_lock(state):
            owner = runtime.read_json(Path(state) / "active/owner.json", {})
            return not (
                runtime.active_job(state)
                and owner.get("id") != os.environ.get("MOWER_RESTART_JOB")
            )
    except runtime.LockBusyError:
        return False


def _handoff(
    context,
    listener,
    token,
    directory,
    idle_timeout,
    factory,
    max_requests,
    registration,
    process,
    control,
):
    """先让替代工作进程完成登记，再授权旧工作进程退出并交接监听套接字。

    旧工作进程在请求回收后暂停接受新连接。替代进程只有完成更新准入登记
    后才会获得退出授权，因此登记被拒（例如更新恰好开始）时旧工作进程仍
    可继续服务，端点和整代服务都不会消失。
    """
    from arknights_mower.utils.device.owned import close_process

    state = registration.directory
    try:
        replacement, replacement_control = _start_worker(
            context,
            listener,
            token,
            directory,
            idle_timeout,
            factory,
            max_requests,
            state,
            model_lock_timeout=HANDOFF_MODEL_TIMEOUT,
            wait_for_start=True,
        )
    except BaseException:
        _log("共享 OCR 替代工作进程未能启动：" + traceback.format_exc())
        return None
    try:
        registered = False
        deadline = monotonic() + HANDOFF_TIMEOUT
        while monotonic() < deadline and not registration.shutdown_requested():
            try:
                if replacement_control.poll(ACCEPT_POLL):
                    message = replacement_control.recv()
                    if message == CONTROL_REGISTERED:
                        registered = True
                        break
                    if isinstance(message, (int, float)):
                        continue
            except (EOFError, OSError):
                break
            if not replacement.is_alive():
                break
        if not registered:
            raise RuntimeError("替代工作进程未能在更新快照前完成登记")
        # 旧工作进程仍持有模型锁；替代进程登记后会在模型监督锁上等待。
        _send_control(control, CONTROL_RECYCLE)
        deadline = monotonic() + RECYCLE_GRACE
        while process.is_alive() and monotonic() < deadline:
            sleep(ACCEPT_POLL)
    except BaseException as exc:
        _log(f"共享 OCR 替代工作进程未能接管：{exc}")
        replacement_control.close()
        close_process(replacement, os.getpid(), timeout=CLOSE_TIMEOUT)
        return None
    return replacement, replacement_control


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
    """运行共享 OCR 服务代际。

    协调进程始终持有监听套接字与端点；工作进程达到回收阈值、且更新或
    进程操作没有占用准入时，先交接给已登记的新工作进程，再让旧进程退出。
    """
    from arknights_mower.utils.device.owned import close_process

    context = mp.get_context("spawn")
    state = registration.directory
    process, control = _start_worker(
        context,
        listener,
        token,
        directory,
        idle_timeout,
        factory,
        max_requests,
        state,
    )
    deadline = monotonic() + REQUEST_TIMEOUT
    deferred = False
    try:
        runtime.write_json(endpoint, _endpoint_record(listener, token, process.pid))
        while not registration.shutdown_requested():
            try:
                if control.poll(ACCEPT_POLL):
                    message = control.recv()
                    if message == CONTROL_RECYCLE:
                        if not _recycle_allowed(state):
                            if not deferred:
                                deferred = True
                                _log("共享 OCR 工作进程等待更新或进程操作结束后再回收")
                            _send_control(control, CONTROL_RESUME)
                            continue
                        deferred = False
                        replacement = _handoff(
                            context,
                            listener,
                            token,
                            directory,
                            idle_timeout,
                            factory,
                            max_requests,
                            registration,
                            process,
                            control,
                        )
                        if replacement is None:
                            _send_control(control, CONTROL_RESUME)
                            continue
                        old_process, old_control = process, control
                        process, control = replacement
                        old_control.close()
                        # 旧进程完全退出后才放行替代进程，避免两个模型短暂重叠。
                        close_process(old_process, os.getpid(), timeout=CLOSE_TIMEOUT)
                        _send_control(control, CONTROL_START)
                        runtime.write_json(
                            endpoint, _endpoint_record(listener, token, process.pid)
                        )
                        runtime.instances(state, timeout=0, strict=False)
                        deadline = monotonic() + REQUEST_TIMEOUT
                        continue
                    if message is None or isinstance(message, (int, float)):
                        # 请求完成后工作进程发送 None 清除执行截止时间；只有
                        # 正在执行的请求才约束整代服务的生命周期。
                        deadline = message
                if not process.is_alive():
                    # 即使工作进程已退出，也先读完它在退出前发送的回收通知。
                    if control.poll():
                        continue
                    break
            except (EOFError, OSError):
                # Windows 的 poll 也会报告管道关闭；保留已收到的回收通知。
                break
            if deadline is not None and monotonic() >= deadline:
                break
    finally:
        control.close()
        close_process(process, os.getpid(), timeout=CLOSE_TIMEOUT)
        runtime.instances(state, timeout=0, strict=False)


def main():
    mp.freeze_support()
    serve(sys.argv[-1])


if __name__ == "__main__":
    main()
