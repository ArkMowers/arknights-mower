from inspect import getframeinfo, stack
from pathlib import Path

from arknights_mower.utils.path import get_path


def caller_info():
    caller = getframeinfo(stack()[2][0])
    relative_name = Path(caller.filename)
    try:
        relative_name = relative_name.relative_to(get_path("@install"))
    except ValueError:
        pass
    return f"{relative_name}:{caller.lineno}"
