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
    return datetime.now(pytz.timezone("Asia/Dubai")).weekday()


# newbing说用这个来定义休息时间省事
def format_time(seconds):
    if seconds < 0:  # 权宜之计 配合刷生息演算
        return f"{0} 分钟"  # 权宜之计 配合刷生息演算
    # 计算小时和分钟
    rest_hours = int(seconds / 3600)
    rest_minutes = int((seconds % 3600) / 60)
    # 根据小时是否为零来决定是否显示
    if rest_hours == 0:
        return f"{rest_minutes} 分钟"
    elif rest_minutes == 0:
        return f"{rest_hours} 小时"
    else:
        return f"{rest_hours} 小时 {rest_minutes} 分钟"
