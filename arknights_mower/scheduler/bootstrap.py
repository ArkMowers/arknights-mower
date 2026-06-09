from __future__ import annotations

from datetime import datetime
from typing import Optional

from arknights_mower.scheduler.constants import StartMode
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.scheduler.dispatch import TaskDispatch
from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.errors import ConfigError, DeviceError
from arknights_mower.scheduler.infra import InfraKit
from arknights_mower.scheduler.infra.pause_controller import PauseController
from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController
from arknights_mower.scheduler.loop import MainLoop
from arknights_mower.scheduler.state import SchedulerState
from arknights_mower.utils.log import logger


def _create_device():
    from arknights_mower.utils.device.device import Device

    return Device()


def _build_infra(v1_device, state) -> InfraKit:
    from arknights_mower.scheduler.infra.pc_device_port import PCDevicePort

    device = PCDevicePort(v1_device)

    from arknights_mower.scheduler.graph import build_default_graph
    from arknights_mower.scheduler.infra.agent_selection import AgentSelection
    from arknights_mower.scheduler.navigator import Navigator
    from arknights_mower.utils.recognize import Scene, Recognizer

    recognizer = Recognizer(v1_device)
    graph = build_default_graph()

    def get_scene() -> Scene:
        recognizer.update()
        return recognizer.get_scene()

    navigator = Navigator(device, graph, get_scene, recognizer)
    agent_selector = AgentSelection.create(device, recognizer)

    return InfraKit(
        device=device,
        state=state,
        navigator=navigator,
        agent_selector=agent_selector,
    )


def _build_planners(state: SchedulerState) -> list:
    planners = []

    from arknights_mower.scheduler.planners.workshop import WorkshopPlanner
    # from arknights_mower.scheduler.planners.infra_scan import InfraScanPlanner

    planners.append(WorkshopPlanner())
    # planners.append(InfraScanPlanner())

    return planners


def _build_dispatch() -> TaskDispatch:
    dispatch = TaskDispatch()

    from arknights_mower.scheduler.executors.run_order import RunOrderExecutor
    from arknights_mower.scheduler.executors.shift import ShiftExecutor
    from arknights_mower.scheduler.executors.exhaust import ExhaustExecutor
    from arknights_mower.scheduler.executors.fiammetta import FiammettaExecutor
    from arknights_mower.scheduler.executors.clue import ClueExecutor
    from arknights_mower.scheduler.executors.correction import CorrectionExecutor
    from arknights_mower.scheduler.executors.skill import SkillExecutor
    from arknights_mower.scheduler.executors.workshop import WorkshopExecutor
    from arknights_mower.scheduler.executors.infra_scan import InfraScanExecutor

    dispatch.register(TaskTypes.INFRA_SCAN, InfraScanExecutor)
    dispatch.register(TaskTypes.RUN_ORDER, RunOrderExecutor)
    dispatch.register(TaskTypes.SHIFT_OFF, ShiftExecutor)
    dispatch.register(TaskTypes.SHIFT_ON, ShiftExecutor)
    dispatch.register(TaskTypes.EXHAUST_OFF, ExhaustExecutor)
    dispatch.register(TaskTypes.FIAMMETTA, FiammettaExecutor)
    dispatch.register(TaskTypes.CLUE_PARTY, ClueExecutor)
    dispatch.register(TaskTypes.SELF_CORRECTION, CorrectionExecutor)
    dispatch.register(TaskTypes.SKILL_UPGRADE, SkillExecutor)
    dispatch.register(TaskTypes.WORKSHOP, WorkshopExecutor)
    dispatch.register(TaskTypes.RELEASE_DORM, ShiftExecutor)
    dispatch.register(TaskTypes.RE_ORDER, ShiftExecutor)

    return dispatch


def run(
    pause: Optional[PauseController] = None,
    start_type: str = StartMode.FULL.value,
) -> None:
    pause = pause or ThreadPauseController()

    logger.info("building global plan")
    from arknights_mower.utils.operators import build_global_plan

    global_plan = build_global_plan()

    logger.info("initializing state")
    try:
        state = SchedulerState(global_plan=global_plan)
    except ConfigError as e:
        logger.error(f"config error: {e}")
        return

    from arknights_mower.scheduler.database.repositories.state import StateRepository
    from arknights_mower.scheduler.database.sqlite_storage import SQLiteStorage

    repo = StateRepository(SQLiteStorage())

    if start_type != StartMode.CLEAN.value:
        snapshot = repo.load("operator_mood")
        if snapshot:
            state.restore_snapshot(snapshot)
            logger.info(f"restored {len(snapshot)} operator snapshots from db")
        tasks = repo.load("tasks")
        if tasks and start_type == StartMode.FULL.value:
            state.restore_tasks(tasks)
            logger.info(f"restored {len(tasks)} pending tasks from db")
    else:
        logger.info("clean start: skipping snapshot restore")

    if start_type == StartMode.MOOD_ONLY.value:
        state.task_queue.clear()
        logger.info("mood only: tasks cleared")

    # test: arrange room_1_1
    state.task_queue.push(SchedulerTask(
        time=datetime.now(),
        type=TaskTypes.SHIFT_ON,
        plan={"room_1_1": ["Current", "能天使", "空爆"]},
    ))
    
    logger.info("test: pushed SHIFT_ON for room_1_1")
    logger.info("initializing device")
    v1_device = _create_device()
    infra = _build_infra(v1_device, state)

    logger.info("registering planners")
    planners = _build_planners(state)

    logger.info("registering executors")
    dispatch = _build_dispatch()

    logger.info("starting main loop")
    loop = MainLoop(state, planners, dispatch, infra)
    try:
        loop.run_forever()
    except DeviceError:
        logger.warning("device error in main loop, reconnecting...")
        infra.device.reconnect()
        loop.run_forever()
    finally:
        snapshot = state.save_snapshot()
        if snapshot:
            repo.save("operator_mood", snapshot)
            logger.info(f"saved {len(snapshot)} operator snapshots on stop")
        tasks = state.save_tasks()
        if tasks:
            repo.save("tasks", tasks)
            logger.info(f"saved {len(tasks)} pending tasks on stop")
