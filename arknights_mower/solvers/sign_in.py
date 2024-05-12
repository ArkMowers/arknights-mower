import sys
from importlib import reload
from io import BytesIO
from shutil import rmtree
from urllib.request import urlopen
from zipfile import ZipFile

from arknights_mower.utils.image import loadimg
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


def update_sign_in_solver():
    extract_path = get_path("@internal/tmp/hot_update", "")
    if extract_path.exists():
        rmtree(extract_path)
    for i in range(3):
        try:
            logger.info("签到活动：开始更新")
            with urlopen("https://mower.zhaozuohong.vip/hot_update.zip") as u:
                ZipFile(BytesIO(u.read())).extractall(extract_path)
            break
        except Exception as e:
            logger.info(f"更新出错：{e}")
    if i >= 3:
        logger.error("签到活动更新失败！")
        return

    extract_path = str(extract_path)
    global sign_in
    if "sign_in" in sys.modules:
        loadimg.cache_clear()
        reload(sign_in)
    else:
        if extract_path not in sys.path:
            sys.path.append(extract_path)
        import sign_in

    return sign_in.SignInSolver
