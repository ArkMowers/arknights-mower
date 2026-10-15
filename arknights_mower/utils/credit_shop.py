"""信用商店规格与购买选择；理智估值由调用方提供当前用户的价值表。"""

from math import inf, isfinite

from arknights_mower.utils.log import logger

# 规格来自已确认的 25 种信用商品。这里只保存物品 ID、基础售价和整份数量，
# 不保存理智价值；售价与减价百分比必须共同匹配，避免混淆龙门币和家具零件规格。
CREDIT_SHOP_PACKS = {
    "龙门币": ("4001", {100: 1800, 200: 3600}),
    "家具零件": ("3401", {160: 20, 200: 25}),
    "招聘许可": ("7001", {160: 1}),
    "加急许可": ("7002", {160: 1}),
    "赤金": ("3003", {160: 6}),
    "基础作战记录": ("2001", {100: 9}),
    "初级作战记录": ("2002", {200: 9}),
    "技巧概要·卷1": ("3301", {160: 5}),
    "技巧概要·卷2": ("3302", {200: 3}),
    "碳": ("3112", {160: 5}),
    "碳素": ("3113", {200: 3}),
    "源岩": ("30011", {80: 2}),
    "代糖": ("30021", {100: 2}),
    "酯原料": ("30031", {100: 2}),
    "异铁碎片": ("30041", {120: 2}),
    "双酮": ("30051", {120: 2}),
    "破损装置": ("30061", {80: 1}),
    "固源岩": ("30012", {200: 3}),
    "糖": ("30022", {200: 2}),
    "聚酸酯": ("30032", {200: 2}),
    "异铁": ("30042", {240: 2}),
    "酮凝集": ("30052", {240: 2}),
    "装置": ("30062", {160: 1}),
}


def product_sanity_value(product, catalog):
    """匹配整份数量；未知规格或无有效估值时返回 None，不猜测数量或价值。"""
    spec = CREDIT_SHOP_PACKS.get(product.get("name"))
    price, discount = product.get("price"), product.get("discount")
    if (
        spec is None
        or type(price) is not int
        or price <= 0
        or type(discount) is not int
        or discount not in (0, 50, 75, 95, 99)
    ):
        return None
    item_id, packs = spec
    quantity = next(
        (
            quantity
            for base_price, quantity in packs.items()
            if price * 100 == base_price * (100 - discount)
        ),
        None,
    )
    value = catalog["items"].get(item_id, {}).get("value")
    if (
        quantity is None
        or type(value) not in (int, float)
        or not isfinite(value)
        or value < 0
    ):
        return None
    total = quantity * value
    return total if isfinite(total) else None


def value_purchase_deficit(
    products, catalog, remain, threshold, priority_names, blacklist
):
    """优先商品与原始性价比达标商品的总缺口，不计入溢出抵扣。"""
    total = 0
    for product in products:
        if not product:
            continue
        if product["name"] in priority_names:
            total += product["price"]
        elif product["name"] not in blacklist:
            value = product_sanity_value(product, catalog)
            if value is not None and value / product["price"] > threshold:
                total += product["price"]
    return max(total - remain, 0)


def select_value_product(products, catalog, remain, threshold, blacklist):
    """原始性价比优先，之后用溢出抵扣有效成本；调用方仍须核验全价可付。"""
    ranked = []
    for product in products:
        if not product or product["name"] in blacklist:
            continue
        value = product_sanity_value(product, catalog)
        if value is None:
            logger.warning(
                "信用商品规格或理智价值无法确定，跳过：%s，售价 %s，减价 %s%%",
                product.get("name"),
                product.get("price"),
                product.get("discount"),
            )
        elif value > 0:
            ranked.append((product, value))
    ranked.sort(key=lambda row: row[1] / row[0]["price"], reverse=True)
    if not ranked:
        return None
    product, value = ranked[0]
    if value / product["price"] > threshold:
        # 最高性价比买不起时，由调用方结束，不能改买便宜的次优商品。
        return product
    overflow = remain - 300
    if overflow <= 0:
        return None
    best = None
    best_ratio = threshold
    for product, value in ranked:
        effective_cost = max(product["price"] - overflow, 0)
        ratio = value / effective_cost if effective_cost else inf
        if ratio > best_ratio:
            best, best_ratio = product, ratio
    return best
