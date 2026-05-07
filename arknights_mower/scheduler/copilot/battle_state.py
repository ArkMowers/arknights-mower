from dataclasses import dataclass, field


@dataclass
class OperatorState:
    name: str = ""
    deployed: bool = False
    row: int = 0
    col: int = 0
    skill_ready: bool = False


@dataclass
class BattleState:
    dp: int = 0
    max_dp: int = 99
    deployable_count: int = 0
    deploy_limit: int = 7
    operators: dict[str, OperatorState] = field(default_factory=dict)
    enemies_killed: int = 0
    is_paused: bool = False
