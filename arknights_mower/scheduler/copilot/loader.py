import json
from pathlib import Path

from arknights_mower.scheduler.copilot.combat_plan import (
    Action,
    ActionType,
    CombatDoc,
    Direction,
    OperatorGroup,
    StageInfo,
)


def load_stage(path: str) -> StageInfo:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return _parse_stage(raw)


def _parse_stage(raw: dict) -> StageInfo:
    actions = []
    for a in raw.get("actions", []):
        actions.append(
            Action(
                type=ActionType(a.get("type", "Deploy")),
                name=a.get("name"),
                location=a.get("location"),
                direction=Direction(a.get("direction", "None")),
                skill=a.get("skill"),
                skill_usage=a.get("skill_usage"),
                kills=a.get("kills"),
                costs=a.get("costs"),
                cooling=a.get("cooling"),
                doc=a.get("doc"),
                doc_color=a.get("doc_color"),
                pre_delay=a.get("pre_delay"),
                rear_delay=a.get("rear_delay"),
            )
        )

    groups = []
    for g in raw.get("groups", []):
        groups.append(
            OperatorGroup(
                name=g["name"],
                operators=g.get("opers", []),
            )
        )

    doc = raw.get("doc", {})
    return StageInfo(
        stage_name=raw.get("stage_name", ""),
        minimum_required=raw.get("minimum_required", ""),
        opers=raw.get("opers", []),
        groups=groups,
        actions=actions,
        doc=CombatDoc(
            title=doc.get("title", ""),
            details=doc.get("details", ""),
            title_color=doc.get("title_color"),
            details_color=doc.get("details_color"),
        ),
    )
