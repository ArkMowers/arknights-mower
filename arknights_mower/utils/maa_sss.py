"""SSS script validation, legacy import and single-round task parameters."""

import json

from arknights_mower.utils.maa_copilot import (
    MAX_SCRIPT_BYTES,
    parse_script,
    script_path,
    store_script,
)
from arknights_mower.utils.path import get_path


def validate_script(data):
    if not isinstance(data, dict) or data.get("type") != "SSS":
        raise ValueError("请导入保全派驻作业")
    if (
        not isinstance(data.get("stage_name"), str)
        or not data["stage_name"].strip()
        or len(data["stage_name"]) > 256
    ):
        raise ValueError("作业缺少有效关卡名称")
    if not isinstance(data.get("tool_men"), dict):
        raise ValueError("保全作业缺少 tool_men")
    stages = data.get("stages")
    if not isinstance(stages, list) or not 1 <= len(stages) <= 100:
        raise ValueError("保全作业需要 stages 列表，最多 100 关")
    for stage in stages:
        if (
            not isinstance(stage, dict)
            or not isinstance(stage.get("draw_as_possible"), bool)
            or not isinstance(stage.get("strategies"), list)
        ):
            raise ValueError("保全关卡格式无效")
        parse_script(json.dumps(stage).encode())
    for key in ("opers", "groups"):
        if key in data and (
            not isinstance(data[key], list)
            or not all(isinstance(item, dict) for item in data[key])
        ):
            raise ValueError(f"作业的 {key} 必须是对象列表")
    return data


def migrate_legacy(conf):
    if "scripts" in conf.model_fields_set:
        return False
    legacy = get_path("@app/sss.json")
    if not legacy.is_file():
        return False
    if legacy.is_symlink():
        raise ValueError("保全作业不能使用符号链接")
    with legacy.open("rb") as stream:
        info = store_script(stream.read(MAX_SCRIPT_BYTES + 1), sss=True)
    from arknights_mower.utils.config.conf import LongTaskPart

    conf.scripts = [
        LongTaskPart.SSSQueueItem(id=info["id"], type=conf.type, ec=conf.ec)
    ]
    return True


def build_sss_params(item):
    path = script_path(item.id, sss=True)
    with path.open("rb") as stream:
        parse_script(stream.read(MAX_SCRIPT_BYTES + 1), sss=True)
    return {"filename": str(path), "loop_times": 1}
