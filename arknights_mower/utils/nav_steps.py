"""导航步骤两层数据源（官方 + 本机）的读取与合并。

- 官方层 `nav_steps.json`（随程序发布）：只读，程序不写它。
- 本机层 `nav_trie_steps.json`（`persist_nav_steps` 每次导航成功后覆写）：用户自学。
两层分开存、命名不同、互不覆盖；读取时合并，**用户已学会（success=true）条目优先，
官方只补缺**——官方不会冲掉用户学过的步骤。
"""

import json
from pathlib import Path

__all__ = [
    "empty_nav_steps",
    "load_nav_file",
    "merge_nav_steps",
    "select_replay_steps",
]


def empty_nav_steps() -> dict:
    """空导航步骤数据。每次返回新对象，避免共享可变默认值。"""
    return {"version": 1, "stages": {}, "patterns": {}}


def load_nav_file(path: Path) -> dict:
    """读一份导航步骤 json。缺失 / 损坏 / 形状不对都回退为空数据，不抛异常。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty_nav_steps()
    if not isinstance(data, dict):
        return empty_nav_steps()
    if not isinstance(data.get("stages"), dict):
        data["stages"] = {}
    if not isinstance(data.get("patterns"), dict):
        data["patterns"] = {}
    return data


def merge_nav_steps(official: dict, user: dict) -> dict:
    """官方打底 + 本机优先合并导航步骤。

    对每个 stage / pattern：
      - 用户已学会（success=true **且带步骤**）-> 用用户的（覆盖官方同名，用户优先）；
      - 否则官方有 -> 用官方（补缺；用户 success=true 但无步骤不会盖掉官方有步骤的）；
      - 否则用户有（非 success 记录）-> 保留用户条目。
    返回合并后的新 dict，不改动入参（两层分开存、互不覆盖的底线）。
    """
    merged: dict = {
        "version": 1,
        "stages": {
            k: v
            for k, v in (official.get("stages") or {}).items()
            if isinstance(v, dict)
        },
        "patterns": {
            k: v
            for k, v in (official.get("patterns") or {}).items()
            if isinstance(v, dict)
        },
    }
    _merge_layer(merged["stages"], user.get("stages") or {})
    _merge_layer(merged["patterns"], user.get("patterns") or {})
    return merged


def _merge_layer(merged: dict, user: dict) -> None:
    for key, entry in user.items():
        if not isinstance(entry, dict):
            continue
        # 用户已学会且有步骤才覆盖官方；学会但无步骤不该盖掉官方有步骤的（官方补缺）。
        if entry.get("success") is True and entry.get("steps"):
            merged[key] = entry
        elif key not in merged:
            merged[key] = entry


def _pick_success_steps(entries: dict, key: str) -> list[dict]:
    """取某 key 下 success=true 且有步骤的条目；否则空。"""
    entry = entries.get(key, {})
    steps = entry.get("steps", []) if isinstance(entry, dict) else []
    if steps and entry.get("success") is True:
        return steps
    return []


def select_replay_steps(
    data: dict, stage_name: str, pattern_key: str | None
) -> list[dict]:
    """从合并视图里选出本关要回放的步骤集。

    命中顺序：精确关卡 success=true -> 同 pattern success=true -> 空。
    返回空即触发「AI 自学导航」兜底（复用现有在线构建）。
    """
    steps = _pick_success_steps(data.get("stages", {}), stage_name)
    if steps:
        return steps
    if pattern_key:
        return _pick_success_steps(data.get("patterns", {}), pattern_key)
    return []
