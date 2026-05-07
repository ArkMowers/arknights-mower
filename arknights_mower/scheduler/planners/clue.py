from arknights_mower.scheduler.planners.base import AbstractPlanner


class CluePlanner(AbstractPlanner):
    def plan(self) -> None:
        raise NotImplementedError("Step 4p: 线索规划器 (待从 base_schedule.py 迁入)")
