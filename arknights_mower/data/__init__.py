import json
from pathlib import Path

from .. import __rootdir__
from ..utils.path import get_path
from ..utils.resource_pkg import register_resource_reload, resource_pkg_path


def _data_path(name: str) -> Path:
    """读取本实例在任务边界选定的完整资源版本。"""
    return resource_pkg_path(f"arknights_mower/data/{name}")


def stage_data_path() -> Path:
    """资源包里的全量关卡基线（常驻 + 当时活动）。"""
    return _data_path("stage_data_full.json")


def stage_data_overlay_path() -> Path:
    """热更的活动关卡层（只含 ACTIVITY），运行时读，热更落地即生效。"""
    return get_path("@app/tmp/hot_update/stage_data.json")


# 全量基线：启动时读入，资源包更新后原位刷新（常驻关卡只在基线）。
_stage_data_base = json.loads(stage_data_path().read_text("utf-8"))


def _stage_key(item: dict) -> str | None:
    """关卡唯一键：优先 id，缺省用 name，与调用方按 id/name 查询一致。"""
    key = item.get("id")
    if not key:
        key = item.get("name")
    return key


class StageData:
    """关卡信息合并视图：资源包全量基线 + 热更活动层（运行时读）。

    常驻关卡（MAIN/DAILY/剿灭）只在基线；热更层按约定只含 ACTIVITY 活动关，
    按 id（缺省 name）覆盖基线同名、补全新关。stageType 不做代码过滤——"只放活动关"
    属于生成侧约定，代码过滤反而可能误丢合法活动关；"永久关被误覆盖"依赖生成侧不丢
    永久 id，属数据契约。热更层缺失/损坏（读不到、非列表、元素非对象）时回退基线，
    不抛异常。调用方 `for item in stage_data_full` / `item.get("id")` 保持不变。
    """

    def _merge(self) -> list:
        base = list(_stage_data_base)
        overlay_path = stage_data_overlay_path()
        if overlay_path.exists():
            try:
                overlay = json.loads(overlay_path.read_text("utf-8"))
            except (OSError, ValueError):
                overlay = None
            if isinstance(overlay, list) and all(
                isinstance(item, dict) for item in overlay
            ):
                by_key = {}
                for i, item in enumerate(base):
                    key = _stage_key(item)
                    if key:
                        by_key.setdefault(key, i)
                for item in overlay:
                    key = _stage_key(item)
                    if key and key in by_key:
                        base[by_key[key]] = item
                    elif key:
                        base.append(item)
                        by_key[key] = len(base) - 1
        return base

    def __iter__(self):
        return iter(self._merge())


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
