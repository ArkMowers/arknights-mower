from arknights_mower.scheduler.planners.base import AbstractPlanner


class WorkshopPlanner(AbstractPlanner):
    def plan(self) -> None:
        raise NotImplementedError("Step 4m: 加工站规划器 (待从 base_schedule.py 迁入)")
