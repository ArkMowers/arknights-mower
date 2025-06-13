import functools

from arknights_mower.utils.log import logger
from arknights_mower.utils.traceback import caller_info


def deprecated(msg=None):
    def decorator(func):
        @functools.wraps(func)
        def new_func(*args, **kwargs):
            # 使用默认消息或自定义消息
            warning_msg = msg or f"已弃用的函数 {func.__name__} 被 {caller_info()} 调用"
            logger.warning(warning_msg)
            return func(*args, **kwargs)

        return new_func

    return decorator
