from __future__ import annotations

import socket
from typing import Tuple, List

from .socket import Socket
from .. import config
from ..log import logger


class Session(object):
    """ Session between ADB client and ADB server """

    def __init__(self, server: Tuple[str, int] = None, timeout: int = None) -> None:
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

    def connect(self, device: str) -> None:
        """ connect device [ip:port] """
        if len(device.split(':')) != 2 or not device.split(':')[-1].isdigit():
            raise ValueError('wrong format of device address')
        resp = self.request(f'host:connect:{device}').response()
        logger.debug(f'adb connect {device}: {repr(resp)}')
        if b'unable' in resp or b'cannot' in resp:
            raise RuntimeError(repr(resp))

    def disconnect(self, device: str) -> None:
        """ disconnect device [ip:port] """
        if len(device.split(':')) != 2 or not device.split(':')[-1].isdigit():
            raise ValueError('wrong format of device address')
        resp = self.request(f'host:disconnect:{device}').response()
        logger.debug(f'adb disconnect {device}: {repr(resp)}')
        if b'unable' in resp or b'cannot' in resp:
            raise RuntimeError(repr(resp))

    def devices_list(self) -> List[Tuple[str, str]]:
        """ returns list of devices that the adb server knows """
        resp = self.request('host:devices').response().decode(errors='ignore')
        devices = [tuple(line.split('\t')) for line in resp.splitlines()]
        return devices
