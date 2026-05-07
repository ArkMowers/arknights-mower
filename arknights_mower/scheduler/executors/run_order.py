from arknights_mower.scheduler.executors.base import AbstractExecutor


class RunOrderExecutor(AbstractExecutor):
    def execute(self, task) -> None:
        raise NotImplementedError("Step 4f: 跑单执行器 (待从 base_schedule.py 迁入)")
