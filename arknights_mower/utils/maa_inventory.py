"""Apply cumulative MAA drops once per task within one assistant instance."""

from threading import Lock

from arknights_mower.data import key_mapping
from arknights_mower.solvers.record import (
    apply_workshop_inventory,
    get_inventory_counts,
)
from arknights_mower.utils.log import logger


class MaaDropInventory:
    def __init__(self):
        self._totals = {}
        self._lock = Lock()

    def record(self, payload):
        task_id = payload.get("taskid")
        details = payload.get("details")
        if type(task_id) is not int or task_id < 0 or not isinstance(details, dict):
            return
        stats = details.get("stats")
        if not isinstance(stats, list):
            return
        totals = {}
        for item in stats:
            if not isinstance(item, dict):
                continue
            item_id, count = item.get("itemId"), item.get("quantity")
            if not isinstance(item_id, str) or type(count) is not int or count < 0:
                continue
            metadata = key_mapping.get(item_id)
            if not isinstance(metadata, list) or len(metadata) < 3:
                continue
            name = metadata[2]
            totals[name] = max(totals.get(name, 0), count)
        if not totals:
            return
        with self._lock:
            # Refuse additional tasks at the bound instead of forgetting receipts.
            if task_id not in self._totals and len(self._totals) >= 256:
                raise ValueError("MAA 掉落任务数量超过单次运行上限")
            previous = self._totals.get(task_id, {})
            delta = {
                name: count - previous.get(name, 0)
                for name, count in totals.items()
                if count > previous.get(name, 0)
            }
            if not delta:
                return
            unknown = delta.keys() - get_inventory_counts(list(delta)).keys()
            newly_unknown = unknown - previous.keys()
            if newly_unknown:
                logger.warning(
                    "MAA 掉落缺少库存基线，未估算总库存，请读取仓库：%s",
                    "、".join(sorted(newly_unknown)),
                )
            apply_workshop_inventory(delta)
            self._totals[task_id] = {
                **previous,
                **{
                    name: previous.get(name, 0) + amount
                    for name, amount in delta.items()
                },
            }

    def accumulated(self, task_id):
        """Return accepted cumulative quantities using canonical item IDs."""
        with self._lock:
            return {
                str(key_mapping[name][0]): count
                for name, count in self._totals.get(task_id, {}).items()
                if name in key_mapping
            }
