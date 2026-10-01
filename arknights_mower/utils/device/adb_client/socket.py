from __future__ import annotations

import os
import socket
from threading import Lock

from arknights_mower.utils.device.adb_client.server import current_adb_server
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.log import logger


def verify_owned_server(owner, endpoint, generation, *, timeout=None):
    """An owned connection never adopts another listener or server generation."""
    if owner is None:
        return
    if owner.generation != generation or owner.address != endpoint:
        raise ConnectionError("ADB 服务已重建，旧连接不能继续使用")
    if timeout is not None:
        owner.check(owner.adb_path, timeout=io_timeout(timeout))
        if owner.generation != generation or owner.address != endpoint:
            raise ConnectionError("ADB 服务已重建，旧连接不能继续使用")


class Socket:
    """Connect ADB server with socket"""

    def __init__(self, server: tuple[str, int], timeout: float) -> None:
        try:
            self.owner_pid = os.getpid()
            self._close_lock = Lock()
            self._interrupted = False
            self.sock = None
            self.timeout = timeout
            self.server = server
            self.server_owner = current_adb_server()
            self.server_generation = (
                self.server_owner.generation if self.server_owner is not None else None
            )
            verify_owned_server(
                self.server_owner, server, self.server_generation, timeout=timeout
            )
            self.sock = socket.create_connection(server, timeout=io_timeout(timeout))
            verify_owned_server(self.server_owner, server, self.server_generation)
            io_timeout(timeout)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except ConnectionRefusedError as e:
            logger.error(f"ConnectionRefusedError: {server}")
            raise e
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> Socket:
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def _verify_server(self, *, timeout=None):
        verify_owned_server(
            getattr(self, "server_owner", None),
            getattr(self, "server", None),
            getattr(self, "server_generation", None),
            timeout=timeout,
        )

    def close(self) -> None:
        """Detach once and interrupt a blocking send/receive before closing."""
        self.interrupt()

    def interrupt(self):
        """Windows requires closing the socket to reliably wake blocked I/O."""
        if getattr(self, "owner_pid", None) != os.getpid():
            return
        with self._close_lock:
            if self._interrupted:
                return
            self._interrupted = True
            sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                sock.close()

    def recv_all(self, chunklen: int = 65536) -> bytes:
        data = []
        buf = bytearray(chunklen)
        view = memoryview(buf)
        pos = 0
        while True:
            if pos >= chunklen:
                data.append(buf)
                buf = bytearray(chunklen)
                view = memoryview(buf)
                pos = 0
            rcvlen = self.recv_into(view, len(view))
            if rcvlen == 0:
                break
            view = view[rcvlen:]
            pos += rcvlen
        data.append(buf[:pos])
        return b"".join(data)

    def recv_exactly(self, len: int) -> bytes:
        buf = bytearray(len)
        view = memoryview(buf)
        pos = 0
        while pos < len:
            rcvlen = self.recv_into(view, len - pos)
            if rcvlen == 0:
                break
            view = view[rcvlen:]
            pos += rcvlen
        if pos != len:
            raise ConnectionError("recv_exactly %d bytes failed" % len)
        return bytes(buf)

    def recv_response(self) -> bytes:
        """read a chunk of length indicated by 4 hex digits"""
        len = int(self.recv_exactly(4), 16)
        if len == 0:
            return b""
        return self.recv_exactly(len)

    def check_okay(self) -> None:
        """check if first 4 bytes is "OKAY" """
        result = self.recv_exactly(4)
        if result != b"OKAY":
            raise ConnectionError(self.recv_response())

    def recv(self, len: int) -> bytes:
        self._verify_server()
        self.sock.settimeout(io_timeout(self.timeout))
        data = self.sock.recv(len)
        self._verify_server()
        io_timeout(self.timeout)
        return data

    def send(self, data: bytes) -> Socket:
        """send data to server"""
        return self.sendall(data)

    def sendall(self, data: bytes) -> Socket:
        """send data to server"""
        try:
            self._verify_server(timeout=self.timeout)
            self.sock.settimeout(io_timeout(self.timeout))
        except Exception as exc:
            exc.input_not_sent = True
            raise
        self.sock.sendall(data)
        self._verify_server()
        io_timeout(self.timeout)
        return self

    def recv_into(self, buffer, nbytes: int) -> int:
        self._verify_server()
        self.sock.settimeout(io_timeout(self.timeout))
        received = self.sock.recv_into(buffer, nbytes)
        self._verify_server()
        io_timeout(self.timeout)
        return received
