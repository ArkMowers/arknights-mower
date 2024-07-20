from enum import Enum, IntEnum


class PackageEnum(int, Enum):
    Official = 1
    Bilibili = 2


class TouchMethodEnum(str, Enum):
    Maatouch = "maatouch"
    Scrcpy = "scrcpy"


class ThemeEnum(str, Enum):
    Light = "light"
    Dark = "dark"


class SimulatorEnum(str, Enum):
    夜神 = "夜神"
    MuMu模拟器12 = "MuMu12"
    Waydroid = "Waydroid"
    雷电模拟器9 = "雷电9"
    ReDroid = "ReDroid"
    MuMu模拟器Pro = "MuMuPro"
    其他 = ""


class LingXiModeEnum(IntEnum):
    感知信息 = 1
    人间烟火 = 2
    均衡模式 = 3


class WeekdayStrEnum(str, Enum):
    Monday = "周一"
    Tuesday = "周二"
    Wednesday = "周三"
    Thursday = "周四"
    Friday = "周五"
    Saturday = "周六"
    Sunday = "周日"


class MaaRGEnum(str, Enum):
    集成战略 = "rogue"
    保全派驻 = "sss"
    生息演算 = "ra"
    隐秘战线 = "sf"


class RogueRoleEnum(str, Enum):
    先手必胜 = "先手必胜"
    稳扎稳打 = "稳扎稳打"
    取长补短 = "取长补短"
    随心所欲 = "随心所欲"


class RogueModeEnum(IntEnum):
    刷等级 = 0
    刷源石锭 = 1


class SATargetEnum(str, Enum):
    结局A = "结局A"
    结局B = "结局B"
    结局C = "结局C"
    结局D = "结局D"
    结局E = "结局E"


class DirectionEnum(str, Enum):
    Up = "Up"
    Down = "Down"
    Left = "Left"
    Right = "Right"


class EmailEncryptionEnum(str, Enum):
    SSL_TLS = "tls"
    STARTTLS = "starttls"


class PhantomSquadEnum(str, Enum):
    研究分队 = "研究分队"
    指挥分队 = "指挥分队"
    集群分队 = "集群分队"
    后勤分队 = "后勤分队"
    矛头分队 = "矛头分队"
    突击战术分队 = "突击战术分队"
    堡垒战术分队 = "堡垒战术分队"
    远程战术分队 = "远程战术分队"
    破坏战术分队 = "破坏战术分队"
    高规格分队 = "高规格分队"


class MizukiSquadEnum(str, Enum):
    心胜于物分队 = "心胜于物分队"
    物尽其用分队 = "物尽其用分队"
    以人为本分队 = "以人为本分队"
    研究分队 = "研究分队"
    指挥分队 = "指挥分队"
    集群分队 = "集群分队"
    后勤分队 = "后勤分队"
    矛头分队 = "矛头分队"
    突击战术分队 = "突击战术分队"
    堡垒战术分队 = "堡垒战术分队"
    远程战术分队 = "远程战术分队"
    破坏战术分队 = "破坏战术分队"
    高规格分队 = "高规格分队"


class SamiSquadEnum(str, Enum):
    永恒狩猎分队 = "永恒狩猎分队"
    生活至上分队 = "生活至上分队"
    科学主义分队 = "科学主义分队"
    特训分队 = "特训分队"
    指挥分队 = "指挥分队"
    集群分队 = "集群分队"
    后勤分队 = "后勤分队"
    矛头分队 = "矛头分队"
    突击战术分队 = "突击战术分队"
    堡垒战术分队 = "堡垒战术分队"
    远程战术分队 = "远程战术分队"
    破坏战术分队 = "破坏战术分队"
    高规格分队 = "高规格分队"


SquadEnum = PhantomSquadEnum | MizukiSquadEnum | SamiSquadEnum
