from typing import Optional, Self


class LogicExpression:
    def __init__(
        self,
        left: Optional[str | Self] = None,
        operator: Optional[str] = None,
        right: Optional[str | Self] = None,
    ):
        self.operator = operator
        self.left = left
        self.right = right

    def __str__(self):
        return f"({(self.left)} {self.operator} {(self.right)})"


def get_logic_exp(trigger: dict) -> LogicExpression:
    for k in ["left", "operator", "right"]:
        if k not in trigger:
            trigger[k] = ""
        if not isinstance(trigger[k], str):
            trigger[k] = get_logic_exp(trigger[k])
    return LogicExpression(trigger["left"], trigger["operator"], trigger["right"])
