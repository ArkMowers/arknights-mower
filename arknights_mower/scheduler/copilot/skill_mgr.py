import logging

from arknights_mower.scheduler.copilot.battle_state import BattleState

logger = logging.getLogger(__name__)


class SkillManager:
    def __init__(self) -> None:
        self._auto_skill_ops: set[str] = set()

    def register(self, operator_name: str) -> None:
        self._auto_skill_ops.add(operator_name)

    def auto_release(self, state: BattleState) -> None:
        raise NotImplementedError(
            "Step 6: 技能自动释放 (待从 battle_state 读取 + 截图识别实现)"
        )
