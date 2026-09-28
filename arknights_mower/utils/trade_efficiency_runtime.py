"""贸易站效率自检与两阶段原生排班纠偏；不在跑单和其他任务中途进入房间。"""

from datetime import datetime, timedelta

from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.log import logger
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.trade_efficiency import (
    EXPECTED_LOSS,
    OCR_TOLERANCE,
    PAIR,
    canonical_key,
    configured_rule,
    decide,
    key_for,
    load_history,
    migrate_reference,
    monitored_rooms,
    parse_bonus,
    save_history,
)


def _preserve_other_slots(roster):
    """非绮良、鸿雪位置使用原生 Current，不覆盖伺夜／吉星等正常轮班。"""
    return [name if name in PAIR else "Current" for name in roster]


def _swap_pair(roster):
    swapped = list(roster)
    first, second = swapped.index("绮良"), swapped.index("鸿雪")
    swapped[first], swapped[second] = swapped[second], swapped[first]
    return _preserve_other_slots(swapped)


def _queue_swap(solver, repair):
    room = repair["room"]
    repair["stage"] = "swap_pending"
    repair["recovery_attempts"] = 0
    _persist_repair(repair)
    solver.tasks.append(
        SchedulerTask(
            time=datetime.now(),
            task_plan={room: _swap_pair(repair["original"])},
            task_type=TaskTypes.RE_ORDER,
            meta_data=f"trade-efficiency-swap:{room}",
        )
    )
    solver.tasks.sort(key=lambda task: task.time)


def _persist_repair(repair):
    history = load_history()
    history["_active_repair"] = repair
    save_history(history)


def _recover_missing_task(solver, repair):
    """真实调度任务因重试失败消失时，只补发一次恢复原顺序的任务。"""
    room = repair["room"]
    expected_meta = f"trade-efficiency-{'swap' if repair['stage'] == 'swap_pending' else 'restore'}:{room}"
    if any(getattr(task, "meta_data", "") == expected_meta for task in solver.tasks):
        return
    if repair.get("recovery_attempts", 0) >= 1:
        history = load_history()
        history.setdefault(canonical_key(repair["key"]) or repair["key"], {})[
            "unresolved"
        ] = True
        history.pop("_active_repair", None)
        save_history(history)
        solver._trade_efficiency_repair = None
        solver._trade_efficiency_pending.pop(room, None)
        logger.error(
            "效率纠偏：%s 原顺序恢复失败，请人工确认房间人员，已停止自动重试", room
        )
        return
    repair["recovery_attempts"] = 1
    repair["stage"] = "restore_pending"
    _persist_repair(repair)
    solver.tasks.append(
        SchedulerTask(
            time=datetime.now(),
            task_plan={room: _preserve_other_slots(repair["original"])},
            task_type=TaskTypes.RE_ORDER,
            meta_data=f"trade-efficiency-restore:{room}",
        )
    )
    solver.tasks.sort(key=lambda task: task.time)
    logger.warning("效率纠偏：%s 检测到中断，只补发一次原顺序恢复任务", room)


def mark_changed(solver, changed_room: str):
    """任何实际换班确认后标记本设施及关联设施；不立刻打断当前任务。"""
    rules = getattr(config.conf, "trade_efficiency_rules", ())
    for room in monitored_rooms(rules, changed_room):
        repair = getattr(solver, "_trade_efficiency_repair", None)
        if repair and repair["room"] == room:
            continue
        if not hasattr(solver, "_trade_efficiency_pending"):
            solver._trade_efficiency_pending = {}
        solver._trade_efficiency_pending[room] = datetime.now()


def initialize_pending(solver):
    if hasattr(solver, "_trade_efficiency_initialized"):
        return
    solver._trade_efficiency_initialized = True
    if not hasattr(solver, "_trade_efficiency_pending"):
        solver._trade_efficiency_pending = {}
    if not hasattr(solver, "_trade_efficiency_repair"):
        solver._trade_efficiency_repair = None
    active = load_history().get("_active_repair")
    if isinstance(active, dict) and active.get("room") and active.get("original"):
        solver._trade_efficiency_repair = active
    for rule in getattr(config.conf, "trade_efficiency_rules", ()):
        if rule.enabled and rule.room:
            solver._trade_efficiency_pending.setdefault(rule.room, datetime.now())


def on_arrangement_completed(solver, room: str):
    """原生换人任务确认成功后续上恢复阶段，不把纠偏当作普通换班递归检查。"""
    task = getattr(solver, "task", None)
    meta = getattr(task, "meta_data", "") or ""
    repair = getattr(solver, "_trade_efficiency_repair", None)
    if repair and room == repair["room"]:
        if (
            meta == f"trade-efficiency-swap:{room}"
            and repair["stage"] == "swap_pending"
        ):
            repair["stage"] = "restore_pending"
            _persist_repair(repair)
            solver.tasks.append(
                SchedulerTask(
                    time=datetime.now() + timedelta(seconds=1),
                    task_plan={room: _preserve_other_slots(repair["original"])},
                    task_type=TaskTypes.RE_ORDER,
                    meta_data=f"trade-efficiency-restore:{room}",
                )
            )
            solver.tasks.sort(key=lambda task: task.time)
            logger.debug("效率纠偏：%s 首次重排成功，已安排恢复原顺序", room)
            return
        if (
            meta == f"trade-efficiency-restore:{room}"
            and repair["stage"] == "restore_pending"
        ):
            repair["stage"] = "read_pending"
            _persist_repair(repair)
            solver._trade_efficiency_pending[room] = datetime.now()
            logger.debug("效率纠偏：%s 已恢复原顺序，等待复核", room)
            return
    mark_changed(solver, room)


def _ocr_value(result):
    """仅从 OCR 文本字段取值，忽略坐标；拒绝低置信度和多候选数字。"""
    if not isinstance(result, (list, tuple)):
        return parse_bonus(result) if isinstance(result, str) else None
    readings = []
    for item in result:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            # RapidOCR with use_det=False returns [text, confidence]; detection
            # enabled returns [box, text, confidence]. Both are supported.
            if isinstance(item[0], str):
                text, score = item[0], item[1]
            elif len(item) >= 3 and isinstance(item[1], str):
                text, score = item[1], item[2]
            else:
                continue
            if isinstance(score, (int, float)) and score < 0.55:
                continue
            candidate = parse_bonus(text)
            if candidate is not None:
                readings.append(candidate)
        elif isinstance(item, str):
            candidate = parse_bonus(item)
            if candidate is not None:
                readings.append(candidate)
    return readings[0] if len(readings) == 1 else None


def _read_efficiency(solver):
    """仅识别贸易站蓝色加成块，连续两张截图数值一致才采信。"""
    from arknights_mower.utils.image import cropimg

    if rapidocr.engine is None:
        rapidocr.initialize_ocr()
    w, h = solver.recog.w, solver.recog.h
    # 实机 1920×1080 B101 截图：蓝色小块为 +117%，右侧是绿色趋势箭头。
    scope = (
        (w * 1290 // 1920, h * 955 // 1080),
        (w * 1430 // 1920, h * 1030 // 1080),
    )
    samples = []
    for _ in range(2):
        solver.recog.update()
        output = rapidocr.engine(
            cropimg(solver.recog.img, scope),
            use_det=False,
            use_cls=False,
            use_rec=True,
        )
        value = _ocr_value(output[0] if isinstance(output, (list, tuple)) else output)
        if value is None:
            return None
        samples.append(value)
        solver.sleep(0.3)
    if abs(samples[0] - samples[1]) > 0.6:
        return None
    return {"blue": samples[0], "total": None}


def _snapshot(solver, rule):
    """只在非任务间隙读取实际房间；实际成员为主，不依赖计划意图。"""
    from arknights_mower.utils.recognize import Scene

    room = rule.room
    room_plan = solver.op_data.plan.get(room) or []
    if not room_plan or getattr(room_plan[0], "facility", "") != "贸易站":
        return None
    solver.scene_graph_navigation(Scene.INFRA_MAIN)
    solver.enter_room(room)
    solver._wait_drone_interface(
        interval=3, accelerate_template="bill_accelerate", page_template="order_label"
    )
    value = _read_efficiency(solver)
    if value is None:
        logger.warning("效率自检：%s 蓝色加成 OCR 两次读数无法核对，跳过", room)
        solver.scene_graph_navigation(Scene.INFRA_MAIN)
        return None
    logger.debug(
        "贸易站效率自检：%s 蓝色加成 OCR 读取 %s%%（两次一致）",
        room,
        f"{value['blue']:g}",
    )
    actual = solver.get_agent_from_room(room)
    roster = [x.get("agent", "") for x in actual]
    related = {}
    for related_room in rule.related_rooms:
        related[related_room] = (
            solver.op_data.get_current_room(related_room, True) or []
        )
    product = solver.op_data.facility_states.get(room, {}).get("product", "")
    solver.scene_graph_navigation(Scene.INFRA_MAIN)
    if len(roster) != len(room_plan) or not PAIR.issubset(roster):
        return None
    # 已读到的顺序用于先交换再恢复，首位保留原人的身份；不修改持久化排班表。
    return {
        "room": room,
        "roster": roster,
        "percent": value["blue"],
        "total_percent": value["total"],
        "key": key_for(room, roster, product, related),
    }


def _complete(solver, repair, snapshot, history):
    room = repair["room"]
    context = canonical_key(repair["key"]) or repair["key"]
    record = history.setdefault(context, {})
    value = (
        (
            snapshot.get("total_percent")
            if repair["metric"] == "total"
            else snapshot["percent"]
        )
        if snapshot and canonical_key(snapshot["key"]) == context
        else None
    )
    before = repair["before"]
    initial_before = repair.get("initial_before", before)
    attempt = int(repair.get("attempt", 1))
    retry_limit = max(1, min(5, int(repair.get("retry_limit", 2))))
    regression = False

    if value is not None and abs((value - before) - EXPECTED_LOSS) <= OCR_TOLERANCE:
        record["verified_baseline"] = max(record.get("verified_baseline", value), value)
        record["unresolved"] = False
        logger.info(
            "贸易站效率纠偏：%s %g%% → %g%%（已恢复，%d/%d）",
            room,
            initial_before,
            value,
            attempt,
            retry_limit,
        )
    elif (
        value is not None
        and repair["kind"] == "calibrate"
        and abs((before - value) - EXPECTED_LOSS) <= OCR_TOLERANCE
    ):
        # Calibration itself can trigger the random bug. Preserve the higher
        # pre-calibration efficiency; the next idle audit will enter normal repair.
        record["verified_baseline"] = max(
            record.get("verified_baseline", before), before
        )
        record["unresolved"] = False
        regression = True
        logger.warning(
            "贸易站效率校准：%s %g%% → %g%%（疑似触发20%%异常，转入纠偏）",
            room,
            before,
            value,
        )
    elif (
        value is not None
        and repair["kind"] == "calibrate"
        and abs(value - before) <= OCR_TOLERANCE
    ):
        record["provisional_baseline"] = max(
            record.get("provisional_baseline", value), value
        )
        record["unresolved"] = False
        logger.info("贸易站效率自检：%s %g%%（候选基准，继续观察）", room, value)
    elif repair["kind"] == "repair" and value is not None and attempt < retry_limit:
        # The random-order bug can survive one round-trip. Retry only within this
        # user-defined bounded cycle; every new future trigger starts a fresh cycle.
        repair["attempt"] = attempt + 1
        repair["before"] = value
        repair["initial_before"] = initial_before
        history["_active_repair"] = repair
        save_history(history)
        solver._trade_efficiency_repair = repair
        solver._trade_efficiency_pending.pop(room, None)
        _queue_swap(solver, repair)
        logger.info(
            "贸易站效率纠偏：%s %g%% → %g%%（未恢复，重试 %d/%d）",
            room,
            initial_before,
            value,
            repair["attempt"],
            retry_limit,
        )
        return
    else:
        # Do not poison the verified baseline after a bounded failure. Clear only
        # this cycle so the next run-order/charging/arrangement trigger may try again.
        record["unresolved"] = False
        if repair["kind"] == "repair":
            if value is None:
                logger.warning(
                    "贸易站效率纠偏：%s %g%% → 识别失败（本轮结束，等待下次触发）",
                    room,
                    initial_before,
                )
            else:
                logger.warning(
                    "贸易站效率纠偏：%s %g%% → %g%%（未恢复，已达 %d/%d，本轮结束）",
                    room,
                    initial_before,
                    value,
                    attempt,
                    retry_limit,
                )
        else:
            logger.warning(
                "贸易站效率校准：%s 初始 %g%%，复核 %s（未确认，本轮结束）",
                room,
                before,
                value,
            )

    history.pop("_active_repair", None)
    save_history(history)
    solver._trade_efficiency_repair = None
    if regression:
        solver._trade_efficiency_pending[room] = datetime.now()
    else:
        solver._trade_efficiency_pending.pop(room, None)


def audit_when_idle(solver):
    """只在所有正常任务完成且两分钟内没有新任务时审查；单次至多处理一站。"""
    # Before checking whether the feature is disabled, load any interrupted
    # repair from disk: a disabled rule must never strand a swapped roster.
    initialize_pending(solver)
    rules = getattr(config.conf, "trade_efficiency_rules", ())
    if not rules and not solver._trade_efficiency_repair:
        return
    pending = solver._trade_efficiency_pending
    repair = solver._trade_efficiency_repair
    if not pending and repair is None:
        return
    if not solver.no_pending_task(2):
        return
    if repair is not None and repair["stage"] in ("swap_pending", "restore_pending"):
        _recover_missing_task(solver, repair)
        return
    room = repair["room"] if repair else next(iter(pending))
    rule = (
        next((item for item in rules if item.room == room), None)
        if repair is not None
        else configured_rule(rules, room)
    )
    if rule is None and repair is not None:
        _complete(solver, repair, None, load_history())
        return
    if rule is None:
        pending.pop(room, None)
        return
    snapshot = None
    try:
        snapshot = _snapshot(solver, rule)
    except Exception as exc:
        from arknights_mower.utils.csleep import MowerExit

        if isinstance(exc, MowerExit):
            raise
        logger.warning("效率自检：%s 识别失败：%s", room, exc)
        try:
            from arknights_mower.utils.recognize import Scene

            solver.scene_graph_navigation(Scene.INFRA_MAIN)
        except Exception:
            logger.debug("效率自检退出房间失败，交回原调度导航", exc_info=True)
    if repair is not None:
        history = load_history()
        _complete(solver, repair, snapshot, history)
        return
    pending.pop(room, None)
    if snapshot is None:
        return
    history = load_history()
    context = snapshot["key"]
    if rule.baseline_mode == "auto" and migrate_reference(history, context):
        save_history(history)
        logger.debug("贸易站效率自检：%s 已继承已验证的原阵容基准", room)
    # 自动和手动基准均只比较蓝色加成。
    metric = "blue"
    observed = snapshot["percent"]
    if rule.baseline_mode == "manual":
        bindings = history.setdefault("_manual_binding", {})
        bound = bindings.get(room)
        if not bound or (
            isinstance(bound, dict) and bound.get("percent") != rule.manual_percent
        ):
            bindings[room] = {"key": context, "percent": rule.manual_percent}
            history.pop(context, None)
            save_history(history)
    kind = decide(rule, context, observed, history)
    retry_limit = max(1, min(5, int(getattr(rule, "retry_limit", 2))))
    labels = {
        "normal": "符合预期",
        "provisional": "候选基准，继续观察",
        "repair": f"疑似缺失20%，开始纠偏 1/{retry_limit}",
        "calibrate": "首次校准",
        "uncertain": "偏差未确认，跳过",
        "observe": "仅记录",
    }
    logger.info(
        "贸易站效率自检：%s %g%%（%s）",
        room,
        observed,
        labels.get(kind, kind),
    )
    if kind not in ("calibrate", "repair"):
        # An observed +5 normal variant promotes only the high watermark.
        if kind in ("normal", "provisional"):
            record = history.setdefault(context, {})
            if rule.baseline_mode == "manual":
                attr = "verified_baseline"
                baseline = max(
                    rule.manual_percent, record.get(attr, rule.manual_percent)
                )
            else:
                attr = (
                    "verified_baseline"
                    if "verified_baseline" in record
                    else "provisional_baseline"
                )
                baseline = record.get(attr)
            if (
                baseline is not None
                and 5 - OCR_TOLERANCE <= observed - baseline <= 5 + OCR_TOLERANCE
            ):
                record[attr] = observed
                save_history(history)
        return
    roster = snapshot["roster"]
    solver._trade_efficiency_repair = {
        "room": room,
        "key": context,
        "before": observed,
        "initial_before": observed,
        "metric": metric,
        "kind": kind,
        "original": list(roster),
        "stage": "swap_pending",
        "recovery_attempts": 0,
        "attempt": 1,
        "retry_limit": retry_limit,
    }
    _queue_swap(solver, solver._trade_efficiency_repair)
    logger.debug(
        "效率自检：%s 已建立%s任务（第1/%d次，先交换、再恢复）",
        room,
        kind,
        retry_limit,
    )
