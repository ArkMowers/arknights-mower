from arknights_mower.scheduler.executors.base import AbstractExecutor


class WorkshopExecutor(AbstractExecutor):
    def execute(self, task) -> None:
        raise NotImplementedError("Step 4d: 加工站执行器 (待从 base_schedule.py 迁入)")
