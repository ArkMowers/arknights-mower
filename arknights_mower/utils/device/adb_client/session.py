from __future__ import annotations

import socket
import struct
import time

from ... import config
from ...log import logger
from .socket import Socket


class Session(object):
    """ Session between ADB client and ADB server """

    def __init__(self, server: tuple[str, int] = None, timeout: int = None) -> None:
        if server is None:
            server = (config.ADB_SERVER_IP, config.ADB_SERVER_PORT)
        if timeout is None:
            timeout = config.ADB_SERVER_TIMEOUT
        self.server = server
        self.timeout = timeout
        self.device_id = None
        self.sock = Socket(self.server, self.timeout)

    def __enter__(self) -> Session:
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        pass

    def request(self, cmd: str, reconnect: bool = False) -> Session:
        """ make a service request to ADB server, consult ADB sources for available services """
        cmdbytes = cmd.encode()
        data = b'%04X%b' % (len(cmdbytes), cmdbytes)
        while self.timeout <= 60:
            try:
                self.sock.send(data).check_okay()
                return self
            except socket.timeout:
                logger.warning(f'socket.timeout: {self.timeout}s, +5s')
                self.timeout += 5
                self.sock = Socket(self.server, self.timeout)
                if reconnect:
                    self.device(self.device_id)
        raise socket.timeout(f'server: {self.server}')

    def response(self, recv_all: bool = False) -> bytes:
        """ receive response """
        if recv_all:
            return self.sock.recv_all()
        else:
            return self.sock.recv_response()

    def exec(self, cmd: str) -> bytes:
        """ exec: cmd """
        if len(cmd) == 0:
            raise ValueError('no command specified for exec')
        return self.request('exec:' + cmd, True).response(True)

    def shell(self, cmd: str) -> bytes:
        """ shell: cmd """
        if len(cmd) == 0:
            raise ValueError('no command specified for shell')
        return self.request('shell:' + cmd, True).response(True)

    def host(self, cmd: str) -> bytes:
        """ host: cmd """
        if len(cmd) == 0:
            raise ValueError('no command specified for host')
        return self.request('host:' + cmd, True).response()

    def run(self, cmd: str, recv_all: bool = False) -> bytes:
        """ run command """
        if len(cmd) == 0:
            raise ValueError('no command specified')
        return self.request(cmd, True).response(recv_all)

    def device(self, device_id: str = None) -> Session:
        """ switch to a device """
        self.device_id = device_id
        if device_id is None:
            return self.request('host:transport-any')
        else:
            return self.request('host:transport:' + device_id)

    def connect(self, device: str, throw_error: bool = False) -> None:
        """ connect device [ip:port] """
        resp = self.request(f'host:connect:{device}').response()
        logger.debug(f'adb connect {device}: {repr(resp)}')
        if throw_error and (b'unable' in resp or b'cannot' in resp):
            raise RuntimeError(repr(resp))

    def disconnect(self, device: str, throw_error: bool = False) -> None:
        """ disconnect device [ip:port] """
        resp = self.request(f'host:disconnect:{device}').response()
        logger.debug(f'adb disconnect {device}: {repr(resp)}')
        if throw_error and (b'unable' in resp or b'cannot' in resp):
            raise RuntimeError(repr(resp))

    def devices_list(self) -> list[tuple[str, str]]:
        """ returns list of devices that the adb server knows """
        resp = self.request('host:devices').response().decode(errors='ignore')
        devices = [tuple(line.split('\t')) for line in resp.splitlines()]
        logger.debug(devices)
        return devices

    def push(self, target_path: str, target: bytes, mode=0o100755, mtime: int = None):
        """ push data to device """
        self.request('sync:', True)
        request = b'%s,%d' % (target_path.encode(), mode)
        self.sock.send(b'SEND' + struct.pack('<I', len(request)) + request)
        buf = bytearray(65536+8)
        buf[0:4] = b'DATA'
        idx = 0
        while idx < len(target):
            content = target[idx:idx+65536]
            content_len = len(content)
            idx += content_len
            buf[4:8] = struct.pack('<I', content_len)
            buf[8:8+content_len] = content
            self.sock.sendall(bytes(buf[0:8+content_len]))
        if mtime is None:
            mtime = int(time.time())
        self.sock.send(b'DONE' + struct.pack('<I', mtime))
        response = self.sock.recv_exactly(8)
        if response[:4] != b'OKAY':
            raise RuntimeError('push failed')
