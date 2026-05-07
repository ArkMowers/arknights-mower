#!/usr/bin/env python3
"""
从 ArknightsGameResource 提取专精所需数据，生成精简 JSON。

使用方式：
  python extract_skill_data.py [--source DIR] [--output FILE]

默认：
  --source  ArknightsGameResource/gamedata/excel
  --output  arknights_mower/resources/skill_data.json

每次游戏资源更新后重新运行即可。
"""

import argparse
import json
import sys
import time
from pathlib import Path

DEFAULT_SOURCE = Path(__file__).parent / "ArknightsGameResource" / "gamedata" / "excel"
DEFAULT_OUTPUT = Path(__file__).parent / "arknights_mower" / "resources" / "skill_data.json"


def extract(source_dir: Path, output_path: Path):
    char_path = source_dir / "character_table.json"
    item_path = source_dir / "item_table.json"

    if not char_path.exists():
        print(f"错误：未找到 {char_path}", file=sys.stderr)
        sys.exit(1)
    if not item_path.exists():
        print(f"错误：未找到 {item_path}", file=sys.stderr)
        sys.exit(1)

    print(f"读取 {char_path} ...")
    t0 = time.time()
    with open(char_path, "r", encoding="utf-8") as f:
        char_table = json.load(f)
    print(f"  character_table.json 读取完成 ({time.time() - t0:.1f}s, {len(char_table)} 条目)")

    print(f"读取 {item_path} ...")
    t0 = time.time()
    with open(item_path, "r", encoding="utf-8") as f:
        item_table_raw = json.load(f)
    item_table = item_table_raw.get("items", {})
    print(f"  item_table.json 读取完成 ({time.time() - t0:.1f}s, {len(item_table)} 条目)")

    # ── 提取干员技能数据 ──
    characters = {}
    skill_count = 0
    skipped = 0

    for char_id, char_info in char_table.items():
        skills_raw = char_info.get("skills", [])
        if not skills_raw:
            skipped += 1
            continue

        has_any_upgrade = False
        skills = []

        for skill_def in skills_raw:
            level_up_cost_cond = skill_def.get("levelUpCostCond", [])
            if not level_up_cost_cond:
                continue
            has_any_upgrade = True

            levels = []
            for entry in level_up_cost_cond:
                level_up_cost = entry.get("levelUpCost", [])
                lvl_up_time = entry.get("lvlUpTime", 0)
                materials = [
                    {"id": mat["id"], "count": mat["count"]}
                    for mat in level_up_cost
                    if mat.get("type") == "MATERIAL"
                ]
                levels.append({
                    "materials": materials,
                    "time": lvl_up_time
                })

            skills.append({
                "skillId": skill_def.get("skillId", ""),
                "levels": levels
            })

        if not has_any_upgrade:
            skipped += 1
            continue

        characters[char_id] = {
            "name": char_info.get("name", char_id),
            "rarity": char_info.get("rarity", 0) + 1,
            "profession": char_info.get("profession", ""),
            "skills": skills
        }
        skill_count += len(skills)

    # ── 提取物品名称（仅材料类） ──
    items = {}
    for item_id, item_info in item_table.items():
        classify = item_info.get("classifyType", "")
        if classify == "MATERIAL":
            items[item_id] = {
                "name": item_info.get("name", item_id),
                "icon": item_info.get("iconId", ""),
                "rarity": item_info.get("rarity", 0)
            }

    # ── 提取合成路径（composite_table） ──
    composite_path = Path(__file__).parent.parent / "frontend-v2-plus-dev" / "src" / "static" / "json" / "material" / "composite_table.v2.json"
    composite = {}
    if composite_path.exists():
        print(f"读取 {composite_path} ...")
        t0 = time.time()
        with open(composite_path, "r", encoding="utf-8") as f:
            composite_raw = json.load(f)
        for entry in composite_raw:
            if not entry.get("resolve", False):
                composite[entry["itemId"]] = {
                    "name": entry.get("itemName", ""),
                    "rarity": entry.get("rarity", 0),
                    "pathway": [
                        {"id": p["itemId"], "name": p.get("itemName", ""), "count": p.get("count", 1)}
                        for p in entry.get("pathway", [])
                    ]
                }
        print(f"  composite_table 读取完成 ({time.time() - t0:.1f}s, {len(composite)} 合成配方)")
    else:
        print(f"警告：未找到 {composite_path}，跳过合成路径提取")

    # ── 输出 ──
    output = {
        "_meta": {
            "description": "专精推荐精简数据 - 由 extract_skill_data.py 生成",
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "character_count": len(characters),
            "item_count": len(items),
            "skill_entry_count": skill_count,
            "composite_count": len(composite)
        },
        "characters": characters,
        "items": items,
        "composite": composite
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = output_path.stat().st_size / 1024
    print(f"\n生成完成: {output_path}")
    print(f"  干员数: {len(characters)}")
    print(f"  物品数: {len(items)}")
    print(f"  技能条目: {skill_count}")
    print(f"  跳过干员: {skipped} (无专精数据)")
    print(f"  文件大小: {size_kb:.0f} KB")


def main():
    parser = argparse.ArgumentParser(description="从 ArknightsGameResource 提取专精数据")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="ArknightsGameResource/gamedata/excel 目录路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="输出 JSON 文件路径")
    args = parser.parse_args()
    extract(args.source, args.output)


if __name__ == "__main__":
    main()
