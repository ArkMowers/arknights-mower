from __future__ import annotations

import types
import unittest
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from arknights_mower.scheduler.constants import (
    CURRENT,
    WORKSHOP_AGENT_JIUSE,
    WORKSHOP_JIUSE_SKILL_TARGET,
)
fake_log = types.ModuleType("arknights_mower.utils.log")
fake_log.logger = MagicMock()
with patch.dict("sys.modules", {"arknights_mower.utils.log": fake_log}):
    from arknights_mower.scheduler.executors.workshop import WorkshopExecutor
    from arknights_mower.scheduler.services.agent_swap_service import AgentSwapService
    import arknights_mower.scheduler.executors.workshop_support as workshop_support
from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.graph import build_default_graph
from arknights_mower.scheduler.infra import workshop_scanner
from arknights_mower.scheduler.scene import Scene as V2Scene
from arknights_mower.scheduler.infra.workshop_scanner import FormulaScanItem
from arknights_mower.scheduler.services.workshop_service import (
    WorkshopCandidate,
    jiuselu_candidate_matches_gap,
    jiuselu_should_switch_candidate,
    make_jiuselu_production_plan,
    workshop_inventory_name,
)

FURNITURE = "\u5bb6\u5177\u96f6\u4ef6"
FURNITURE_CARBON = "\u5bb6\u5177\u96f6\u4ef6_\u78b3\u7d20"
ELITE_TAB = "\u7cbe\u82f1\u6750\u6599"
DEVICE = "\u88c5\u7f6e"
CRIT_ITEM = "\u805a\u80fd\u52a8\u529b\u5355\u5143"


class DummyDevice:
    def __init__(self):
        self.calls = []

    def tap(self, x, y):
        self.calls.append(("tap", round(x, 4), round(y, 4)))

    def swipe(self, x1, y1, x2, y2, duration=100):
        self.calls.append(
            ("swipe", round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4), duration)
        )

    def back(self):
        self.calls.append(("back",))


class DummyRecognizer:
    def __init__(self, img=None):
        self.img = img if img is not None else np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.saved = []
        self._find = {}

    def find(self, key):
        return self._find.get(key)

    def save_screencap(self, name):
        self.saved.append(name)

    def update(self):
        return None

    def get_scene(self):
        return 225


class DummyNavigator:
    def __init__(self, recognizer):
        self._recognizer = recognizer
        self.calls = []

    def navigate(self, target):
        self.calls.append(("navigate", target))

    def enter_room(self, room):
        self.calls.append(("enter_room", room))

    def wait_scene_stable(self, **kwargs):
        self.calls.append(("wait_scene_stable", kwargs))


@dataclass
class DummyOperator:
    mood: float = 24.0
    time_stamp: object | None = None
    current_room: str = ""
    current_index: int = -1


class WorkshopScannerTest(unittest.TestCase):
    def test_scan_formula_items_reads_ocr_and_valid_samples(self):
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        img[200, 385] = [50, 50, 50]
        img[200, 540] = [50, 50, 50]
        img[200, 695] = [50, 50, 50]
        recognizer = DummyRecognizer(img=img)
        box = [[0, 0], [200, 0], [200, 120], [0, 120]]
        fake_ocr = [[box, DEVICE, 0.99]]
        with (
            patch.object(workshop_scanner.rapidocr, "engine", return_value=[fake_ocr]),
            patch.object(workshop_scanner, "save_child_inventory_zero") as save_counts,
        ):
            items = workshop_scanner.scan_formula_items(recognizer)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, DEVICE)
        self.assertTrue(items[0].valid)
        self.assertEqual(items[0].box[0], [370, 125])
        save_counts.assert_not_called()

    def test_scan_formula_items_marks_invalid_child_material(self):
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        img[200, 385] = [255, 255, 255]
        recognizer = DummyRecognizer(img=img)
        box = [[0, 0], [200, 0], [200, 120], [0, 120]]
        fake_ocr = [[box, DEVICE, 0.99]]
        with (
            patch.object(workshop_scanner.rapidocr, "engine", return_value=[fake_ocr]),
            patch.object(workshop_scanner, "save_child_inventory_zero") as save_counts,
        ):
            items = workshop_scanner.scan_formula_items(recognizer)
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0].valid)
        save_counts.assert_called_once()


class WorkshopServiceTest(unittest.TestCase):
    def test_inventory_name_for_furniture(self):
        self.assertEqual(workshop_inventory_name(FURNITURE_CARBON), FURNITURE)
        self.assertEqual(workshop_inventory_name(CRIT_ITEM), CRIT_ITEM)

    def test_jiuselu_gap_rules(self):
        crit = WorkshopCandidate(CRIT_ITEM, CRIT_ITEM, ELITE_TAB, 4.0, object())
        small = WorkshopCandidate(DEVICE, DEVICE, ELITE_TAB, 1.0, object())
        self.assertTrue(jiuselu_candidate_matches_gap(crit, 3))
        self.assertFalse(jiuselu_candidate_matches_gap(small, 3))
        self.assertTrue(jiuselu_candidate_matches_gap(small, 8))
        self.assertTrue(jiuselu_should_switch_candidate(small, 3, 4))
        self.assertTrue(jiuselu_should_switch_candidate(crit, 8, 24))
        self.assertFalse(jiuselu_should_switch_candidate(crit, 3, 4))


    def test_near_crit_requires_enough_mood(self):
        plan = make_jiuselu_production_plan(gap=3, mood=3, ap_cost=4)
        self.assertIsNone(plan)

    def test_production_plan_selection(self):
        plan = make_jiuselu_production_plan(gap=8, mood=24, ap_cost=2)
        self.assertIsNotNone(plan)
        self.assertFalse(plan.use_max)
        self.assertEqual(plan.add_taps, 2)
        self.assertGreater(plan.estimated_mood_cost, 0)
        self.assertIsNone(make_jiuselu_production_plan(gap=41, mood=24, ap_cost=2))


class WorkshopExecutorTest(unittest.TestCase):
    def setUp(self):
        self.recognizer = DummyRecognizer()
        self.device = DummyDevice()
        self.navigator = DummyNavigator(self.recognizer)
        self.state = SimpleNamespace(operators={WORKSHOP_AGENT_JIUSE: DummyOperator()})
        self.infra = SimpleNamespace(
            device=self.device,
            navigator=self.navigator,
            state=self.state,
            pause=SimpleNamespace(wait_if_paused=lambda: None),
        )
        self.executor = WorkshopExecutor(self.infra)
        self.executor._agent = WORKSHOP_AGENT_JIUSE
        self.executor._is_9colored = True
        self.executor._tab_queue = deque()
        self.executor._all_tabs = []
        self.executor._tasks = deque(["process"])
        self.executor._current_material = WorkshopCandidate(
            DEVICE,
            DEVICE,
            ELITE_TAB,
            2.0,
            object(),
        )
        self.executor._production_plan = None
        self.executor._gap = 8


    def test_arranges_jiuselu_before_processing_and_restores_previous_agent(self):
        self.state.plan = {"room_1_1": [object(), object(), object()]}
        self.state.operators[WORKSHOP_AGENT_JIUSE].current_room = "room_1_1"
        self.state.operators[WORKSHOP_AGENT_JIUSE].current_index = 1
        self.state.operators["???"] = DummyOperator(
            current_room="factory",
            current_index=0,
        )
        arrange_calls = []
        self.executor._run_arrange = lambda plan: arrange_calls.append(plan)
        self.executor._navigate = lambda target: None
        self.executor._gather_inventory = lambda: None
        self.executor._process_workshop = lambda: None

        self.executor.execute(
            SchedulerTask(
                time=datetime.now(),
                type=TaskTypes.WORKSHOP,
                meta_data=WORKSHOP_AGENT_JIUSE,
            )
        )

        self.assertEqual(arrange_calls[0], {"factory": [WORKSHOP_AGENT_JIUSE]})
        self.assertEqual(
            arrange_calls[1],
            {
                "factory": ["???"],
                "room_1_1": [CURRENT, WORKSHOP_AGENT_JIUSE, CURRENT],
            },
        )

    def test_graph_can_return_from_factory_room_to_infra_main(self):
        graph = build_default_graph()
        path = graph.find_path(V2Scene.FACTORY_DASHBOARD, V2Scene.INFRA_MAIN)
        self.assertIsNotNone(path)
        self.assertEqual([step.target for step in path], [V2Scene.FACTORY_ROOM, V2Scene.INFRA_MAIN])

    def test_graph_can_return_from_formula_to_infra_main(self):
        graph = build_default_graph()
        path = graph.find_path(V2Scene.FACTORY_FORMULA, V2Scene.INFRA_MAIN)
        self.assertIsNotNone(path)
        self.assertEqual(
            [step.target for step in path],
            [
                V2Scene.FACTORY_DASHBOARD,
                V2Scene.FACTORY_ROOM,
                V2Scene.INFRA_MAIN,
            ],
        )


    def test_factory_detail_scene_taps_workshop_entry(self):
        self.executor._tasks = deque(["enter"])
        self.executor._dispatch_scene("INFRA_DETAILS_OPEN")
        self.assertEqual(self.device.calls[-1], ("tap", 0.1, 0.95))


    def test_factory_detail_scene_is_not_blocked_by_arrange_checkin(self):
        self.executor._tasks = deque(["enter"])
        scenes = ["INFRA_DETAILS_OPEN", "FACTORY_DASHBOARD"]
        arrange_visible = [False]
        self.executor._get_factory_scene = lambda: scenes.pop(0)
        self.executor._is_arrange_checkin_visible = lambda: arrange_visible.pop(0)
        with patch.object(WorkshopExecutor, "_refresh_jiuselu_gap", return_value=False):
            self.executor._process_workshop()
        self.assertEqual(self.device.calls[0], ("tap", 0.1, 0.95))

    def test_refresh_gap_reads_skill_number(self):
        with patch.object(WorkshopExecutor, "_read_number", return_value=32):
            self.assertTrue(self.executor._refresh_jiuselu_gap())
            self.assertEqual(self.executor._gap, WORKSHOP_JIUSE_SKILL_TARGET - 32)

    def test_formula_replay_selects_crit_material_near_gap(self):
        crit = WorkshopCandidate(CRIT_ITEM, CRIT_ITEM, ELITE_TAB, 4.0, object())
        small = WorkshopCandidate(DEVICE, DEVICE, ELITE_TAB, 2.0, object())
        self.executor._tasks = deque(["select", "process"])
        self.executor._active_tab = ELITE_TAB
        self.executor._active_candidates = {CRIT_ITEM: crit, DEVICE: small}
        self.executor._gap = 3
        box = [[370, 125], [570, 125], [570, 225], [370, 225]]
        scan_items = [
            FormulaScanItem(name=DEVICE, box=box, valid=True),
            FormulaScanItem(name=CRIT_ITEM, box=box, valid=True),
        ]
        with patch.object(
            workshop_support,
            "scan_formula_items",
            return_value=scan_items,
        ):
            self.executor._select_formula()
        self.assertEqual(self.executor._current_material, crit)
        self.assertEqual(self.executor._tasks[0], "process")
        self.assertEqual(self.device.calls[-1][0], "tap")


    def test_gap_far_switches_away_from_crit_material(self):
        self.executor._current_material = WorkshopCandidate(
            CRIT_ITEM,
            CRIT_ITEM,
            ELITE_TAB,
            4.0,
            object(),
        )
        self.executor._gap = 8
        self.executor._tasks = deque(["process"])
        with (
            patch.object(WorkshopExecutor, "_refresh_jiuselu_gap", return_value=True),
            patch.object(WorkshopExecutor, "_agent_mood", return_value=24),
        ):
            self.executor._process_current_material()
        self.assertEqual(self.executor._tasks[0], "select")
        self.assertIsNone(self.executor._current_material)

    def test_near_crit_low_mood_stops_without_producing(self):
        self.executor._current_material = WorkshopCandidate(
            CRIT_ITEM,
            CRIT_ITEM,
            ELITE_TAB,
            4.0,
            object(),
        )
        self.executor._gap = 3
        self.executor._tasks = deque(["process"])
        with (
            patch.object(WorkshopExecutor, "_refresh_jiuselu_gap", return_value=True),
            patch.object(WorkshopExecutor, "_agent_mood", return_value=3),
        ):
            self.executor._process_current_material()
        self.assertFalse(self.executor._tasks)
        self.assertNotIn(("tap", 0.88, 0.88), self.device.calls)

    def test_process_uses_add_buttons_then_produce_and_collect(self):
        with (
            patch.object(WorkshopExecutor, "_refresh_jiuselu_gap", return_value=True),
            patch.object(WorkshopExecutor, "_agent_mood", return_value=24),
            patch.object(WorkshopExecutor, "_has_factory_warning", return_value=False),
            patch.object(WorkshopExecutor, "_item_valid", return_value=True),
        ):
            self.executor._process_current_material()
            self.executor._process_current_material()
            self.executor._process_current_material()
        self.executor._collect_product()
        self.assertEqual(
            self.device.calls[:3],
            [("tap", 0.84, 0.4), ("tap", 0.84, 0.4), ("tap", 0.88, 0.88)],
        )
        self.assertIn(("back",), self.device.calls)
        self.assertIn("workshop", self.recognizer.saved)


class AgentSwapSortDetectionTest(unittest.TestCase):
    def _service_for_fixture(self, name: str) -> AgentSwapService:
        fixture = Path(__file__).with_name("fixtures") / name
        img = cv2.imread(str(fixture))
        self.assertIsNotNone(img, str(fixture))
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        device = SimpleNamespace(screencap=lambda: rgb)
        return AgentSwapService(
            device,
            SimpleNamespace(),
            lambda: V2Scene.RIIC_OPERATOR_SELECT,
            pause=SimpleNamespace(wait_if_paused=lambda: None),
        )

    def test_detects_dorm_heart_sort_down_from_device_screenshot(self):
        service = self._service_for_fixture("agent_sort_heart_down.jpg")
        self.assertEqual(service._detect_arrange("dormitory_1"), ("心情", False))

    def test_detects_dorm_heart_sort_up_from_device_screenshot(self):
        service = self._service_for_fixture("agent_sort_heart_up.jpg")
        self.assertEqual(service._detect_arrange("dormitory_1"), ("心情", True))


if __name__ == "__main__":
    unittest.main()
