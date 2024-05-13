import os
import sys
from datetime import datetime
from importlib import reload
from io import BytesIO
from shutil import rmtree
from time import mktime
from urllib.request import urlopen
from zipfile import ZipFile

from htmllistparse import fetch_listing

from arknights_mower.utils.image import loadimg
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


def update_sign_in_solver():
    logger.info("签到活动：检查更新")
    mirror = "https://mower.zhaozuohong.vip"
    filename = "hot_update.zip"
    cwd, listing = fetch_listing(mirror)
    entry = next(i for i in listing if i.name == filename)
    remote_time = datetime.fromtimestamp(mktime(entry.modified))
    download_update = True
    extract_path = get_path("@install/tmp/hot_update", "")
    if extract_path.exists():
        local_time = datetime.fromtimestamp(os.path.getctime(extract_path))
        if local_time > remote_time:
            download_update = False
        else:
            rmtree(extract_path)
    if download_update:
        logger.info("开始下载热更新资源")
        retry_times = 3
        for i in range(retry_times):
            try:
                with urlopen(f"{mirror}/{filename}") as u:
                    ZipFile(BytesIO(u.read())).extractall(extract_path)
                break
            except Exception as e:
                logger.info(f"更新出错：{e}")
        if i >= retry_times:
            logger.error("签到活动更新失败！")
            return
        logger.info("热更新成功")
    else:
        logger.info("本地资源已是最新")

    extract_path = str(extract_path)
    global sign_in
    if "sign_in" in sys.modules:
        if download_update:
            loadimg.cache_clear()
            reload(sign_in)
    else:
        if extract_path not in sys.path:
            sys.path.append(extract_path)
        import sign_in

    return sign_in.SignInSolver
