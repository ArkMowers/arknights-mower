from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from arknights_mower.scheduler.constants import (
    WORKSHOP_ADD_BUTTON_POS,
    WORKSHOP_AGENT_JIUSE,
    WORKSHOP_ARRANGE_CHECK_IN_POS,
    WORKSHOP_FORMULA_BUTTON_POS,
    WORKSHOP_MAX_BUTTON_POS,
    WORKSHOP_PRODUCE_BUTTON_POS,
    WORKSHOP_ROOM_ENTRY_POS,
    WORKSHOP_UNKNOWN_RETRY_LIMIT,
    CURRENT,
)
from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor
from arknights_mower.scheduler.executors.workshop_support import (
    WorkshopExecutorSupportMixin,
)
from arknights_mower.scheduler.services.workshop_service import (
    WorkshopCandidate,
    WorkshopProductionPlan,
    build_workshop_candidates,
    jiuselu_should_switch_candidate,
    make_jiuselu_production_plan,
)
from arknights_mower.utils.log import logger


class WorkshopExecutor(WorkshopExecutorSupportMixin, AbstractExecutor):
    MAX_DURATION = timedelta(minutes=5)

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._agent = ""
        self._is_9colored = False
        self._tab_queue: deque[tuple[str, dict[str, WorkshopCandidate]]] = deque()
        self._all_tabs: list[tuple[str, dict[str, WorkshopCandidate]]] = []
        self._tasks: deque[str] = deque()
        self._current_material: WorkshopCandidate | None = None
        self._production_plan: WorkshopProductionPlan | None = None
        self._remaining_add_taps = 0
        self._max_tapped = False
        self._waiting_collect = False
        self._active_tab: str | None = None
        self._active_candidates: dict[str, WorkshopCandidate] = {}
        self._last_scan: list[str] = []
        self._gap = 0
        self._restore_plan: dict[str, list[str]] = {}

    def execute(self, task: SchedulerTask) -> None:
        self._agent = task.meta_data
        self._is_9colored = self._agent == WORKSHOP_AGENT_JIUSE
        self._reset_runtime()

        from arknights_mower.scheduler.scene import Scene as V2Scene

        self._navigate(V2Scene.INFRA_MAIN)
        self._gather_inventory()
        self._arrange_workshop_agent()
        try:
            self._tasks = deque(["enter", "select", "process"])
            self._process_workshop()
        finally:
            self._restore_previous_agent()

    def _reset_runtime(self) -> None:
        self._current_material = None
        self._production_plan = None
        self._remaining_add_taps = 0
        self._max_tapped = False
        self._waiting_collect = False
        self._active_tab = None
        self._active_candidates = {}
        self._last_scan = []
        self._gap = 0
        self._restore_plan = {}

    def _arrange_workshop_agent(self) -> None:
        current_agents = self._current_workshop_agents()
        agent_location = self._agent_location(self._agent)
        self._restore_plan = self._build_restore_plan(current_agents, agent_location)
        self._run_arrange({"factory": [self._agent]})

    def _restore_previous_agent(self) -> None:
        if self._restore_plan:
            self._run_arrange(self._restore_plan)

    def _current_workshop_agents(self) -> list[str]:
        state = getattr(self.infra, "state", None)
        operators = getattr(state, "operators", {}) if state is not None else {}
        indexed: list[tuple[int, str]] = []
        fallback: list[str] = []
        for name, operator in operators.items():
            if getattr(operator, "current_room", "") != "factory":
                continue
            index = getattr(operator, "current_index", -1)
            if index >= 0:
                indexed.append((index, name))
            else:
                fallback.append(name)
        return [name for _, name in sorted(indexed)] + fallback

    def _agent_location(self, agent: str) -> tuple[str, int]:
        operator = self._agent_operator(agent)
        if operator is None:
            return "", -1
        return (getattr(operator, "current_room", ""), getattr(operator, "current_index", -1))

    def _build_restore_plan(
        self,
        previous_factory_agents: list[str],
        agent_location: tuple[str, int],
    ) -> dict[str, list[str]]:
        plan: dict[str, list[str]] = {}
        if previous_factory_agents and previous_factory_agents[0] != self._agent:
            plan["factory"] = previous_factory_agents
        room, index = agent_location
        state = getattr(self.infra, "state", None)
        state_plan = getattr(state, "plan", {}) if state is not None else {}
        if room and room != "factory" and index >= 0 and room in state_plan:
            restored_room = [CURRENT] * len(state_plan[room])
            if index < len(restored_room):
                restored_room[index] = self._agent
                plan[room] = restored_room
        return plan

    def _run_arrange(self, plan: dict[str, list[str]]) -> None:
        if not plan:
            return
        from arknights_mower.scheduler.domain.task import TaskTypes
        from arknights_mower.scheduler.executors.shift import ShiftExecutor

        task = SchedulerTask(
            time=datetime.now(),
            type=TaskTypes.SHIFT_ON,
            plan=plan,
        )
        ShiftExecutor(self.infra).execute(task)

    def _navigate(self, target) -> None:
        self.infra.navigator.navigate(target)

    def _gather_inventory(self) -> None:
        group = build_workshop_candidates(self._agent, is_jiuselu=self._is_9colored)
        self._all_tabs = list(group.items())
        self._tab_queue = deque(self._all_tabs)

    def _process_workshop(self) -> None:
        start = datetime.now()
        unknown_cnt = 0
        while self._tasks:
            self.guard()
            if datetime.now() - start > self.MAX_DURATION:
                raise TimeoutError("workshop processing timed out")
            scene = self._get_factory_scene()
            if scene in ("FACTORY_ROOM", "INFRA_DETAILS", "INFRA_DETAILS_OPEN"):
                self._dispatch_scene(scene)
                continue
            if self._is_arrange_checkin_visible():
                self.infra.device.tap(*WORKSHOP_ARRANGE_CHECK_IN_POS)
                continue
            if scene == "UNKNOWN":
                unknown_cnt += 1
                if unknown_cnt > WORKSHOP_UNKNOWN_RETRY_LIMIT:
                    self._navigate_infra()
                    unknown_cnt = 0
                continue
            unknown_cnt = 0
            self._dispatch_scene(scene)

    def _dispatch_scene(self, scene: str) -> None:
        if scene == "CONNECTING":
            return
        if scene == "FACTORY_DASHBOARD":
            self._handle_dashboard()
        elif scene == "FACTORY_FORMULA":
            self._handle_formula()
        elif scene == "FACTORY_PRODUCT_COLLECT":
            self._collect_product()
        elif scene in ("FACTORY_ROOM", "INFRA_DETAILS", "INFRA_DETAILS_OPEN"):
            self.infra.device.tap(*WORKSHOP_ROOM_ENTRY_POS)
        elif scene == "INFRA_MAIN":
            self.infra.navigator.enter_room("factory")
        else:
            self._tasks.clear()

    def _handle_dashboard(self) -> None:
        step = self._tasks[0]
        if step == "enter":
            if self._is_9colored and not self._refresh_jiuselu_gap():
                self._tasks.clear()
                return
            self._tasks.popleft()
            return
        if step == "select":
            if not self._tab_queue and self._active_tab is None:
                logger.info("no workshop material candidates")
                self._tasks.clear()
                return
            self.infra.device.tap(*WORKSHOP_FORMULA_BUTTON_POS)
            return
        if step == "process":
            self._process_current_material()

    def _handle_formula(self) -> None:
        if self._tasks[0] != "select":
            self.infra.device.back()
            return
        self._select_formula()

    def _process_current_material(self) -> None:
        if self._current_material is None:
            self._request_reselect()
            return
        if self._is_9colored and not self._can_continue_jiuselu_material():
            return
        if self._waiting_collect:
            return
        if self._production_plan is None and not self._prepare_production_plan():
            self._tasks.clear()
            return
        if self._tap_quantity_button():
            return
        if self._has_factory_warning() or not self._item_valid():
            self._handle_unavailable_material()
            return
        self.infra.device.tap(*WORKSHOP_PRODUCE_BUTTON_POS)
        self._waiting_collect = True

    def _can_continue_jiuselu_material(self) -> bool:
        if not self._refresh_jiuselu_gap():
            self._tasks.clear()
            return False
        if jiuselu_should_switch_candidate(
            self._current_material,
            self._gap,
            self._agent_mood(),
        ):
            logger.info("jiuselu switches workshop material for gap=%s", self._gap)
            self._request_reselect()
            return False
        return True

    def _tap_quantity_button(self) -> bool:
        use_max = self._production_plan and self._production_plan.use_max
        if use_max and not self._max_tapped:
            self.infra.device.tap(*WORKSHOP_MAX_BUTTON_POS)
            self._max_tapped = True
            return True
        if self._remaining_add_taps > 0:
            self.infra.device.tap(*WORKSHOP_ADD_BUTTON_POS)
            self._remaining_add_taps -= 1
            return True
        return False

    def _handle_unavailable_material(self) -> None:
        if not self._has_factory_warning():
            logger.info("current workshop material exhausted; reselect")
            self._request_reselect()
            return
        logger.info("workshop stopped because mood or material is insufficient")
        self._mark_agent_exhausted()
        self._tasks.clear()

    def _prepare_production_plan(self) -> bool:
        assert self._current_material is not None
        if self._is_9colored:
            plan = make_jiuselu_production_plan(
                gap=self._gap,
                mood=self._agent_mood(),
                ap_cost=self._current_material.ap_cost,
            )
            if plan is None:
                logger.info(
                    "jiuselu mood is insufficient for workshop gap=%s",
                    self._gap,
                )
                return False
        else:
            plan = WorkshopProductionPlan(use_max=True, estimated_mood_cost=0)
        self._production_plan = plan
        self._remaining_add_taps = plan.add_taps
        self._max_tapped = False
        return True

    def _request_reselect(self) -> None:
        self._current_material = None
        self._production_plan = None
        self._remaining_add_taps = 0
        self._max_tapped = False
        self._waiting_collect = False
        self._active_tab = None
        self._active_candidates = {}
        self._last_scan = []
        self._tab_queue = deque(self._all_tabs)
        if not self._tasks or self._tasks[0] != "select":
            self._tasks.appendleft("select")
