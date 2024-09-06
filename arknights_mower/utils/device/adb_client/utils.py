import subprocess
from typing import Union

from arknights_mower import __system__
from arknights_mower.utils.log import logger


def run_cmd(cmd: list[str], decode: bool = False) -> Union[bytes, str]:
    logger.debug(f"run command: {cmd}")
    try:
        r = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if __system__ == "windows" else 0,
        )
    except subprocess.CalledProcessError as e:
        logger.debug(e.output)
        raise e
    if decode:
        return r.decode("utf8")
    return r
