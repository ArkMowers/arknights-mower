"""Serialize bounded shared ADB recovery across application processes."""

import errno
import json
import math
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import (
    SharedADBError,
    SharedADBHandshakeTimeout,
    SharedADBStopTimeout,
    _check_server_environment,
    adb_client_version,
    check_adb_version,
    kill_adb_server,
    probe_adb_server,
)
from arknights_mower.utils.device.adb_client.server_process import (
    adb_listener_absent,
    terminate_verified_adb,
)
from arknights_mower.utils.device.manager_io import run_command
from arknights_mower.utils.log import logger


class SharedADBRecovery:
    """Use a monotonic failure window and a persisted wall-clock kill cooldown."""

    def __init__(
        self,
        *,
        lock_path=None,
        run=None,
        probe=None,
        kill=None,
        monotonic=time.monotonic,
        wall_clock=time.time,
        sleep=time.sleep,
        cooldown=30,
    ):
        self.adb_path = ""
        self.generation = 0
        self._shared_generation = 0
        self._lock_path = (
            Path(lock_path)
            if lock_path is not None
            else Path.home() / ".cache" / "arknights-mower" / "adb-5037.lock"
        )
        self._run = run or run_command
        self._probe = probe
        self._kill = kill
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._sleep = sleep
        self._cooldown = max(0, min(60, cooldown))
        self._failed_since = None
        self._last_failure = None
        self._failed_probes = 0

    def _clear_failures(self):
        self._failed_since = None
        self._last_failure = None
        self._failed_probes = 0

    def _remaining(self, deadline, cancelled):
        try:
            is_cancelled = cancelled is not None and cancelled()
        except MowerExit:
            self._clear_failures()
            raise
        if is_cancelled:
            self._clear_failures()
            raise MowerExit
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            self._clear_failures()
            raise SharedADBError("共享 ADB 恢复的时间预算已耗尽")
        return remaining

    def _pause(self, deadline, cancelled):
        self._sleep(min(0.1, self._remaining(deadline, cancelled)))
        self._remaining(deadline, cancelled)

    def _observe(self, deadline, cancelled):
        timeout = min(1, self._remaining(deadline, cancelled))
        try:
            version = (
                self._probe(timeout)
                if self._probe is not None
                else probe_adb_server(timeout, monotonic=self._monotonic)
            )
        except (SharedADBError, OSError) as exc:
            self._remaining(deadline, cancelled)
            if isinstance(exc, SharedADBHandshakeTimeout) and exc.phase == "connect":
                try:
                    absent = adb_listener_absent(
                        remaining=lambda: self._remaining(deadline, cancelled)
                    )
                except (SharedADBError, OSError):
                    self._remaining(deadline, cancelled)
                else:
                    self._remaining(deadline, cancelled)
                    if absent is True:
                        return None, None
            return None, exc
        self._remaining(deadline, cancelled)
        if version is not None and (type(version) is not int or version <= 0):
            return None, SharedADBError("共享 ADB server 的协议版本无效")
        return version, None

    def _require_host_timeout(self, error):
        if error is not None and not isinstance(error, SharedADBHandshakeTimeout):
            self._clear_failures()
            raise SharedADBError("共享 ADB 握手无法验证，保留现有监听") from error

    @contextmanager
    def _locked(self, deadline, cancelled):
        self._remaining(deadline, cancelled)
        self._lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "r+b") as handle:
            if os.name == "nt" and os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            locked = False
            try:
                while not locked:
                    self._remaining(deadline, cancelled)
                    try:
                        if os.name == "nt":
                            import msvcrt

                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                    except OSError as exc:
                        if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                            raise
                        self._pause(deadline, cancelled)
                self._remaining(deadline, cancelled)
                yield handle
            finally:
                if locked:
                    if os.name == "nt":
                        import msvcrt

                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _state(self, handle):
        handle.seek(0)
        if handle.read(1) not in (b"", b"\0"):
            raise SharedADBError("共享 ADB 恢复记录无效，保留现有服务")
        record = handle.read(1025)
        if not record:
            return {"generation": 0, "last_attempt": None}
        try:
            state = json.loads(record)
            generation, last_attempt = state["generation"], state["last_attempt"]
            if (
                len(record) > 1024
                or type(generation) is not int
                or generation < 0
                or type(last_attempt) not in {int, float}
                or not math.isfinite(last_attempt)
                or last_attempt < 0
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise SharedADBError("共享 ADB 恢复记录无效，保留现有服务") from exc
        return state

    def _sync_generation(self, generation):
        if generation != self._shared_generation:
            self.generation = max(self.generation + 1, generation)
            self._shared_generation = generation

    def _healthy_generation(self, deadline, cancelled):
        self._remaining(deadline, cancelled)
        try:
            with self._lock_path.open("rb") as handle:
                self._sync_generation(self._state(handle)["generation"])
        except FileNotFoundError:
            self._sync_generation(0)
        except (SharedADBError, OSError) as exc:
            self._remaining(deadline, cancelled)
            if self._shared_generation is not None:
                self.generation += 1
                self._shared_generation = None
                logger.warning(
                    "共享 ADB 服务正常，但恢复协调记录不可读，继续使用现有服务"
                    "并重建截图与触控连接：%s",
                    str(exc)[:1024],
                )
        self._remaining(deadline, cancelled)

    def _record_attempt(self, handle, state):
        generation = state["generation"] + 1
        record = {
            "generation": generation,
            "last_attempt": self._wall_clock(),
        }
        handle.seek(0)
        handle.write(b"\0" + json.dumps(record, allow_nan=False).encode("ascii"))
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
        self._sync_generation(generation)

    def _wait_absent(self, deadline, cancelled):
        while True:
            version, error = self._observe(deadline, cancelled)
            if error is None and version is None:
                return
            self._pause(deadline, cancelled)

    def _start(self, adb_path, client_version, deadline, cancelled):
        version, error = self._observe(deadline, cancelled)
        if error is not None:
            raise SharedADBError("启动前无法确认共享 ADB server 状态") from error
        if version is not None:
            check_adb_version(client_version, version)
            return
        result = self._run(
            [adb_path, "start-server"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=self._remaining(deadline, cancelled),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        result.check_returncode()
        self._remaining(deadline, cancelled)
        while True:
            version, error = self._observe(deadline, cancelled)
            self._require_host_timeout(error)
            if error is None and version is not None:
                check_adb_version(client_version, version)
                return
            self._pause(deadline, cancelled)

    def recover(self, adb_path, *, timeout, cancelled=None, action=None):
        """Return true after starting/restarting; generation retains failed attempts."""
        deadline = self._monotonic() + max(0, timeout)
        self._remaining(deadline, cancelled)
        _check_server_environment(os.environ)
        self.adb_path = adb_path
        try:
            try:
                client_version = adb_client_version(
                    adb_path,
                    timeout=self._remaining(deadline, cancelled),
                    run=self._run,
                )
            except SharedADBError:
                self._clear_failures()
                raise
            self._remaining(deadline, cancelled)
            version, error = self._observe(deadline, cancelled)
            self._require_host_timeout(error)
            initial_error = error
            if error is None:
                self._clear_failures()
            if error is None and version is not None:
                try:
                    check_adb_version(client_version, version)
                except SharedADBError:
                    self._clear_failures()
                    raise
                self._healthy_generation(deadline, cancelled)
                self._remaining(deadline, cancelled)
                return False
            with self._locked(deadline, cancelled) as handle:
                state = self._state(handle)
                self._sync_generation(state["generation"])
                version, error = self._observe(deadline, cancelled)
                self._require_host_timeout(error)
                if error is None and version is not None:
                    self._clear_failures()
                    check_adb_version(client_version, version)
                    return False
                if error is not None:
                    now = self._monotonic()
                    if (
                        self._last_failure is None
                        or not 0 <= now - self._last_failure <= 60
                        or initial_error is None
                    ):
                        self._clear_failures()
                        self._failed_since = now
                    self._last_failure = now
                    self._failed_probes = min(2, self._failed_probes + 1)
                    if self._failed_probes < 2 or now - self._failed_since < 30:
                        raise SharedADBError(
                            "共享 ADB 主机握手超时尚未持续至少 30 秒，保留服务"
                        ) from error
                else:
                    self._clear_failures()
                last_attempt = state["last_attempt"]
                if (
                    error is not None
                    and last_attempt is not None
                    and self._wall_clock() - last_attempt < self._cooldown
                ):
                    raise SharedADBError("共享 ADB 恢复处于冷却期，保留当前服务")

                restarted = False

                def rebuild():
                    nonlocal restarted
                    self._remaining(deadline, cancelled)
                    latest_version, latest_error = self._observe(deadline, cancelled)
                    self._require_host_timeout(latest_error)
                    if latest_error is None and latest_version is not None:
                        self._clear_failures()
                        check_adb_version(client_version, latest_version)
                        return True
                    if latest_error is not None and error is None:
                        self._clear_failures()
                        raise SharedADBError("启动前主机握手超时，尚未确认持续失活")
                    self._record_attempt(handle, state)
                    self._clear_failures()
                    operation = "重启" if latest_error is not None else "启动"
                    logger.warning(
                        "共享 ADB 服务无应答，正在%s共享服务；"
                        "其他主机工具的 ADB 连接可能断开",
                        operation,
                    )
                    try:
                        if latest_error is not None:
                            kill_timeout = min(1, self._remaining(deadline, cancelled))
                            try:
                                if self._kill is not None:
                                    self._kill(kill_timeout)
                                else:
                                    kill_adb_server(
                                        kill_timeout, monotonic=self._monotonic
                                    )
                            except SharedADBStopTimeout as exc:
                                logger.warning(
                                    "共享 ADB 协议停止无应答，正在核对端口占用进程"
                                )

                                def probe_stop(timeout):
                                    if self._probe is not None:
                                        return self._probe(timeout)
                                    return probe_adb_server(
                                        timeout, monotonic=self._monotonic
                                    )

                                try:
                                    stopped = terminate_verified_adb(
                                        adb_path,
                                        min(5, self._remaining(deadline, cancelled)),
                                        probe=probe_stop,
                                        monotonic=self._monotonic,
                                        cancelled=cancelled,
                                    )
                                except (SharedADBError, OSError) as stop_error:
                                    raise SharedADBError(
                                        f"{exc}；{stop_error}"
                                    ) from stop_error
                                if not stopped:
                                    resumed_version, resumed_error = self._observe(
                                        deadline, cancelled
                                    )
                                    self._require_host_timeout(resumed_error)
                                    if (
                                        resumed_error is None
                                        and resumed_version is not None
                                    ):
                                        check_adb_version(
                                            client_version, resumed_version
                                        )
                                        return True
                            self._remaining(deadline, cancelled)
                            self._wait_absent(deadline, cancelled)
                        self._start(adb_path, client_version, deadline, cancelled)
                        self._remaining(deadline, cancelled)
                    except (SharedADBError, OSError, subprocess.SubprocessError) as exc:
                        logger.warning(
                            "共享 ADB 服务%s未成功，保留现状：%s",
                            operation,
                            str(exc)[:1024],
                        )
                        raise
                    logger.info("共享 ADB 服务已%s，连接恢复正常", operation)
                    restarted = True
                    return True

                if action is None:
                    rebuild()
                else:
                    action(rebuild)
                self._remaining(deadline, cancelled)
                return restarted
        except (OSError, subprocess.SubprocessError) as exc:
            self._remaining(deadline, cancelled)
            self._clear_failures()
            raise SharedADBError(f"共享 ADB 恢复失败：{exc}") from exc
