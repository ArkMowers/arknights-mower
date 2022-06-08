from __future__ import annotations

import socket

from ...log import logger

DEFAULT_HOST = '127.0.0.1'


class Session(object):
    """ manage socket connections between PC and Android """

    def __init__(self, port: int, buf_size: int = 0) -> None:
        self.port = port
        self.buf_size = buf_size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((DEFAULT_HOST, port))
        socket_out = self.sock.makefile()

        # v <version>
        # protocol version, usually it is 1. needn't use this
        socket_out.readline()

        # ^ <max-contacts> <max-x> <max-y> <max-pressure>
        _, max_contacts, max_x, max_y, max_pressure, *_ = (
            socket_out.readline().strip().split(' '))
        self.max_contacts = max_contacts
        self.max_x = max_x
        self.max_y = max_y
        self.max_pressure = max_pressure

        # $ <pid>
        _, pid = socket_out.readline().strip().split(' ')
        self.pid = pid

        logger.debug(
            f'minitouch running on port: {self.port}, pid: {self.pid}')
        logger.debug(
            f'max_contact: {max_contacts}; max_x: {max_x}; max_y: {max_y}; max_pressure: {max_pressure}')

    def __enter__(self) -> Session:
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        pass

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        """ cancel connection """
        self.sock and self.sock.close()
        self.sock = None

    def send(self, content: str) -> bytes:
        content = content.encode('utf8')
        self.sock.sendall(content)
        return self.sock.recv(self.buf_size)
