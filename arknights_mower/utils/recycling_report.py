"""Submit saved recycling evidence with restartable per-collection progress."""

import json
from threading import Lock, Thread
from time import sleep
from uuid import uuid4

import requests

from arknights_mower import __version__
from arknights_mower.data import key_mapping
from arknights_mower.utils.config import atomic_write
from arknights_mower.utils.growth import growth_data
from arknights_mower.utils.log import logger
from arknights_mower.utils.mastery_recommendation import get_skill_data
from arknights_mower.utils.path import get_path
from arknights_mower.utils.update_runtime import submission_lock

REPORT_URL = "https://backend.yituliu.cn/report/recycleDrop"
REQUEST_TIMEOUT = (3, 15)
MAX_BATCH_DROPS = 100
RETRY_DELAYS = (5, 30)
_lock = Lock()
_running = False
_dirty = False


def _connection():
    from arknights_mower.solvers.record import _conn

    return _conn()


def _operator_ids(names):
    if not names:
        return None
    candidates = {}
    try:
        for cid, char in growth_data(get_skill_data())["characters"].items():
            candidates.setdefault(char["name"], set()).add(
                char.get("progression_owner", cid)
            )
    except Exception:
        logger.debug("回收站上报未能确认干员 ID，省略干员字段")
        return None
    result = []
    for name in names:
        ids = candidates.get(name, set())
        if len(ids) != 1:
            return None
        result.append(next(iter(ids)))
    return result


def _wake(directory):
    global _running, _dirty
    with _lock:
        if _running:
            _dirty = True
            return True
        try:
            worker = Thread(
                target=_drain,
                args=(directory,),
                name="recycling-report",
                daemon=True,
            )
            worker.start()
            _running = True
            return True
        except RuntimeError:
            logger.warning("回收站上报线程未启动，待发送记录已保留")
            return False


def start_recycling_reports():
    """Resume saved progress and include pre-reporting collection history."""
    try:
        # Release interrupted observations before this run can collect new rewards.
        _recover_progress()
        return _wake(get_path("@app/config/recycling_report"))
    except Exception:
        logger.warning("回收站历史补发未启动，已保存的记录和发送进度保持不变")
        return False


def _recover_progress():
    with _connection() as connection:
        connection.execute(
            "UPDATE recycling_report_progress SET status = 'pending' "
            "WHERE status IN ('waiting', 'failed')"
        )
        connection.commit()


def report_recycling_collection(event_id):
    """Release one collection after its actual roster observation has finished."""
    try:
        with _connection() as connection:
            connection.execute(
                "UPDATE recycling_report_progress SET status = 'pending' "
                "WHERE event_id = ? AND status = 'waiting'",
                (event_id,),
            )
            connection.commit()
        return _wake(get_path("@app/config/recycling_report"))
    except Exception:
        logger.warning("回收站上报未启动，本地收取记录已保留")
        return False


def _allocate_time(connection, event_id, collected_at, total, base_ms):
    if base_ms is not None:
        return base_ms
    base_ms = int(collected_at * 1000)
    # Allocate only overlapping intervals; newer reports never move old dates to now.
    while True:
        end = connection.execute(
            "SELECT MAX(end_ms) FROM recycling_report_progress "
            "WHERE base_ms <= ? AND end_ms >= ?",
            (base_ms + total - 1, base_ms),
        ).fetchone()[0]
        if end is None:
            break
        base_ms = end + 1
    connection.execute(
        "UPDATE recycling_report_progress SET base_ms = ?, end_ms = ? WHERE event_id = ?",
        (base_ms, base_ms + total - 1, event_id),
    )
    return base_ms


def _next_batch():
    drops, progress = [], []
    while len(drops) < MAX_BATCH_DROPS:
        with _connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            exclusions = ""
            params = []
            if progress:
                exclusions = (
                    " AND c.event_id NOT IN (" + ",".join("?" for _ in progress) + ")"
                )
                params = [event_id for _, _, event_id in progress]
            rows = connection.execute(
                "SELECT c.event_id, c.collected_at, c.operators, c.materials, "
                "COALESCE(p.next_unit, 0), p.base_ms FROM recycling_collection c "
                "LEFT JOIN recycling_report_progress p ON p.event_id = c.event_id "
                "WHERE (p.event_id IS NULL OR p.status = 'pending') "
                + exclusions
                + " ORDER BY c.collected_at, c.event_id LIMIT ?",
                (*params, MAX_BATCH_DROPS),
            ).fetchall()
            if not rows:
                break
            for event_id, collected_at, names, materials, offset, base_ms in rows:
                connection.execute(
                    "INSERT OR IGNORE INTO recycling_report_progress (event_id, status) "
                    "VALUES (?, 'pending')",
                    (event_id,),
                )
                materials = json.loads(materials)
                if not materials:
                    connection.execute(
                        "UPDATE recycling_report_progress SET status = 'skipped' WHERE event_id = ?",
                        (event_id,),
                    )
                    continue
                items = [
                    (key_mapping.get(name, [None])[0], count)
                    for name, count in materials.items()
                ]
                if any(iid is None for iid, _ in items):
                    connection.execute(
                        "UPDATE recycling_report_progress SET status = 'failed' WHERE event_id = ?",
                        (event_id,),
                    )
                    logger.warning("回收站历史材料 ID 未确认，保留待补发记录")
                    continue
                total = sum(count for _, count in items)
                base_ms = _allocate_time(
                    connection, event_id, collected_at, total, base_ms
                )
                ids = _operator_ids(json.loads(names))
                next_offset = min(total, offset + MAX_BATCH_DROPS - len(drops))
                position = 0
                for iid, count in items:
                    for unit in range(
                        max(offset, position), min(next_offset, position + count)
                    ):
                        drop = {"itemId": str(iid), "dropTime": base_ms + unit}
                        if ids:
                            drop["operators"] = list(ids)
                        drops.append(drop)
                    position += count
                progress.append(
                    (
                        next_offset,
                        "submitted" if next_offset == total else "pending",
                        event_id,
                    )
                )
                if len(drops) == MAX_BATCH_DROPS:
                    break
            connection.commit()
    return {
        "drops": drops,
        "server": "CN",
        "source": "mower",
        "version": __version__,
    }, progress


def _submit_with_retry(directory, batch):
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            _submit(directory, batch)
            return
        except requests.RequestException:
            if attempt == len(RETRY_DELAYS):
                raise
            logger.debug("回收站上报连接失败，等待后重试本批请求")
            sleep(RETRY_DELAYS[attempt])


def _drain(directory):
    global _running, _dirty
    try:
        with submission_lock(directory):
            while True:
                with _lock:
                    _dirty = False
                batch, progress = _next_batch()
                if not batch["drops"]:
                    break
                try:
                    _submit_with_retry(directory, batch)
                except Exception:
                    with _connection() as connection:
                        connection.executemany(
                            "UPDATE recycling_report_progress SET status = 'failed' WHERE event_id = ?",
                            [(event_id,) for _, _, event_id in progress],
                        )
                        connection.commit()
                    logger.warning("回收站上报请求失败，进度已保留，下次启动时继续")
                else:
                    with _connection() as connection:
                        connection.executemany(
                            "UPDATE recycling_report_progress SET next_unit = ?, status = ? WHERE event_id = ?",
                            progress,
                        )
                        connection.commit()
    except Exception:
        logger.warning("回收站历史补发已暂停，已保存的记录和发送进度保持不变")
    finally:
        with _lock:
            restart = _dirty
            _dirty = False
            _running = False
        if restart:
            _wake(directory)


def _submit(directory, batch):
    path = directory / "state.json"
    if path.exists():
        state = json.loads(path.read_text("utf-8"))
        uid = state["uid"]
        if not isinstance(uid, str) or not uid.strip() or len(uid) > 50:
            raise ValueError("上报标识无效")
    else:
        state = {"uid": uuid4().hex}
        atomic_write(path, lambda stream: json.dump(state, stream))
    with requests.Session() as session:
        session.trust_env = False
        with session.post(
            REPORT_URL,
            headers={"authorization": f"Bearer {state['uid']}"},
            json=batch,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            stream=True,
        ) as response:
            if 500 <= response.status_code < 600:
                raise requests.HTTPError("回收站上报服务暂时不可用")
            if response.status_code != 200 or response.raw.read(1):
                raise ValueError("上报接口未返回预期的空响应")
    logger.info("回收站上报请求已提交，接口不提供入库确认")
