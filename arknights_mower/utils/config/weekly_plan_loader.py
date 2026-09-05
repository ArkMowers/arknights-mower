import time
from typing import Optional

import yaml

from arknights_mower.utils.config import atomic_write, weekly_plans_path
from arknights_mower.utils.config.app_state import read_app_state, write_app_state
from arknights_mower.utils.log import logger

_UNSET = object()


class WeeklyPlanManager:
    """Persist weekly plan presets and keep the active plan synced to runtime config."""

    WEEKLY_PLANS_FILE = weekly_plans_path
    DEFAULT_PLAN_KEY = "默认"
    ACTIVITY_FALLBACKS_KEY = "activity_fallbacks"
    ACTIVITY_FALLBACK_END_TIMES_KEY = "activity_fallback_end_times"
    ACTIVITY_FALLBACK_SWITCH_TIMES_KEY = "activity_fallback_switch_times"

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

        data["plans"] = plans
        return data

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
        def dump(f):
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

        atomic_write(self.WEEKLY_PLANS_FILE, dump)

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

    def get_activity_fallbacks(self) -> dict[str, str]:
        data = self._read_weekly_plans()
        plans = data.get("plans") or {}
        raw_fallbacks = data.get(self.ACTIVITY_FALLBACKS_KEY) or {}
        if not isinstance(raw_fallbacks, dict):
            return {}
        return {
            str(source): str(target)
            for source, target in raw_fallbacks.items()
            if source in plans and target in plans and source != target
        }

    @staticmethod
    def _timestamp(value) -> int | None:
        if value in (None, ""):
            return None
        try:
            result = int(value)
        except (TypeError, ValueError):
            raise ValueError("切换时间必须是有效时间戳") from None
        if result <= 0:
            raise ValueError("切换时间必须大于 0")
        return result

    def get_activity_fallback_switch_times(self) -> dict[str, int]:
        data = self._read_weekly_plans()
        fallbacks = self.get_activity_fallbacks()
        raw_switch_times = data.get(self.ACTIVITY_FALLBACK_SWITCH_TIMES_KEY) or {}
        if not isinstance(raw_switch_times, dict):
            return {}
        result = {}
        for source, value in raw_switch_times.items():
            if source not in fallbacks:
                continue
            try:
                timestamp = self._timestamp(value)
            except ValueError:
                continue
            if timestamp is not None:
                result[str(source)] = timestamp
        return result

    def get_activity_plan_end_times(self, stages=None) -> dict[str, int]:
        """返回各方案可识别或已缓存的活动结束时间。"""
        if stages is None:
            from arknights_mower.data import stage_data_full

            stages = list(stage_data_full)
        data = self._read_weekly_plans()
        plans = data.get("plans") or {}
        raw_end_times = data.get(self.ACTIVITY_FALLBACK_END_TIMES_KEY) or {}
        cached_end_times = raw_end_times if isinstance(raw_end_times, dict) else {}
        result = {}
        for key, plan_data in plans.items():
            detected = self._activity_end_ts_for_plan_data(plan_data, stages)
            if detected is not None:
                result[str(key)] = detected
                continue
            try:
                cached = self._timestamp(cached_end_times.get(key))
            except ValueError:
                cached = None
            if cached is not None:
                result[str(key)] = cached
        return result

    def set_activity_fallback(
        self, source: str, target: str = "", switch_time=_UNSET
    ) -> bool:
        source = (source or "").strip()
        target = (target or "").strip()
        data = self._read_weekly_plans()
        plans = data.get("plans") or {}
        if source not in plans or (
            target and (target not in plans or target == source)
        ):
            return False

        raw_fallbacks = data.get(self.ACTIVITY_FALLBACKS_KEY)
        fallbacks = dict(raw_fallbacks) if isinstance(raw_fallbacks, dict) else {}
        raw_end_times = data.get(self.ACTIVITY_FALLBACK_END_TIMES_KEY)
        end_times = dict(raw_end_times) if isinstance(raw_end_times, dict) else {}
        raw_switch_times = data.get(self.ACTIVITY_FALLBACK_SWITCH_TIMES_KEY)
        switch_times = (
            dict(raw_switch_times) if isinstance(raw_switch_times, dict) else {}
        )
        if switch_time is not _UNSET:
            try:
                switch_time = self._timestamp(switch_time)
            except ValueError:
                return False
        if target:
            fallbacks[source] = target
            activity_end_ts = self._activity_end_ts_for_plan_data(plans[source])
            if activity_end_ts is not None:
                end_times[source] = activity_end_ts
            if switch_time is not _UNSET:
                if switch_time is None:
                    switch_times.pop(source, None)
                else:
                    switch_times[source] = switch_time
        else:
            fallbacks.pop(source, None)
            end_times.pop(source, None)
            switch_times.pop(source, None)
        if fallbacks:
            data[self.ACTIVITY_FALLBACKS_KEY] = fallbacks
        else:
            data.pop(self.ACTIVITY_FALLBACKS_KEY, None)
        if end_times:
            data[self.ACTIVITY_FALLBACK_END_TIMES_KEY] = end_times
        else:
            data.pop(self.ACTIVITY_FALLBACK_END_TIMES_KEY, None)
        if switch_times:
            data[self.ACTIVITY_FALLBACK_SWITCH_TIMES_KEY] = switch_times
        else:
            data.pop(self.ACTIVITY_FALLBACK_SWITCH_TIMES_KEY, None)
        self._write_weekly_plans(data)
        return True

    @staticmethod
    def _plan_stage_ids(plan_data) -> list[str]:
        result = []
        for item in plan_data or []:
            if not isinstance(item, dict):
                continue
            for stage in item.get("stage") or []:
                if isinstance(stage, str) and stage.strip():
                    result.append(stage.strip())
        return result

    def _activity_end_ts_for_plan_data(self, plan_data, stages=None) -> int | None:
        from arknights_mower.data import stage_data_full
        from arknights_mower.utils.weekly_stage import activity_end_ts_for_stages

        return activity_end_ts_for_stages(
            list(stage_data_full) if stages is None else stages,
            self._plan_stage_ids(plan_data),
        )

    def maybe_switch_expired_activity_plan(
        self, stages=None, now: int | None = None
    ) -> dict | None:
        """到达活动默认结束时间或用户设定时间后切换绑定方案。"""
        source = self.get_active_plan_key()
        target = self.get_activity_fallbacks().get(source)
        if not source or not target:
            return None

        plan_data = self.get_plan(source) or []
        detected_end_ts = self._activity_end_ts_for_plan_data(plan_data, stages)
        data = self._read_weekly_plans()
        raw_end_times = data.get(self.ACTIVITY_FALLBACK_END_TIMES_KEY)
        end_times = dict(raw_end_times) if isinstance(raw_end_times, dict) else {}
        stored_end_ts = end_times.get(source)
        try:
            stored_end_ts = int(stored_end_ts) if stored_end_ts is not None else None
        except (TypeError, ValueError):
            stored_end_ts = None
        activity_end_ts = (
            detected_end_ts if detected_end_ts is not None else stored_end_ts
        )
        if detected_end_ts is not None and detected_end_ts != stored_end_ts:
            end_times[source] = detected_end_ts
            data[self.ACTIVITY_FALLBACK_END_TIMES_KEY] = end_times
            self._write_weekly_plans(data)
        custom_switch_ts = self.get_activity_fallback_switch_times().get(source)
        switch_ts = custom_switch_ts or activity_end_ts
        current_ts = self._current_server_timestamp() if now is None else int(now)
        if switch_ts is None or switch_ts > current_ts:
            return None
        if not self.set_active_plan(target):
            return None

        result = {
            "source": source,
            "target": target,
            "activity_end_ts": activity_end_ts,
            "switch_ts": switch_ts,
        }
        logger.info(
            "weekly plan switch time reached | source=%s | target=%s | "
            "activity_end=%s | switch=%s",
            source,
            target,
            activity_end_ts,
            switch_ts,
        )
        return result

    @staticmethod
    def _current_server_timestamp() -> int:
        """使用已校准的服务器时钟偏移，避免设备时间误差影响切换。"""
        try:
            from arknights_mower.utils import skland

            offset = int(getattr(skland, "server_time_offset", 0) or 0)
        except (ImportError, TypeError, ValueError):
            offset = 0
        return int(time.time()) + offset

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
        raw_fallbacks = data.get(self.ACTIVITY_FALLBACKS_KEY)
        fallbacks = dict(raw_fallbacks) if isinstance(raw_fallbacks, dict) else {}
        if key in fallbacks:
            raw_end_times = data.get(self.ACTIVITY_FALLBACK_END_TIMES_KEY)
            end_times = dict(raw_end_times) if isinstance(raw_end_times, dict) else {}
            activity_end_ts = self._activity_end_ts_for_plan_data(plan_data)
            if activity_end_ts is not None:
                end_times[key] = activity_end_ts
            if end_times:
                data[self.ACTIVITY_FALLBACK_END_TIMES_KEY] = end_times
            else:
                data.pop(self.ACTIVITY_FALLBACK_END_TIMES_KEY, None)
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
        raw_fallbacks = data.get(self.ACTIVITY_FALLBACKS_KEY)
        fallbacks = dict(raw_fallbacks) if isinstance(raw_fallbacks, dict) else {}
        raw_end_times = data.get(self.ACTIVITY_FALLBACK_END_TIMES_KEY)
        end_times = dict(raw_end_times) if isinstance(raw_end_times, dict) else {}
        raw_switch_times = data.get(self.ACTIVITY_FALLBACK_SWITCH_TIMES_KEY)
        switch_times = (
            dict(raw_switch_times) if isinstance(raw_switch_times, dict) else {}
        )
        fallbacks.pop(key, None)
        end_times.pop(key, None)
        switch_times.pop(key, None)
        fallbacks = {
            source: target for source, target in fallbacks.items() if target != key
        }
        end_times = {
            source: end for source, end in end_times.items() if source in fallbacks
        }
        switch_times = {
            source: switch
            for source, switch in switch_times.items()
            if source in fallbacks
        }
        if fallbacks:
            data[self.ACTIVITY_FALLBACKS_KEY] = fallbacks
        else:
            data.pop(self.ACTIVITY_FALLBACKS_KEY, None)
        if end_times:
            data[self.ACTIVITY_FALLBACK_END_TIMES_KEY] = end_times
        else:
            data.pop(self.ACTIVITY_FALLBACK_END_TIMES_KEY, None)
        if switch_times:
            data[self.ACTIVITY_FALLBACK_SWITCH_TIMES_KEY] = switch_times
        else:
            data.pop(self.ACTIVITY_FALLBACK_SWITCH_TIMES_KEY, None)
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
