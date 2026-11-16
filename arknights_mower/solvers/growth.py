"""Run supplied promotions/basic skills through MAA; Mower owns chips and crafting."""

import json
import time
from collections import Counter
from datetime import datetime, timedelta

from arknights_mower.solvers import record
from arknights_mower.utils import config
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.growth_execution import (
    candidates,
    finish_attempt,
    publish_progress,
    reject_attempt,
    save_attempt,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.manufacture_product import (
    DUALCHIP_PRODUCTS,
    MANUFACTURE_PRODUCTS,
    drone_plan,
)
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.solver import MowerExit


def _chip_state(value=None, *, clear=False):
    with record._conn() as conn:
        if clear:
            conn.execute("DELETE FROM growth_chip_restore")
        elif value is not None:
            conn.execute(
                "INSERT INTO growth_chip_restore (id, payload) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (json.dumps(value, ensure_ascii=False),),
            )
        else:
            row = conn.execute(
                "SELECT payload FROM growth_chip_restore WHERE id=1"
            ).fetchone()
            return json.loads(row[0]) if row else None
        conn.commit()


def restore_chip_product(solver):
    state = _chip_state()
    if state is None:
        return True
    solver._open_manufacture_product_detail(state["room"])
    try:
        current = solver.read_manufacture_product()
    except RecognizeError:
        current = None
    if current != state["original"]:
        if state.get("started") and not state.get("produced"):
            state["produced"] = _chip_output_complete(solver, state)
            _chip_state(state)
        solver._select_manufacture_product(state["original"])
        solver.recog.update()
        if solver.read_manufacture_product() != state["original"]:
            raise RecognizeError("双芯片制造后未确认恢复原产物")
    solver._cache_facility_state(state["room"], "manufacture", state["original"])
    with record._conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        delta = Counter(state.get("confirmed_delta", {}))
        if state.get("produced"):
            delta.update(state["delta"])
        record._apply_inventory_delta(conn, delta)
        if state["delta"] and not state.get("produced"):
            names = state["delta"]
            conn.executemany(
                "DELETE FROM inventory WHERE item_name=?", [(name,) for name in names]
            )
            record._mark_workshop_inventory(conn, names)
        conn.execute("DELETE FROM growth_chip_restore")
        conn.commit()
    record.workshop_inventory_changed.set()
    return not state["delta"] or state.get("produced", False)


def _chip_output_complete(solver, state):
    title = solver._product_ocr_text(((1500, 325), (1870, 460)))
    return (
        state["product_name"] in title and solver._read_manufacture_queue_count() == 0
    )


def manufacture_chips(solver, action, deadline):
    """Survey eligible manufacturing rooms, finish the nearest unit and borrow its line."""
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    skills = get_skill_data()
    rooms = set()
    for room, slots in solver.op_data.plan.items():
        if slots and slots[0].facility == "制造站":
            rooms.add(room)
    rooms.update(
        room
        for room, state in getattr(solver.op_data, "facility_states", {}).items()
        if state.get("facility") == "manufacture"
    )
    exhausted_rooms = {
        operator.current_room
        for operator in solver.op_data.operators.values()
        if solver.op_data.config.is_exhaust_require(operator.name)
    }
    eligible_rooms = rooms - exhausted_rooms or rooms
    observations = []
    for room in sorted(eligible_rooms):
        if datetime.now() >= deadline or config.stop_mower.is_set():
            return False
        try:
            observation = solver._survey_manufacture_switch(
                room, "growth_dualchip", growth_chip=True
            )
        except RecognizeError as error:
            logger.warning(
                "%s制造进度未确认：%s",
                room,
                error,
                extra={"log_group": "growth-planning"},
            )
            continue
        original = observation["current_product"]
        rate = observation.get("production_rate", 1)
        if observation.get("current_remaining", 0) and not observation.get(
            "production_rate_observed", False
        ):
            continue
        observation["growth_chip"] = True
        observation["drone_count"], observation["wait_seconds"] = drone_plan(
            observation["current_remaining"],
            MANUFACTURE_PRODUCTS[original].unit_seconds,
            30,
        )
        if observation["available_drones"] < observation["drone_count"]:
            continue
        ready = observation.get("observed_at", datetime.now()) + timedelta(
            seconds=observation["current_remaining"] / rate
        )
        observations.append((ready, room, observation))
    if not observations:
        return False
    _, room, observation = min(observations, key=lambda item: (item[0], item[1]))
    solver._execute_manufacture_acceleration(observation)
    remaining = observation.get("remaining_after_acceleration", 0)
    rate = observation.get("production_rate", 1)
    confirm_after = observation.get("accelerated_at", datetime.now()) + timedelta(
        seconds=remaining / rate
    )
    if confirm_after > deadline:
        return False
    state = {
        "room": room,
        "original": observation["current_product"],
        "confirmed_delta": {},
        "delta": {},
    }
    _chip_state(state)
    try:
        for iid, total in action["dual"].items():
            product = DUALCHIP_PRODUCTS[iid]
            group = skills["items"][iid[:-1] + "2"]["name"]
            catalyst = skills["items"]["32001"]["name"]
            while total:
                if (
                    config.stop_mower.is_set()
                    or not config.conf.maa_growth_enable
                    or datetime.now() >= deadline
                    or solver.find_next_task(datetime.now() + timedelta(seconds=30))
                    is not None
                ):
                    return False
                count = min(total, 99)
                state.update(
                    delta={product.name: count, group: -2 * count, catalyst: -count},
                    product_name=product.name,
                    started=False,
                    produced=False,
                )
                _chip_state(state)
                solver._select_manufacture_recipe(
                    product, count=count, confirm_after=confirm_after
                )
                state["started"] = True
                _chip_state(state)
                solver._open_manufacture_product_detail(room)
                if not _chip_output_complete(solver, state):
                    raise RecognizeError("双芯片制造结果未确认，请读取仓库")
                confirmed = Counter(state["confirmed_delta"])
                confirmed.update(state["delta"])
                state.update(confirmed_delta=dict(confirmed), delta={}, started=False)
                _chip_state(state)
                total -= count
                logger.info(
                    "已确认制造 %d 个%s",
                    count,
                    product.name,
                    extra={"log_group": "growth-planning"},
                )
    finally:
        restore_chip_product(solver)
    return True


def record_growth_callback(solver, message, payload, generation):
    run = getattr(solver, "maa_growth_run", None)
    if (
        not isinstance(run, dict)
        or run.get("finished")
        or generation is not run.get("generation")
        or generation is not getattr(solver, "_maa_activity_generation", None)
        or payload.get("taskchain") != "OperProgress"
        or type(payload.get("taskid")) is not int
        or payload["taskid"] != run.get("task_id")
    ):
        return
    detail = payload.get("details", {})
    if not isinstance(detail, dict):
        return
    action = run["action"]
    if message == 20001 and action["field"] == "evolvePhase":
        node = str(detail.get("task", "")).rsplit("@", 1)[-1]
        if node in ("CurrentElite0", "CurrentElite1", "CurrentElite2"):
            run.setdefault("initial_elite", int(node[-1]))
        return
    if message != 20003 or payload.get("what") != "OperProgressDetail":
        return
    field = "elite" if action["field"] == "evolvePhase" else "skill_level"
    if detail.get("name") != action["name"] or detail.get("role") != action["role"]:
        return
    if (
        detail.get("result") == "Success"
        and type(detail.get(field)) is int
        and detail[field] == action["target"]
    ):
        run["finished"] = True
        finish_attempt(
            action,
            success=True,
            already=detail.get("result_detail") == "AlreadySatisfied",
            payment_known=action["field"] != "evolvePhase"
            or run.get("initial_elite") == action.get("from_phase"),
        )
        publish_progress()
        run["success"] = True
        logger.info(
            "%s%s已完成",
            action["name"],
            f"精英化 {action['target']}"
            if field == "elite"
            else f"基础技能 {action['target']} 级",
            extra={"log_group": "growth-planning"},
        )
    elif detail.get("result") in ("Failed", "Skipped"):
        run["finished"] = True
        finish_attempt(action)
        logger.warning(
            "%s培养未确认，保留目标并等待新的库存或练度观测",
            action["name"],
            extra={"log_group": "growth-planning"},
        )


def _run_maa(solver, action, deadline):
    solver.maa_growth_run = None
    accepted = False
    try:
        solver.initialize_maa()
        field = "elite" if action["field"] == "evolvePhase" else "skill_level"
        params = {
            "plans": [
                {
                    "role": action["role"],
                    "name": action["name"],
                    field: action["target"],
                }
            ]
        }
        task_id = solver.MAA.append_task("OperProgress", params)
        run = {
            "action": action,
            "task_id": task_id,
            "generation": solver._maa_activity_generation,
            "finished": False,
        }
        solver.maa_growth_run = run
        save_attempt(action)
        accepted = True
        solver.MAA.start()
        budget = time.monotonic() + max(0, (deadline - datetime.now()).total_seconds())
        while solver.MAA.running():
            if (
                config.stop_mower.is_set()
                or config.stop_maa.is_set()
                or not config.conf.maa_growth_enable
                or solver.find_next_task(datetime.now() + timedelta(seconds=30))
                is not None
                or time.monotonic() >= budget
            ):
                solver.MAA.stop()
                break
            solver.sleep(0.5)
        return run.get("success", False)
    except (MowerExit, DeviceRecoveryError, SharedADBError):
        raise
    except Exception:
        if not accepted:
            reject_attempt(action)
        raise
    finally:
        try:
            if accepted and not solver.maa_growth_run["finished"]:
                finish_attempt(action)
        finally:
            solver.maa_growth_run = None
            try:
                if getattr(solver, "MAA", None) is not None:
                    solver.MAA.stop()
            finally:
                solver.release_maa()
                record.battle_inventory_active.clear()
                solver.recog.reset_after_external_control()


def purchase_catalyst(solver, action, deadline):
    """Run an exact-shortage Custom purchase before native chip manufacturing."""
    from arknights_mower.utils.maa_catalyst import (
        begin_purchase,
        cancel_purchase,
        entry_for_count,
        finish_purchase,
        task_quantity,
    )
    from arknights_mower.utils.scene import Scene

    if (
        config.stop_mower.is_set()
        or config.stop_maa.is_set()
        or not config.conf.maa_growth_enable
        or datetime.now() >= deadline
        or solver.find_next_task(datetime.now() + timedelta(seconds=30)) is not None
    ):
        return False
    count = action.get("catalyst_purchase", 1)
    token = begin_purchase(action["uid"], count)
    if token is None:
        return False
    accepted = False
    attempted = False
    run = {"token": token, "count": count, "confirmed": False}
    try:
        solver.scene_graph_navigation(Scene.SHOP_OTHERS)
        if (
            config.stop_mower.is_set()
            or config.stop_maa.is_set()
            or not config.conf.maa_growth_enable
            or datetime.now() >= deadline
            or solver.find_next_task(datetime.now() + timedelta(seconds=30)) is not None
        ):
            return False
        attempted = True
        with task_quantity(count):
            solver.initialize_maa()
        task_id = solver.MAA.append_task(
            "Custom", {"task_names": [entry_for_count(count)]}
        )
        run.update(task_id=task_id, generation=solver._maa_activity_generation)
        solver.maa_catalyst_run = run
        accepted = True
        solver.MAA.start()
        budget = time.monotonic() + max(0, (deadline - datetime.now()).total_seconds())
        while solver.MAA.running():
            if (
                config.stop_mower.is_set()
                or config.stop_maa.is_set()
                or not config.conf.maa_growth_enable
                or solver.find_next_task(datetime.now() + timedelta(seconds=30))
                is not None
                or time.monotonic() >= budget
            ):
                solver.MAA.stop()
                break
            solver.sleep(0.5)
        if run["confirmed"]:
            logger.info(
                "已兑换%d个芯片助剂，扣除%d采购凭证",
                count,
                90 * count,
                extra={"log_group": "growth-planning"},
            )
        else:
            logger.warning(
                "芯片助剂兑换未确认，保留养成目标并等待新库存观测",
                extra={"log_group": "growth-planning"},
            )
        return run["confirmed"]
    finally:
        try:
            if not attempted:
                cancel_purchase(token)
            elif not run["confirmed"]:
                finish_purchase(token, accepted=accepted)
        finally:
            solver.maa_catalyst_run = None
            try:
                if getattr(solver, "MAA", None) is not None:
                    solver.MAA.stop()
            finally:
                solver.release_maa()
                record.battle_inventory_active.clear()
                solver.recog.reset_after_external_control()


def run_growth(solver):
    """Consume existing idle windows without adding retries, waits or task timestamps."""
    if getattr(solver, "MAA", None) is not None or config.stop_mower.is_set():
        return
    if not config.conf.maa_growth_enable and _chip_state() is None:
        return
    if solver.find_next_task(datetime.now() + timedelta(minutes=5)) is not None:
        return
    try:
        restore_chip_product(solver)
        if not config.conf.maa_growth_enable:
            return
        from arknights_mower.utils.growth_execution import recover_attempts
        from arknights_mower.utils.maa_catalyst import recover_purchase

        recover_attempts()
        recover_purchase()
        publish_progress()
        from arknights_mower.utils.growth import load_goals
        from arknights_mower.utils.mastery_db import get_all_plans
        from arknights_mower.utils.mastery_recommendation import (
            get_cultivate_snapshot,
            get_skill_data,
        )

        progressed = False
        for _ in range(8):
            if (
                solver.find_next_task(datetime.now() + timedelta(minutes=5)) is not None
                or config.stop_mower.is_set()
                or not config.conf.maa_growth_enable
            ):
                break
            snapshot = get_cultivate_snapshot()
            if snapshot is None:
                return
            ready = list(
                candidates(
                    snapshot,
                    get_skill_data(),
                    get_all_plans(),
                    load_goals(),
                    config.conf.growth_crafting_order,
                    record.get_inventory_counts(),
                    cumulative=True,
                )
            )
            if not ready:
                break
            action = ready[0]
            catalyst_purchase = sum(item.get("catalyst_purchase", 0) for item in ready)
            next_task = solver.find_next_task()
            deadline = (
                min(
                    datetime.now() + timedelta(minutes=5),
                    next_task.time - timedelta(seconds=30),
                )
                if next_task
                else datetime.now() + timedelta(minutes=5)
            )
            if catalyst_purchase:
                from arknights_mower.utils.maa_catalyst import MAX_PURCHASE

                purchase = {
                    **action,
                    "catalyst_purchase": min(catalyst_purchase, MAX_PURCHASE),
                }
                if not purchase_catalyst(solver, purchase, deadline):
                    return
                continue
            dual = Counter()
            for item in ready:
                dual.update(item["dual"])
            if dual:
                if not manufacture_chips(solver, {"dual": dict(dual)}, deadline):
                    return
                continue
            progressed = _run_maa(solver, action, deadline) or progressed
        if progressed:
            solver._auto_schedule_mastery_after_scan()
    except (MowerExit, DeviceRecoveryError, SharedADBError):
        raise
    except Exception:
        logger.exception(
            "MAA 干员培养未完成，保留养成目标", extra={"log_group": "growth-planning"}
        )
