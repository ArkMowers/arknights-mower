import json
from pathlib import Path

from .. import __rootdir__
from ..utils.path import get_path
from ..utils.resource_pkg import resource_pkg_path


def _data_path(name: str) -> Path:
    """资源包 overlay 优先（@install/tmp/resource），回退内置 data/。"""
    return resource_pkg_path(f"arknights_mower/data/{name}")


def stage_data_path() -> Path:
    """打包内置的全量关卡基线（常驻 + 当时活动），启动读一次，之后不变。"""
    return _data_path("stage_data_full.json")


def stage_data_overlay_path() -> Path:
    """热更的活动关卡层（只含 ACTIVITY），运行时读，热更落地即生效。"""
    return get_path("@install/tmp/hot_update/stage_data.json")


# 全量基线：启动读一次进内存，之后不变（常驻关卡只在基线，不随热更改）。
_stage_data_base = json.loads(stage_data_path().read_text("utf-8"))


def _stage_key(item: dict) -> str | None:
    """关卡唯一键：优先 id，缺省用 name，与调用方按 id/name 查询一致。"""
    key = item.get("id")
    if not key:
        key = item.get("name")
    return key


class StageData:
    """关卡信息合并视图：内置全量基线（启动固定）+ 热更活动层（运行时读）。

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

recruit_tag = ["资深干员", "高级资深干员"]
for x in recruit_agent.values():
    recruit_tag += x["tags"]
recruit_tag = list(set(recruit_tag))

"""
按tag分类组合干员
"""

agent_with_tags = {}
for item in recruit_tag:
    agent_with_tags[item] = []
    for agent in recruit_agent:
        if {item} < set(recruit_agent[agent]["tags"]):
            agent_with_tags[item].append(
                {
                    "id": agent,
                    "name": recruit_agent[agent]["name"],
                    "star": recruit_agent[agent]["stars"],
                }
            )

result_template_list = []

for item in recruit_result:
    for name in recruit_result[item]:
        result_template_list.append(name)
