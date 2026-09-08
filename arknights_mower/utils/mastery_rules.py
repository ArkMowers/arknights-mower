"""Compile game building data into small, versioned training rules (no application imports).

Source: ArknightsAssets/ArknightsGamedata cn/gamedata/excel/building_data.json.
Descriptions are interpreted only at resource-generation time, never in the scheduler.
"""

import re

BRANCHES = {
    "行医": "wandermedic",
    "链愈师": "chainhealer",
    "领主": "lord",
    "斗士": "fighter",
    "速射手": "fastshot",
    "攻城手": "siegesniper",
    "驭法铁卫": "artsprotector",
    "游击手": "supportiveranger",
}
GROUPS = {
    "深海猎人": "abyssal",
    "萨米": "sami",
    "骑士": "knights",
    "进攻方": "attack",
    "防守方": "defence",
    "叙拉古": "siracusa",
}


def compile_buff(buff):
    text = re.sub(r"<[^>]*>", "", buff["description"])
    effects = []
    if buff["roomType"] == "CONTROL":
        if "专精技能训练速度+5%" in text:
            effects.append({"kind": "control"})
        return effects
    if buff["roomType"] != "TRAINING":
        return effects
    # Cost-only skills do not affect the duration calculation.
    if buff["buffId"].startswith("train_cost"):
        return effects
    targets = buff.get("targets", [])
    # All current stage-specific speed descriptions use 专精技能至N级.
    stage = re.search(r"专精技能至([123])级", text)
    branch = re.search(r"分支为([^，]+)", text)
    extra = re.search(r"训练速度额外\+(\d+)%", text)
    if "每名" in text and "最多生效" in text:
        match = re.search(
            r"每名(.+?)干员为当前干员的专精技能训练速度\+(\d+)%（最多生效(\d+)名）",
            text,
        )
        if not match or match[1] not in GROUPS:
            raise ValueError(f"未识别的训练环境技能: {buff['buffId']}")
        effects.append(
            {
                "kind": "environment",
                "group": GROUPS[match[1]],
                "bonus": int(match[2]),
                "cap": int(match[3]),
            }
        )
    elif "人间烟火" in text:
        effects.append(
            {"kind": "environment", "group": "fireworks", "bonus": 1, "cap": 10000}
        )
    elif "训练速度" in text:
        bonus = buff.get("efficiency", 0)
        effect = {"kind": "speed", "bonus": bonus, "professions": targets}
        if extra:
            effect["extra"] = int(extra[1])
        if stage:
            effect["stage"] = int(stage[1])
            if not extra:  # e.g. 望: the entire bonus is conditional on M3.
                amount = re.search(r"训练速度\+(\d+)%", text)
                effect["bonus"] = 0
                effect["extra"] = int(amount[1])
        if branch:
            if branch[1] not in BRANCHES:
                raise ValueError(f"未识别的干员分支: {branch[1]}")
            effect["branch"] = BRANCHES[branch[1]]
        effects.append(effect)
    if "下次训练所需时间-50%" in text and "5小时" in text:
        effects.append({"kind": "halve"})
    if "武道" in text:
        effects.append({"kind": "unsupported", "reason": "武道瞬间完成"})
    if not effects:
        raise ValueError(f"未识别的训练技能: {buff['buffId']} {text}")
    return effects


def compile_training_data(characters, building):
    rules = {
        key: compile_buff(buff)
        for key, buff in building["buffs"].items()
        if buff.get("roomType") in ("TRAINING", "CONTROL")
    }
    operators = {}
    for cid, char in characters.items():
        if not cid.startswith("char_") or char.get("isNotObtainable"):
            continue
        groups = []
        for group in building.get("chars", {}).get(cid, {}).get("buffChar", []):
            versions = []
            for ref in group["buffData"]:
                effects = rules.get(ref["buffId"], [])
                # Retain empty upgrades too: an upgrade can replace a training skill.
                cond = ref["cond"]
                versions.append(
                    {
                        "elite": int(str(cond["phase"]).removeprefix("PHASE_")),
                        "level": cond["level"],
                        "effects": effects,
                    }
                )
            if any(v["effects"] for v in versions):
                groups.append(versions)
        operators[cid] = {
            key: char.get(key)
            for key in (
                "name",
                "profession",
                "subProfessionId",
                "groupId",
                "nationId",
                "teamId",
            )
        }
        operators[cid]["groups"] = groups
    return {"version": 1, "operators": operators}
