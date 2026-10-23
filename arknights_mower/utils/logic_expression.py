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
        if all(
            value is None or isinstance(value, str) and not value.strip()
            for value in (self.left, self.operator, self.right)
        ):
            return "False"
        return f"({(self.left)} {self.operator} {(self.right)})"


class FunctionExpression:
    def __init__(self, function, args):
        self.function = function
        self.args = args

    def __str__(self):
        args = ", ".join(str(arg) for arg in self.args)
        if self.function in ("sum", "any", "all") or (
            self.function in ("max", "min") and len(self.args) == 1
        ):
            args = f"[{args}]"
        return f"{self.function}({args})"


def get_logic_exp(trigger: dict) -> LogicExpression | FunctionExpression:
    if "function" in trigger:
        function = trigger["function"]
        args = trigger.get("args")
        if function not in ("max", "min", "sum", "any", "all", "abs"):
            raise ValueError("不支持的副表函数")
        if not isinstance(args, list) or not args:
            raise ValueError("函数条件需要参数")
        if function == "abs" and len(args) != 1:
            raise ValueError("abs 条件只接受一项参数")
        return FunctionExpression(
            function,
            [get_logic_exp(arg) if isinstance(arg, dict) else arg for arg in args],
        )
    for k in ["left", "operator", "right"]:
        if k not in trigger:
            trigger[k] = ""
        if not isinstance(trigger[k], str):
            trigger[k] = get_logic_exp(trigger[k])
    return LogicExpression(trigger["left"], trigger["operator"], trigger["right"])
