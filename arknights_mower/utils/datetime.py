from datetime import datetime
import pytz


def the_same_day(a: datetime = None, b: datetime = None) -> bool:
    if a is None or b is None:
        return False
    return a.year == b.year and a.month == b.month and a.day == b.day


def the_same_time(a: datetime = None, b: datetime = None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b).total_seconds() < 1.5


def get_server_weekday():
    return datetime.now(pytz.timezone('Asia/Dubai')).weekday()
