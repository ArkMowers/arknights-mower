"""Read public operator survey aggregates without player identity or credentials."""

import json
import re
from time import monotonic, sleep, time

import requests

from arknights_mower.utils.config import atomic_write
from arknights_mower.utils.path import get_path
from arknights_mower.utils.update_runtime import (
    LockBusyError,
    read_json,
    submission_lock,
)

SOURCE_URL = "https://auth.yituliu.cn/open/ak-operator-statistics/result"
CACHE_TTL = 24 * 60 * 60
CACHE_VERSION = 2
REQUEST_TIMEOUT = (3, 8)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RETRY_COOLDOWN = 5 * 60
LOCK_WAIT_TIMEOUT = 12
_SKILL_LEVELS = frozenset(map(str, range(256)))
_FAILURES = {
    "timeout": "一图流公开统计读取超时",
    "connection": "无法连接一图流公开统计服务",
    "rate_limit": "一图流公开统计请求受到限流",
    "http": "一图流公开统计服务返回错误",
    "invalid": "一图流公开统计响应格式无效",
}


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
            valid_levels = _SKILL_LEVELS if key.startswith("skill") else levels
            if (
                not isinstance(histogram, dict)
                or any(
                    level not in valid_levels or type(count) is not int or count < 0
                    for level, count in histogram.items()
                )
                or sum(histogram.values()) > own
            ):
                raise ValueError("干员调查分布无效")
            if key.startswith("skill"):
                if any(int(level) > 10 for level in histogram):
                    continue
                # Canonical 0–3 are mastery stages. Legacy 4–7 have no mastery;
                # legacy 8–10 combine basic level seven with mastery one–three.
                normalized = {}
                for level, count in histogram.items():
                    rank = int(level)
                    stage = str(rank if rank <= 3 else max(0, rank - 7))
                    normalized[stage] = normalized.get(stage, 0) + count
                histogram = normalized
            clean[key] = dict(histogram)
        result.append(clean)
        seen.add(cid)
    return result


def _read_cache(path):
    try:
        saved = json.loads(path.read_text("utf-8"))
        timestamp = saved["fetched_at"]
        if type(timestamp) not in (float, int) or not 0 < timestamp <= time():
            return None
        return {
            "operators": _operators(saved["operators"]),
            "fetched_at": timestamp,
            "version": saved.get("version"),
        }
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _result(cache):
    fetched_at = cache["fetched_at"] if cache else None
    return {
        "operators": cache["operators"] if cache else [],
        "fetched_at": fetched_at,
        "stale": fetched_at is None
        or time() - fetched_at >= CACHE_TTL
        or cache.get("version") != CACHE_VERSION,
        "error": None,
        "source_url": SOURCE_URL,
    }


def _save_cache(path, result):
    atomic_write(
        path,
        lambda stream: json.dump(
            {
                **{key: result[key] for key in ("operators", "fetched_at")},
                "version": CACHE_VERSION,
            },
            stream,
            ensure_ascii=False,
        ),
    )


def _failure(result, reason, retry_after):
    return {
        **result,
        "error": _FAILURES[reason]
        + ("，已保留上次缓存" if result["operators"] else "")
        + "；请稍后重试",
        "retry_after": retry_after,
    }


def get_statistics():
    """Share public cache and refresh admission across configuration spaces."""
    path = get_path("@app/tmp/yituliu_statistics.json", space="")
    legacy_path = get_path("@app/tmp/yituliu_statistics.json")
    shared = _read_cache(path)
    result = _result(shared)
    if shared and not result["stale"]:
        return result
    legacy = _read_cache(legacy_path) if legacy_path != path else None
    cached = max(
        (entry for entry in (shared, legacy) if entry),
        key=lambda entry: entry["fetched_at"],
        default=None,
    )
    result = _result(cached)
    directory = path.parent / "yituliu_statistics"
    retry_path = directory / "retry.json"
    deadline = monotonic() + LOCK_WAIT_TIMEOUT
    while True:
        try:
            # The shared nonblocking native lock also coordinates separate processes.
            with submission_lock(directory):
                shared = _read_cache(path)
                if shared and (
                    cached is None or shared["fetched_at"] >= cached["fetched_at"]
                ):
                    cached = shared
                result = _result(cached)
                if not result["stale"]:
                    if shared is None or shared["fetched_at"] < result["fetched_at"]:
                        try:
                            _save_cache(path, result)
                        except OSError:
                            result["error"] = "公开调查已读取，但共享缓存保存失败"
                    return result
                retry = read_json(retry_path, {})
                if (
                    isinstance(retry, dict)
                    and type(retry.get("retry_after")) in (int, float)
                    and 0 < retry["retry_after"] - time() <= RETRY_COOLDOWN
                    and isinstance(retry.get("reason"), str)
                    and retry["reason"] in _FAILURES
                ):
                    return _failure(result, retry["reason"], retry["retry_after"])
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
                except (requests.RequestException, ValueError, TypeError) as exc:
                    if isinstance(exc, requests.Timeout):
                        reason = "timeout"
                    elif isinstance(exc, requests.HTTPError):
                        reason = (
                            "rate_limit"
                            if exc.response is not None
                            and exc.response.status_code == 429
                            else "http"
                        )
                    elif isinstance(exc, requests.ConnectionError):
                        reason = "connection"
                    else:
                        reason = "invalid"
                    retry_after = time() + RETRY_COOLDOWN
                    try:
                        atomic_write(
                            retry_path,
                            lambda stream: json.dump(
                                {"retry_after": retry_after, "reason": reason}, stream
                            ),
                        )
                    except OSError:
                        pass
                    return _failure(result, reason, retry_after)
                result.update(operators=rows, fetched_at=time(), stale=False)
                try:
                    _save_cache(path, result)
                except OSError:
                    result["error"] = "公开调查已获取，但本地缓存保存失败"
                return result
        except LockBusyError:
            if monotonic() >= deadline:
                return {**result, "error": "其他实例正在读取一图流公开统计，请稍后重试"}
            sleep(0.1)
        except OSError:
            return {**result, "error": "一图流公开统计缓存无法访问，请检查数据目录权限"}
