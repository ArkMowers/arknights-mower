from enum import Enum

SCREEN_W = 1920
SCREEN_H = 1080


class Server(Enum):
    CN = "CN"
    US = "US"
    JP = "JP"
    KR = "KR"


class Locale(Enum):
    ZH_CN = "zh_CN"
    EN_US = "en_US"
    JA_JP = "ja_JP"
    KO_KR = "ko_KR"


SERVER_TO_LOCALE = {
    Server.CN: Locale.ZH_CN,
    Server.US: Locale.EN_US,
    Server.JP: Locale.JA_JP,
    Server.KR: Locale.KO_KR,
}


DORM_ROOM_PREFIX = "dorm"


AGENT_SELECT_POSITIONS = [
    (0.35, 0.35),
    (0.35, 0.75),
    (0.45, 0.35),
    (0.45, 0.75),
    (0.55, 0.35),
]


DORM_SORT = ("心情", True)
DEFAULT_SORT = ("技能", False)
SPECIAL_AGENT_ALL_FILTER = "阿米娅"
DEFAULT_FILTER = "ALL"

PROFESSION_LABELS = [
    "ALL", "PIONEER", "WARRIOR", "TANK",
    "SNIPER", "CASTER", "MEDIC", "SUPPORT", "SPECIAL",
]
PROFESSION_LABEL_POS = [(1918, 135 + i * 110) for i in range(9)]

DORM_ARRANGE_NAMES = ["工作状态", "技能", "心情", "信赖值"]
DORM_ARRANGE_X = [1070, 1220, 1358, 1490]
PROD_ARRANGE_NAMES = ["工作状态", "效率", "技能", "心情", "信赖值"]
PROD_ARRANGE_X = [935, 1072, 1215, 1360, 1495]
ARRANGE_Y = 60

FILTER_CLOSE_THRESHOLD = 1650
MAX_PAGE = 50
MAX_RETRY = 10

INFRA_ROOM_SLOT_TAP = (0.82, 0.2)
INFRA_CLEAR_ALL = (0.38, 0.95)

CONFIRM_BLUE = "confirm_blue"
CONFIRM_TRAIN = "confirm_train"
ARRANGE_CONFIRM = "arrange_confirm"

CURRENT = "Current"


class StartMode(Enum):
    FULL = "0"
    MOOD_ONLY = "1"
    CLEAN = "2"


class FacilityType(Enum):
    TRAIN = "train"
    FACTORY = "factory"
    CENTRAL = "central"
    MEETING = "meeting"
    CONTACT = "contact"
    TRADING = "trading"
    POWER = "power"
    DORMITORY = "dormitory"

    @staticmethod
    def from_room_name(name: str) -> "FacilityType":
        for ft in FacilityType:
            if name.startswith(ft.value):
                return ft
        return FacilityType.TRADING


class TapPosition(Enum):
    BACK = (90 / SCREEN_W, 57 / SCREEN_H)
    CONFIRM_YES = (1371 / SCREEN_W, 998 / SCREEN_H)
    CONFIRM_NO = (549 / SCREEN_W, 998 / SCREEN_H)
    CENTER = (960 / SCREEN_W, 540 / SCREEN_H)
    MATERIEL = (960 / SCREEN_W, 960 / SCREEN_H)
    FRIEND_LIST = (194 / SCREEN_W, 333 / SCREEN_H)
    BUSINESS_CARD = (188 / SCREEN_W, 198 / SCREEN_H)
    OPERATION_FINISH = (310 / SCREEN_W, 330 / SCREEN_H)
    TODO_COMPLETE = (1840 / SCREEN_W, 140 / SCREEN_H)
    INDEX_INFRASTRUCTURE = (1410 / SCREEN_W, 870 / SCREEN_H)
    INFRA_ARRANGE_CONFIRM = (1452 / SCREEN_W, 1029 / SCREEN_H)
    RIIC_BACK = (30 / SCREEN_W, 55 / SCREEN_H)
    LOGIN_START = (665 / SCREEN_W, 741 / SCREEN_H)
    AGREEMENT_LINE1 = (791 / SCREEN_W, 728 / SCREEN_H)
    AGREEMENT_LINE2 = (959 / SCREEN_W, 828 / SCREEN_H)
    LOGIN_BILIBILI = (1000 / SCREEN_W, 600 / SCREEN_H)


WORKSHOP_AGENT_JIUSE = "九色鹿"
WORKSHOP_FURNITURE_PREFIX = "家具零件"
WORKSHOP_TABS = ["基建材料", "精英材料", "技巧概要", "芯片"]
WORKSHOP_TAB_POS = {
    "基建材料": (0.1, 0.18),
    "精英材料": (0.1, 0.31),
    "技巧概要": (0.1, 0.45),
    "芯片": (0.1, 0.57),
}
WORKSHOP_MOOD_MIN = 22
WORKSHOP_MOOD_CRIT = 4
WORKSHOP_JIUSE_SKILL_TARGET = 40
WORKSHOP_JIUSE_CRIT_GAP = 5
WORKSHOP_JIUSE_MAX_AP = 4
WORKSHOP_JIUSE_MAX_PRODUCTION_COST = 24
WORKSHOP_UNKNOWN_RETRY_LIMIT = 5
WORKSHOP_ARRANGE_CHECK_IN_POS = (0.25, 0.95)
WORKSHOP_FORMULA_BUTTON_POS = (0.45, 0.65)
WORKSHOP_ADD_BUTTON_POS = (0.84, 0.4)
WORKSHOP_MAX_BUTTON_POS = (0.95, 0.4)
WORKSHOP_PRODUCE_BUTTON_POS = (0.88, 0.88)
WORKSHOP_ROOM_ENTRY_POS = (0.1, 0.95)
WORKSHOP_FORMULA_SCAN_REGION = (370, 125, 1860, 1040)
WORKSHOP_FORMULA_SAMPLE_OFFSET = (15, 75)
WORKSHOP_FORMULA_SAMPLE_X_STEP = 155
WORKSHOP_FORMULA_SAMPLE_COUNT = 3
WORKSHOP_FORMULA_VALID_COLOR_LOW = 40
WORKSHOP_FORMULA_VALID_COLOR_HIGH = 80
WORKSHOP_FORMULA_SWIPE_START = (0.5, 0.9)
WORKSHOP_FORMULA_SWIPE_END = (0.5, 0.25)
WORKSHOP_FORMULA_SWIPE_DURATION = 200
WORKSHOP_ITEM_VALID_REGION = (0.77, 0.83, 0.96, 0.92)
WORKSHOP_ITEM_VALID_TARGET_COLOR = (189.2, 163.8, 23.7)
WORKSHOP_ITEM_VALID_DISTANCE = 30
WORKSHOP_JIUSE_SKILL_REGION = (95, 290, 200, 335)
WORKSHOP_FURNITURE_FORMULA_KEYS = [
    "家具零件_碳素",
    "家具零件_碳素组",
    "家具零件_基础加固建材",
    "家具零件_进阶加固建材",
    "家具零件_高级加固建材",
    "家具零件_碳",
]


def _t(key: str, locale: Locale = Locale.ZH_CN) -> str:
    return _TASK_DISPLAY_NAMES.get(key, {}).get(locale, key)


_TASK_DISPLAY_NAMES: dict[str, dict[Locale, str]] = {
    "跑单": {Locale.ZH_CN: "跑单"},
    "肥鸭": {Locale.ZH_CN: "肥鸭"},
    "下班": {Locale.ZH_CN: "下班"},
    "上班": {Locale.ZH_CN: "上班"},
    "用尽下班": {Locale.ZH_CN: "用尽下班"},
    "纠错": {Locale.ZH_CN: "纠错"},
    "趴体": {Locale.ZH_CN: "趴体"},
    "MAA信用购物": {Locale.ZH_CN: "MAA信用购物"},
    "空任务": {Locale.ZH_CN: "空任务"},
    "公招": {Locale.ZH_CN: "公招"},
    "森空岛签到": {Locale.ZH_CN: "森空岛签到"},
    "宿舍排序": {Locale.ZH_CN: "宿舍排序"},
    "释放宿舍空位": {Locale.ZH_CN: "释放宿舍空位"},
    "强制刷新任务时间": {Locale.ZH_CN: "强制刷新任务时间"},
    "技能专精": {Locale.ZH_CN: "技能专精"},
    "仓库扫描": {Locale.ZH_CN: "仓库扫描"},
    "加工材料": {Locale.ZH_CN: "加工材料"},
}
