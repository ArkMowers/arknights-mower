"""资源包 version.json 的纯逻辑（无重依赖，可直接单测）。

- pick_latest_activity / pick_latest_gacha：从活动/卡池表取"最新一个"。
- 包内容哈希：决定 res_version 的哈希部分，反映实际产物内容是否变化。

auto_get_res_new.py 生成完后据此写 version.json；
MowerResource 管线发布时从本模块导入 RES_PACKAGE_* 打包（单一来源，避免两处漂移）。
"""

import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 资源包文件集（相对仓库根）：生成脚本的产出，内容哈希覆盖的就是这些。
RES_PACKAGE_DIRS = (
    "ui/public/depot",
    "ui/public/avatar",
    "ui/public/building_skill",
)
RES_PACKAGE_MODELS = (
    "arknights_mower/models/NORMAL.pkl",
    "arknights_mower/models/CONSUME.pkl",
    "arknights_mower/models/recruit.pkl",
    "arknights_mower/models/recruit_result.pkl",
    "arknights_mower/models/operator_room.model",
    "arknights_mower/models/operator_select.model",
    "arknights_mower/models/operator_train.model",
)
RES_PACKAGE_DATA = (
    "arknights_mower/data/agent.json",
    "arknights_mower/data/agent_profession.json",
    "arknights_mower/data/key_mapping.json",
    "arknights_mower/data/stage_data_full.json",
    "arknights_mower/data/stage_order.json",
    "arknights_mower/data/recruit.json",
    "arknights_mower/data/recruit_result.json",
    "arknights_mower/data/skill_data.json",
    "arknights_mower/data/workshop_formula.json",
    # 前端基建技能数据：静态 import 作内置兜底，运行时由资源包下发
    "ui/src/pages/basement_skill/skill.json",
    "ui/src/pages/basement_skill/buffer.json",
)


def package_file_paths(root) -> list:
    """展开资源包实际存在的文件（相对 root 的路径），按路径排序。"""
    root = Path(root)
    rels = []
    for rel in RES_PACKAGE_DIRS:
        d = root / rel
        if d.is_dir():
            rels.extend(p.relative_to(root) for p in d.rglob("*") if p.is_file())
    for rel in RES_PACKAGE_MODELS + RES_PACKAGE_DATA:
        p = root / rel
        if p.is_file():
            rels.append(p.relative_to(root))
    return sorted(rels)


def content_hash(root, rels) -> str:
    """对相对路径文件集算聚合 sha256（含路径，结果与顺序无关）。

    Windows 检出（core.autocrlf）会把文本文件的 LF 转成 CRLF。明确判定为文本的
    文件（见 _TEXT_SUFFIXES）归一化到 LF，使摘要在任何检出下与打包内容一致；
    二进制文件一律按原始字节参与。分块读取避免一次载入整文件。
    """
    root = Path(root)
    digest = hashlib.sha256()
    for rel in sorted(rels, key=lambda p: p.as_posix()):
        digest.update(rel.as_posix().encode("utf-8"))
        digest.update(b"\0")
        with open(root / rel, "rb") as f:
            _update_digest(digest, f, _is_text(rel))
    return digest.hexdigest()


# 文本后缀：仅这些类型会在 Git 检出时把 LF 转成 CRLF，才值得归一化。二进制文件
# 一律按原始字节参与——仅凭「无 NUL 字节」误判为文本，会让两份内容不同的二进制
# 样例被换行归一化后得到相同摘要。
_TEXT_SUFFIXES = frozenset(
    {
        ".json",
        ".txt",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".css",
        ".html",
        ".md",
        ".yaml",
        ".yml",
    }
)


def _is_text(rel) -> bool:
    """Whether ``rel`` names a text file whose line endings Git may rewrite."""
    return Path(rel).suffix.lower() in _TEXT_SUFFIXES


def _update_digest(digest, stream, normalize: bool) -> None:
    """Hash a stream, normalizing CRLF to LF for text files.

    A trailing ``\\r`` can pair with the leading ``\\n`` of the next chunk, so it
    is carried over between reads instead of being dropped.
    """
    if not normalize:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
        return
    pending = b""
    while chunk := stream.read(1 << 20):
        data = pending + chunk
        if data.endswith(b"\r"):
            pending = b"\r"
            data = data[:-1]
        else:
            pending = b""
        digest.update(data.replace(b"\r\n", b"\n"))
    if pending:
        digest.update(pending)


def _pick_latest(entries, filter_field, skip_keys, time_key, name_key) -> dict:
    """过滤掉 filter_field 含任一 skip_key 的条目，取 time_key 最大者投影。"""
    kept = [
        e
        for e in entries
        if not any(k in (e.get(filter_field) or "") for k in skip_keys)
    ]
    if not kept:
        return {}
    latest = max(kept, key=lambda e: e.get(time_key, 0))
    return {
        "name": latest.get(name_key),
        "time": latest.get(time_key),
        "endTime": latest.get("endTime"),
    }


def pick_latest_activity(activity_table: dict) -> dict:
    """活动表 basicInfo 里开启时间最新的一个（剔签到/预约/收藏夹类）。"""
    return _pick_latest(
        activity_table.get("basicInfo", {}).values(),
        "type",
        ("CHECKIN", "ONLY", "COLLECTION"),
        "startTime",
        "name",
    )


def pick_latest_gacha(gacha_table: dict) -> dict:
    """卡池表 gachaPoolClient 里开启时间最新的一个（剔标准池）。"""
    return _pick_latest(
        gacha_table.get("gachaPoolClient", []),
        "gachaPoolName",
        ("适合多种场合的强力干员",),
        "openTime",
        "gachaPoolName",
    )


def display_version(version_info: dict) -> str:
    """客户端展示用可读版本号：较晚开启的 activity/gacha 的 name + #构建日期（MMDD）。"""
    later = max(
        (version_info.get("activity") or {}, version_info.get("gacha") or {}),
        key=lambda e: e.get("time", 0),
    )
    name = later.get("name")
    if not name:
        return ""
    parsed = parse_version(version_info.get("res_version") or "")
    if parsed:
        mmdd = f"{parsed[1]:02d}{parsed[2]:02d}"
    elif later.get("time"):
        mmdd = datetime.fromtimestamp(
            later["time"], tz=timezone(timedelta(hours=8))
        ).strftime("%m%d")
    else:
        return ""
    return f"{name}#{mmdd}"


_VERSION_RE = re.compile(r"^v?(\d{4})\.(\d{2})\.(\d{2})-([0-9a-fA-F]{6,40})$")


def parse_version(v: str, require_v: bool = False) -> tuple[int, int, int, str] | None:
    """解析「日期-内容哈希」版本串 -> (年, 月, 日, 哈希)；非法返回 None。

    热更 tag（``vYYYY.MM.DD-hash``，前导 v 强制）与资源 res_version（v 可选）共用。
    """
    m = _VERSION_RE.match(v or "")
    if not m:
        return None
    if require_v and not (v or "").startswith("v"):
        return None
    return (
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        m.group(4),
    )


def version_newer(remote: str, local: str, require_v: bool = False) -> bool:
    """remote 严格新于 local 才 True（防手滑发旧版降级）。

    日期不同按日期定序；同日哈希不同 = 内容变了 = 视为更新。本地缺失时 remote 恒新。
    无法解析的版本回退到「不同即更新」的保守行为。
    """
    remote_t = parse_version(remote, require_v=require_v)
    local_t = parse_version(local, require_v=require_v)
    if remote_t is None or local_t is None:
        return remote != local
    if remote_t[:3] != local_t[:3]:
        return remote_t[:3] > local_t[:3]
    return remote_t[3] != local_t[3]
