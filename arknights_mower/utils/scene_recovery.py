from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from arknights_mower.utils.csleep import check_cancelled
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene


class SceneRecoveryExhausted(RuntimeError):
    pass


@dataclass
class SceneRestartBudget:
    used: bool = False


_restart_budget = ContextVar("scene_restart_budget", default=None)


@contextmanager
def scene_restart_scope(budget=None):
    if _restart_budget.get() is not None:
        yield
        return
    token = _restart_budget.set(budget if budget is not None else SceneRestartBudget())
    try:
        yield
    finally:
        _restart_budget.reset(token)


def claim_scene_restart():
    budget = _restart_budget.get()
    if budget is not None:
        check_cancelled()
        if budget.used:
            raise SceneRecoveryExhausted("本次场景恢复已尝试重进游戏")
        budget.used = True


def recover_base_scene(solver):
    try:
        with scene_restart_scope():
            if solver.scene() != Scene.UNKNOWN:
                return
            for retry in range(5):
                logger.warning(f"当前场景无法识别，尝试返回纠正，第{retry + 1}次")
                solver.back()
                if solver.scene() != Scene.UNKNOWN:
                    return
            claim_scene_restart()
            logger.warning(
                "连续返回 5 次后仍无法识别场景，退出游戏重进",
                extra={"archive_screenshots": True},
            )
            solver.device.exit()
            solver.check_current_focus()
    except SceneRecoveryExhausted:
        logger.warning("基建场景恢复已尝试重进游戏，结束本次纠错")
