"""独立保存计算心情，复用收益演算中的技能规则。"""

import copy
import hashlib
import json
import math
import threading
from bisect import bisect_left
from collections import OrderedDict
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from time import perf_counter

_runtime = threading.local()
_DATA = Path(__file__).parents[1] / "data" / "mood"


def log_mood_calculation(label):
    """按调度批次汇总模型同步与预测耗时，嵌套批次共用外层统计。"""

    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            if (
                not getattr(
                    getattr(self, "op_data", None), "mood_calculation_enabled", False
                )
                or getattr(_runtime, "timing", None) is not None
            ):
                return function(self, *args, **kwargs)
            timing = {"elapsed": 0.0, "calls": 0, "measuring": False}
            _runtime.timing = timing
            result = "完成"
            try:
                return function(self, *args, **kwargs)
            except BaseException:
                result = "中断"
                raise
            finally:
                _runtime.timing = None
                if timing["calls"]:
                    from arknights_mower.utils.log import logger

                    logger.info(
                        "实时心情计算耗时：%s，模型同步与预测累计 %.3f 秒，计算调用 %d 次，%s",
                        label,
                        timing["elapsed"],
                        timing["calls"],
                        result,
                    )

        return wrapped

    return decorate


def measure_mood_calculation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        timing = getattr(_runtime, "timing", None)
        if timing is None or timing["measuring"]:
            return function(*args, **kwargs)
        timing["measuring"] = True
        started = perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            timing["elapsed"] += perf_counter() - started
            timing["calls"] += 1
            timing["measuring"] = False

    return wrapped


def _shared_runtime():
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
        _runtime.rate_results = OrderedDict()
        _runtime.facility_levels = context.get("mowerFacilityLevels")
        _runtime.facility_level_results = OrderedDict()
    return _runtime


def shared_rates(payload):
    _shared_runtime()
    key = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    cached = _runtime.rate_results
    if key in cached:
        cached.move_to_end(key)
        return json.loads(cached[key])
    _runtime.context.set_time_limit(2)
    result = _runtime.calculate(key)
    cached[key] = result
    if len(cached) > 256:
        cached.popitem(last=False)
    return json.loads(result)


def _facility_levels(owner):
    primary = owner.global_plan.get(owner.global_plan.get("default"))
    if primary is None:
        primary = {
            room: {
                "name": slots[0].facility if slots else "",
                "plans": [{"agent": slot.agent} for slot in slots],
            }
            for room, slots in owner.global_plan["default_plan"].plan.items()
        }
    payload = json.dumps(
        {
            "default": "plan1",
            "plan1": primary,
            "facility_levels": owner.facility_levels,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    runtime = _shared_runtime()
    cached = runtime.facility_level_results
    if payload not in cached:
        runtime.context.set_time_limit(2)
        cached[payload] = runtime.facility_levels(payload)
        if len(cached) > 32:
            cached.popitem(last=False)
    cached.move_to_end(payload)
    return json.loads(cached[payload])


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

    def __deepcopy__(self, memo):
        projected = type(self).__new__(type(self))
        memo[id(self)] = projected
        signature = getattr(self, "_rate_signature", None)
        if signature is not None:
            memo[id(signature)] = signature
        projected.__dict__.update(copy.deepcopy(self.__dict__, memo))
        return projected

    def _input_signature(self):
        return json.dumps(
            [
                self.rooms,
                self.stages,
                self.single_targets,
                self.versions,
                self.automatic_targets,
            ],
            sort_keys=True,
        )

    def _signature(self, source):
        thresholds = getattr(self, "thresholds", ())
        upper = tuple(threshold + 1e-8 for threshold in thresholds)
        bands = []
        for name, value in sorted(source.items()):
            index = bisect_left(thresholds, value)
            near = -1
            if index < len(thresholds) and abs(value - thresholds[index]) <= 1e-8:
                near = index
            elif index and abs(value - thresholds[index - 1]) <= 1e-8:
                near = index - 1
            bands.append((name, bisect_left(upper, value), near))
        return self._input_signature(), tuple(bands)

    def _rates(self, moods=None):
        source = self.moods if moods is None else moods
        signature = self._signature(source)
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
        inputs_changed = (
            self.automatic_targets != result["automaticTargets"]
            or getattr(self, "thresholds", ()) != result["thresholds"]
        )
        self.automatic_targets = result["automaticTargets"]
        self.thresholds = result["thresholds"]
        self._rate_signature = self._signature(source) if inputs_changed else signature
        self._cached_rates = result["rates"]
        return result["rates"]

    @measure_mood_calculation
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
            for name, value in self.moods.items():
                rate = rates.get(name) or 0
                updated = max(0, min(24, value - rate * step))
                index = bisect_left(self.thresholds, updated)
                if index and abs(updated - self.thresholds[index - 1]) <= 1e-9:
                    updated = self.thresholds[index - 1]
                elif (
                    index < len(self.thresholds)
                    and abs(updated - self.thresholds[index]) <= 1e-9
                ):
                    updated = self.thresholds[index]
                self.moods[name] = updated
            remaining -= step
        else:
            raise RuntimeError("心情计算分段超过上限")
        self.at = now

    def _projection_key(self, now):
        return (
            self.rules_hash,
            self.at,
            now,
            self._input_signature(),
            tuple(sorted(self.moods.items())),
            tuple(getattr(self, "thresholds", ())),
        )

    @staticmethod
    def _deadline_node(projected):
        rates = projected._rates()
        boundary_hours = float("inf")
        for member, mood in projected.moods.items():
            rate = rates.get(member) or 0
            if rate:
                for boundary in projected.thresholds:
                    distance = (mood - boundary) / rate
                    if distance > 1e-9:
                        boundary_hours = min(boundary_hours, distance)
        return projected, rates, boundary_hours

    @classmethod
    def _next_deadline_node(cls, node, future):
        projected = copy.copy(node[0])
        projected.moods = node[0].moods.copy()
        projected.advance(future)
        return cls._deadline_node(projected)

    @measure_mood_calculation
    def value(self, name, now=None):
        if name not in self.moods:
            return None
        if now is not None:
            if now == self.at and self._signature(self.moods) == getattr(
                self, "_rate_signature", None
            ):
                return (
                    self.moods[name]
                    if self._cached_rates.get(name) is not None
                    else None
                )
            if not hasattr(_runtime, "future_values"):
                _runtime.future_values = OrderedDict()
            cached = _runtime.future_values
            key = self._projection_key(now)
            if key not in cached:
                projected = copy.deepcopy(self)
                projected.advance(now)
                cached[key] = (projected.moods, projected._rates())
                if len(cached) > 32:
                    cached.popitem(last=False)
            cached.move_to_end(key)
            moods, rates = cached[key]
            return moods.get(name) if rates.get(name) is not None else None
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

    @measure_mood_calculation
    def deadline(self, name, target, now=None, max_hours=240):
        now = now or datetime.now()
        if name not in self.moods:
            return None
        if not hasattr(_runtime, "deadline_trajectories"):
            _runtime.deadline_trajectories = OrderedDict()
        cached = _runtime.deadline_trajectories
        key = self._projection_key(now)
        if key not in cached:
            projected = copy.deepcopy(self)
            projected.advance(now)
            if name not in projected.moods:
                return None
            while cached and (
                len(cached) >= 16
                or sum(len(trajectory) for trajectory in cached.values()) >= 256
            ):
                cached.popitem(last=False)
            cached[key] = [self._deadline_node(projected)]
        cached.move_to_end(key)
        nodes = cached[key]
        projected, rates, _ = nodes[0]
        value = projected.moods.get(name)
        initial_rate = rates.get(name)
        if value is None or initial_rate is None:
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
        if not 0 <= target <= 24:
            return None
        end = now + timedelta(hours=max_hours)
        node = nodes[0]
        shared = True
        for index in range(4096):
            projected, rates, boundary_hours = node
            rate = rates.get(name) or 0
            target_hours = (
                (projected.moods[name] - target) / rate
                if rate and recovering != (rate > 0)
                else float("inf")
            )
            hours = min(target_hours, boundary_hours)
            if not math.isfinite(hours):
                return None
            future = projected.at + timedelta(hours=max(hours, 1e-8))
            if future > end:
                return None
            # 本段速率已知；到达查询目标后无需再演算目标之后的技能。
            # 后续查询若需要越过此边界，仍从共享轨迹继续求值。
            if target_hours <= boundary_hours:
                return future
            if shared and hours == boundary_hours:
                if index + 1 == len(nodes):
                    node = self._next_deadline_node(node, future)
                    while (
                        sum(len(trajectory) for trajectory in cached.values()) >= 256
                        and len(cached) > 1
                    ):
                        cached.popitem(last=False)
                    if len(nodes) < 256:
                        nodes.append(node)
                    else:
                        shared = False
                else:
                    node = nodes[index + 1]
            else:
                node = self._next_deadline_node(node, future)
                shared = False
            mood = node[0].moods[name]
            if (
                recovering
                and mood >= target - 1e-7
                or not recovering
                and mood <= target + 1e-7
            ):
                return future
        return None


@measure_mood_calculation
def sync_model(owner, now=None, *, advance_clock=True):
    from arknights_mower.utils import config

    model = owner.mood_model
    now = now or getattr(owner, "_projection_now", None) or datetime.now()
    from arknights_mower.utils.building_skills import load_skill_snapshot
    from arknights_mower.utils.mastery_recommendation import get_cultivate_snapshot

    if getattr(owner, "_mood_frozen_inputs", False):
        stages = dict(model.stages)
    else:
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
        stages = dict(_runtime.growth_stages)
    levels = _facility_levels(owner)
    observed_rooms = (
        set(owner.plan)
        | set(owner.facility_states)
        | {op.current_room for op in owner.operators.values() if op.current_room}
    )
    rosters = {room: [] for room in observed_rooms}
    for op in sorted(owner.operators.values(), key=lambda op: op.current_index):
        if op.current_room in rosters:
            rosters[op.current_room].append(op.name)
    rooms = {
        room: {
            "roster": rosters[room],
            "facility": owner.facility_states.get(room, {}).get("facility")
            or (slots[0].facility if slots else None),
            "product": owner.facility_states.get(room, {}).get("product")
            or owner.products.get(room),
            "level": levels.get(room, 0),
        }
        for room in observed_rooms
        for slots in [owner.plan.get(room, [])]
    }
    positions = {
        op.name: (op.current_room, op.current_index) for op in owner.operators.values()
    }
    versions = {
        op.name: getattr(op, "dorm_position_version", 0)
        for op in owner.operators.values()
    }
    single_targets = {
        manager[0]: op.name
        for op in owner.operators.values()
        if op.current_room.startswith("dorm")
        and (op.current_room, op.current_index)
        == (op.dorm_recovery_room, op.dorm_recovery_index)
        for manager in getattr(op, "dorm_recovery_fixed", ())
        if len(manager) == 3
    }
    if advance_clock or any(
        (
            model.stages != stages,
            model.rooms != rooms,
            model.versions != versions,
            model.single_targets != single_targets,
        )
    ):
        model.advance(now)
    model.enabled = True
    model.metadata_loaded = True
    model.stages = stages
    model.rooms = rooms
    model.positions = positions
    model.versions = versions
    model.single_targets = single_targets
    for op in owner.operators.values():
        op._mood_model = model
        op._mood_conf = getattr(owner, "runtime_conf", None) or config.conf
    return model
