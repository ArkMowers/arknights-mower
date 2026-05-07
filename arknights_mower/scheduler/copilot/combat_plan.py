from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionType(Enum):
    DEPLOY = "Deploy"
    RETREAT = "Retreat"
    SKILL = "Skill"
    SKILL_USAGE = "SkillUsage"
    SPEED_UP = "SpeedUp"
    BULGE = "Bulge"
    SKILL_DAEMON = "SkillDaemon"
    MOVE_CAMERA = "MoveCamera"
    PRINT = "Print"


class Direction(Enum):
    UP = "Up"
    DOWN = "Down"
    LEFT = "Left"
    RIGHT = "Right"
    NONE = "None"


@dataclass
class Action:
    type: ActionType
    name: Optional[str] = None
    location: Optional[list[int]] = None
    direction: Direction = Direction.NONE
    skill: Optional[int] = None
    skill_usage: Optional[int] = None
    kills: Optional[int] = None
    costs: Optional[int] = None
    cooling: Optional[int] = None
    doc: Optional[str] = None
    doc_color: Optional[str] = None
    pre_delay: Optional[int] = None
    rear_delay: Optional[int] = None


@dataclass
class OperatorGroup:
    name: str
    operators: list[dict] = field(default_factory=list)


@dataclass
class CombatDoc:
    title: str = ""
    details: str = ""
    title_color: Optional[str] = None
    details_color: Optional[str] = None


@dataclass
class StageInfo:
    stage_name: str = ""
    minimum_required: str = ""
    opers: list[dict] = field(default_factory=list)
    groups: list[OperatorGroup] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    doc: CombatDoc = field(default_factory=CombatDoc)
