"""独立保存计算心情，复用收益演算中的技能规则。"""

import copy
import hashlib
import json
import math
import threading
from datetime import datetime, timedelta
from pathlib import Path

_runtime = threading.local()
_DATA = Path(__file__).parents[1] / "data" / "mood"


def shared_rates(payload):
    import quickjs

    if not hasattr(_runtime, "context"):
        source = (_DATA / "runtime.js").read_text("utf-8").encode("utf-8")
        manifest = json.loads((_DATA / "source.json").read_text("utf-8"))
        if hashlib.sha256(source).hexdigest() != manifest["sha256"]:
            raise RuntimeError("心情计算资源校验失败，请重新安装当前版本")
        context = quickjs.Context()
        context.set_memory_limit(128 * 1024 * 1024)
        context.set_max_stack_size(1024 * 1024)
        context.set_time_limit(2)
        context.eval(source.decode("utf-8"))
        _runtime.context = context
        _runtime.calculate = context.get("mowerMoodRates")
    _runtime.context.set_time_limit(2)
    return json.loads(_runtime.calculate(json.dumps(payload, ensure_ascii=False)))


class CalculatedMood:
    def __init__(self):
        self.schema = 1
        self.rules_hash = json.loads((_DATA / "source.json").read_text("utf-8"))[
            "sha256"
        ]
        self.at = None
        self.enabled = False
        self.moods = {}
        self.observed = {}
        self.barriers = {}
        self.positions = {}
        self.rooms = {}
        self.stages = {}
        self.single_targets = {}
        self.automatic_targets = {}
        self.versions = {}
        self.metadata_loaded = False
        self.events = {}
        self.pending_events = {}
        self.event_watermark = None
        self.revision = 0

    def _rates(self, moods=None):
        source = self.moods if moods is None else moods
        signature = (
            json.dumps(
                [
                    self.rooms,
                    self.stages,
                    self.single_targets,
                    self.versions,
                    self.automatic_targets,
                ],
                sort_keys=True,
            ),
            tuple(
                (
                    name,
                    tuple(
                        (value > threshold + 1e-8, abs(value - threshold) <= 1e-8)
                        for threshold in getattr(self, "thresholds", ())
                    ),
                )
                for name, value in sorted(source.items())
            ),
        )
        if signature == getattr(self, "_rate_signature", None):
            return self._cached_rates
        result = shared_rates(
            {
                "moods": source,
                "rooms": self.rooms,
                "stages": self.stages,
                "singleTargets": self.single_targets,
                "automaticTargets": self.automatic_targets,
                "versions": self.versions,
            }
        )
        warnings = tuple(sorted(set(result.get("unquantified", []))))
        if warnings and warnings != getattr(self, "_warnings", ()):
            from arknights_mower.utils.log import logger

            logger.warning("心情演算含未量化技能：" + "；".join(warnings))
        self._warnings = warnings
        self.automatic_targets = result["automaticTargets"]
        self.thresholds = result["thresholds"]
        self._rate_signature = signature
        self._cached_rates = result["rates"]
        return result["rates"]

    def advance(self, now=None):
        now = now or datetime.now()
        if self.at is None:
            self.at = now
            return
        if now <= self.at:
            return
        remaining = (now - self.at).total_seconds() / 3600
        # 技能只在心情跨过这些边界时改变；每段重新调用同一个演算引擎。
        for _ in range(4096):
            if remaining <= 1e-12 or not self.moods:
                break
            rates = self._rates()
            step = remaining
            for name, value in self.moods.items():
                rate = rates.get(name) or 0
                if rate == 0:
                    continue
                for boundary in self.thresholds:
                    distance = (value - boundary) / rate
                    if distance > 1e-9:
                        step = min(step, distance)
            for name, value in tuple(self.moods.items()):
                rate = rates.get(name) or 0
                updated = max(0, min(24, value - rate * step))
                self.moods[name] = next(
                    (
                        boundary
                        for boundary in self.thresholds
                        if abs(updated - boundary) <= 1e-9
                    ),
                    updated,
                )
            remaining -= step
        else:
            raise RuntimeError("心情计算分段超过上限")
        self.at = now

    def value(self, name, now=None):
        if now is not None:
            projected = copy.deepcopy(self)
            projected.advance(now)
            return (
                projected.moods.get(name)
                if projected._rates().get(name) is not None
                else None
            )
        now = max(datetime.now(), self.at or datetime.min)
        self.advance(now)
        return self.moods.get(name) if self._rates().get(name) is not None else None

    def observe(self, name, value, observed_at=None):
        observed_at = observed_at or datetime.now()
        if (
            not isinstance(value, (float, int))
            or not math.isfinite(value)
            or not 0 <= value <= 24
        ):
            return False
        barrier = max(
            (
                stamp
                for stamp in (self.observed.get(name), self.barriers.get(name))
                if stamp is not None
            ),
            default=None,
        )
        if barrier is not None and observed_at < barrier:
            return False
        if (
            self.at is not None
            and observed_at < self.at
            and self.positions.get(name, ("", -1))[0]
        ):
            return False
        self.advance(observed_at)
        self.moods[name] = float(value)
        self.observed[name] = observed_at
        for key, pending in tuple(self.pending_events.items()):
            if name in pending["changes"] and pending["started_at"] <= observed_at:
                self.events[key] = observed_at
                del self.pending_events[key]
        self.revision += 1
        return True

    def move(self, name, room, index, now=None):
        position = (room, index)
        if self.positions.get(name) == position:
            return
        now = max(now or datetime.now(), self.at or datetime.min)
        self.advance(now)
        self.positions[name] = position
        self.versions[name] = self.versions.get(name, 0) + 1
        for data in self.rooms.values():
            data["roster"] = [
                occupant for occupant in data["roster"] if occupant != name
            ]
        if room in self.rooms:
            roster = self.rooms[room]["roster"]
            roster.insert(max(0, index), name)
        self.barriers[name] = now
        self.revision += 1

    def begin_event(self, event_id, changes, started_at=None):
        if event_id in self.events or event_id in self.pending_events:
            return False
        self.pending_events[event_id] = {
            "changes": dict(changes),
            "started_at": started_at or datetime.now(),
        }
        return True

    def event(self, event_id, changes, confirmed_at=None):
        now = confirmed_at or datetime.now()
        if (
            event_id in self.events
            or self.event_watermark is not None
            and now <= self.event_watermark
        ):
            return False
        self.advance(now)
        pending = self.pending_events.pop(event_id, None)
        effect_after = pending["started_at"] if pending is not None else now
        for name, delta in changes.items():
            if (
                name in self.moods
                and self.observed.get(name, datetime.min) < effect_after
            ):
                self.moods[name] = max(0, min(24, self.moods[name] + delta))
                self.barriers[name] = now
        self.events[event_id] = now
        if len(self.events) > 2048:
            oldest = min(self.events, key=self.events.get)
            self.event_watermark = self.events.pop(oldest)
        self.revision += 1
        return True

    def restore(self):
        current_hash = json.loads((_DATA / "source.json").read_text("utf-8"))["sha256"]
        if (
            getattr(self, "schema", None) != 1
            or getattr(self, "rules_hash", None) != current_hash
        ):
            return CalculatedMood()
        for pending in self.pending_events.values():
            for name in pending["changes"]:
                self.moods.pop(name, None)
        return self

    def deadline(self, name, target, now=None, max_hours=240):
        now = now or datetime.now()
        projected = copy.deepcopy(self)
        projected.advance(now)
        value = projected.moods.get(name)
        if value is None:
            return None
        initial_rate = projected._rates().get(name)
        if initial_rate is None:
            return None
        recovering = initial_rate <= 0
        if (
            abs(value - target) <= 1e-7
            or recovering
            and value >= target
            or not recovering
            and value <= target
        ):
            return now
        end = now + timedelta(hours=max_hours)
        # 在技能边界内按当前速率推进，跨界后重新求值；只修改副本。
        for _ in range(4096):
            rates = projected._rates()
            rate = rates.get(name) or 0
            hours = (
                (projected.moods[name] - target) / rate
                if rate and recovering != (rate > 0)
                else float("inf")
            )
            for member, mood in projected.moods.items():
                member_rate = rates.get(member) or 0
                if member_rate:
                    for boundary in projected.thresholds:
                        distance = (mood - boundary) / member_rate
                        if distance > 1e-9:
                            hours = min(hours, distance)
            if not math.isfinite(hours):
                return None
            future = projected.at + timedelta(hours=max(hours, 1e-8))
            if future > end:
                return None
            projected.advance(future)
            mood = projected.moods[name]
            if (
                recovering
                and mood >= target - 1e-7
                or not recovering
                and mood <= target + 1e-7
            ):
                return future
        return None


def sync_model(owner, now=None):
    from arknights_mower.utils import config

    model = owner.mood_model
    now = now or datetime.now()
    model.advance(now)
    model.enabled = True
    from arknights_mower.utils.building_skills import load_skill_snapshot
    from arknights_mower.utils.mastery_recommendation import get_cultivate_snapshot

    payload = get_cultivate_snapshot()
    if (
        not hasattr(_runtime, "growth_payload")
        or _runtime.growth_payload is not payload
    ):
        cached = load_skill_snapshot(payload or {})
        _runtime.growth_payload = payload
        _runtime.growth_stages = {
            entry["name"]: (entry["phase"], entry["level"])
            for entry in cached["operators"]
            if entry["owned"]
            and type(entry["phase"]) is int
            and type(entry["level"]) is int
        }
    model.stages = dict(_runtime.growth_stages)
    model.metadata_loaded = True
    levels = owner.facility_levels
    observed_rooms = (
        set(owner.plan)
        | set(owner.facility_states)
        | {op.current_room for op in owner.operators.values() if op.current_room}
    )
    model.rooms = {
        room: {
            "roster": [
                op.name
                for op in sorted(
                    owner.operators.values(), key=lambda op: op.current_index
                )
                if op.current_room == room
            ],
            "facility": owner.facility_states.get(room, {}).get("facility")
            or (slots[0].facility if slots else None),
            "product": owner.facility_states.get(room, {}).get("product")
            or owner.products.get(room),
            "level": levels.get(
                room, 5 if room.startswith("dorm") or room == "central" else 3
            ),
        }
        for room in observed_rooms
        for slots in [owner.plan.get(room, [])]
    }
    model.positions = {
        op.name: (op.current_room, op.current_index) for op in owner.operators.values()
    }
    model.versions = {
        op.name: getattr(op, "dorm_position_version", 0)
        for op in owner.operators.values()
    }
    model.single_targets = {
        manager[0]: op.name
        for op in owner.operators.values()
        if op.current_room.startswith("dorm")
        and (op.current_room, op.current_index)
        == (op.dorm_recovery_room, op.dorm_recovery_index)
        for manager in getattr(op, "dorm_recovery_fixed", ())
        if len(manager) == 3
    }
    for op in owner.operators.values():
        op._mood_model = model
        op._mood_conf = getattr(owner, "runtime_conf", None) or config.conf
    return model
