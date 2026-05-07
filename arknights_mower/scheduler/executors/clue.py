from arknights_mower.scheduler.executors.base import AbstractExecutor


class ClueExecutor(AbstractExecutor):
    def execute(self, task) -> None:
        raise NotImplementedError("Step 4a: 线索执行器 (待从 base_schedule.py:clue_new() 迁入)")
