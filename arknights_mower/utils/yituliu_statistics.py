"""Read public operator survey aggregates without player identity or credentials."""

import json
import re
from threading import Lock
from time import time

import requests

from arknights_mower.utils.config import atomic_write
from arknights_mower.utils.path import get_path

SOURCE_URL = "https://auth.yituliu.cn/open/ak-operator-statistics/result"
CACHE_TTL = 24 * 60 * 60
REQUEST_TIMEOUT = (3, 8)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_lock = Lock()


def _operators(rows):
    if not isinstance(rows, list) or not rows or len(rows) > 2000:
        raise ValueError("干员调查列表无效")
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("干员调查条目无效")
        cid = row.get("charId")
        if (
            not isinstance(cid, str)
            or not re.fullmatch(r"[A-Za-z0-9_]{1,100}", cid)
            or cid in seen
        ):
            raise ValueError("干员调查标识无效")
        own, sample = row.get("own"), row.get("sampleSize")
        if (
            type(own) is not int
            or type(sample) is not int
            or not 0 <= own <= sample
            or sample < 0
        ):
            raise ValueError("干员调查样本无效")
        clean = {"charId": cid, "own": own, "sampleSize": sample}
        for key in (
            "elite",
            "skill1",
            "skill2",
            "skill3",
            "modA",
            "modX",
            "modY",
            "modD",
            "modB",
        ):
            if key not in row:
                continue
            histogram = row[key]
            levels = ("0", "1", "2") if key == "elite" else ("0", "1", "2", "3")
            if (
                not isinstance(histogram, dict)
                or any(
                    level not in levels or type(count) is not int or count < 0
                    for level, count in histogram.items()
                )
                or sum(histogram.values()) > own
            ):
                raise ValueError("干员调查分布无效")
            clean[key] = dict(histogram)
        result.append(clean)
        seen.add(cid)
    return result


def get_statistics():
    """Serve a 24-hour cache; failed refreshes retain visibly stale public data."""
    path = get_path("@app/tmp/yituliu_statistics.json")
    with _lock:
        cached, fetched_at = [], None
        try:
            saved = json.loads(path.read_text("utf-8"))
            timestamp = saved["fetched_at"]
            if type(timestamp) not in (float, int) or not 0 < timestamp <= time():
                raise ValueError("调查缓存时间无效")
            cached, fetched_at = _operators(saved["operators"]), timestamp
        except (OSError, ValueError, TypeError, KeyError):
            pass
        result = {
            "operators": cached,
            "fetched_at": fetched_at,
            "stale": True,
            "error": None,
            "source_url": SOURCE_URL,
        }
        if fetched_at is not None and time() - fetched_at < CACHE_TTL:
            return {**result, "stale": False}
        try:
            # An isolated session also excludes .netrc credentials and cookies.
            with requests.Session() as session:
                session.trust_env = False
                with session.get(
                    SOURCE_URL, timeout=REQUEST_TIMEOUT, allow_redirects=False
                ) as response:
                    response.raise_for_status()
                    if (
                        response.status_code != 200
                        or len(response.content) > MAX_RESPONSE_BYTES
                    ):
                        raise ValueError("公开调查响应无效")
                    payload = response.json()
            if not isinstance(payload, dict) or payload.get("code") != 200:
                raise ValueError("公开调查响应无效")
            rows = _operators(payload.get("data"))
        except (requests.RequestException, ValueError, TypeError):
            return {
                **result,
                "error": "公开调查暂时无法更新，已保留上次缓存"
                if cached
                else "公开调查暂时无法获取",
            }
        fetched_at = time()
        result.update(operators=rows, fetched_at=fetched_at, stale=False)
        try:
            atomic_write(
                path,
                lambda stream: json.dump(
                    {"operators": rows, "fetched_at": fetched_at},
                    stream,
                    ensure_ascii=False,
                ),
            )
        except OSError:
            result["error"] = "公开调查已获取，但本地缓存保存失败"
        return result
