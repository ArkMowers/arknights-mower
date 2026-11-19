"""森空岛签到历史的读取、归并与统计。

签到任务把每次尝试按行追加到 ``config/tmp/skland.csv``（GBK、无表头）：
日期、账号、游戏区服、奖励或失败信息。新记录附加状态、返回码、角色键和尝试标识。
读取时兼容旧记录，缺失的状态列由奖励文本推断。
获取可签到角色前的失败及后续恢复只记录账号，游戏区服和角色键留空。
一次签到的记录行之后追加一行完成标记；读取时缺少完成标记的事件按未写完处理。

本模块只读该文件，输出已脱敏的记录与按账号区服汇总的统计，供 Web 界面展示。
"""

from __future__ import annotations

import csv
import datetime
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from arknights_mower.utils.csv_utils import EmptyDataError, read_csv_rows
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skland_log import (
    mask_account as mask_account_text,
)
from arknights_mower.utils.skland_log import (
    redact_signing_text,
)

RECORD_PATH = "@app/tmp/skland.csv"

_DATE_FORMAT = "%Y/%m/%d"
_REWARD_PATTERN = re.compile(r"^(?P<item>.+?)×(?P<count>\d+)$")
_EVENT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_REPEAT_MARKERS = ("重复签到", "已签到", "已经签到", "已领取")
_SUCCESS_MARKERS = ("签到成功",)
SIGNED_OUTCOMES = ("signed", "repeated")
ACCOUNT_FAILED = "account_failed"
ACCOUNT_RECOVERED = "account_recovered"
EVENT_COMMITTED = "event_committed"
GAME_GROUPS = ("明日方舟", "终末地")
_GAME_ORDER = {name: index for index, name in enumerate(GAME_GROUPS)}


@dataclass(frozen=True)
class SklandRecord:
    """一次签到尝试写入的一行记录（账号已脱敏）。"""

    date: datetime.date
    account: str
    game: str
    outcome: str
    reward: str
    item: str | None
    count: int
    role_key: str | None = None
    event_id: str | None = None

    @property
    def pair_key(self) -> str:
        return f"{self.account}::{self.game}"

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "account": self.account,
            "game": self.game,
            "game_group": game_group(self.game),
            "channel": game_channel(self.game),
            "outcome": self.outcome,
            "reward": self.reward,
            "item": self.item,
            "count": self.count,
            "pair": self.pair_key,
            **({"role_key": self.role_key} if self.role_key else {}),
            **({"event_id": self.event_id} if self.event_id else {}),
        }


@dataclass(frozen=True)
class PairSummary:
    """一个账号与一个游戏区服的组合在全部历史中的表现。"""

    account: str
    game: str
    first_date: datetime.date
    last_date: datetime.date
    record_days: int
    signed_days: int
    current_streak: int
    longest_streak: int
    last_outcome: str
    multiple_roles: bool = False

    @property
    def key(self) -> str:
        return f"{self.account}::{self.game}"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "account": self.account,
            "game": self.game,
            "game_group": game_group(self.game),
            "channel": game_channel(self.game),
            "first_date": self.first_date.isoformat(),
            "last_date": self.last_date.isoformat(),
            "record_days": self.record_days,
            "signed_days": self.signed_days,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "last_outcome": self.last_outcome,
            **({"multiple_roles": True} if self.multiple_roles else {}),
        }


def default_record_path() -> Path:
    return get_path(RECORD_PATH)


def mask_account(value: str) -> str:
    """按日志脱敏规则遮蔽账号，保留可辨认的首尾字符。"""
    text = str(value or "").strip()
    if not text:
        return "未知账号"
    return mask_account_text(text)


def game_group(value: str) -> str:
    text = str(value or "").strip()
    for group in GAME_GROUPS:
        if text.startswith(group):
            return group
    return text or "未知游戏"


def game_channel(value: str) -> str:
    text = str(value or "").strip()
    for group in GAME_GROUPS:
        if text.startswith(group):
            return text[len(group) :] or "未知区服"
    return "未知区服"


def classify_outcome(status: str, reward: str) -> str:
    """把一行签到结果归为 signed / repeated / failed。

    ``repeated`` 表示服务器判定今天已经签到过（通常由森空岛 App 或其他客户端
    先签到），对签到覆盖率的含义与 ``signed`` 相同，界面上单独标注。
    """
    reward = str(reward or "")
    status = str(status or "").strip().lower()
    if status == "success":
        return "signed"
    if status == "failure":
        return "repeated" if _is_repeated(reward) else "failed"
    if _is_repeated(reward):
        return "repeated"
    if _REWARD_PATTERN.match(reward.strip()) or any(
        marker in reward for marker in _SUCCESS_MARKERS
    ):
        return "signed"
    return "failed"


def parse_record(row: Iterable[str]) -> SklandRecord | None:
    values = list(row)
    if len(values) < 4:
        return None
    date = _parse_date(values[0])
    account = str(values[1]).strip()
    game = str(values[2]).strip()
    reward = str(values[3]).strip()
    status = str(values[4]).strip() if len(values) > 4 else ""
    account_event = status in (ACCOUNT_FAILED, ACCOUNT_RECOVERED)
    if date is None:
        return None
    if account_event and game:
        return None
    if not account_event and (not account or not game):
        return None
    outcome = status if account_event else classify_outcome(status, reward)
    safe_reward = redact_signing_text(reward, account)
    item, count = _parse_reward(reward) if outcome == "signed" else (None, 0)
    role_key = str(values[6]).strip() if len(values) > 6 else ""
    if account_event or not re.fullmatch(r"[0-9a-f]{64}", role_key):
        role_key = None
    event_id = str(values[7]).strip() if len(values) > 7 else ""
    return SklandRecord(
        date=date,
        account=mask_account(account),
        game=game,
        outcome=outcome,
        reward=safe_reward,
        item=redact_signing_text(item, account) if item else None,
        count=count,
        role_key=role_key,
        event_id=event_id if re.fullmatch(r"[0-9a-f]{32}", event_id) else None,
    )


def committed_events(rows: Iterable[Iterable[str]]) -> set[str]:
    """返回已写入完成标记的签到事件标识。"""
    committed = set()
    for row in rows:
        values = list(row)
        if len(values) > 7 and str(values[4]).strip() == EVENT_COMMITTED:
            event_id = str(values[7]).strip()
            if _EVENT_ID_PATTERN.fullmatch(event_id):
                committed.add(event_id)
    return committed


def event_is_complete(record: SklandRecord, committed: set[str]) -> bool:
    """旧记录没有事件标识，按原样读取；新记录以完成标记确认是否写完。"""
    return record.event_id is None or record.event_id in committed


def read_history(path: str | Path | None = None) -> list[SklandRecord]:
    """读取签到历史；文件不存在或为空时返回空列表，读取错误交给调用方处理。"""
    rows = _history_rows(path)
    committed = committed_events(rows)
    return [
        record
        for row in rows
        if (record := parse_record(row)) is not None
        and event_is_complete(record, committed)
    ]


def read_unambiguous_history(
    configured_accounts: Iterable[str], path: str | Path | None = None
) -> tuple[list[SklandRecord], list[str]]:
    """返回可按账号统计的记录，以及无法区分的脱敏账号名称。"""
    accounts = {name.strip() for name in configured_accounts if name.strip()}
    rows = _history_rows(path)
    committed = committed_events(rows)
    records = []
    for row in rows:
        record = parse_record(row)
        if record is None or not event_is_complete(record, committed):
            continue
        accounts.add(row[1].strip())
        records.append(record)
    account_counts = Counter(map(mask_account, accounts))
    ambiguous = sorted(label for label, count in account_counts.items() if count > 1)
    distinct_records = [
        record for record in records if account_counts[record.account] == 1
    ]
    return distinct_records, ambiguous


def _history_rows(path: str | Path | None) -> list[list[str]]:
    target = Path(path) if path is not None else default_record_path()
    rows, _ = _read_rows(target)
    return rows


def read_sign_in_state(
    path: str | Path,
) -> tuple[
    set[tuple[datetime.date, str, str, str]], set[tuple[datetime.date, str]], str
]:
    rows, encoding = _read_rows(Path(path))
    committed = committed_events(rows)
    completed = set()
    account_failures = set()
    for row in rows:
        record = parse_record(row)
        if record is None or not event_is_complete(record, committed):
            continue
        account = (record.date, row[1].strip())
        if record.outcome == ACCOUNT_FAILED:
            account_failures.add(account)
        elif record.outcome == ACCOUNT_RECOVERED:
            account_failures.discard(account)
        elif record.role_key and record.outcome in SIGNED_OUTCOMES:
            completed.add((*account, record.game, record.role_key))
    return completed, account_failures, encoding


def _read_rows(target: Path) -> tuple[list[list[str]], str]:
    """优先按 GBK 读取，兼容被 Excel 另存为 UTF-8 的文件。"""
    for encoding in ("gbk", "utf-8-sig"):
        try:
            return read_csv_rows(target, header=False, encoding=encoding), encoding
        except (FileNotFoundError, EmptyDataError):
            return [], encoding
        except UnicodeDecodeError:
            continue
        except csv.Error as error:
            raise OSError("skland.csv 格式无法解析") from error
    raise OSError("skland.csv 编码无法识别")


def build_pairs(
    records: Iterable[SklandRecord], today: datetime.date
) -> list[PairSummary]:
    grouped: dict[tuple[str, str], list[SklandRecord]] = {}
    for record in records:
        grouped.setdefault((record.account, record.game), []).append(record)

    pairs = []
    for (account, game), rows in grouped.items():
        days = sorted({record.date for record in rows})
        signed = sorted(
            {record.date for record in rows if record.outcome in SIGNED_OUTCOMES}
        )
        role_keys = {record.role_key for record in rows if record.role_key}
        last_outcome = _day_outcome(
            [record for record in rows if record.date == days[-1]]
        )
        pairs.append(
            PairSummary(
                account=account,
                game=game,
                first_date=days[0],
                last_date=days[-1],
                record_days=len(days),
                signed_days=len(signed),
                current_streak=current_streak(signed, today),
                longest_streak=longest_streak(signed),
                last_outcome=last_outcome,
                multiple_roles=len(role_keys) > 1,
            )
        )
    pairs.sort(
        key=lambda pair: (
            pair.account,
            _GAME_ORDER.get(game_group(pair.game), len(_GAME_ORDER)),
            pair.game,
        )
    )
    return pairs


def current_streak(days: Iterable[datetime.date], today: datetime.date) -> int:
    """截至今天的连续签到天数；昨天签到而今天还没签时连续数仍然成立。"""
    signed = set(days)
    anchor = today if today in signed else today - datetime.timedelta(days=1)
    if anchor not in signed:
        return 0
    count = 0
    cursor = anchor
    while cursor in signed:
        count += 1
        cursor -= datetime.timedelta(days=1)
    return count


def longest_streak(days: Iterable[datetime.date]) -> int:
    ordered = sorted(set(days))
    longest = 0
    run = 0
    previous = None
    for day in ordered:
        run = (
            run + 1 if previous and day - previous == datetime.timedelta(days=1) else 1
        )
        longest = max(longest, run)
        previous = day
    return longest


def _account_failure_summaries(events, start, end):
    groups = {}
    for record in events:
        if not start <= record.date <= end:
            continue
        key = (record.date, record.account)
        if record.outcome == ACCOUNT_RECOVERED:
            if key in groups:
                groups[key]["resolved"] = True
            continue
        group = groups.setdefault(
            key,
            {
                "date": record.date.isoformat(),
                "account": record.account,
                "attempts": 0,
                "messages": [],
                "resolved": False,
            },
        )
        group["attempts"] += 1
        group["resolved"] = False
        if record.reward and record.reward not in group["messages"]:
            group["messages"].append(record.reward)
    return [groups[key] for key in sorted(groups, reverse=True)]


def build_statistics(
    records: Iterable[SklandRecord],
    *,
    start: datetime.date,
    end: datetime.date,
    today: datetime.date,
    account: str | None = None,
    game: str | None = None,
) -> dict:
    """构造界面所需的数据；日期范围只约束明细与日历，汇总基于全部历史。"""
    entries = list(records)
    all_records = [record for record in entries if record.game]
    account_events = [
        record
        for record in entries
        if record.outcome in (ACCOUNT_FAILED, ACCOUNT_RECOVERED)
        and (account is None or record.account == account)
    ]
    first_failure = min(
        (record.date for record in account_events if record.outcome == ACCOUNT_FAILED),
        default=None,
    )
    filtered = [
        record
        for record in all_records
        if (account is None or record.account == account)
        and (game is None or record.game == game)
    ]
    pairs = build_pairs(filtered, today)
    today_rows: dict[str, list[SklandRecord]] = {}
    for record in filtered:
        if record.date == today:
            today_rows.setdefault(record.pair_key, []).append(record)

    today_counts = {"signed": 0, "repeated": 0, "failed": 0, "pending": 0}
    for pair in pairs:
        outcome = _day_outcome(today_rows.get(pair.key, ()))
        today_counts[outcome or "pending"] += 1

    in_range = [record for record in filtered if start <= record.date <= end]
    in_range.sort(
        key=lambda record: (record.date, record.account, record.game), reverse=True
    )
    today_records = sorted(
        (record for rows in today_rows.values() for record in rows),
        key=lambda record: (record.account, record.game, record.reward),
    )

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "today": {"date": today.isoformat(), **today_counts, "total": len(pairs)},
        "today_records": [record.to_dict() for record in today_records],
        "accounts": sorted({record.account for record in all_records}),
        "games": sorted(
            {record.game for record in all_records},
            key=lambda name: (
                _GAME_ORDER.get(game_group(name), len(_GAME_ORDER)),
                name,
            ),
        ),
        "pairs": [pair.to_dict() for pair in pairs],
        "records": [record.to_dict() for record in in_range],
        "account_failures": _account_failure_summaries(account_events, start, end),
        "first_account_failure_date": first_failure.isoformat()
        if first_failure
        else None,
    }


def _parse_date(value: str) -> datetime.date | None:
    text = str(value or "").strip()
    for pattern in (_DATE_FORMAT, "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _parse_reward(reward: str) -> tuple[str | None, int]:
    match = _REWARD_PATTERN.match(str(reward or "").strip())
    if not match:
        return None, 0
    item = match.group("item").strip()
    return (item or None), int(match.group("count"))


def _is_repeated(reward: str) -> bool:
    return any(marker in str(reward or "") for marker in _REPEAT_MARKERS)


def _day_outcome(rows: Iterable[SklandRecord]) -> str | None:
    outcomes = {record.outcome for record in rows}
    if "signed" in outcomes:
        return "signed"
    if "repeated" in outcomes:
        return "repeated"
    if "failed" in outcomes:
        return "failed"
    return None
