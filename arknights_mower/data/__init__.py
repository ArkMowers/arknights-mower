import json
from pathlib import Path

from .. import __rootdir__
from ..utils.resource_pkg import register_resource_reload, resource_pkg_path


def _data_path(name: str) -> Path:
    """读取本实例在任务边界选定的完整资源版本。"""
    return resource_pkg_path(f"arknights_mower/data/{name}")


def stage_data_path() -> Path:
    """资源包里的全量关卡基线（常驻 + 当时活动）。"""
    return _data_path("stage_data_full.json")


# 全量关卡数据：启动时读入，资源包更新后原位刷新。
_stage_data_base = json.loads(stage_data_path().read_text("utf-8"))


class StageData:
    """关卡数据视图，保留资源包更新后的实时可见性。"""

    def __iter__(self):
        return iter(list(_stage_data_base))


stage_data_full = StageData()

# agents list in Arknights
agent_list = json.loads(_data_path("agent.json").read_text("utf-8"))

agent_profession = json.loads(_data_path("agent_profession.json").read_text("utf-8"))
workshop_formula = json.loads(_data_path("workshop_formula.json").read_text("utf-8"))

stage_order = json.loads(_data_path("stage_order.json").read_text("utf-8"))

# # agents base skills
# agent_base_config = json.loads(
#     Path(f'{__rootdir__}/data/agent-base.json').read_text('utf-8'))

# name of each room in the basement
base_room_list = json.loads(Path(f"{__rootdir__}/data/base.json").read_text("utf-8"))

# the camps to which the clue belongs
clue_name = json.loads(Path(f"{__rootdir__}/data/clue.json").read_text("utf-8"))

# goods sold in shop
shop_items = json.loads(Path(f"{__rootdir__}/data/shop.json").read_text("utf-8"))

# collection of the obtained ocr error
ocr_error = json.loads(Path(f"{__rootdir__}/data/ocr.json").read_text("utf-8"))

agent_arrange_order = json.loads(
    Path(f"{__rootdir__}/data/arrange_order.json").read_text("utf-8")
)

# chapter name in English
chapter_list = json.loads(Path(f"{__rootdir__}/data/chapter.json").read_text("utf-8"))

# list of supported levels
level_list = json.loads(Path(f"{__rootdir__}/data/level.json").read_text("utf-8"))

# open zones
zone_list = json.loads(Path(f"{__rootdir__}/data/zone.json").read_text("utf-8"))

# list of supported weekly levels
weekly_zones = json.loads(Path(f"{__rootdir__}/data/weekly.json").read_text("utf-8"))

# list of scene defined
scene_list = json.loads(Path(f"{__rootdir__}/data/scene.json").read_text("utf-8"))

# recruit database
recruit_agent = json.loads(_data_path("recruit.json").read_text("utf-8"))

recruit_result = json.loads(_data_path("recruit_result.json").read_text("utf-8"))

key_mapping = json.loads(_data_path("key_mapping.json").read_text("utf-8"))


def _build_recruit_views(recruit_data: dict, result_data: dict):
    tags = {"资深干员", "高级资深干员"}
    for recruit in recruit_data.values():
        tags.update(recruit["tags"])

    by_tag = {}
    for tag in tags:
        by_tag[tag] = []
        for agent, recruit in recruit_data.items():
            if {tag} < set(recruit["tags"]):
                by_tag[tag].append(
                    {
                        "id": agent,
                        "name": recruit["name"],
                        "star": recruit["stars"],
                    }
                )

    templates = []
    for result in result_data.values():
        templates.extend(result)
    return sorted(tags), by_tag, templates


recruit_tag, agent_with_tags, result_template_list = _build_recruit_views(
    recruit_agent, recruit_result
)


def _replace_list(target: list, source: list) -> None:
    target[:] = source


def _replace_dict(target: dict, source: dict) -> None:
    target.clear()
    target.update(source)


def _read_resource_json(name: str, expected_type: type):
    value = json.loads(_data_path(name).read_text("utf-8"))
    if not isinstance(value, expected_type):
        raise ValueError(f"资源数据 {name} 类型错误")
    return value


@register_resource_reload
def reload_resource_data() -> None:
    """资源包切换后原位刷新数据，保留各调用模块已经导入的对象引用。"""
    new_stage_data_base = _read_resource_json("stage_data_full.json", list)
    new_agent_list = _read_resource_json("agent.json", list)
    new_agent_profession = _read_resource_json("agent_profession.json", dict)
    new_workshop_formula = _read_resource_json("workshop_formula.json", dict)
    new_stage_order = _read_resource_json("stage_order.json", list)
    new_recruit_agent = _read_resource_json("recruit.json", dict)
    new_recruit_result = _read_resource_json("recruit_result.json", dict)
    new_key_mapping = _read_resource_json("key_mapping.json", dict)
    new_recruit_tag, new_agent_with_tags, new_result_template_list = (
        _build_recruit_views(new_recruit_agent, new_recruit_result)
    )

    _replace_list(_stage_data_base, new_stage_data_base)
    _replace_list(agent_list, new_agent_list)
    _replace_dict(agent_profession, new_agent_profession)
    _replace_dict(workshop_formula, new_workshop_formula)
    _replace_list(stage_order, new_stage_order)
    _replace_dict(recruit_agent, new_recruit_agent)
    _replace_dict(recruit_result, new_recruit_result)
    _replace_dict(key_mapping, new_key_mapping)
    _replace_list(recruit_tag, new_recruit_tag)
    _replace_dict(agent_with_tags, new_agent_with_tags)
    _replace_list(result_template_list, new_result_template_list)
