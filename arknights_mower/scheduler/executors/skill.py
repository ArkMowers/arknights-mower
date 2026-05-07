from arknights_mower.scheduler.executors.base import AbstractExecutor


class SkillExecutor(AbstractExecutor):
    def execute(self, task) -> None:
        raise NotImplementedError("Step 4e: 技能专精执行器 (待从 base_schedule.py 迁入)")
