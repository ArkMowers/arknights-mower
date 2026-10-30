"""Generate shared operator profiles and derive legacy resource views."""

import json
import re
from pathlib import Path

OPERATOR_CATALOG_DATA = "arknights_mower/data/riic/operators.json"
CATALOG_SCHEMA = 1


def operator_profile(character, char_id=""):
    rarity = character.get("rarity", 0)
    rarity = (
        int(rarity.removeprefix("TIER_")) if isinstance(rarity, str) else rarity + 1
    )
    return {
        "charId": char_id,
        "name": character.get("name", char_id),
        "appellation": character.get("appellation", ""),
        "rarity": rarity,
        "profession": character.get("profession", ""),
        "subProfessionId": character.get("subProfessionId", ""),
        "nationId": character.get("nationId"),
        "groupId": character.get("groupId"),
        "teamId": character.get("teamId"),
        "isAlter": bool(character.get("isSpChar", False)),
    }


def compile_operator_catalog(characters, building, source_version, *, order=()):
    operators = {}
    for source_order, (char_id, character) in enumerate(characters.items()):
        if (
            not char_id.startswith("char_")
            or character.get("isNotObtainable")
            or not character.get("itemObtainApproach", True)
        ):
            continue
        slots = []
        for group in building.get("chars", {}).get(char_id, {}).get("buffChar", []):
            versions = []
            for entry in group["buffData"]:
                buff = building["buffs"][entry["buffId"]]
                versions.append(
                    {
                        "buffId": entry["buffId"],
                        "name": buff["buffName"],
                        "roomType": buff["roomType"],
                        "skillIcon": buff["skillIcon"],
                        "description": re.sub(r"<[^>]*>", "", buff["description"]),
                        "unlockPhase": int(
                            str(entry["cond"]["phase"]).removeprefix("PHASE_")
                        ),
                        "unlockLevel": entry["cond"]["level"],
                    }
                )
            if versions:
                versions.sort(
                    key=lambda skill: (skill["unlockPhase"], skill["unlockLevel"])
                )
                slots.append(versions)
        operators[char_id] = {
            **operator_profile(character, char_id),
            "sourceOrder": source_order,
            "skillSlots": slots,
        }
    ordered = [operators.pop(char_id) for char_id in order if char_id in operators]
    ordered.extend(operators.values())
    return {
        "schemaVersion": CATALOG_SCHEMA,
        "sourceVersion": source_version,
        "operatorCount": len(ordered),
        "skillCount": sum(len(operator["skillSlots"]) for operator in ordered),
        "skillStageCount": sum(
            len(slot) for operator in ordered for slot in operator["skillSlots"]
        ),
        "operators": ordered,
    }


def operator_views(catalog):
    if (
        not isinstance(catalog, dict)
        or type(catalog.get("schemaVersion")) is not int
        or catalog["schemaVersion"] != CATALOG_SCHEMA
        or not isinstance(catalog.get("operators"), list)
        or type(catalog.get("operatorCount")) is not int
        or catalog.get("operatorCount") != len(catalog["operators"])
    ):
        raise ValueError("共享干员目录格式无效")
    records = catalog["operators"]
    ids, names = set(), set()
    for record in records:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("charId"), str)
            or not record["charId"]
            or record["charId"] in ids
            or not isinstance(record.get("name"), str)
            or not record["name"]
            or record["name"] in names
            or not isinstance(record.get("profession"), str)
            or type(record.get("sourceOrder")) is not int
            or record["sourceOrder"] < 0
        ):
            raise ValueError("共享干员资料无效或重复")
        ids.add(record["charId"])
        names.add(record["name"])
    records = sorted(records, key=lambda record: record["sourceOrder"])
    names = sorted((record["name"] for record in records), key=len)
    professions = {record["name"]: record["profession"] for record in records}
    return names, professions


def write_operator_catalog(catalog, root=Path(".")):
    names, professions = operator_views(catalog)
    outputs = {
        OPERATOR_CATALOG_DATA: json.dumps(
            catalog, ensure_ascii=False, separators=(",", ":")
        ),
        "arknights_mower/data/agent.json": json.dumps(names, ensure_ascii=False),
        "arknights_mower/data/agent_profession.json": json.dumps(
            professions, ensure_ascii=False
        ),
    }
    for relative, content in outputs.items():
        path = Path(root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
