"""Read only this device's already-synced Skland roster; never read credentials.

The cultivate snapshot has no reliable character/UID binding. The caller must
label it *device cache, account unverified* until users confirm the source.
"""

from __future__ import annotations

import json
from pathlib import Path

from arknights_mower.utils.path import get_path
from arknights_mower.utils.resource_pkg import resource_pkg_path


def roster_preview(base: Path | None = None) -> dict:
    cache = (
        Path(base) / "tmp" / "cultivate.json"
        if base is not None
        else get_path("@app/tmp/cultivate.json")
    )
    catalog_path = resource_pkg_path("arknights_mower/data/operator_catalog.json")
    if not cache.is_file():
        return {
            "available": False,
            "message": "尚无森空岛干员缓存；请在 Mower 中手动同步森空岛干员数据。",
        }
    if not catalog_path.is_file():
        return {"available": False, "message": "当前安装缺少干员资源表。"}
    if cache.stat().st_size > 8_000_000 or catalog_path.stat().st_size > 8_000_000:
        raise ValueError("本机干员缓存文件异常过大")
    raw = json.loads(cache.read_text(encoding="utf-8"))
    chars = raw.get("data", {}).get("characters")
    if not isinstance(chars, list) or not chars:
        return {
            "available": False,
            "message": "当前缓存没有有效的森空岛干员列表，请先在 Mower 中同步。",
        }
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    result = []
    unknown = 0
    for char in chars:
        if not isinstance(char, dict) or not isinstance(char.get("id"), str):
            continue
        meta = catalog.get(char["id"])
        if not isinstance(meta, dict) or not isinstance(meta.get("name"), str):
            unknown += 1
            continue
        result.append(
            {
                "id": char["id"],
                "name": meta["name"],
                "rarity": meta.get("rarity"),
                "profession": meta.get("profession", ""),
                "level": char.get("level"),
                "evolve_phase": char.get("evolvePhase"),
                "potential_rank": char.get("potentialRank"),
            }
        )
    result.sort(
        key=lambda a: (-(a["rarity"] if isinstance(a["rarity"], int) else 0), a["name"])
    )
    return {
        "available": True,
        "source": "current-device-skland-cache",
        "account_verified": False,
        "message": "当前 Mower 实例的森空岛缓存；缓存未记录可核验的角色 UID，请先确认它属于所选寻访账号。",
        "observed_at": int(cache.stat().st_mtime),
        "operator_count": len(result),
        "unknown_id_count": unknown,
        "operators": result,
        "catalog_count": len(catalog),
    }
