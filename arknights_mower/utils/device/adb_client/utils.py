import subprocess
from typing import Union

from arknights_mower import __system__
from arknights_mower.utils.device.adb_client.server import guard_adb
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.log import logger


def run_cmd(cmd: list[str], decode: bool = False) -> Union[bytes, str]:
    logger.debug(f"run command: {cmd}")
    try:
        timeout = guard_adb(cmd[0], timeout=io_timeout(10), run=subprocess.run)
        r = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        )
        io_timeout(10)
    except subprocess.CalledProcessError as e:
        logger.debug(e.output)
        raise e
    if decode:
        return r.decode("utf8")
    return r
