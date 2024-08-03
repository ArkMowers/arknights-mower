import functools

from arknights_mower.utils.log import logger
from arknights_mower.utils.traceback import caller_info


def deprecated(func):
    @functools.wraps(func)
    def new_func(*args, **kwargs):
        logger.warning(f"已弃用的函数{func.__name__}被{caller_info()}调用")
        return func(*args, **kwargs)

    return new_func
