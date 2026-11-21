import subprocess
from typing import Union

from arknights_mower import __system__
from arknights_mower.utils.device.adb_client.server import guard_adb
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.manager_io import run_command
from arknights_mower.utils.log import logger


def run_cmd(cmd: list[str], decode: bool = False) -> Union[bytes, str]:
    logger.debug(f"run command: {cmd}")
    try:
        timeout = guard_adb(cmd[0], timeout=io_timeout(10), run=run_command)
        r = run_command(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        ).stdout
        io_timeout(10)
    except subprocess.CalledProcessError as e:
        logger.debug(e.output)
        raise e
    if decode:
        return r.decode("utf8")
    return r
