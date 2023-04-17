from __future__ import annotations

import http
import socket
import tempfile

import requests

from ... import __system__
from ..log import logger


def download_file(target_url: str) -> str:
    """ download file to temp path, and return its file path for further usage """
    logger.debug(f'downloading: {target_url}')
    resp = requests.get(target_url, verify=False)
    with tempfile.NamedTemporaryFile('wb+', delete=False) as f:
        file_name = f.name
        f.write(resp.content)
    return file_name

# def is_port_using(host: str, port: int) -> bool:
#     """ if port is using by others, return True. else return False """
#     s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     s.settimeout(1)

#     try:
#         result = s.connect_ex((host, port))
#         # if port is using, return code should be 0. (can be connected)
#         return result == 0
#     finally:
#         s.close()
