"""家具任务的运行预算与异常分类，供调度和执行共用。"""

FURNITURE_RUN_SECONDS = 30 * 60
FURNITURE_EXIT_SECONDS = 60


class FurnitureNavigationError(RuntimeError):
    """尚未提交加工时的可恢复场景导航错误。"""


class FurnitureSafetyError(RuntimeError):
    """保护检查失败或提交结果不明，必须终止当前任务。"""
