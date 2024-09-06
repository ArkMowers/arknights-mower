import time
from datetime import datetime, timedelta

from arknights_mower.utils import config


class MowerExit(Exception):
    pass


def csleep(interval: float = 1):
    """check and sleep"""
    stop_time = datetime.now() + timedelta(seconds=interval)
    while True:
        if config.stop_mower.is_set():
            raise MowerExit
        remaining = stop_time - datetime.now()
        if remaining > timedelta(seconds=1):
            time.sleep(1)
        elif remaining > timedelta():
            time.sleep(remaining.total_seconds())
        else:
            return
