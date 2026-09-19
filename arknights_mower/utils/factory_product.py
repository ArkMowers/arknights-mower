from dataclasses import dataclass


@dataclass(frozen=True)
class FactoryProduct:
    name: str
    category: tuple[int, int]
    recipe: tuple[int, int]
    unit_seconds: int


@dataclass(frozen=True)
class TradeProduct:
    strategy_name: str
    option: tuple[int, int]


FACTORY_PRODUCTS = {
    "gold": FactoryProduct("赤金", (180, 335), (500, 250), 72 * 60),
    "exp3": FactoryProduct("中级作战记录", (180, 195), (500, 525), 180 * 60),
    "orirock": FactoryProduct("源石碎片（固源岩）", (180, 620), (500, 250), 60 * 60),
    "orirock_device": FactoryProduct(
        "源石碎片（装置）", (180, 620), (1240, 250), 60 * 60
    ),
}

TRADE_PRODUCTS = {
    "lmd": TradeProduct("龙门商法", (780, 530)),
    "orundum": TradeProduct("开采协力", (1140, 530)),
}

DRONE_SECONDS = 3 * 60


def current_unit_remaining(total_remaining_seconds: int, unit_seconds: int) -> int:
    if total_remaining_seconds <= 0 or unit_seconds <= 0:
        return 0
    return total_remaining_seconds % unit_seconds or unit_seconds


def drone_plan(
    total_remaining_seconds: int,
    unit_seconds: int,
    max_loss_seconds: int = 30,
) -> tuple[int, int]:
    """返回完成当前一份产物所需的无人机数和剩余等待秒数。

    游戏加速面板显示的是去除生产力加成后的时间。每架无人机抵扣三分钟，
    默认允许最后一架无人机损耗至多 30 秒，即余数达到 2 分 30 秒时
    直接再使用一架；否则等待不足三分钟的余数自然完成。
    """
    current_remaining = current_unit_remaining(total_remaining_seconds, unit_seconds)
    drone_count, wait_seconds = divmod(current_remaining, DRONE_SECONDS)
    max_loss_seconds = min(DRONE_SECONDS, max(0, max_loss_seconds))
    if wait_seconds and DRONE_SECONDS - wait_seconds <= max_loss_seconds:
        return drone_count + 1, 0
    return drone_count, wait_seconds


def product_task_meta(room: str, product_id: str) -> str:
    return f"{room},{product_id}"


def parse_product_task_meta(meta_data: str) -> tuple[str, str]:
    room, product_id = meta_data.split(",", 1)
    if room == "" or product_id not in FACTORY_PRODUCTS | TRADE_PRODUCTS:
        raise ValueError(f"无效的基建产物切换任务：{meta_data}")
    return room, product_id
