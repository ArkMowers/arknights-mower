from typing import Optional

import yaml

from arknights_mower.utils.config.app_state import read_app_state, write_app_state
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


class WeeklyPlanManager:
    """Persist weekly plan presets and keep the active plan synced to runtime config."""

    WEEKLY_PLANS_FILE = get_path("@app/weekly_plans.yml")
    DEFAULT_PLAN_KEY = "默认"

    def __init__(self):
        self._ensure_weekly_plans_exists()
        self.sync_active_plan_to_config()

    @staticmethod
    def _is_blank_plan(plan_data) -> bool:
        if not isinstance(plan_data, list):
            return False
        for item in plan_data:
            if not isinstance(item, dict):
                return False
            if item.get("medicine") not in (0, None):
                return False
            if item.get("sanity_threshold") not in (0, None):
                return False
            if item.get("stage") not in ([], [""], None):
                return False
        return True

    def _normalize_legacy_plans(self, data: dict) -> dict:
        plans = dict(data.get("plans") or {})
        changed = False

        if "default" in plans and self.DEFAULT_PLAN_KEY not in plans:
            plans[self.DEFAULT_PLAN_KEY] = plans.pop("default")
            changed = True

        for legacy_key in ("holiday", "light"):
            if legacy_key in plans and self._is_blank_plan(plans[legacy_key]):
                del plans[legacy_key]
                changed = True

        if not plans:
            from arknights_mower.utils import config

            plans[self.DEFAULT_PLAN_KEY] = [
                item.model_dump() for item in config.conf.maa_weekly_plan
            ]
            changed = True

        if changed:
            data["plans"] = plans
            self._write_weekly_plans(data)

            state = self._read_state()
            active_key = state.get("active_weekly_plan", "")
            if active_key == "default" or active_key not in plans:
                state["active_weekly_plan"] = self.DEFAULT_PLAN_KEY
                self._write_state(state)

        return {"plans": plans}

    def _ensure_weekly_plans_exists(self):
        if not self.WEEKLY_PLANS_FILE.exists():
            logger.info("weekly_plans.yml not found, creating from current config")
            from arknights_mower.utils import config

            default_plan = [item.model_dump() for item in config.conf.maa_weekly_plan]
            self._write_weekly_plans({"plans": {self.DEFAULT_PLAN_KEY: default_plan}})
            return

        data = self._normalize_legacy_plans(self._read_weekly_plans())
        plans = data.get("plans") or {}
        if plans:
            return

        logger.warning("weekly_plans.yml contains no plans, recreating default")
        from arknights_mower.utils import config

        default_plan = [item.model_dump() for item in config.conf.maa_weekly_plan]
        self._write_weekly_plans({"plans": {self.DEFAULT_PLAN_KEY: default_plan}})

    def _read_weekly_plans(self) -> dict:
        if not self.WEEKLY_PLANS_FILE.exists():
            return {"plans": {}}
        with self.WEEKLY_PLANS_FILE.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"plans": {}}

    def _write_weekly_plans(self, data: dict):
        self.WEEKLY_PLANS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with self.WEEKLY_PLANS_FILE.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _read_state(self) -> dict:
        return read_app_state()

    def _write_state(self, data: dict):
        write_app_state(data)

    def get_plans(self) -> list[str]:
        return list((self._read_weekly_plans().get("plans") or {}).keys())

    def get_active_plan_key(self) -> str:
        active = self._read_state().get("active_weekly_plan", "").strip()
        plans = self.get_plans()
        if active in plans:
            return active
        if self.DEFAULT_PLAN_KEY in plans:
            return self.DEFAULT_PLAN_KEY
        if plans:
            return plans[0]
        return ""

    def get_plan(self, key: str) -> Optional[list[dict]]:
        if not key:
            return None
        return (self._read_weekly_plans().get("plans") or {}).get(key)

    def set_active_plan(self, key: str) -> bool:
        key = (key or "").strip()
        if not key or key not in self.get_plans():
            return False
        state = self._read_state()
        state["active_weekly_plan"] = key
        self._write_state(state)
        self.sync_active_plan_to_config(key)
        return True

    def create_or_update_plan(self, key: str, plan_data: list[dict]) -> bool:
        key = (key or "").strip()
        if not key:
            return False
        data = self._read_weekly_plans()
        plans = data.get("plans") or {}
        plans[key] = plan_data
        data["plans"] = plans
        self._write_weekly_plans(data)
        self.set_active_plan(key)
        return True

    def delete_plan(self, key: str) -> bool:
        plans = self.get_plans()
        if len(plans) <= 1 or key not in plans:
            return False
        active_before = self.get_active_plan_key()
        data = self._read_weekly_plans()
        del data["plans"][key]
        self._write_weekly_plans(data)

        if active_before == key:
            remaining = list(data["plans"].keys())
            if remaining:
                self.set_active_plan(remaining[0])
        return True

    def sync_active_plan_to_config(self, key: Optional[str] = None) -> bool:
        from arknights_mower.utils import config
        from arknights_mower.utils.config.conf import RegularTaskPart

        active_key = key or self.get_active_plan_key()
        plan_data = self.get_plan(active_key)
        if not plan_data:
            return False

        try:
            config.conf.maa_weekly_plan = [
                RegularTaskPart.MaaDailyPlan(**item) for item in plan_data
            ]
            return True
        except Exception as exc:
            logger.error("failed to sync active weekly plan '%s': %s", active_key, exc)
            return False


_weekly_plan_manager: Optional[WeeklyPlanManager] = None


def get_weekly_plan_manager() -> WeeklyPlanManager:
    global _weekly_plan_manager
    if _weekly_plan_manager is None:
        _weekly_plan_manager = WeeklyPlanManager()
    return _weekly_plan_manager
