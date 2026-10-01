from __future__ import annotations

import os
import socket
import struct
import time
from threading import Lock

from arknights_mower.utils.device.adb_client.server import (
    adb_server_address,
    adb_server_scope,
    current_adb_server,
)
from arknights_mower.utils.device.adb_client.socket import Socket, verify_owned_server
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.log import logger


class Session:
    """Session between ADB client and ADB server"""

    def __init__(self):
        self.owner_pid = os.getpid()
        self._lock = Lock()
        self._closed = False
        self.server = adb_server_address()
        self.timeout = 5
        self.device_id = None
        self.server_owner = current_adb_server()
        self.server_generation = (
            self.server_owner.generation if self.server_owner is not None else None
        )
        verify_owned_server(
            self.server_owner, self.server, self.server_generation, timeout=self.timeout
        )
        self.sock = Socket(self.server, self.timeout)

    def __enter__(self) -> Session:
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def close(self):
        if self.owner_pid != os.getpid():
            return
        with self._lock:
            self._closed = True
            sock, self.sock = getattr(self, "sock", None), None
        if sock is not None:
            sock.close()

    def interrupt(self):
        if self.owner_pid != os.getpid():
            return
        with self._lock:
            self._closed = True
            sock = getattr(self, "sock", None)
        if sock is not None:
            sock.interrupt()

    def detach(self):
        """Transfer the live stream to its helper, with one explicit owner."""
        with self._lock:
            if self._closed:
                raise ConnectionError("ADB 会话已关闭")
            sock, self.sock = self.sock, None
            self._closed = True
            return sock

    def request(self, cmd: str) -> Session:
        """Retry only read-only host queries and connection-local transport selection."""
        cmdbytes = cmd.encode()
        data = b"%04X%b" % (len(cmdbytes), cmdbytes)
        retryable = cmd in {
            "host:version",
            "host:devices",
            "host:transport-any",
        } or cmd.startswith("host:transport:")
        while self.timeout <= 10:
            try:
                try:
                    if self._closed or self.owner_pid != os.getpid():
                        raise ConnectionError("ADB 会话已关闭或所有权不匹配")
                    io_timeout(self.timeout)
                    verify_owned_server(
                        self.server_owner,
                        self.server,
                        self.server_generation,
                        timeout=self.timeout,
                    )
                except Exception as exc:
                    exc.input_not_sent = True
                    raise
                self.sock.send(data).check_okay()
                return self
            except socket.timeout:
                # A send or acknowledgement timeout cannot prove the service
                # did not run. Its caller owns recovery and the input verdict.
                if not retryable:
                    self.close()
                    raise
                # Never open another socket after the application deadline.
                with self._lock:
                    expired, self.sock = self.sock, None
                if expired is not None:
                    expired.close()
                io_timeout(self.timeout)
                if self.timeout >= 10:
                    raise
                logger.warning(f"socket.timeout: {self.timeout}s, +5s")
                self.timeout += 5
                verify_owned_server(
                    self.server_owner,
                    self.server,
                    self.server_generation,
                    timeout=self.timeout,
                )
                with adb_server_scope(self.server_owner):
                    replacement = Socket(self.server, self.timeout)
                with self._lock:
                    if self._closed:
                        replacement.close()
                        raise ConnectionError("ADB 会话已关闭")
                    self.sock = replacement
        raise socket.timeout(f"server: {self.server}")

    def response(self, recv_all: bool = False) -> bytes:
        """receive response"""
        if recv_all:
            return self.sock.recv_all()
        else:
            return self.sock.recv_response()

    def exec(self, cmd: str) -> bytes:
        """exec: cmd"""
        if len(cmd) == 0:
            raise ValueError("no command specified for exec")
        return self.request("exec:" + cmd).response(True)

    def shell(self, cmd: str) -> bytes:
        """shell: cmd"""
        if len(cmd) == 0:
            raise ValueError("no command specified for shell")
        return self.request("shell:" + cmd).response(True)

    def host(self, cmd: str) -> bytes:
        """host: cmd"""
        if len(cmd) == 0:
            raise ValueError("no command specified for host")
        return self.request("host:" + cmd).response()

    def run(self, cmd: str, recv_all: bool = False) -> bytes:
        """run command"""
        if len(cmd) == 0:
            raise ValueError("no command specified")
        return self.request(cmd).response(recv_all)

    def device(self, device_id: str = None) -> Session:
        """switch to a device"""
        self.device_id = device_id
        if device_id is None:
            return self.request("host:transport-any")
        else:
            return self.request("host:transport:" + device_id)

    def connect(self, device: str, throw_error: bool = False) -> None:
        """connect device [ip:port]"""
        resp = self.request(f"host:connect:{device}").response()
        logger.debug(f"adb connect {device}: {repr(resp)}")
        if throw_error and (b"unable" in resp or b"cannot" in resp):
            raise RuntimeError(repr(resp))

    def disconnect(self, device: str, throw_error: bool = False) -> None:
        """disconnect device [ip:port]"""
        resp = self.request(f"host:disconnect:{device}").response()
        logger.debug(f"adb disconnect {device}: {repr(resp)}")
        if throw_error and (b"unable" in resp or b"cannot" in resp):
            raise RuntimeError(repr(resp))

    def devices_list(self) -> list[tuple[str, str]]:
        """returns list of devices that the adb server knows"""
        resp = self.request("host:devices").response().decode(errors="ignore")
        devices = [tuple(line.split("\t")) for line in resp.splitlines()]
        logger.debug(devices)
        return devices

    def push(self, target_path: str, target: bytes, mode=0o100755, mtime: int = None):
        """push data to device"""
        self.request("sync:")
        request = b"%s,%d" % (target_path.encode(), mode)
        self.sock.send(b"SEND" + struct.pack("<I", len(request)) + request)
        buf = bytearray(65536 + 8)
        buf[0:4] = b"DATA"
        idx = 0
        while idx < len(target):
            content = target[idx : idx + 65536]
            content_len = len(content)
            idx += content_len
            buf[4:8] = struct.pack("<I", content_len)
            buf[8 : 8 + content_len] = content
            self.sock.sendall(bytes(buf[0 : 8 + content_len]))
        if mtime is None:
            mtime = int(time.time())
        self.sock.send(b"DONE" + struct.pack("<I", mtime))
        response = self.sock.recv_exactly(8)
        if response[:4] != b"OKAY":
            raise RuntimeError("push failed")
