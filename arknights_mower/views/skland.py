"""森空岛签到统计与奖励查询接口。"""

from __future__ import annotations

import datetime
import hashlib
import json
from calendar import monthrange
from collections import Counter, defaultdict
from threading import Lock

from flask import Blueprint, request

from arknights_mower.utils import config
from arknights_mower.utils.config_backup import backup_lock
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skland_log import skland_day
from arknights_mower.utils.skland_rewards import fetch_pair_rewards
from arknights_mower.utils.skland_statistics import (
    build_statistics,
    read_unambiguous_history,
)
from arknights_mower.utils.web_auth import require_token

skland_bp = Blueprint("skland", __name__, url_prefix="/skland")

_DEFAULT_DAYS = 30
_MAX_RANGE_DAYS = 366
_REWARDS_LOCK = Lock()
_REWARDS_CACHE_PATH = "@app/tmp/skland_rewards.json"


def _unambiguous_history():
    return read_unambiguous_history(
        account.account for account in config.conf.skland_info
    )


@skland_bp.get("/statistics")
@require_token
def statistics():
    today = skland_day()
    start, end, error = _parse_range(request.args, today)
    if error:
        return {"error": error}, 400
    try:
        records, ambiguous = _unambiguous_history()
    except PermissionError:
        return {"error": "skland.csv 正在被其他程序占用，请关闭后刷新"}, 503
    except OSError:
        return {"error": "skland.csv 读取失败，请检查文件编码或稍后重试"}, 503
    account = request.args.get("account") or None
    result = build_statistics(
        records,
        start=start,
        end=end,
        today=today,
        account=account,
        game=request.args.get("game") or None,
    )
    ambiguous = [label for label in ambiguous if account is None or label == account]
    if ambiguous:
        result["ambiguous_accounts"] = ambiguous
    return result


def _reward_month():
    return skland_day().strftime("%Y-%m")


def _reward_configuration():
    accounts = [account.model_copy() for account in config.conf.skland_info]
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                account.model_dump(exclude={"password", "cultivate_select"})
                for account in accounts
            ],
            sort_keys=True,
        ).encode()
    )
    return accounts, fingerprint.hexdigest()


def _pack_reward_pairs(pairs):
    tables = []
    stored_pairs = []
    for pair in pairs:
        stored_pair = pair.copy()
        slots = stored_pair.pop("reward_slots")
        table = [slot["rewards"] for slot in slots]
        try:
            table_index = tables.index(table)
        except ValueError:
            table_index = len(tables)
            tables.append(table)
        stored_pair.update(
            reward_table=table_index,
            done_slots=[slot["index"] for slot in slots if slot["done"]],
            available_slots=[slot["index"] for slot in slots if slot["available"]],
        )
        stored_pairs.append(stored_pair)
    return tables, stored_pairs


def _unpack_reward_pairs(tables, stored_pairs):
    if not isinstance(tables, list) or any(
        not isinstance(table, list)
        or any(not isinstance(rewards, list) for rewards in table)
        for table in tables
    ):
        return None
    pairs = []
    for stored_pair in stored_pairs:
        if not isinstance(stored_pair, dict):
            return None
        pair = stored_pair.copy()
        table_index = pair.pop("reward_table", None)
        done = pair.pop("done_slots", None)
        available = pair.pop("available_slots", None)
        if (
            type(table_index) is not int
            or not 0 <= table_index < len(tables)
            or not isinstance(done, list)
            or not isinstance(available, list)
        ):
            return None
        pair["reward_slots"] = [
            {
                "index": index,
                "done": index in done,
                "available": index in available,
                "rewards": rewards,
            }
            for index, rewards in enumerate(tables[table_index], start=1)
        ]
        pairs.append(pair)
    return pairs


def _read_reward_snapshot(path):
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        isinstance(snapshot, dict)
        and _parse_month(snapshot.get("month")) is not None
        and isinstance(snapshot.get("pairs"), list)
        and isinstance(snapshot.get("warnings"), list)
    ):
        return snapshot
    return None


def _cached_rewards(snapshot, month, fingerprint=None):
    if (
        snapshot is not None
        and snapshot["month"] == month
        and (fingerprint is None or snapshot.get("configuration") == fingerprint)
    ):
        pairs = snapshot["pairs"]
        if "reward_tables" in snapshot:
            pairs = _unpack_reward_pairs(snapshot["reward_tables"], pairs)
            if pairs is None:
                return None
        return {
            "month": month,
            "cached": True,
            "pairs": pairs,
            "warnings": snapshot["warnings"],
        }
    return None


def _retain_reward_pairs(pairs, cached_pairs):
    role_keys = {pair["role_key"] for pair in pairs if pair.get("role_key")}
    keyed_scopes = {
        (pair["account"], pair["game"]) for pair in pairs if pair.get("role_key")
    }
    indices = defaultdict(set)
    for pair in pairs:
        indices[pair["account"], pair["game"]].add(pair.get("role_index") or 1)

    merged = list(pairs)
    for pair in cached_pairs:
        role_key = pair.get("role_key")
        scope = (pair["account"], pair["game"])
        used = indices[scope]
        index = pair.get("role_index") or 1
        if role_key in role_keys or (
            not role_key and (scope in keyed_scopes or index in used)
        ):
            continue
        if index in used:
            index = max(used) + 1
        used.add(index)
        merged.append({**pair, "role_index": index, "stale": True})
    return merged


def _parse_month(value):
    if not isinstance(value, str) or len(value) != 7:
        return None
    try:
        return datetime.date.fromisoformat(value + "-01")
    except ValueError:
        return None


def _earliest_reward_month(path, current_month, active):
    months = [
        entry.stem
        for entry in path.with_suffix("").glob("*.json")
        if _parse_month(entry.stem) is not None and entry.stem < current_month
    ]
    if active and active["month"] < current_month and active["pairs"]:
        months.append(active["month"])
    return min(months, default=None)


def _has_complete_reward_history(snapshot):
    pairs = snapshot["pairs"]
    if snapshot["warnings"]:
        return False
    if not pairs:
        return True
    month = _parse_month(snapshot["month"])
    days = monthrange(month.year, month.month)[1]
    try:
        records, _ = _unambiguous_history()
    except OSError:
        return False

    daily_rewards = defaultdict(Counter)
    for record in records:
        if (
            record.date.year == month.year
            and record.date.month == month.month
            and record.outcome == "signed"
            and record.item
        ):
            daily_rewards[
                record.account, record.game, record.role_key, record.date.day
            ][record.item, record.count] += 1

    seen = set()
    for pair in pairs:
        scope = (pair["account"], pair["game"])
        role = (*scope, pair.get("role_key"))
        slots = pair["reward_slots"]
        if pair.get("progress_ambiguous") or scope in seen or len(slots) != days:
            return False
        seen.add(scope)
        for day, slot in enumerate(slots, start=1):
            expected = Counter(
                (item["item"], item["count"]) for item in slot["rewards"]
            )
            if not expected or expected - daily_rewards[(*role, day)]:
                return False
    return True


def _write_reward_snapshot(path, snapshot):
    config.atomic_write(
        path, lambda stream: json.dump(snapshot, stream, ensure_ascii=False)
    )


@skland_bp.get("/rewards")
@require_token
def rewards():
    current_month = _reward_month()
    month = request.args.get("month", current_month)
    if _parse_month(month) is None or month > current_month:
        return {"error": "月份应为 YYYY-MM，且不能晚于当前月"}, 400
    path = get_path(_REWARDS_CACHE_PATH)
    active = _read_reward_snapshot(path)
    if month == current_month:
        _, fingerprint = _reward_configuration()
        cached = _cached_rewards(active, month, fingerprint)
    else:
        archived = _read_reward_snapshot(path.with_suffix("") / f"{month}.json")
        cached = _cached_rewards(active, month) or _cached_rewards(archived, month)
    return {
        "month": month,
        "cached": False,
        "pairs": [],
        "warnings": [],
        **(cached or {}),
        "earliest_month": _earliest_reward_month(path, current_month, active),
    }


@skland_bp.post("/rewards/refresh")
@require_token
def refresh_rewards():
    if not _REWARDS_LOCK.acquire(blocking=False):
        return {"error": "正在读取本月奖励，请稍后重试"}, 409
    try:
        with backup_lock:
            accounts, fingerprint = _reward_configuration()
            month = _reward_month()
            path = get_path(_REWARDS_CACHE_PATH)
            active = _read_reward_snapshot(path)
            cached = _cached_rewards(active, month, fingerprint)
        pairs, warnings = fetch_pair_rewards(accounts)
        with backup_lock:
            current_accounts, current_fingerprint = _reward_configuration()
            if (
                _reward_month() != month
                or get_path(_REWARDS_CACHE_PATH) != path
                or current_fingerprint != fingerprint
                or [account.password for account in current_accounts]
                != [account.password for account in accounts]
            ):
                return {"error": "月份或森空岛账号设置已变化，请重新读取"}, 409
            current_pairs = [
                pair for pair in pairs if pair["progress_date"].startswith(month + "-")
            ]
            if len(current_pairs) != len(pairs):
                warnings.append("森空岛返回的部分奖励与当前月份不符")
            pairs = current_pairs
            if warnings and cached is not None:
                pairs = _retain_reward_pairs(pairs, cached["pairs"])
            result = {
                "month": month,
                "cached": False,
                "pairs": pairs,
                "warnings": warnings,
            }
            if pairs or not warnings:
                reward_tables, stored_pairs = _pack_reward_pairs(pairs)
                snapshot = {
                    "month": month,
                    "configuration": fingerprint,
                    "reward_tables": reward_tables,
                    "pairs": stored_pairs,
                    "warnings": warnings,
                }
                try:
                    if active and active["month"] < month and active["pairs"]:
                        previous = _cached_rewards(active, active["month"])
                        if previous is not None and not _has_complete_reward_history(
                            previous
                        ):
                            archive = path.with_suffix("") / f"{active['month']}.json"
                            _write_reward_snapshot(archive, active)
                    _write_reward_snapshot(path, snapshot)
                    result["cached"] = True
                    active = snapshot
                except OSError:
                    warnings.append("本月奖励缓存写入失败")
            result["earliest_month"] = _earliest_reward_month(path, month, active)
            return result
    finally:
        _REWARDS_LOCK.release()


def _parse_range(args, today: datetime.date):
    start_text = args.get("startDate")
    end_text = args.get("endDate")
    try:
        start = (
            datetime.date.fromisoformat(start_text)
            if start_text
            else today - datetime.timedelta(days=_DEFAULT_DAYS - 1)
        )
        end = datetime.date.fromisoformat(end_text) if end_text else today
    except ValueError:
        return None, None, "日期格式应为 YYYY-MM-DD"
    if start > end:
        return None, None, "开始日期不能晚于结束日期"
    if (end - start).days + 1 > _MAX_RANGE_DAYS:
        return None, None, f"日期范围不能超过 {_MAX_RANGE_DAYS} 天"
    return start, end, None
