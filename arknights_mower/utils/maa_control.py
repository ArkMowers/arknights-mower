import os
from contextlib import contextmanager
from inspect import Parameter, signature
from threading import Lock
from time import monotonic, sleep

from arknights_mower.utils import config
from arknights_mower.utils.activity_observations import clear_maa_observations
from arknights_mower.utils.log import logger

_lock = Lock()
_active_scopes = 0


@contextmanager
def execution():
    """嵌套任务沿用本轮的停止请求，最外层退出时清理。"""
    global _active_scopes
    with _lock:
        _active_scopes += 1
    try:
        yield
    finally:
        with _lock:
            _active_scopes -= 1
            if not _active_scopes:
                config.stop_maa.clear()


def request_stop():
    with _lock:
        if not _active_scopes or config.stop_mower.is_set():
            return False
        config.stop_maa.set()
        return True


def release(solver):
    """关闭本轮桌面工作进程，Android 核心继续由宿主管理。"""
    released = True
    clear_maa_observations(solver)
    if getattr(solver, "MAA", None) is not None:
        try:
            close = getattr(solver.MAA, "close", None)
            if close is not None:
                close()
        except Exception:
            released = False
            logger.exception(
                "关闭 MAA 工作进程失败", extra={"log_group": "maa-runtime"}
            )
    solver.MAA = None
    solver.maa_copilot_task = None
    solver.maa_paradox_task = None
    solver.maa_sss_task = None
    solver.maa_blackflow_task = None
    solver.maa_event_shop_task = None
    return released


def _supports_android_game_handoff(device):
    if not callable(getattr(device, "exit_after_task_stop", None)):
        return False
    try:
        from mower_android.bridge import Bridge

        timeout = signature(Bridge.call).parameters.get("socket_timeout")
    except (ImportError, AttributeError, TypeError, ValueError):
        return False
    return timeout is not None and timeout.kind in (
        Parameter.KEYWORD_ONLY,
        Parameter.POSITIONAL_OR_KEYWORD,
    )


def _confirm_android_stop():
    from mower_android.bridge import Bridge

    bridge = Bridge()
    deadline = monotonic() + 3
    while (remaining := deadline - monotonic()) > 0:
        running = bridge.call("maa_running", socket_timeout=remaining)
        if running is False and monotonic() < deadline:
            return
        if running is not True:
            break
        sleep(min(0.1, max(0, deadline - monotonic())))
    raise TimeoutError("未在 Android 核心停止确认期限内收到已停止状态")


def _exit_game(solver):
    try:
        solver.device.exit_after_task_stop()
    except Exception:
        logger.exception(
            "停止大型任务后关闭游戏失败", extra={"log_group": "maa-integration"}
        )


def _stop_for_game_handoff(solver):
    android = os.environ.get("MOWER_ANDROID") == "1"
    can_handoff = not android or _supports_android_game_handoff(solver.device)
    if not can_handoff:
        logger.warning(
            "当前 Android APK 不支持停止后保留游戏。请手动关闭游戏，并更新 APK 后使用手动接管。",
            extra={"log_group": "maa-integration"},
        )
    stopped = True
    if getattr(solver, "MAA", None) is not None:
        try:
            stopped = bool(solver.maa_stop())
            if stopped and android and can_handoff:
                _confirm_android_stop()
        except Exception:
            stopped = False
            logger.exception(
                "未能确认 MAA 已停止", extra={"log_group": "maa-integration"}
            )
    released = solver.release_maa()
    if not can_handoff:
        return
    if stopped and released:
        logger.info(
            "已停止 MAA 大型任务，保留当前游戏", extra={"log_group": "maa-integration"}
        )
        return
    logger.warning(
        "未能确认 MAA 已停止并释放资源，将尝试退出游戏",
        extra={"log_group": "maa-integration"},
    )
    _exit_game(solver)


def stop_for_mower_exit(solver, large_task_started, shop_started):
    if (
        large_task_started
        and config.stop_mower.is_set()
        and config.keep_game_on_stop.is_set()
    ):
        _stop_for_game_handoff(solver)
        return
    try:
        if getattr(solver, "MAA", None) is not None:
            solver.maa_stop()
            logger.info("停止MAA", extra={"log_group": "maa-integration"})
    finally:
        if (large_task_started or shop_started) and config.stop_mower.is_set():
            _exit_game(solver)
        solver.release_maa()
