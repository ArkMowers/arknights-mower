"""Validate and store ordinary and SSS scripts in separate libraries."""

import hashlib
import json
import re

from arknights_mower.utils.path import get_path
from arknights_mower.utils.update_runtime import write_json

MAX_SCRIPT_BYTES = 1024 * 1024
MAX_SCRIPTS = 64
MAX_TOTAL_BYTES = 8 * 1024 * 1024


def run_key(conf):
    return hashlib.sha256(
        json.dumps(conf.model_dump(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def queue_key(conf):
    return hashlib.sha256(
        json.dumps(
            conf.model_dump(include={"run_id", "scripts"}),
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def script_path(script_id, *, sss=False):
    if not isinstance(script_id, str) or not re.fullmatch(r"[a-f0-9]{64}", script_id):
        raise ValueError("作业标识无效")
    root = get_path("@app/config/sss-copilots" if sss else "@app/config/copilots")
    path = root / f"{script_id}.json"
    if root.is_symlink() or path.is_symlink():
        raise ValueError("作业目录或文件不能使用符号链接")
    return path


def parse_script(raw, *, sss=False):
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
    return data


def script_info(script_id, data, *, sss=False):
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
    return info


def list_scripts(*, sss=False):
    root = get_path("@app/config/sss-copilots" if sss else "@app/config/copilots")
    if root.is_symlink():
        raise ValueError("作业目录不能使用符号链接")
    paths = sorted(root.glob("*.json"))
    if len(paths) > MAX_SCRIPTS:
        raise ValueError("作业文件超过 64 个，请整理作业目录")
    result = []
    for path in paths:
        script_id = path.stem
        path = script_path(script_id, sss=sss)
        with path.open("rb") as stream:
            data = parse_script(stream.read(MAX_SCRIPT_BYTES + 1), sss=sss)
        result.append(script_info(script_id, data, sss=sss))
    return result


def store_script(raw, *, sss=False):
    data = parse_script(raw, sss=sss)
    content = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(content) > MAX_SCRIPT_BYTES:
        raise ValueError("作业文件不能超过 1 MB")
    script_id = hashlib.sha256(content).hexdigest()
    path = script_path(script_id, sss=sss)
    files = list(path.parent.glob("*.json"))
    if not path.exists() and (
        len(files) >= MAX_SCRIPTS
        or sum(item.stat().st_size for item in files) + len(content) > MAX_TOTAL_BYTES
    ):
        raise ValueError("作业存储已满，请先删除不再使用的作业")
    write_json(path, data)
    return script_info(script_id, data, sss=sss)


def build_copilot_params(conf):
    if not conf.scripts:
        raise ValueError("请先导入并选择自动战斗作业")
    queue = []
    for item in conf.scripts:
        path = script_path(item.id)
        with path.open("rb") as stream:
            parse_script(stream.read(MAX_SCRIPT_BYTES + 1))
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
