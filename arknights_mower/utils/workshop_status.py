"""Read-only crafting diagnostics from project budgets and dispatch checks."""

from datetime import datetime
from sqlite3 import Error as DatabaseError

from arknights_mower.utils import config, workshop_automation
from arknights_mower.utils.workshop_config import workshop_lock
from arknights_mower.utils.workshop_limits import (
    WorkshopBlock,
    workshop_admission_block,
)


def workshop_status(scheduler=None, *, running=False):
    from arknights_mower.data import workshop_formula
    from arknights_mower.solvers.record import (
        get_inventory_counts,
        workshop_inventory_changed,
    )
    from arknights_mower.utils.scheduler_task import TaskTypes
    from arknights_mower.utils.workshop_material_policy import workshop_recipe_allowed
    from arknights_mower.utils.workshop_recommendation import (
        prioritize_workshop_settings,
    )

    with workshop_lock:
        conf = config.conf
        result = {
            "mode": "automatic" if conf.workshop_auto_active else "manual",
            "execution": "idle",
            "project_key": None,
            "project_name": None,
            "recipe": None,
            "generation": conf.workshop_generation,
            "pending_refresh": workshop_inventory_changed.is_set(),
            "observed_at": datetime.now().isoformat(),
            "blockers": [],
        }
        blocks = []
        try:
            inventory = get_inventory_counts()
            if conf.enable_mastery or conf.workshop_auto_active:
                plan = workshop_automation.calculate_workshop_plan(
                    conf, local_stock=inventory
                )
                result["recipe"] = plan.recipe
                if plan.focus:
                    result["project_key"] = plan.focus["key"]
                    result["project_name"] = plan.focus["char_name"]
                    if plan.focus["locked"] and plan.focus["reason"]:
                        blocks.append(
                            WorkshopBlock(
                                "protected_training_shortage", plan.focus["reason"]
                            )
                        )
                    for row in plan.focus.get("shortages", []):
                        name = row["name"]
                        code = (
                            "lmd_shortage"
                            if row["id"] == "4001"
                            else "material_shortage"
                        )
                        message = (
                            f"{name}不足（库存 {row['owned']}，需求 {row['required']}）"
                        )
                        if name in workshop_formula and not workshop_recipe_allowed(
                            workshop_formula[name]
                        ):
                            code, message = (
                                "protected_material",
                                f"{name}所需配方使用受保护材料",
                            )
                        elif name not in inventory:
                            code, message = (
                                "inventory_unknown",
                                f"{name}缺少本地仓库读数，请读取仓库",
                            )
                        blocks.append(
                            WorkshopBlock(
                                code,
                                message,
                                material=name,
                                available=inventory.get(name),
                                required=row["required"],
                            )
                        )
                    if plan.recipe and not any(
                        entry["items"] for entry in plan.settings
                    ):
                        blocks.append(
                            WorkshopBlock(
                                "no_operator", f"{plan.recipe}没有适用的已选加工干员"
                            )
                        )
                    elif not conf.workshop_auto_active and not blocks:
                        blocks.append(
                            WorkshopBlock("pending_refresh", "等待调度生成养成合成配置")
                        )
            settings = [
                entry
                for entry in prioritize_workshop_settings(conf.workshop_settings)
                if entry.enabled
            ]
            tasks = list(getattr(scheduler, "tasks", []))
            op_data = getattr(scheduler, "op_data", None)
            current = getattr(scheduler, "task", None)
            queued = [
                task
                for task in tasks
                if task.type == TaskTypes.WORKSHOP
                and workshop_automation.workshop_task_current(task)
            ]
            ready = False
            candidate_blocks = []
            for setting in settings:
                if result["recipe"] is None:
                    result["recipe"] = next(
                        (name for item in setting.items for name in item.item_names),
                        None,
                    )
                if op_data is None:
                    continue
                block = workshop_admission_block(
                    op_data, setting, inventory, tasks, readonly=True
                )
                if block is None:
                    ready = True
                else:
                    candidate_blocks.append(block)
            if ready and not blocks:
                result["execution"] = "ready"
            else:
                blocks.extend(candidate_blocks if not ready else [])
            if blocks:
                result["execution"] = "waiting"
            if queued:
                result["execution"] = "queued"
            if any(task is current for task in queued) and not getattr(
                scheduler, "sleeping", False
            ):
                result["execution"] = "running"
            if workshop_automation._refresh_error:
                blocks = [
                    WorkshopBlock("refresh_failed", workshop_automation._refresh_error)
                ]
                result["execution"] = "waiting"
            result["pending_refresh"] = workshop_inventory_changed.is_set()
            if (
                result["pending_refresh"]
                and conf.workshop_auto_active
                and result["execution"] in ("ready", "queued")
            ):
                blocks.insert(
                    0,
                    WorkshopBlock(
                        "pending_refresh", "库存已更新，等待调度重算合成缺口"
                    ),
                )
                result["execution"] = "waiting"
            if not running:
                result["execution"] = "stopped"
            elif op_data is None:
                result["execution"] = "unavailable"
                blocks.insert(
                    0, WorkshopBlock("scheduler_unavailable", "调度器尚未完成初始化")
                )
        except (OSError, ValueError, KeyError, TypeError, DatabaseError) as exc:
            result["execution"] = "unavailable"
            blocks = [WorkshopBlock("data_unavailable", f"合成数据不可用：{exc}")]
        result["blockers"] = [block.as_dict() for block in dict.fromkeys(blocks)][:3]
        return result
