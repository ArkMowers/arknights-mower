import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from arknights_mower.utils.log import logger


def get_update_time():
    host = "https://ak.hypergryph.com"
    url = host + "/news/"
    response = requests.get(url)
    response.encoding = "utf8"
    soup = BeautifulSoup(response.text, "lxml")
    soup.encode("utf-8")

    for h1 in soup.find_all("h1"):
        if "闪断更新公告" in h1.text:
            pattern = r"(\d+)月(\d+)日(\d+):(\d+)"
            result = re.findall(pattern, h1.text)[0]
            result = list(map(int, result))
            now = datetime.now()
            update_time = datetime(now.year, result[0], result[1], result[2], result[3])
            logger.debug(f"闪断更新时间：{update_time}")

            if now > update_time:
                logger.info("闪断更新时间已过")
            else:
                delta = update_time - now
                msg = "距离闪断更新的时间："
                if delta.days > 0:
                    msg += f"{delta.days}天{delta.seconds // 3600}小时"
                else:
                    h = delta.seconds // 3600
                    m = (delta.seconds - h * 3600) // 60
                    msg += f"{h}小时{m}分钟"
                link = h1.parent["href"]
                msg += "；更新公告：" + host + link
                logger.info(msg)
            return update_time
    return None
