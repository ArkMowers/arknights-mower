"""Foreground ADB ownership and bounded service recovery for simulator runs."""

import os
import re
import socket
import subprocess
import sys
import time
from itertools import islice
from pathlib import Path

from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.adb_client.server import (
    SharedADBError,
    probe_adb_server,
)
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import run_manager_command
from arknights_mower.utils.log import logger


class OwnedADBCleanupError(SharedADBError):
    cleanup_failed = True


class OwnedADBProbeError(SharedADBError):
    pass


def _reserve_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    if port == 5037:
        raise SharedADBError("自有 ADB 不能使用共享端口")
    return port


def _owns_listener(pid, port, timeout):
    if sys.platform == "darwin":
        result = run_manager_command(
            [
                "/usr/sbin/lsof",
                "-nP",
                "-a",
                "-p",
                str(pid),
                "-iTCP:" + str(port),
                "-sTCP:LISTEN",
                "-Fn",
            ],
            timeout=timeout,
        )
        return f"n127.0.0.1:{port}".encode() in result.stdout.splitlines()
    if os.name == "nt":
        result = run_manager_command(
            ["netstat", "-ano", "-p", "tcp"],
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return any(
            len(fields := line.split()) == 5
            and fields[1] == f"127.0.0.1:{port}"
            and fields[3] == "LISTENING"
            and fields[4] == str(pid)
            for line in result.stdout.decode("ascii", "replace").splitlines()
        )
    expected = f"0100007F:{port:04X}"
    with Path(f"/proc/{pid}/net/tcp").open() as table:
        inodes = {
            fields[9]
            for line in islice(table, 4096)
            if len(fields := line.split()) >= 10
            and fields[1] == expected
            and fields[3] == "0A"
        }
    return any(
        os.readlink(descriptor) in {f"socket:[{inode}]" for inode in inodes}
        for descriptor in islice(Path(f"/proc/{pid}/fd").iterdir(), 4096)
    )


class OwnedADBServer:
    def __init__(
        self,
        *,
        spawn=None,
        run=None,
        probe=None,
        listener=None,
        reserve=None,
        monotonic=time.monotonic,
        sleep=csleep,
    ):
        self.owner_pid = os.getpid()
        self.process = None
        self.port = None
        self.adb_path = ""
        self.version = None
        self.generation = 0
        self._failed_since = None
        self._failed_probes = 0
        self._cleanup_error = None
        self._spawn = spawn or subprocess.Popen
        self._run = run or subprocess.run
        self._probe = probe or probe_adb_server
        self._listener = listener or _owns_listener
        self._reserve = reserve or _reserve_port
        self._monotonic = monotonic
        self._sleep = sleep

    @property
    def address(self):
        if self.port is None or self.process is None:
            raise SharedADBError("自有 ADB 服务尚未取得监听所有权")
        return "127.0.0.1", self.port

    def _remaining(self, deadline):
        csleep(0)
        if self.owner_pid != os.getpid():
            raise SharedADBError("不能使用其他进程的自有 ADB 服务")
        if self._cleanup_error is not None:
            raise self._cleanup_error
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise SharedADBError("自有 ADB 服务恢复预算已耗尽")
        return io_timeout(remaining)

    def _client_version(self, adb_path, deadline):
        result = self._run(
            [adb_path, "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=self._remaining(deadline),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._remaining(deadline)
        result.check_returncode()
        output = (
            result.stdout.encode() if isinstance(result.stdout, str) else result.stdout
        )
        matches = re.findall(
            rb"^Android Debug Bridge version 1\.0\.(\d+)\s*$", output, re.M
        )
        if len(matches) != 1 or int(matches[0]) < 41:
            raise SharedADBError(
                "自有 ADB 需要协议版本 1.0.41 或更新版本，请选择新版 SDK ADB"
            )
        return int(matches[0])

    def _record_failure(self):
        if self._failed_since is None:
            self._failed_since = self._monotonic()
        self._failed_probes += 1

    def check(self, adb_path, *, timeout):
        deadline = self._monotonic() + max(0, timeout)
        self._remaining(deadline)
        if self.process is None:
            self._start(adb_path, deadline)
            return
        if (
            adb_path != self.adb_path
            and self._client_version(adb_path, deadline) != self.version
        ):
            raise SharedADBError("所选 ADB 与自有服务协议不一致，不执行命令")
        try:
            if self.process.poll() is not None:
                raise SharedADBError("自有 ADB 服务进程已退出")
            version = self._probe(
                min(1, self._remaining(deadline)),
                address=self.address,
                monotonic=self._monotonic,
            )
            self._remaining(deadline)
            if version != self.version:
                raise SharedADBError("自有 ADB 服务未响应或协议版本改变")
            if not self._listener(
                self.process.pid, self.port, min(1, self._remaining(deadline))
            ):
                raise SharedADBError("自有 ADB 监听所有权已改变")
            self._remaining(deadline)
        except MowerExit:
            raise
        except (SharedADBError, OSError, subprocess.SubprocessError) as exc:
            self._remaining(deadline)
            self._record_failure()
            raise OwnedADBProbeError(f"自有 ADB 服务探活失败：{exc}") from exc
        self._failed_since = None
        self._failed_probes = 0

    def recover(self, adb_path, *, timeout, action=None):
        deadline = self._monotonic() + max(0, timeout)
        self._remaining(deadline)
        if self.process is not None:
            try:
                self.check(adb_path, timeout=self._remaining(deadline))
                self._remaining(deadline)
                return False
            except MowerExit:
                raise
            except OwnedADBProbeError:
                if (
                    self._failed_probes < 2
                    or self._failed_since is None
                    or self._monotonic() - self._failed_since < 30
                ):
                    raise

        def rebuild():
            self._remaining(deadline)
            if self.process is not None:
                logger.warning(
                    "自有 ADB 服务持续失活，重建本次运行的服务，保留所选实例"
                )
                self.close(timeout=min(2, self._remaining(deadline)))
            self._start(adb_path, deadline)
            return True

        return action(rebuild) if action is not None else rebuild()

    def _start(self, adb_path, deadline):
        self._remaining(deadline)
        version = self._client_version(adb_path, deadline)
        port = self._reserve()
        if not 1024 <= port <= 65535 or port == 5037:
            raise SharedADBError("自有 ADB 监听端口无效")
        environment = dict(os.environ)
        environment.update(
            ADB_USB="0",
            ADB_EMU="0",
            ADB_MDNS="0",
            ADB_MDNS_AUTO_CONNECT="0",
            ADB_SERVER_SOCKET=f"tcp:127.0.0.1:{port}",
            ANDROID_ADB_SERVER_ADDRESS="127.0.0.1",
            ANDROID_ADB_SERVER_PORT=str(port),
            ADB_SERVER_PORT=str(port),
        )
        self._remaining(deadline)
        self.process = self._spawn(
            [adb_path, "-L", f"tcp:127.0.0.1:{port}", "nodaemon", "server"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.port, self.adb_path, self.version = port, adb_path, version
        try:
            while True:
                remaining = self._remaining(deadline)
                if self.process.poll() is not None:
                    raise SharedADBError("自有 ADB 前台进程启动失败，请检查所选 ADB")
                try:
                    listening = self._listener(
                        self.process.pid, port, min(1, remaining)
                    )
                except (OSError, subprocess.SubprocessError):
                    listening = False
                try:
                    ready = (
                        listening
                        and self._probe(
                            min(1, self._remaining(deadline)),
                            address=self.address,
                            monotonic=self._monotonic,
                        )
                        == version
                    )
                except (SharedADBError, OSError):
                    ready = False
                if ready:
                    self._remaining(deadline)
                    self.generation += 1
                    self._failed_since = None
                    self._failed_probes = 0
                    logger.info("本次运行使用自有 ADB 服务：127.0.0.1:%s", port)
                    return
                self._sleep(min(0.1, self._remaining(deadline)))
        except SharedADBError as exc:
            self.close(timeout=1)
            raise SharedADBError(f"自有 ADB 启动或监听所有权未确认：{exc}") from exc
        except BaseException:
            self.close(timeout=1)
            raise

    def close(self, *, timeout=2):
        if self.owner_pid != os.getpid() or self.process is None:
            return
        if self._cleanup_error is not None:
            raise self._cleanup_error
        deadline = self._monotonic() + max(0, timeout)
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(
                        timeout=max(0, (deadline - self._monotonic()) / 2)
                    )
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=max(0, deadline - self._monotonic()))
        except Exception as exc:
            if self.process.poll() is None:
                self._cleanup_error = OwnedADBCleanupError(
                    f"关闭自有 ADB 进程失败：{exc}"
                )
                raise self._cleanup_error from exc
        self.process = None
        self.port = None
