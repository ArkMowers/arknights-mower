"""Perform the drop-data upload MAA core delegates to its client.

MAA core decides whether a drop report should be produced and builds the
complete HTTP request, but does not send it: it hands the prepared request to the
client through the ``ReportRequest`` callback (30000) carrying ``url``,
``headers``, ``body`` and ``subtask``. This module sends that request.

The callback arrives on the MAA callback thread, so an upload starts a daemon
thread and returns immediately; the callback never blocks on the network and
never sees an exception from it. Network parameters mirror the MAA desktop
client: retries only for server faults, and a backup domain for the penguin
statistics endpoint. A report is given up after at most six attempts — three per
domain — with the backoff sleeps between them, so an upload whose attempts each
reach the connection deadline occupies its worker for about 105 seconds. The
deadline is per phase rather than per attempt: ``requests`` applies it to the
connection and again to each read, and neither covers name resolution.
"""

import threading
import time
from urllib.parse import urlparse, urlunparse

import requests
from requests.structures import CaseInsensitiveDict

from arknights_mower.utils.log import logger

# 单次尝试的网络预算；与 MAA 客户端一致。
REPORT_TIMEOUT = 15
# 同一域名内的尝试次数与 5xx 退避，同样照搬客户端。
REPORT_ATTEMPTS = 3
REPORT_BACKOFF = 3.0
REPORT_BACKOFF_FACTOR = 1.5
# 企鹅物流主域名在部分网络下不可达，客户端会改用备用域名重试整轮。
PENGUIN_SUBTASK = "ReportToPenguinStats"
PENGUIN_DOMAIN = "https://penguin-stats.io"
PENGUIN_DOMAIN_NETLOC = urlparse(PENGUIN_DOMAIN).netloc
PENGUIN_BACKUP_DOMAINS = ("penguin-stats.cn",)
# 核心给出的上报子任务；名称只影响措辞与失败级别，不影响发送。
SUBTASK_TEXT = {
    PENGUIN_SUBTASK: "企鹅物流",
    "ReportToYituliu": "一图流",
}
# 非企鹅目标的失败与客户端一致保持安静；首次失败升到告警，让界面日志至少留下一次线索。
_report_failure_reported = False


def report_label(subtask) -> str:
    name = subtask if isinstance(subtask, str) else ""
    return SUBTASK_TEXT.get(name, name or "MAA")


def upload_report(details: dict) -> bool:
    """Start the upload for one ReportRequest payload.

    Returns whether a request was started. A payload without a usable ``url`` or
    ``body`` is refused, and every other failure surfaces on the worker thread as
    a log line rather than an exception.
    """
    url = details.get("url")
    if not isinstance(url, str) or not url:
        logger.warning("MAA 上报请求缺少 url，已跳过")
        return False
    body = details.get("body")
    if not isinstance(body, str) or not body:
        logger.warning("MAA 上报请求缺少 body，已跳过")
        return False
    headers = details.get("headers")
    if not _valid_url(url):
        logger.warning(
            f"{report_label(details.get('subtask'))}上报地址无法解析，已跳过"
        )
        return False
    try:
        threading.Thread(
            target=_post,
            args=(
                url,
                dict(headers) if isinstance(headers, dict) else {},
                body,
                details.get("subtask"),
            ),
            name="maa-report",
            daemon=True,
        ).start()
    except RuntimeError as e:
        # 线程资源耗尽时不能把异常抛回 MAA 回调线程。
        logger.warning(f"{report_label(details.get('subtask'))}上报线程创建失败：{e}")
        return False
    return True


def _valid_url(url: str) -> bool:
    """协议规定的 URL 必须能解析出主机名，否则备用域名替换无从谈起。"""
    try:
        return bool(urlparse(url).netloc)
    except ValueError:
        return False


def _with_netloc(url: str, netloc: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(netloc=netloc))


def _post(url: str, extra_headers: dict, body: str, subtask) -> None:
    """Send one report on a worker thread; every failure stays a log line.

    The guard is the whole body: an exception escaping a worker thread reaches
    only ``threading.excepthook``, so it would leave no record in the runtime log.
    """
    try:
        _upload(url, extra_headers, body, subtask)
    except Exception as e:
        logger.warning(f"{report_label(subtask)}上报异常：{e}")


def _upload(url: str, extra_headers: dict, body: str, subtask) -> None:
    label = report_label(subtask)
    # 头部名不区分大小写，用大小写不敏感的映射合并，负载给出的 Content-Type 才会生效。
    headers = CaseInsensitiveDict({"Accept": "application/json"})
    headers.update(extra_headers)
    # 协议规定负载 headers 不含 Content-Type，由客户端补齐。
    headers.setdefault("Content-Type", "application/json; charset=utf-8")
    data = body.encode("utf-8")

    targets = [url]
    if subtask == PENGUIN_SUBTASK and urlparse(url).netloc == PENGUIN_DOMAIN_NETLOC:
        targets += [_with_netloc(url, backup) for backup in PENGUIN_BACKUP_DOMAINS]
    for target in targets:
        if _attempt_domain(target, headers, data):
            logger.info(f"{label}上报成功")
            return
    _log_give_up(label, subtask)


def _log_give_up(label: str, subtask) -> None:
    """放弃上报时记一行；非企鹅目标只在首次失败时打扰用户。"""
    global _report_failure_reported
    if subtask == PENGUIN_SUBTASK:
        logger.warning(f"{label}上报失败，已放弃本次上报")
    elif _report_failure_reported:
        logger.debug(f"{label}上报失败，已放弃本次上报")
    else:
        # MAA 客户端对一图流保持沉默，这里记一次告警，否则界面日志里看不到任何线索。
        _report_failure_reported = True
        logger.warning(f"{label}上报失败，已放弃本次上报（后续同类失败只记调试日志）")


def _attempt_domain(url: str, headers: dict, data: bytes) -> bool:
    """Post once per attempt on one domain; only server faults are retried."""
    backoff = REPORT_BACKOFF
    for attempt in range(REPORT_ATTEMPTS):
        try:
            with requests.post(
                url, headers=headers, data=data, timeout=REPORT_TIMEOUT
            ) as response:
                status = response.status_code
        except Exception as e:
            logger.debug(f"MAA 上报请求失败：{e}")
            return False
        if status == 200:
            return True
        if not 500 <= status < 600:
            logger.debug(f"MAA 上报返回 {status}")
            return False
        if attempt + 1 < REPORT_ATTEMPTS:
            logger.debug(f"MAA 上报返回 {status}，{backoff:g} 秒后重试")
            time.sleep(backoff)
            backoff *= REPORT_BACKOFF_FACTOR
    return False
