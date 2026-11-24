"""Validate and store ordinary, paradox and SSS scripts in separate libraries."""

import hashlib
import json
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from arknights_mower.utils.path import get_path
from arknights_mower.utils.update_runtime import write_json

MAX_SCRIPT_BYTES = 1024 * 1024
MAX_SCRIPTS = 64
MAX_TOTAL_BYTES = 8 * 1024 * 1024


def run_key(conf):
    settings = conf.model_dump()
    if settings.get("operbox_assist") is False:
        del settings["operbox_assist"]  # Preserve pre-existing progress when disabled.
    return hashlib.sha256(
        json.dumps(settings, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def queue_key(conf):
    return hashlib.sha256(
        json.dumps(
            conf.model_dump(include={"run_id", "scripts"}),
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def script_root(*, sss=False, paradox=False):
    name = "sss-copilots" if sss else "paradox-copilots" if paradox else "copilots"
    return get_path(f"@app/config/{name}")


def script_path(script_id, *, sss=False, paradox=False):
    if not isinstance(script_id, str) or not re.fullmatch(r"[a-f0-9]{64}", script_id):
        raise ValueError("作业标识无效")
    root = script_root(sss=sss, paradox=paradox)
    path = root / f"{script_id}.json"
    if root.is_symlink() or path.is_symlink():
        raise ValueError("作业目录或文件不能使用符号链接")
    return path


def parse_script(raw, *, sss=False, paradox=False):
    if len(raw) > MAX_SCRIPT_BYTES:
        raise ValueError("作业文件不能超过 1 MB")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("作业文件不是有效 JSON") from exc
    if sss:
        from arknights_mower.utils.maa_sss import validate_script

        return validate_script(data)
    if not isinstance(data, dict) or data.get("type") == "SSS":
        raise ValueError("请导入普通自动战斗作业，保全作业应在保全派驻中导入")
    stage = data.get("stage_name")
    actions = data.get("actions")
    if not isinstance(stage, str) or not stage.strip() or len(stage) > 256:
        raise ValueError("作业缺少有效关卡名称")
    if (
        not isinstance(actions, list)
        or len(actions) > 10000
        or not all(isinstance(item, dict) for item in actions)
    ):
        raise ValueError("作业需要有效的 actions 列表，最多 10000 步")
    for key in ("opers", "groups"):
        if key in data and (
            not isinstance(data[key], list)
            or not all(isinstance(item, dict) for item in data[key])
        ):
            raise ValueError(f"作业的 {key} 必须是对象列表")
    is_paradox = bool(re.fullmatch(r"mem_[A-Za-z0-9_]+_[1-3]", stage))
    if paradox and not is_paradox:
        raise ValueError("请导入悖论模拟作业，关卡名称应为 mem_ 开头的关卡标识")
    if not paradox and is_paradox:
        raise ValueError("悖论模拟作业应在悖论模拟中导入")
    return data


def script_info(script_id, data, *, sss=False, paradox=False):
    doc = data.get("doc")
    doc = doc if isinstance(doc, dict) else {}
    info = {
        "id": script_id,
        "stage_name": data["stage_name"],
        "title": str(doc.get("title") or data["stage_name"])[:1024],
        "details": str(doc.get("details") or "")[:4096],
        "stages" if sss else "actions": len(data["stages"] if sss else data["actions"]),
    }
    if sss:
        info["operators"] = [
            {"name": str(item.get("name", ""))[:256], "skill": item.get("skill", 0)}
            for item in data.get("opers", [])[:64]
        ]
    elif not paradox:
        difficulty = data.get("difficulty")
        info["difficulty"] = (
            difficulty if type(difficulty) is int and difficulty in (1, 2, 3) else 0
        )
    return info


def list_scripts(*, sss=False, paradox=False):
    root = script_root(sss=sss, paradox=paradox)
    if root.is_symlink():
        raise ValueError("作业目录不能使用符号链接")
    paths = sorted(root.glob("*.json"))
    if len(paths) > MAX_SCRIPTS:
        raise ValueError("作业文件超过 64 个，请整理作业目录")
    result = []
    for path in paths:
        script_id = path.stem
        path = script_path(script_id, sss=sss, paradox=paradox)
        with path.open("rb") as stream:
            data = parse_script(
                stream.read(MAX_SCRIPT_BYTES + 1), sss=sss, paradox=paradox
            )
        result.append(script_info(script_id, data, sss=sss, paradox=paradox))
    return result


def _script_content(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _normalized_copilot_content(data):
    from arknights_mower.utils.maa_copilot_normalization import normalize_copilot

    normalize_copilot(data)
    return _script_content(data)


def store_script(raw, *, sss=False, paradox=False):
    data = parse_script(raw, sss=sss, paradox=paradox)
    original = _script_content(data)
    content = original if sss or paradox else _normalized_copilot_content(data)
    if len(content) > MAX_SCRIPT_BYTES:
        raise ValueError("作业文件不能超过 1 MB")
    script_id = hashlib.sha256(content).hexdigest()
    path = script_path(script_id, sss=sss, paradox=paradox)
    if original != content and not path.exists():
        old_id = hashlib.sha256(original).hexdigest()
        old_path = script_path(old_id)
        if old_path.exists():
            with old_path.open("rb") as stream:
                if stream.read(MAX_SCRIPT_BYTES + 1) == original:
                    return script_info(old_id, data)
    files = list(path.parent.glob("*.json"))
    if not path.exists() and (
        len(files) >= MAX_SCRIPTS
        or sum(item.stat().st_size for item in files) + len(content) > MAX_TOTAL_BYTES
    ):
        raise ValueError("作业存储已满，请先删除不再使用的作业")
    write_json(path, data)
    return script_info(script_id, data, sss=sss, paradox=paradox)


def _copilot_operators():
    from arknights_mower.utils.mastery_recommendation import (
        get_cultivate_snapshot,
        get_skill_data,
    )

    snapshot = get_cultivate_snapshot()
    error = "请先在「养成规划」中刷新森空岛干员练度，再使用辅助编队"

    def integer(entry, key, low, high):
        value = entry.get(key) if isinstance(entry, dict) else None
        if type(value) is not int or not low <= value <= high:
            raise ValueError(error)
        return value

    if snapshot is None:
        raise ValueError(error)
    definitions = get_skill_data().get("growth", {}).get("characters", {})
    operators = []
    seen = set()
    for char in snapshot["data"]["characters"]:
        if char["id"] in seen:
            raise ValueError(error)
        seen.add(char["id"])
        definition = definitions.get(char["id"])
        if not definition:
            continue
        skills = char.get("skills", [])
        equips = char.get("equips", [])
        if not isinstance(skills, list) or not isinstance(equips, list):
            raise ValueError(error)

        modules = {module["id"]: module["type"] for module in definition["modules"]}
        equipped = []
        for equip in equips:
            level = integer(equip, "level", 0, 3)
            equip_id = equip.get("id")
            if not isinstance(equip_id, str):
                raise ValueError(error)
            if not level or equip_id.startswith("uniequip_001_"):
                continue
            branch = modules.get(equip_id, "").rsplit("-", 1)[-1]
            if branch not in {"A", "B", "D", "X", "Y"}:
                raise ValueError("缺少模组资源，请更新 Mower 资源后再使用辅助编队")
            equipped.append({"id": equip_id, "type": branch, "level": level})
        operators.append(
            {
                "id": char["id"],
                "name": definition["name"],
                "own": True,
                "rarity": definition["rarity"],
                "elite": integer(char, "evolvePhase", 0, 2),
                "level": integer(char, "level", 1, 90),
                "potential": integer(char, "potentialRank", 0, 5) + 1,
                "mainSkillLevel": integer(char, "mainSkillLevel", 1, 7)
                if skills
                else 0,
                "skills": [
                    {"level": integer(skill, "level", 0, 3)} for skill in skills
                ],
                "equips": equipped,
            }
        )
    if not any(oper["skills"] for oper in operators):
        raise ValueError(error)
    return operators


@contextmanager
def copilot_formation_params(params, conf, maa):
    if not params.get("formation") or not conf.operbox_assist:
        yield params
        return

    from arknights_mower.utils.maa_update import is_maa_version_newer

    if is_maa_version_newer("v6.19.0", maa.get_version()):
        raise ValueError("使用干员练度辅助编队需要 MAA v6.19.0 或更新版本")
    operators = _copilot_operators()
    root = get_path("@app/tmp")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix="copilot-") as directory:
        path = Path(directory) / "OperBoxData.json"
        path.write_text(
            json.dumps({"own_opers": operators}, ensure_ascii=False), "utf-8"
        )
        yield {**params, "operbox_data_path": str(path.absolute())}


def build_copilot_params(conf, work_dir):
    if not conf.scripts:
        raise ValueError("请先导入并选择自动战斗作业")
    queue = []
    for item in conf.scripts:
        path = script_path(item.id)
        with path.open("rb") as stream:
            data = parse_script(stream.read(MAX_SCRIPT_BYTES + 1))
        before = _script_content(data)
        content = _normalized_copilot_content(data)
        if len(content) > MAX_SCRIPT_BYTES:
            raise ValueError("作业文件不能超过 1 MB")
        if before != content:
            path = work_dir / path.name
            write_json(path, data)
        entry = {"filename": str(path), "is_raid": item.is_raid}
        if item.nav_name_override.strip():
            entry["nav_name_override"] = item.nav_name_override.strip()
        queue.append(entry)
    params = {
        "copilot_list": queue,
        "use_sanity_potion": conf.use_sanity_potion,
        "formation": conf.formation,
    }
    if conf.formation:
        params.update(
            formation_index=conf.formation_index,
            add_trust=conf.add_trust,
            ignore_requirements=conf.ignore_requirements,
            support_unit_usage=conf.support_unit_usage,
            user_additional=[
                item.model_dump() for item in conf.user_additional if item.name.strip()
            ],
        )
        if conf.support_unit_usage == 2:
            if not conf.support_unit_name.strip():
                raise ValueError("请填写指定助战干员的中文名")
            params["support_unit_name"] = conf.support_unit_name.strip()
    return params


def copilot_navigation_target(item):
    from arknights_mower.data import stage_data_full

    target = item.nav_name_override.strip()
    if not target:
        with script_path(item.id).open("rb") as stream:
            target = parse_script(stream.read(MAX_SCRIPT_BYTES + 1))[
                "stage_name"
            ].strip()
    for stage in stage_data_full:
        if target in (stage.get("id"), stage.get("name")):
            return stage["id"]
    main = re.fullmatch(r"main_(\d+)-(\d+)", target, re.IGNORECASE)
    if main:
        return f"{int(main[1])}-{int(main[2])}"
    if re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", target.upper()):
        return target.upper()
    raise ValueError("无法确定作业关卡，请填写导航关卡名，例如 1-7 或活动关卡编号")


def build_paradox_params(item, index):
    path = script_path(item.id, paradox=True)
    with path.open("rb") as stream:
        parse_script(stream.read(MAX_SCRIPT_BYTES + 1), paradox=True)
    return {"list": [{"id": index, "filename": str(path)}]}
