from arknights_mower.scheduler.executors.base import AbstractExecutor


class ShiftExecutor(AbstractExecutor):
    def execute(self, task) -> None:
        raise NotImplementedError("Step 4h: 换班执行器 (待从 base_schedule.py 迁入)")
