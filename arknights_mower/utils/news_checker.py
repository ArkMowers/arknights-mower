import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from arknights_mower.utils.log import logger


class NewsChecker:
    last_check_date = None
    cached_st = None
    cached_et = None

    @classmethod
    def get_update_time(cls):
        host = "https://ak.hypergryph.com"
        url = host + "/#information"
        time_pattern = re.compile(
            r"(?:\D|^)"
            r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日"
            r"(\d{1,2}):(\d{2})\s*[~至－–—-]\s*"
            r"(\d{1,2}):(\d{2})"
        )
        news_tz = ZoneInfo("Asia/Shanghai")  # 服务器时区
        local_tz = datetime.now().astimezone().tzinfo

        now_server = datetime.now(news_tz)
        today_server_str = now_server.strftime("%Y-%m-%d")
        now_local = datetime.now()

        # 1. 如果是同一天，直接用缓存
        if cls.last_check_date == today_server_str:
            logger.debug("使用缓存的维护时间")
            return cls.cached_st, cls.cached_et

        # 2. 如果没到 9:00，不请求
        if now_server.hour < 9:
            logger.debug("今天还没到 9:00，不请求维护时间")
            return cls.cached_st, cls.cached_et

        # 3. 请求网页
        response = requests.get(url, timeout=30)
        response.encoding = "utf8"
        soup = BeautifulSoup(response.text, "lxml")

        for script_tag in soup.find_all("script"):
            text = script_tag.get_text()
            if "停机维护公告" in text or "服务器闪断更新" in text:
                m_brief = re.search(r'brief\\":\\"(.*?)\\"', text)
                if not m_brief:
                    continue
                brief_text = m_brief.group(1)

                m_time = time_pattern.search(brief_text)
                if not m_time:
                    continue

                year = int(m_time.group(1)) if m_time.group(1) else now_server.year
                month, day = int(m_time.group(2)), int(m_time.group(3))
                start_h, start_m = int(m_time.group(4)), int(m_time.group(5))
                end_h, end_m = int(m_time.group(6)), int(m_time.group(7))

                start_dt = datetime(year, month, day, start_h, start_m, tzinfo=news_tz)
                end_dt = datetime(year, month, day, end_h, end_m, tzinfo=news_tz)
                start_dt_local = start_dt.astimezone(local_tz).replace(tzinfo=None)
                end_dt_local = end_dt.astimezone(local_tz).replace(tzinfo=None)

                # 更新缓存
                cls.last_check_date = today_server_str
                cls.cached_st = start_dt_local
                cls.cached_et = end_dt_local
                if now_local > end_dt_local:
                    return None, None
                elif now_local < start_dt_local:
                    delta = start_dt_local - now_local
                    msg = f"距离维护开始还有 {delta.days}天{delta.seconds // 3600}小时{(delta.seconds % 3600) // 60}分钟"
                else:
                    delta = end_dt_local - now_local
                    msg = f"维护进行中，还剩 {delta.seconds // 60} 分钟"
                logger.debug(msg)
                return start_dt_local, end_dt_local
        return None, None
