import math
import pickle
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

with pytest.MonkeyPatch.context() as import_patch:
    import_patch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers import base_schedule as base
    from arknights_mower.utils import config
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class Clock(datetime):
    current = None

    @classmethod
    def now(cls):
        return cls.current


@pytest.fixture
def batch(monkeypatch):
    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(Clock, "current", Clock(2026, 10, 27, 10))
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    return ManufactureBatch


class ManufactureBatch:
    """用页面读数替身运行真实巡检、加速和切换，时间与无人机共享。"""

    def __init__(
        self, remaining, *, available=189, products=None, recheck_elapsed=None
    ):
        self.started_at = Clock.now()
        self.available = available
        self.events = []
        self.surveying = False
        self.recheck_elapsed = dict(recheck_elapsed or {})
        self.rooms = {
            room: {
                "remaining": seconds,
                "spent": 0,
                "product": (products or {}).get(room, "exp3"),
            }
            for room, seconds in remaining.items()
        }
        self.tasks = [
            SchedulerTask(
                time=self.started_at,
                task_type=TaskTypes.SWITCH_PRODUCT,
                meta_data=f"{room},gold",
            )
            for room in self.rooms
        ]
        solver = self.solver = object.__new__(base.BaseSchedulerSolver)
        solver.tasks = list(self.tasks)
        solver.op_data = SimpleNamespace(plan={}, operators={})
        solver.recog = SimpleNamespace(
            gray=MagicMock(), h=1080, w=1920, update=MagicMock()
        )
        solver.digit_reader = SimpleNamespace(
            get_drone=MagicMock(side_effect=lambda *args: self.available)
        )
        solver._open_manufacture_product_detail = self.open_room
        solver.read_manufacture_product = lambda: self.rooms[self.room]["product"]
        solver._cache_facility_state = MagicMock()
        solver._manufacture_is_idle = MagicMock(return_value=False)
        solver._read_manufacture_speed = MagicMock(return_value=2.0)
        solver._tap_drone_accelerate = MagicMock()
        solver._read_manufacture_total_seconds = self.read_total
        solver._tap_product_point = MagicMock()
        solver._confirm_drone_count = self.confirm_drones
        solver._select_manufacture_product = self.select_product
        solver._fill_manufacture_queue = MagicMock()
        solver.translate_room = lambda room: room
        solver.sleep = MagicMock(side_effect=AssertionError("不应在页面长时间等待"))
        survey = solver._survey_manufacture_switch

        def survey_room(room, target):
            self.events.append(("survey", room))
            self.surveying = True
            try:
                return survey(room, target)
            finally:
                self.surveying = False

        solver._survey_manufacture_switch = survey_room

    def open_room(self, room):
        self.room = room
        if not self.surveying:
            Clock.current += timedelta(seconds=self.recheck_elapsed.pop(room, 0))

    def read_total(self):
        state = self.rooms[self.room]
        unit = 3600 if state["product"] == "orirock" else 10800
        elapsed = (Clock.now() - self.started_at).total_seconds()
        return math.ceil(
            9 * unit + state["remaining"] - 2 * elapsed - state["spent"] * 180
        )

    def confirm_drones(self, count):
        assert 0 < count <= self.available
        self.events.append(("accelerate", self.room, count))
        self.available -= count
        self.rooms[self.room]["spent"] += count

    def select_product(self, product, *, confirm_after=None, **kwargs):
        if confirm_after is not None:
            wait = max(0, (confirm_after - Clock.now()).total_seconds())
            assert self.solver._product_batch_active
            Clock.current += timedelta(seconds=wait)
        self.events.append(("change", self.room))
        self.rooms[self.room]["product"] = product

    def run(self, *, before_arrangement=False):
        return self.solver.switch_base_products(
            list(self.solver.tasks), before_arrangement=before_arrangement
        )

    def restart(self):
        self.solver.tasks = pickle.loads(pickle.dumps(self.solver.tasks))

    @property
    def accelerations(self):
        return [event for event in self.events if event[0] == "accelerate"]


def test_remainder_order_finishes_each_room_before_next_acceleration(batch):
    scene = batch({"room_2_1": 3000, "room_2_3": 3240})
    scene.run()
    assert scene.events == [
        ("survey", "room_2_1"),
        ("survey", "room_2_3"),
        ("accelerate", "room_2_3", 18),
        ("change", "room_2_3"),
        ("accelerate", "room_2_1", 16),
        ("change", "room_2_1"),
    ]
    assert scene.solver.tasks == []
    assert scene.available == 155
    assert Clock.now() == scene.started_at + timedelta(seconds=62)
    assert all(task.time == scene.started_at for task in scene.tasks)
    assert all(task.product_switch_progress == {} for task in scene.tasks)


def test_recheck_reduces_drone_count_and_completes_serially(batch):
    scene = batch(
        {"room_2_1": 3060, "room_2_3": 3240},
        recheck_elapsed={"room_2_1": 16},
    )
    scene.run()
    assert scene.events == [
        ("survey", "room_2_1"),
        ("survey", "room_2_3"),
        ("accelerate", "room_2_1", 16),
        ("change", "room_2_1"),
        ("accelerate", "room_2_3", 17),
        ("change", "room_2_3"),
    ]
    assert scene.solver.tasks == []
    assert scene.available == 156
    assert Clock.now() == scene.started_at + timedelta(seconds=94)


def test_interrupted_confirmation_resumes_original_unit_without_more_drones(batch):
    scene = batch({"room_2_1": 3000, "room_2_3": 3260})
    select = scene.solver._select_manufacture_product
    scene.solver._select_manufacture_product = MagicMock(side_effect=base.MowerExit())
    with pytest.raises(base.MowerExit):
        scene.run()
    assert scene.accelerations == [("accelerate", "room_2_3", 18)]
    assert scene.solver.tasks == scene.tasks
    original_times = [task.time for task in scene.tasks]
    scene.restart()
    # 原当前份已经跨过边界，新的当前份不重新加速或延长同一次切换。
    Clock.current = scene.started_at + timedelta(seconds=20)
    scene.solver._select_manufacture_product = select
    scene.run()
    assert scene.solver.tasks == []
    assert scene.accelerations == [
        ("accelerate", "room_2_3", 18),
        ("accelerate", "room_2_1", 16),
    ]
    assert scene.available == 155
    assert [task.time for task in scene.tasks] == original_times


def test_natural_only_room_finishes_in_same_batch_after_ready_room(batch):
    config.conf.product_switching.use_drones_when_leaving_orirock = False
    scene = batch(
        {"room_2_1": 120, "room_2_3": 3240},
        products={"room_2_1": "orirock"},
    )
    scene.run()
    assert scene.events == [
        ("survey", "room_2_1"),
        ("survey", "room_2_3"),
        ("accelerate", "room_2_3", 18),
        ("change", "room_2_3"),
        ("change", "room_2_1"),
    ]
    assert scene.solver.tasks == []
    assert scene.available == 171
    assert Clock.now() == scene.started_at + timedelta(seconds=62)


def test_batch_shortage_retains_all_rooms_without_spending(batch):
    scene = batch({"room_2_1": 3000, "room_2_3": 3240}, available=33)

    with pytest.raises(base.ProductSwitchDeferred):
        scene.run()

    assert scene.events == [
        ("survey", "room_2_1"),
        ("survey", "room_2_3"),
        ("survey", "room_2_1"),
        ("survey", "room_2_3"),
    ]
    assert scene.solver.tasks == scene.tasks
    assert scene.available == 33
    assert all(task.time == scene.started_at for task in scene.solver.tasks)
    assert all(state["product"] == "exp3" for state in scene.rooms.values())


def test_before_arrangement_keeps_shared_owner_and_plan_through_whole_batch(batch):
    scene = batch({"room_2_1": 3000, "room_2_3": 3240})
    owner = SchedulerTask(
        time=scene.started_at,
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"room_2_1": ["Current"], "room_2_3": ["Current"]},
    )
    original_plan = dict(owner.plan)
    scene.solver.tasks = [owner]
    scene.solver.task = owner
    scene.solver.switch_base_products(scene.tasks, before_arrangement=True)
    assert scene.solver.tasks[0] is owner
    assert owner.time == scene.started_at
    assert owner.plan == original_plan
    assert owner.product_switch_progress == {}
    assert all(state["product"] == "gold" for state in scene.rooms.values())
    assert len(scene.accelerations) == 2
    assert scene.available == 155
    assert scene.solver._product_batch_active


def test_unknown_timing_observation_does_not_block_other_room(batch):
    scene = batch({"room_2_1": 3000, "room_2_3": 3240})

    def read_speed():
        if scene.room == "room_2_1":
            raise base.RecognizeError("生产力未识别")
        return 2.0

    scene.solver._read_manufacture_speed.side_effect = read_speed
    scene.solver._read_manufacture_adjusted_total_seconds = MagicMock(
        side_effect=base.RecognizeError("倒计时未识别")
    )

    with pytest.raises(base.ProductSwitchDeferred) as deferred:
        scene.run()

    assert scene.accelerations == [("accelerate", "room_2_3", 18)]
    assert deferred.value.rooms == ("room_2_1",)
    assert deferred.value.ready_at is None
    assert scene.solver.tasks[0] is scene.tasks[0]
    assert len(scene.solver.tasks) == 1
    assert scene.solver.tasks[0].time == scene.started_at
    assert scene.rooms["room_2_3"]["product"] == "gold"
    assert scene.available == 171


def test_completed_unit_keeps_absolute_confirmation_time_after_interruption(batch):
    config.conf.product_switching.waiting_seconds = 10
    scene = batch({"room_2_1": 3240, "room_2_3": 3240})
    select = scene.solver._select_manufacture_product
    scene.solver._select_manufacture_product = MagicMock(side_effect=base.MowerExit())
    for elapsed in (0, 1):
        Clock.current = scene.started_at + timedelta(seconds=elapsed)
        with pytest.raises(base.MowerExit):
            scene.run()
        assert scene.accelerations == [("accelerate", "room_2_1", 18)]
        state = scene.solver.tasks[0].product_switch_progress["room_2_1"]
        assert state["completed_at"] == scene.started_at
        scene.restart()
    scene.solver._select_manufacture_product = select
    confirmations = []

    def record_confirmation(product, *, confirm_after=None):
        confirmations.append((scene.room, confirm_after))
        select(product, confirm_after=confirm_after)

    scene.solver._select_manufacture_product = record_confirmation
    scene.run()
    assert confirmations[0] == ("room_2_1", scene.started_at + timedelta(seconds=10))
    assert scene.solver.tasks == []
    assert len(scene.accelerations) == 2
    assert scene.available == 153
    assert all(state["product"] == "gold" for state in scene.rooms.values())


def test_drone_shortage_does_not_block_natural_room_in_admitted_batch(batch):
    config.conf.product_switching.use_drones_when_leaving_orirock = False
    scene = batch(
        {"room_2_1": 120, "room_2_3": 3240},
        available=0,
        products={"room_2_1": "orirock"},
    )
    natural, accelerated = scene.tasks
    with pytest.raises(base.ProductSwitchDeferred) as deferred:
        scene.run()
    assert scene.rooms["room_2_1"]["product"] == "gold"
    assert [task.meta_data for task in scene.solver.tasks] == [accelerated.meta_data]
    assert deferred.value.rooms == ("room_2_3",)
    assert scene.accelerations == []
    assert natural.time == scene.started_at
    assert Clock.now() == scene.started_at + timedelta(seconds=62)
    scene.restart()
    with pytest.raises(base.ProductSwitchDeferred):
        scene.run()
    assert scene.events.count(("change", "room_2_1")) == 1
