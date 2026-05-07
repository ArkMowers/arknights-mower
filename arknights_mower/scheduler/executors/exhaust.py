from arknights_mower.scheduler.executors.base import AbstractExecutor


class ExhaustExecutor(AbstractExecutor):
    def execute(self, task) -> None:
        raise NotImplementedError("Step 4g: 用尽下班执行器 (待从 base_schedule.py 迁入)")
