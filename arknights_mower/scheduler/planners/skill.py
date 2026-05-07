from arknights_mower.scheduler.planners.base import AbstractPlanner


class SkillPlanner(AbstractPlanner):
    def plan(self) -> None:
        raise NotImplementedError("Step 4o: 专精规划器 (待从 base_schedule.py 迁入)")
