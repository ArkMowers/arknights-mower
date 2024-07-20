from pydantic import BaseModel

from .enum import LingXiModeEnum


class OldPlanConfig(BaseModel):
    exhaust_require: list[str] = []
    """
    需要用尽心情的干员

    一个字符串列表。为了兼容老配置，也可以传入一个字符串自动序列化。
    """

    workaholic: list[str] = []
    """
    0心情工作的干员

    一个字符串列表。为了兼容老配置，也可以传入一个字符串自动序列化。
    """

    rest_in_full: list[str] = []
    """
    满心情休息的干员

    一个字符串列表。为了兼容老配置，也可以传入一个字符串自动序列化。
    """

    ling_xi: LingXiModeEnum = LingXiModeEnum.感知信息
    """
    令、夕 模式

    1 为感知信息，2 为人间烟火，3 为均衡模式。
    传入一个整数，将会自动转换为对应的枚举类型。
    """

    resting_priority: list[str] = []
    """
    宿舍低优先级干员

    一个字符串列表。为了兼容老配置，也可以传入一个字符串自动序列化。
    """
