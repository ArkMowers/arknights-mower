import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from arknights_mower.utils.log import logger

NEWS_HOST = "https://ak.hypergryph.com"
NEWS_API = f"{NEWS_HOST}/api/news"
NEWS_TZ = ZoneInfo("Asia/Shanghai")

_TIME_PATTERN = re.compile(
    r"(?:\D|^)"
    r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})日\s*"
    r"(\d{1,2}):(\d{2})\s*[~至－–—-]\s*"
    r"(\d{1,2}):(\d{2})"
)
_START_TIME_PATTERN = re.compile(
    r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})日\s*(\d{1,2}):(\d{2})"
)
_MAINTENANCE_MARKERS = ("停机维护", "闪断更新")
_MAJOR_UPDATE_MARKERS = (
    "强制更新",
    "重新下载和安装",
    "新版本预下载",
    "客户端进行版本更新",
    "客户端版本更新",
    "客户端版本强制更新",
)
_NO_PACKAGE_UPDATE_MARKERS = (
    "无需更新客户端",
    "无需重新下载",
    "不需要更新客户端",
)


@dataclass(frozen=True)
class MaintenanceInfo:
    start: datetime
    end: datetime
    update_type: Literal["hot", "major"]
    title: str
    url: str
    announcement_id: str
    manual: bool = False
    prepare: bool = True
    restart_after_update: bool = True
    preparation_pending: bool = False

    @property
    def allows_early_login(self) -> bool:
        if self.manual:
            return False
        return self.update_type == "major" or "停机维护" in self.title

    @property
    def is_flash_update(self) -> bool:
        return "闪断更新" in self.title

    @property
    def resume_at(self) -> datetime:
        """Try downtime maintenance half an hour before the announced end."""
        if self.allows_early_login:
            return max(self.start, self.end - timedelta(minutes=30))
        return self.end

    def active_at(self, now: datetime) -> bool:
        if self.manual and (
            self.preparation_pending
            or self.update_type == "major"
            and not self.restart_after_update
        ):
            return self.start <= now
        return self.start <= now < self.resume_at


class NewsChecker:
    last_check_date = None
    cached_st = None
    cached_et = None
    cached_maintenance = None
    last_check_ts = None
    manual_maintenance_provider = staticmethod(lambda: ())

    @classmethod
    def get_manual_maintenances(cls, now=None):
        now = now or datetime.now()
        return [
            info
            for info in cls.manual_maintenance_provider()
            if now < info.end or info.active_at(now)
        ]

    @classmethod
    def get_effective_maintenance(cls):
        now = datetime.now()
        announced = cls.get_maintenance()
        candidates = cls.get_manual_maintenances(now)
        if announced is not None:
            candidates.append(announced)
        # 已开始的维护先接管；官网要求更新客户端时仍使用原有停止流程。
        return min(
            candidates,
            key=lambda info: (
                not info.active_at(now),
                not (
                    info.active_at(now)
                    and not info.manual
                    and info.update_type == "major"
                ),
                not (
                    info.active_at(now) and info.manual and info.update_type == "major"
                ),
                not (info.manual and info.active_at(now)),
                info.start,
            ),
            default=None,
        )

    @classmethod
    def get_major_maintenance(cls, now=None):
        now = now or datetime.now()
        candidates = [cls.get_maintenance(), *cls.get_manual_maintenances(now)]
        return min(
            (
                info
                for info in candidates
                if info is not None
                and info.update_type == "major"
                and not info.is_flash_update
                and (now < info.start or info.manual and info.active_at(now))
            ),
            key=lambda info: info.start,
            default=None,
        )

    @classmethod
    def get_daily_reset(cls, now=None):
        """Represent the next 04:00 server refresh as an instantaneous flash update."""
        now = now or datetime.now()
        now_server = now.astimezone(NEWS_TZ)
        reset = now_server.replace(hour=4, minute=0, second=0, microsecond=0)
        if reset <= now_server:
            reset += timedelta(days=1)
        local_reset = reset.astimezone(now.tzinfo).replace(tzinfo=None)
        return MaintenanceInfo(
            start=local_reset,
            end=local_reset,
            update_type="hot",
            title="每日服务器刷新（即时闪断更新）",
            url="",
            announcement_id=f"daily-reset-{reset:%Y-%m-%d}",
        )

    @classmethod
    def _cached_result(cls, now_server, now_local):
        if cls.last_check_date != now_server.strftime("%Y-%m-%d"):
            return None, False
        if not cls.last_check_ts:
            return None, False
        cache_age = now_server - cls.last_check_ts
        cache_ttl = timedelta(hours=3)
        if cls.cached_maintenance is None:
            # Do not miss a same-day flash update published after an earlier check.
            cache_ttl = timedelta(minutes=30)
        if cache_age >= cache_ttl:
            return None, False
        info = cls.cached_maintenance
        if info is not None and now_local >= info.end:
            return None, True
        logger.debug("使用缓存的维护公告")
        return info, True

    @classmethod
    def _fetch_announcements(cls):
        announcements = []
        # The endpoint currently returns six entries per page. Reading three pages
        # prevents a still-relevant maintenance notice from being pushed off page 1.
        for page in range(1, 4):
            response = requests.get(
                NEWS_API,
                params={"category": "ANNOUNCEMENT", "page": page},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                raise ValueError("官网公告接口返回了无法识别的数据")
            items = payload["data"].get("list", [])
            if not isinstance(items, list):
                raise ValueError("官网公告列表格式错误")
            announcements.extend(items)
            if not items or payload["data"].get("end"):
                break
        return announcements

    @classmethod
    def _fetch_detail(cls, announcement_id):
        url = f"{NEWS_HOST}/news/{announcement_id}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml").get_text(" ", strip=True)

    @classmethod
    def _parse_maintenance(cls, item, detail, now_server, local_tz):
        title = str(item.get("title", ""))
        brief = str(item.get("brief", ""))
        text = " ".join((title, brief, detail))
        match = _TIME_PATTERN.search(text)
        if not match:
            return None

        year = int(match.group(1)) if match.group(1) else now_server.year
        month, day = int(match.group(2)), int(match.group(3))
        start_hour, start_minute = int(match.group(4)), int(match.group(5))
        end_hour, end_minute = int(match.group(6)), int(match.group(7))
        start = datetime(year, month, day, start_hour, start_minute, tzinfo=NEWS_TZ)
        if end_hour == 24:
            end_hour = 0
            end = datetime(year, month, day, end_hour, end_minute, tzinfo=NEWS_TZ)
            end += timedelta(days=1)
        else:
            end = datetime(year, month, day, end_hour, end_minute, tzinfo=NEWS_TZ)
            if end <= start:
                end += timedelta(days=1)

        requires_package = not any(
            marker in text for marker in _NO_PACKAGE_UPDATE_MARKERS
        ) and any(marker in text for marker in _MAJOR_UPDATE_MARKERS)
        update_type = "major" if requires_package else "hot"
        announcement_id = str(item.get("cid", ""))
        return MaintenanceInfo(
            start=start.astimezone(local_tz).replace(tzinfo=None),
            end=end.astimezone(local_tz).replace(tzinfo=None),
            update_type=update_type,
            title=title,
            url=f"{NEWS_HOST}/news/{announcement_id}",
            announcement_id=announcement_id,
        )

    @classmethod
    def _summary_is_expired(cls, summary, now_server):
        """Avoid downloading details for obviously old maintenance notices."""
        match = _START_TIME_PATTERN.search(summary)
        if not match:
            return False
        year = int(match.group(1)) if match.group(1) else now_server.year
        start = datetime(
            year,
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
            int(match.group(5)),
            tzinfo=NEWS_TZ,
        )
        return now_server >= start + timedelta(days=1)

    @classmethod
    def get_maintenance(cls):
        local_tz = datetime.now().astimezone().tzinfo
        now_server = datetime.now(NEWS_TZ)
        now_local = datetime.now()

        cached, cache_hit = cls._cached_result(now_server, now_local)
        if cache_hit:
            return cached

        try:
            announcements = cls._fetch_announcements()
            candidates = []
            for item in announcements:
                summary = f"{item.get('title', '')} {item.get('brief', '')}"
                if not any(marker in summary for marker in _MAINTENANCE_MARKERS):
                    continue
                if cls._summary_is_expired(summary, now_server):
                    continue
                detail = cls._fetch_detail(item.get("cid", ""))
                info = cls._parse_maintenance(item, detail, now_server, local_tz)
                # Keep major-update metadata through the official end time. From
                # resume_at onward it no longer blocks Mower, but it defines the
                # early-login retry window.
                if info is not None and now_local < info.end:
                    candidates.append(info)
            info = min(candidates, key=lambda value: value.start, default=None)
        except Exception as exc:
            logger.error(f"请求维护公告出错：{exc}")
            info = cls.cached_maintenance
            if info is not None and now_local >= info.end:
                info = None
            return info

        cls.last_check_ts = now_server
        cls.last_check_date = now_server.strftime("%Y-%m-%d")
        cls.cached_maintenance = info
        cls.cached_st = info.start if info is not None else None
        cls.cached_et = info.resume_at if info is not None else None
        if info is not None:
            update_name = "大版本" if info.update_type == "major" else "服务器维护/热"
            logger.debug(
                f"检测到{update_name}更新：{info.title}，{info.start} - {info.end}"
            )
        return info

    @classmethod
    def get_update_time(cls):
        """Return the maintenance interval used by task scheduling.

        Downtime maintenance deliberately ends 30 minutes before the announced
        time so Mower may attempt to enter an early-opened server. Flash updates
        still use their full announced interval.
        """
        info = cls.get_maintenance()
        if info is None or not info.prepare:
            return None, None
        return info.start, info.resume_at
