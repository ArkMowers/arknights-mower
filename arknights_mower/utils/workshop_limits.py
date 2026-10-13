"""Batch budgets and inventory accounting shared by all workshop operators."""

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from time import time

from arknights_mower.utils.dorm_candidates import dorm_task_reservations
from arknights_mower.utils.workshop_material_policy import workshop_recipe_allowed

# Process-local observations; recipe names bound the cache to the resource catalog.
_rejected_recipes = {}


@dataclass(frozen=True)
class WorkshopBlock:
    code: str
    message: str
    operator: str | None = None
    material: str | None = None
    available: float | None = None
    required: float | None = None
    reserved: float | None = None

    def __str__(self):
        return self.message

    def as_dict(self):
        return asdict(self)


def _recipe_stock(name, inventory):
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import config

    recipe = workshop_formula[name]
    quantities = recipe_quantities(name, recipe)
    output, _, costs = quantities if quantities else (name, 1, recipe["items"])
    names = {output, *costs}
    if recipe.get("goldCost"):
        names.add("龙门币")
    return config.conf.workshop_generation, tuple(
        (item, inventory.get(item)) for item in sorted(names)
    )


def reject_workshop_recipe(name, inventory):
    """Remember a game rejection without inventing an ingredient count."""
    _rejected_recipes[name] = (_recipe_stock(name, inventory), time())


def clear_workshop_recipe_rejections(observed_at):
    """New relevant observations permit retries; rereading old snapshots does not."""
    for name, (signature, rejected_at) in tuple(_rejected_recipes.items()):
        if any(observed_at.get(item, 0) > rejected_at for item, _ in signature[1]):
            _rejected_recipes.pop(name, None)


def blocked_workshop_recipes(inventory, *, readonly=False):
    from arknights_mower.data import workshop_formula

    blocked = set()
    for name, (signature, _) in tuple(_rejected_recipes.items()):
        if name not in workshop_formula or signature != _recipe_stock(name, inventory):
            if not readonly:
                _rejected_recipes.pop(name, None)
        else:
            blocked.add(name)
    return blocked


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


def workshop_material_block_reason(
    operator, items, inventory, mood=None, *, readonly=False
):
    """入队和调人前共用材料检查；可加工返回 None，否则指出阻塞原因。"""
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.workshop_mood import mood_cost, operator_mood_rules
    from arknights_mower.utils.workshop_recipes import scope_workshop_items

    if not items:
        return WorkshopBlock("no_recipe", "未配置加工配方", operator)
    scoped = scope_workshop_items(operator, items, workshop_formula)
    if not scoped:
        protected = any(
            not workshop_recipe_allowed(workshop_formula.get(name, {}))
            for item in items
            for name in item.item_names
        )
        return WorkshopBlock(
            "protected_material" if protected else "no_operator",
            "没有符合干员材料范围及材料保护规则的配方",
            operator,
        )
    check_mood = mood is not None and mood >= 0
    rules, known = operator_mood_rules(operator) if check_mood else ([], False)
    rejected = blocked_workshop_recipes(inventory, readonly=readonly)
    available, blocked = [], []
    for item in scoped:
        for name in item.item_names:
            if name in rejected:
                blocked.append(
                    WorkshopBlock(
                        "recipe_rejected",
                        f"{name}游戏内不可加工，等待库存或配置更新",
                        operator,
                        name,
                    )
                )
                continue
            metadata = workshop_formula[name]
            if batch_limit(name, metadata, item, inventory) > 0:
                required_mood = mood_cost(name, metadata, rules, known)
                if check_mood and mood < required_mood:
                    blocked.append(
                        WorkshopBlock(
                            "mood_insufficient",
                            f"{name}心情不足（当前 {mood:.1f}，单次需 {required_mood:g}）",
                            operator,
                            name,
                            mood,
                            required_mood,
                        )
                    )
                    continue
                available.append(metadata)
                continue
            quantities = recipe_quantities(name, metadata)
            if not workshop_recipe_allowed(metadata):
                blocked.append(
                    WorkshopBlock(
                        "protected_material", f"{name}使用受保护材料", operator, name
                    )
                )
            elif quantities is None:
                blocked.append(
                    WorkshopBlock(
                        "data_unavailable", f"{name}缺少有效配方数量", operator, name
                    )
                )
            else:
                output, count, costs = quantities
                missing = [mat for mat in (output, *costs) if mat not in inventory]
                if missing:
                    blocked.append(
                        WorkshopBlock(
                            "inventory_unknown",
                            f"{name}缺少仓库读数：{'、'.join(missing)}",
                            operator,
                            missing[0],
                        )
                    )
                elif inventory[output] + count > item.self_upper_limit:
                    blocked.append(
                        WorkshopBlock(
                            "output_limit",
                            f"{output}成品达到合成上限或剩余额度不足一批"
                            f"（库存 {inventory[output]}，上限 {item.self_upper_limit}）",
                            operator,
                            output,
                            inventory[output],
                            item.self_upper_limit,
                        )
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
                    child = next(
                        (
                            mat
                            for mat, required in costs.items()
                            if inventory[mat] - item.children_lower_limit < required
                        ),
                        None,
                    )
                    blocked.append(
                        WorkshopBlock(
                            "material_shortage" if child else "lmd_shortage",
                            f"{name}原料不足（{'；'.join(shortages)}）",
                            operator,
                            child or "龙门币",
                            inventory.get(child or "龙门币"),
                            costs[child] if child else gold_cost,
                            item.children_lower_limit if child else 0,
                        )
                    )
    if not available:
        return next(
            iter(blocked), WorkshopBlock("no_recipe", "未配置加工配方", operator)
        )
    if operator == "九色鹿":
        if not any(
            entry["apCost"] < 4 or entry["tab"] == "基建材料" for entry in available
        ):
            return WorkshopBlock(
                "deer_fodder", "缺少可加工的垫刀材料（小于 4 心情或基建材料）", operator
            )
        if not any(
            entry["apCost"] == 4 and entry["tab"] != "基建材料" for entry in available
        ):
            return WorkshopBlock("deer_elite", "缺少可加工的 4 心情精英材料", operator)
    return None


def workshop_operator_block_reason(
    op_data,
    operator,
    tasks=(),
    *,
    current_task=None,
    minimum_mood=0,
    require_known_mood=False,
):
    """返回加工受阻原因；自动入队和调人前共享心情及预约规则。"""
    if operator in getattr(op_data, "emergency_reserved_agents", ()):
        return WorkshopBlock("operator_reserved", "已被自动救急恢复安排预约", operator)
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
                return WorkshopBlock(
                    "operator_reserved", "已被自动救急换班任务预约", operator
                )
            return WorkshopBlock(
                "operator_reserved", f"已被{task.type.display_value}任务预约", operator
            )
    op = op_data.operators.get(operator)
    if op is None and not require_known_mood:
        return None
    mood = (
        op.current_mood() if hasattr(op, "current_mood") else getattr(op, "mood", None)
    )
    # 未知心情的手动加工沿用入站读取；自动入队仍需已知心情超过门槛。
    if (mood is None or mood < 0) and minimum_mood == 0 and not require_known_mood:
        return None
    if mood is None or mood < 0:
        return WorkshopBlock(
            "mood_unknown", "心情尚未读取，无法确认自动加工门槛", operator
        )
    if mood <= minimum_mood:
        return WorkshopBlock(
            "mood_insufficient",
            f"心情不足（当前 {mood:.1f}，需大于 {minimum_mood}）",
            operator,
            available=mood,
            required=minimum_mood,
        )
    return None


def workshop_admission_block(
    op_data, setting, inventory, tasks=(), *, minimum_mood=22, readonly=False
):
    """Use the same first-task eligibility for dispatch and status."""
    from arknights_mower.utils import config

    automatic = config.conf.workshop_auto_active and setting.source == "mastery"
    operator = op_data.operators.get(setting.operator)
    mood = (
        operator.current_mood()
        if hasattr(operator, "current_mood")
        else getattr(operator, "mood", None)
    )
    return workshop_operator_block_reason(
        op_data,
        setting.operator,
        tasks,
        minimum_mood=0 if automatic else minimum_mood,
        require_known_mood=automatic,
    ) or workshop_material_block_reason(
        setting.operator,
        setting.items,
        inventory,
        mood,
        readonly=readonly,
    )


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
