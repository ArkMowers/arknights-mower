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
            assert wait <= 3
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


def test_ready_room_finishes_while_another_accelerated_room_waits(batch):
    scene = batch({"room_2_1": 3000, "room_2_3": 3240})
    first, second = scene.tasks

    with pytest.raises(base.ProductSwitchDeferred) as deferred:
        scene.run()

    assert scene.events[:2] == [("survey", "room_2_1"), ("survey", "room_2_3")]
    assert sorted(scene.accelerations) == [
        ("accelerate", "room_2_1", 16),
        ("accelerate", "room_2_3", 18),
    ]
    assert scene.rooms["room_2_3"]["product"] == "gold"
    assert scene.solver.tasks == [first]
    assert all(task is not second for task in scene.solver.tasks)
    assert first.time == scene.started_at
    assert first.product_switch_progress["room_2_1"]["accelerated"] is True
    assert deferred.value.rooms == ("room_2_1",)
    assert deferred.value.ready_at == scene.started_at + timedelta(seconds=59)

    scene.restart()
    Clock.current = deferred.value.ready_at
    scene.run()

    assert scene.rooms["room_2_1"]["product"] == "gold"
    assert scene.solver.tasks == []
    assert scene.available == 155
    assert len(scene.accelerations) == 2
    scene.solver.sleep.assert_not_called()


def test_recheck_reduces_drone_count_without_blocking_other_room(batch):
    scene = batch(
        {"room_2_1": 3060, "room_2_3": 3240},
        recheck_elapsed={"room_2_1": 16},
    )

    with pytest.raises(base.ProductSwitchDeferred) as deferred:
        scene.run()

    assert scene.events[:2] == [("survey", "room_2_1"), ("survey", "room_2_3")]
    assert sorted(scene.accelerations) == [
        ("accelerate", "room_2_1", 16),
        ("accelerate", "room_2_3", 18),
    ]
    assert scene.rooms["room_2_3"]["product"] == "gold"
    assert deferred.value.ready_at == scene.started_at + timedelta(seconds=89)
    assert deferred.value.rooms == ("room_2_1",)

    scene.restart()
    Clock.current = deferred.value.ready_at + timedelta(seconds=5)
    scene.run()

    assert scene.rooms["room_2_1"]["product"] == "gold"
    assert scene.solver.tasks == []
    assert len(scene.accelerations) == 2
    assert scene.available == 155


def test_each_deferred_room_keeps_its_own_deadline_after_restart(batch):
    scene = batch({"room_2_1": 3000, "room_2_3": 3260})

    with pytest.raises(base.ProductSwitchDeferred) as first_deferred:
        scene.run()

    assert len(scene.accelerations) == 2
    assert set(first_deferred.value.rooms) == {"room_2_1", "room_2_3"}
    assert first_deferred.value.ready_at == scene.started_at + timedelta(seconds=9)
    assert scene.solver.tasks == scene.tasks
    assert all(task.time == scene.started_at for task in scene.solver.tasks)

    scene.restart()
    Clock.current = first_deferred.value.ready_at
    with pytest.raises(base.ProductSwitchDeferred) as remaining:
        scene.run()

    assert remaining.value.rooms == ("room_2_1",)
    assert remaining.value.ready_at == scene.started_at + timedelta(seconds=59)
    assert [task.meta_data for task in scene.solver.tasks] == ["room_2_1,gold"]
    assert scene.rooms["room_2_3"]["product"] == "gold"

    scene.restart()
    Clock.current = remaining.value.ready_at
    scene.run()

    assert scene.solver.tasks == []
    assert len(scene.accelerations) == 2
    assert scene.available == 155


def test_natural_only_room_does_not_block_ready_room(batch):
    config.conf.product_switching.use_drones_when_leaving_orirock = False
    scene = batch(
        {"room_2_1": 120, "room_2_3": 3240},
        products={"room_2_1": "orirock"},
    )

    with pytest.raises(base.ProductSwitchDeferred) as deferred:
        scene.run()

    assert scene.accelerations == [("accelerate", "room_2_3", 18)]
    assert scene.rooms["room_2_3"]["product"] == "gold"
    assert scene.solver.tasks == [scene.tasks[0]]
    assert deferred.value.rooms == ("room_2_1",)
    assert deferred.value.ready_at == scene.started_at + timedelta(seconds=59)

    scene.restart()
    Clock.current = deferred.value.ready_at + timedelta(seconds=5)
    scene.run()

    assert scene.solver.tasks == []
    assert len(scene.accelerations) == 1
    assert scene.available == 171


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


def test_before_arrangement_preserves_shared_owner_until_remaining_room_finishes(batch):
    scene = batch({"room_2_1": 3000, "room_2_3": 3240})
    owner = SchedulerTask(
        time=scene.started_at,
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"room_2_1": ["Current"], "room_2_3": ["Current"]},
    )
    original_plan = dict(owner.plan)
    scene.solver.tasks = [owner]
    scene.solver.task = owner

    with pytest.raises(base.ProductSwitchDeferred) as deferred:
        scene.solver.switch_base_products(scene.tasks, before_arrangement=True)

    assert scene.solver.tasks[0] is owner
    assert owner.time == scene.started_at
    assert owner.plan == original_plan
    assert owner.product_switch_progress["room_2_1"]["accelerated"] is True
    assert scene.rooms["room_2_3"]["product"] == "gold"

    scene.restart()
    restored = scene.solver.tasks[0]
    scene.solver.task = restored
    Clock.current = deferred.value.ready_at
    scene.solver.switch_base_products(scene.tasks, before_arrangement=True)

    assert scene.solver.tasks[0] is restored
    assert restored.time == scene.started_at
    assert restored.plan == original_plan
    assert restored.product_switch_progress == {}
    assert all(state["product"] == "gold" for state in scene.rooms.values())
    assert len(scene.accelerations) == 2
    assert scene.available == 155


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


def test_completed_rooms_keep_absolute_confirmation_time_after_restart(batch):
    config.conf.product_switching.waiting_seconds = 10
    scene = batch({"room_2_1": 3240, "room_2_3": 3240})
    ready_at = scene.started_at + timedelta(seconds=7)

    for elapsed in (0, 1):
        Clock.current = scene.started_at + timedelta(seconds=elapsed)
        with pytest.raises(base.ProductSwitchDeferred) as deferred:
            scene.run()
        assert deferred.value.ready_at == ready_at
        assert set(deferred.value.rooms) == {"room_2_1", "room_2_3"}
        assert len(scene.accelerations) == 2
        for task in scene.solver.tasks:
            state = next(iter(task.product_switch_progress.values()))
            assert state["accelerated"] is True
            assert state["completed_at"] == scene.started_at
            assert task.time == scene.started_at
        scene.restart()

    Clock.current = ready_at
    scene.run()

    assert scene.solver.tasks == []
    assert len(scene.accelerations) == 2
    assert scene.available == 153
    assert all(state["product"] == "gold" for state in scene.rooms.values())


def test_drone_shortage_does_not_block_completed_natural_room(batch):
    config.conf.product_switching.use_drones_when_leaving_orirock = False
    scene = batch(
        {"room_2_1": 120, "room_2_3": 3240},
        available=0,
        products={"room_2_1": "orirock"},
    )
    natural, accelerated = scene.tasks
    with pytest.raises(base.ProductSwitchDeferred):
        scene.run()
    scene.restart()
    Clock.current = scene.started_at + timedelta(seconds=64)
    with pytest.raises(base.ProductSwitchDeferred) as deferred:
        scene.run()
    assert scene.rooms["room_2_1"]["product"] == "gold"
    assert [task.meta_data for task in scene.solver.tasks] == [accelerated.meta_data]
    assert deferred.value.rooms == ("room_2_3",)
    assert scene.accelerations == []
    assert natural.time == scene.started_at
