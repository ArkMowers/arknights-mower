from arknights_mower.scheduler.executors.base import AbstractExecutor


class CorrectionExecutor(AbstractExecutor):
    def execute(self, task) -> None:
        raise NotImplementedError("Step 4b: 纠错执行器 (待从 base_schedule.py 迁入)")
