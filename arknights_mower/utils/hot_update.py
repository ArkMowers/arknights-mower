import os
import sys
from datetime import datetime, timedelta
from importlib import reload
from io import BytesIO
from shutil import rmtree
from time import mktime
from zipfile import ZipFile

import requests
from htmllistparse import fetch_listing

from arknights_mower.utils.image import loadimg
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path

extract_path = get_path("@install/tmp/hot_update")
mirror = "https://mower.zhaozuohong.vip"
sign_in = None
navigation = None

last_listing = None, []
last_update = None


def load_module(download_update):
    global sign_in
    global navigation
    if "sign_in" in sys.modules and "navigation" in sys.modules:
        if download_update:
            loadimg.cache_clear()
            reload(sign_in)
            reload(navigation)
    else:
        if extract_path not in sys.path:
            sys.path.append(str(extract_path))
        import navigation
        import sign_in


def get_listing():
    global last_listing
    last_time, listing = last_listing
    if last_time and datetime.now() - last_time < timedelta(minutes=10):
        return listing
    cwd, listing = fetch_listing(mirror)
    last_listing = datetime.now(), listing
    return listing


def update():
    global last_update

    if last_update and datetime.now() - last_update < timedelta(minutes=30):
        logger.info("跳过热更新检查")
        load_module(False)
        return

    logger.info("检查热更新资源")
    listing = get_listing()
    filename = "hot_update.zip"
    entry = next(i for i in listing if i.name == filename)
    remote_time = datetime.fromtimestamp(mktime(entry.modified))
    download_update = True
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
                r = requests.get(f"{mirror}/{filename}")
                ZipFile(BytesIO(r.content)).extractall(extract_path)
                break
            except Exception as e:
                logger.exception(f"热更新出错：{e}")
        if i >= retry_times:
            logger.error("热更新失败！")
            return
        logger.info("热更新成功")
    else:
        logger.info("本地资源已是最新")

    last_update = datetime.now()
    load_module(download_update)
