"""Compile promotion, basic skill and module costs from game resource tables."""


def compile_growth_data(characters, equips, constants, patch_infos=None):
    result = {}
    for cid, char in characters.items():
        if not cid.startswith("char_") or char.get("isNotObtainable"):
            continue
        rarity = char["rarity"]
        rarity = (
            int(rarity.removeprefix("TIER_")) if isinstance(rarity, str) else rarity + 1
        )
        result[cid] = {
            "name": char["name"],
            "rarity": rarity,
            "profession": char["profession"],
            "subProfessionId": char["subProfessionId"],
            "integrated_strategy": char.get("spTargetType") == "ROGUE",
            "phases": [
                {
                    "max_level": phase["maxLevel"],
                    "materials": phase.get("evolveCost") or [],
                }
                for phase in char["phases"]
            ],
            "basic_skills": [
                level.get("lvlUpCost") or [] for level in char.get("allSkillLvlup", [])
            ],
            "modules": [],
        }
    for mid, module in equips.get("equipDict", {}).items():
        cid = module.get("tmplId") or module.get("charId")
        if cid not in result or not module.get("itemCost"):
            continue
        result[cid]["modules"].append(
            {
                "id": mid,
                "name": module["uniEquipName"],
                "type": "-".join(
                    filter(None, [module.get("typeName1"), module.get("typeName2")])
                ),
                "elite": int(str(module["unlockEvolvePhase"]).removeprefix("PHASE_")),
                "level": module["unlockLevel"],
                "materials": module["itemCost"].get("1") or [],
                "levels": [
                    {"level": int(level), "materials": materials or []}
                    for level, materials in sorted(module["itemCost"].items())
                ],
                "release_at": module.get("uniEquipGetTime", 0),
                "missions": bool(module.get("hasUnlockMission")),
            }
        )
    for owner, info in (patch_infos or {}).items():
        for cid in info.get("tmplIds", []):
            if cid in result:
                result[cid]["progression_owner"] = owner
    return {
        "characters": result,
        "experience": constants["characterExpMap"],
        "level_gold": constants["characterUpgradeCostMap"],
        "promotion_gold": constants["evolveGoldCost"],
    }
