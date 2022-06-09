from __future__ import annotations

import shutil
import subprocess
from typing import Union

from .... import __system__
from ... import config
from ...log import logger
from ..utils import download_file

ADB_BUILDIN_URL = 'https://oss.nano.ac/arknights_mower/adb-binaries'
ADB_BUILDIN_FILELIST = {
    'linux': ['adb'],
    'windows': ['adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll'],
    'darwin': ['adb'],
}


def adb_buildin() -> None:
    """ download adb_bin """
    folder = config.init_adb_buildin()
    folder.mkdir(exist_ok=True, parents=True)
    if __system__ not in ADB_BUILDIN_FILELIST.keys():
        raise NotImplementedError(f'Unknown system: {__system__}')
    for file in ADB_BUILDIN_FILELIST[__system__]:
        target_path = folder / file
        if not target_path.exists():
            url = f'{ADB_BUILDIN_URL}/{__system__}/{file}'
            logger.debug(f'adb_buildin: {url}')
            tmp_path = download_file(url)
            shutil.copy(tmp_path, str(target_path))
    config.ADB_BUILDIN = folder / ADB_BUILDIN_FILELIST[__system__][0]
    config.ADB_BUILDIN.chmod(0o744)


def run_cmd(cmd: list[str], decode: bool = False) -> Union[bytes, str]:
    logger.debug(f"run command: {cmd}")
    try:
        r = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.debug(e.output)
        raise e
    if decode:
        return r.decode('utf8')
    return r
