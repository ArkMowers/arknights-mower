from enum import Enum
from typing import Literal


class PackageEnum(int, Enum):
    Official = 1
    Bilibili = 2


class TouchMethodEnum(str, Enum):
    Maatouch = "maatouch"
    Scrcpy = "scrcpy"


class ThemeEnum(str, Enum):
    Light = "light"
    Dark = "dark"


WeekdayType = Literal["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
