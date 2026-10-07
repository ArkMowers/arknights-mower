"""Batch budgets and inventory accounting shared by all workshop operators."""

import json
from functools import lru_cache
from pathlib import Path

from arknights_mower.utils.dorm_candidates import dorm_task_reservations
from arknights_mower.utils.workshop_material_policy import workshop_recipe_allowed


@lru_cache(maxsize=1)
def _bundled_recipes():
    return json.loads(
        (Path(__file__).parents[1] / "data/workshop_formula.json").read_text("utf-8")
    )


def recipe_quantities(name, metadata):
    """Old resource packs may omit quantities; use a matching bundled recipe."""
    recipe = metadata
    if "costs" not in recipe or "output_count" not in recipe:
        recipe = _bundled_recipes().get(name, {})
        if any(recipe.get(key) != metadata.get(key) for key in ("items", "apCost")):
            return None
    costs = recipe.get("costs", {})
    count = recipe.get("output_count")
    if (
        not costs
        or set(costs) != set(metadata["items"])
        or not isinstance(count, int)
        or count <= 0
        or any(not isinstance(n, int) or n <= 0 for n in costs.values())
    ):
        return None
    return recipe["output_name"], count, costs


def batch_limit(name, metadata, setting, inventory):
    if not workshop_recipe_allowed(metadata):
        return 0
    quantities = recipe_quantities(name, metadata)
    if quantities is None:
        return 0
    output, count, costs = quantities
    if any(name not in inventory for name in (output, *costs)):
        return 0  # Unknown stock must be read from the depot before spending it.
    gold_cost = int(metadata.get("goldCost") or 0)
    gold_limit = (
        inventory["龙门币"] // gold_cost
        if gold_cost > 0 and "龙门币" in inventory
        else 99
    )
    return max(
        0,
        min(
            99,
            gold_limit,
            (setting.self_upper_limit - inventory[output]) // count,
            *(
                (inventory[child] - setting.children_lower_limit) // required
                for child, required in costs.items()
            ),
        ),
    )


def workshop_material_block_reason(operator, items, inventory, mood=None):
    """入队和调人前共用材料检查；可加工返回 None，否则指出阻塞原因。"""
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.workshop_mood import mood_cost, operator_mood_rules
    from arknights_mower.utils.workshop_recipes import scope_workshop_items

    if not items:
        return "未配置加工配方"
    scoped = scope_workshop_items(operator, items, workshop_formula)
    if not scoped:
        return "没有符合干员材料范围及材料保护规则的配方"
    check_mood = mood is not None and mood >= 0
    rules, known = operator_mood_rules(operator) if check_mood else ([], False)
    available, blocked = [], []
    for item in scoped:
        for name in item.item_names:
            metadata = workshop_formula[name]
            if batch_limit(name, metadata, item, inventory) > 0:
                required_mood = mood_cost(name, metadata, rules, known)
                if check_mood and mood < required_mood:
                    blocked.append(
                        f"{name}心情不足（当前 {mood:.1f}，单次需 {required_mood:g}）"
                    )
                    continue
                available.append(metadata)
                continue
            quantities = recipe_quantities(name, metadata)
            if not workshop_recipe_allowed(metadata):
                blocked.append(f"{name}使用受保护材料")
            elif quantities is None:
                blocked.append(f"{name}缺少有效配方数量")
            else:
                output, count, costs = quantities
                missing = [mat for mat in (output, *costs) if mat not in inventory]
                if missing:
                    blocked.append(f"{name}缺少仓库读数：{'、'.join(missing)}")
                elif inventory[output] + count > item.self_upper_limit:
                    blocked.append(
                        f"{output}成品达到合成上限或剩余额度不足一批"
                        f"（库存 {inventory[output]}，上限 {item.self_upper_limit}）"
                    )
                else:
                    shortages = [
                        f"{mat}库存 {inventory[mat]}，需 {required}，保留 {item.children_lower_limit}"
                        for mat, required in costs.items()
                        if inventory[mat] - item.children_lower_limit < required
                    ]
                    gold_cost = int(metadata.get("goldCost") or 0)
                    if gold_cost and inventory.get("龙门币", gold_cost) < gold_cost:
                        shortages.append(
                            f"龙门币库存 {inventory['龙门币']}，加工费需 {gold_cost}"
                        )
                    blocked.append(f"{name}原料不足（{'；'.join(shortages)}）")
    if not available:
        reasons = list(dict.fromkeys(blocked))
        return "；".join(reasons[:3]) or "未配置加工配方"
    if operator == "九色鹿":
        if not any(
            entry["apCost"] < 4 or entry["tab"] == "基建材料" for entry in available
        ):
            return "缺少可加工的垫刀材料（小于 4 心情或基建材料）"
        if not any(
            entry["apCost"] == 4 and entry["tab"] != "基建材料" for entry in available
        ):
            return "缺少可加工的 4 心情精英材料"
    return None


def workshop_operator_block_reason(
    op_data, operator, tasks=(), *, current_task=None, minimum_mood=0
):
    """返回加工受阻原因；自动入队和调人前共享心情及预约规则。"""
    if operator in getattr(op_data, "emergency_reserved_agents", ()):
        return "已被自动救急恢复安排预约"
    for task in tasks:
        if (
            task is not current_task
            and getattr(task.type, "name", "") != "WORKSHOP"
            and (
                any(operator in names for names in task.plan.values())
                or operator in dorm_task_reservations(op_data, [task])[0]
            )
        ):
            if operator in getattr(task, "emergency_staffing_members", ()):
                return "已被自动救急换班任务预约"
            return f"已被{task.type.display_value}任务预约"
    op = op_data.operators.get(operator)
    if op is None:
        return None
    mood = op.current_mood() if hasattr(op, "current_mood") else op.mood
    # 未知心情的手动加工沿用入站读取；自动入队仍需已知心情超过门槛。
    if mood < 0 and minimum_mood == 0:
        return None
    if mood < 0:
        return "心情尚未读取，无法确认自动加工门槛"
    if mood <= minimum_mood:
        return f"心情不足（当前 {mood:.1f}，需大于 {minimum_mood}）"
    return None


def deer_batch_limit(gap, ap_cost):
    """Stop fodder before the guaranteed byproduct, then craft one T4 item."""
    if gap <= 0 or ap_cost <= 0:
        raise ValueError("九色鹿因果或配方心情消耗无效")
    return max(1, (gap - 1) // ap_cost)


def batch_delta(name, metadata, batches):
    """Account only for guaranteed main outputs; ignore all random byproducts."""
    output, count, costs = recipe_quantities(name, metadata)
    if not isinstance(batches, int) or batches <= 0:
        raise ValueError("加工次数无效")
    delta = {child: -amount * batches for child, amount in costs.items()}
    delta[output] = delta.get(output, 0) + count * batches
    if gold_cost := int(metadata.get("goldCost") or 0):
        delta["龙门币"] = delta.get("龙门币", 0) - gold_cost * batches
    return delta
