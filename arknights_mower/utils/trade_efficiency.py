"""贸易站鸿雪组效率基准与异常判别，独立于 OCR、排班和游戏操作。"""

import json
import os
import re
import tempfile
from pathlib import Path

from arknights_mower.utils.path import get_path

EXPECTED_LOSS = 20.0  # 游戏机制缺失的固定百分比点，不是绝对效率
OCR_TOLERANCE = 1.5
PAIR = frozenset(("绮良", "鸿雪"))
BASELINE_FILE = "@app/config/trade_efficiency_baselines.json"


def parse_bonus(text: str) -> float | None:
    """解析界面蓝色加成块的单个百分比；不把计时、订单数当效率。"""
    raw = str(text).replace("％", "%").replace("﹪", "%").replace("＋", "+").strip()
    compact = re.sub(r"\s+", "", raw)
    # 百分比后可能把绿色趋势箭头识别为 ± / ↗，允许最多三个尾随图标。
    # 仍从字符串开头读取唯一数字，拒绝计时、多个百分比或额外的数字。
    match = re.fullmatch(
        r"\+?([0-9]{1,3})(?:[.,]([0-9]))?%?[±↑↓↗↘↖↙⇧⇩▲▼▴▾^]{0,3}",
        compact,
    )
    if not match:
        return None
    amount = float(match.group(1)) + (int(match.group(2)) / 10 if match.group(2) else 0)
    return amount if 0 <= amount <= 500 else None


def key_for(room: str, occupants: list[str], product: str, related: dict) -> str:
    # Third-slot occupants can differ by 5 efficiency points. Keep the pair,
    # product and related facilities as the stable diagnosis context.
    stable_occupants = sorted(PAIR) if PAIR.issubset(occupants) else sorted(occupants)
    return json.dumps(
        [
            room,
            stable_occupants,
            product or "",
            {name: sorted(roster) for name, roster in sorted(related.items())},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def canonical_key(serialized: str) -> str | None:
    """Normalize old full-roster keys without discarding verified baselines."""
    try:
        room, occupants, product, related = json.loads(serialized)
        if not (
            isinstance(room, str)
            and isinstance(occupants, list)
            and all(isinstance(name, str) for name in occupants)
            and isinstance(product, str)
            and isinstance(related, dict)
            and all(
                isinstance(name, str)
                and isinstance(roster, list)
                and all(isinstance(member, str) for member in roster)
                for name, roster in related.items()
            )
        ):
            return None
        return key_for(room, occupants, product, related)
    except (TypeError, ValueError):
        return None


def migrate_reference(history: dict, key: str) -> bool:
    """Inherit same-facility, same-pair legacy references, not unrelated pools."""
    if key in history:
        return False
    matching = [
        record
        for old_key, record in history.items()
        if isinstance(record, dict)
        and not record.get("unresolved")
        and canonical_key(old_key) == key
    ]
    verified = [
        float(record["verified_baseline"])
        for record in matching
        if isinstance(record.get("verified_baseline"), (int, float))
    ]
    provisional = [
        float(record["provisional_baseline"])
        for record in matching
        if isinstance(record.get("provisional_baseline"), (int, float))
    ]
    candidates = verified or provisional
    if not candidates or max(candidates) - min(candidates) > 5 + OCR_TOLERANCE:
        return False
    name = "verified_baseline" if verified else "provisional_baseline"
    history[key] = {name: max(candidates), "migrated_from_roster": True}
    return True


def decide(rule, key: str, measured: float, history: dict) -> str:
    """返回 observe/calibrate/repair/normal/uncertain；不直接修改任何状态。"""
    if not rule.enabled:
        return "observe"
    record = history.get(key, {})
    if record.get("unresolved"):
        return "uncertain"
    if rule.baseline_mode == "manual":
        # If the user entered the lower normal variant, promote to an observed
        # higher normal variant without modifying the user's saved setting.
        baseline = max(
            rule.manual_percent, record.get("verified_baseline", rule.manual_percent)
        )
        # 手工基准只绑定首次设置时的阵容，禁止静默套用到不同替班组合。
        bound = history.get("_manual_binding", {}).get(rule.room)
        if bound:
            if isinstance(bound, dict):
                if (
                    bound.get("percent") == rule.manual_percent
                    and canonical_key(bound.get("key", "")) != key
                ):
                    return "uncertain"
            elif canonical_key(bound) != key:
                return "uncertain"
    else:
        baseline = record.get("verified_baseline")
        if baseline is None and "provisional_baseline" in record:
            # An unchanged first round-trip is a candidate baseline, not proof.
            # Keep checking subsequent staffing changes for a drop of exactly 20.
            baseline = record["provisional_baseline"]
    if baseline is None:
        return "calibrate" if rule.baseline_mode == "auto" else "uncertain"
    diff = baseline - measured
    # A verified reference is kept at the highest observed normal value.
    # A normal third-slot change may subtract 5; the game bug subtracts 20.
    # Therefore high reference H -> healthy H/H-5; broken H-20/H-25.
    if any(
        abs(diff - drop) <= OCR_TOLERANCE for drop in (EXPECTED_LOSS, EXPECTED_LOSS + 5)
    ):
        return "repair"
    if any(abs(diff - offset) <= OCR_TOLERANCE for offset in (-5, 0, 5)):
        return (
            "provisional"
            if rule.baseline_mode == "auto" and "verified_baseline" not in record
            else "normal"
        )
    return "uncertain"


def load_history(path: Path | None = None) -> dict:
    target = path or get_path(BASELINE_FILE)
    try:
        raw = json.loads(target.read_text(encoding="utf8"))
        return raw if isinstance(raw, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def save_history(history: dict, path: Path | None = None) -> None:
    target = path or get_path(BASELINE_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".trade-efficiency-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def configured_rule(rules, room):
    return next((rule for rule in rules if rule.enabled and rule.room == room), None)


def monitored_rooms(rules, changed_room: str) -> list[str]:
    return [
        rule.room
        for rule in rules
        if rule.enabled
        and (rule.room == changed_room or changed_room in rule.related_rooms)
    ]
