import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _require_path(relative_path: str) -> str:
    path = PROJECT_ROOT / relative_path
    if not path.exists():
        raise FileNotFoundError(f"required build asset is missing: {path}")
    return str(path)


def _find_npm_executable() -> str:
    for candidate in ("npm.cmd", "npm"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("npm executable not found in PATH")


def ensure_frontend_built():
    ui_dir = PROJECT_ROOT / "ui"
    package_json = ui_dir / "package.json"
    if not package_json.exists():
        raise FileNotFoundError(f"frontend package.json is missing: {package_json}")

    if sys.platform.startswith("win"):
        subprocess.run(
            ["cmd", "/c", "npm", "run", "build"],
            cwd=ui_dir,
            check=True,
        )
        return

    npm_executable = _find_npm_executable()
    subprocess.run([npm_executable, "run", "build"], cwd=ui_dir, check=True)


def ensure_skill_data_extracted():
    import json as _json
    import time as _time

    output_path = PROJECT_ROOT / "arknights_mower" / "resources" / "skill_data.json"
    char_table_path = (
        PROJECT_ROOT
        / "ArknightsGameResource"
        / "gamedata"
        / "excel"
        / "character_table.json"
    )
    item_table_path = (
        PROJECT_ROOT
        / "ArknightsGameResource"
        / "gamedata"
        / "excel"
        / "item_table.json"
    )
    composite_path = (
        PROJECT_ROOT
        / "frontend-v2-plus-dev"
        / "src"
        / "static"
        / "json"
        / "material"
        / "composite_table.v2.json"
    )

    if not char_table_path.exists():
        print(f"跳过专精数据提取: {char_table_path} 不存在")
        return

    if (
        output_path.exists()
        and output_path.stat().st_mtime > char_table_path.stat().st_mtime
    ):
        print(f"专精数据已是最新: {output_path}")
        return

    print("正在提取专精数据...")

    with open(char_table_path, "r", encoding="utf-8") as f:
        char_table = _json.load(f)
    with open(item_table_path, "r", encoding="utf-8") as f:
        item_table = _json.load(f).get("items", {})

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
                levels.append({"materials": materials, "time": lvl_up_time})

            skills.append({"skillId": skill_def.get("skillId", ""), "levels": levels})

        if not has_any_upgrade:
            skipped += 1
            continue

        characters[char_id] = {
            "name": char_info.get("name", char_id),
            "rarity": char_info.get("rarity", 0) + 1,
            "profession": char_info.get("profession", ""),
            "skills": skills,
        }
        skill_count += len(skills)

    items = {}
    for item_id, item_info in item_table.items():
        if item_info.get("classifyType") == "MATERIAL":
            items[item_id] = {
                "name": item_info.get("name", item_id),
                "icon": item_info.get("iconId", ""),
                "rarity": item_info.get("rarity", 0),
            }

    composite = {}
    if composite_path.exists():
        with open(composite_path, "r", encoding="utf-8") as f:
            composite_raw = _json.load(f)
        for entry in composite_raw:
            if not entry.get("resolve", False):
                composite[entry["itemId"]] = {
                    "name": entry.get("itemName", ""),
                    "rarity": entry.get("rarity", 0),
                    "pathway": [
                        {
                            "id": p["itemId"],
                            "name": p.get("itemName", ""),
                            "count": p.get("count", 1),
                        }
                        for p in entry.get("pathway", [])
                    ],
                }

    output = {
        "_meta": {
            "description": "专精推荐精简数据 - 由 build_assets.py 自动生成",
            "generated": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "character_count": len(characters),
            "item_count": len(items),
            "skill_entry_count": skill_count,
            "composite_count": len(composite),
        },
        "characters": characters,
        "items": items,
        "composite": composite,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        _json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = output_path.stat().st_size / 1024
    print(
        f"  干员: {len(characters)}, 物品: {len(items)}, 技能: {skill_count}, 合成: {len(composite)}"
    )
    print(f"  输出: {output_path} ({size_kb:.0f} KB)")


def get_pyinstaller_common_datas():
    ensure_frontend_built()
    ensure_skill_data_extracted()
    return [
        (_require_path("arknights_mower"), "arknights_mower"),
        (_require_path("logo.png"), "."),
        (_require_path("CHANGELOG.md"), "."),
        (_require_path("ui/dist"), "./ui/dist"),
    ]
