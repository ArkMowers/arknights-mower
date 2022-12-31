import datetime


def the_same_day(a: datetime.datetime = None, b: datetime.datetime = None) -> bool:
    if a is None or b is None:
        return False
    return a.year == b.year and a.month == b.month and a.day == b.day

def the_same_time(a: datetime.datetime = None, b: datetime.datetime = None) -> bool:
    if a is None or b is None:
        return False
    return a.year == b.year and a.month == b.month and a.day == b.day and a.hour ==b.hour and a.minute==b.minute and a.second == b.second
