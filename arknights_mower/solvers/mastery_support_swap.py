"""Verify the active training and execute or defer an assistant handoff."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from arknights_mower.utils.mastery_support import (
    REDUCERS,
    SupportPlanError,
    TrainingInputs,
    candidates,
    check_schedule_name,
    rate,
    schedule_context,
    stage_for,
)

from .mastery_support_state import (
    enqueue_support_swap,
    finish_support_swap,
    notify_support_failure,
    record_work,
    refresh_end,
    save_runtime,
    schedule_support_swap,
    stop_support_swap,
)
from .mastery_support_state import (
    select_swap_support as select_swap_support,
)


def confirm_training_panel(solver, plan, level):
    from arknights_mower.solvers.mastery_reader import (
        RoomState,
        _close_room_detail,
        _plan_matches_room,
        read_main_panel,
    )
    from arknights_mower.utils.scene import Scene

    if solver.train_scene() == Scene.INFRA_DETAILS:
        _close_room_detail(solver)
    if solver.train_scene() != Scene.TRAIN_MAIN:
        raise SupportPlanError("未返回训练室主页面，停止换人")
    panel = read_main_panel(solver)
    if (
        not panel
        or panel.countdown_state != "active"
        or panel.mastery_tier != level
        or not panel.operator_name
        or not panel.skill_name
        or not _plan_matches_room(plan, RoomState("training", panel))
    ):
        raise SupportPlanError("训练室状态变化或读取失败，停止换人")
    return panel


def place_support(solver, plan, level, name):
    from arknights_mower.solvers.mastery_reader import _read_slots_checked

    check_schedule_name(name, schedule_context()[0])
    confirm_training_panel(solver, plan, level)
    solver.choose_train([name, "Current"])
    actual, trainee, _, reliable = _read_slots_checked(solver)
    if not reliable or actual != name or trainee != plan.get("char_name"):
        raise SupportPlanError("换人后无法确认协助者与训练位，停止自动换人")
    panel = confirm_training_panel(solver, plan, level)
    record_work(plan, level, name, panel.countdown)
    return panel


@dataclass
class SwapExecution:
    solver: object
    plan: dict
    level: int
    route: dict

    def collect(self, freeze=False):
        finish_support_swap(self.solver, self.plan, self.level, freeze)

    def restore_first(self, first, central):
        if first is None:
            raise SupportPlanError("计划协助者已不可用，无法恢复协助位")
        self.route.update(
            efficiency=first["efficiency"],
            first_halves=first["halves"],
            central_bonus=central,
        )
        save_runtime(self.plan, self.route)
        panel = place_support(self.solver, self.plan, self.level, first["name"])
        if (
            schedule_support_swap(self.solver, self.plan, panel.countdown, self.level)
            is None
        ):
            self.collect()

    def handoff(self, selected, delay, central):
        self.route.update(
            swap_target=selected["name"],
            swap_efficiency=selected["efficiency"],
            central_bonus=central,
            swap_halves=selected["halves"],
        )
        save_runtime(self.plan, self.route)
        if delay > 5:
            enqueue_support_swap(
                self.solver,
                self.plan,
                datetime.now() + timedelta(seconds=delay),
                selected["name"],
            )
            return
        panel = place_support(self.solver, self.plan, self.level, selected["name"])
        if (
            selected["halves"]
            and (panel.countdown - datetime.now()).total_seconds() <= 5 * 3600
        ):
            notify_support_failure(
                self.plan,
                self.level,
                "换人后的实际倒计时不足 5 小时，下一阶段减半无法保证",
            )
        self.collect(freeze=True)


def _swap_candidates(execution, options):
    route, level = execution.route, execution.level
    names = [route.get("swap_target")]
    if not route.get("manual"):
        names += [n for n in REDUCERS if n not in names]
    return [
        options[n][level]
        for n in names
        if n in options and (route.get("manual") or options[n][level]["halves"])
    ]


def _current_rate(options, support, level, central=0):
    current = options.get(support, {}).get(level)
    if support and current is None:
        raise SupportPlanError("当前协助者不在可用名单中，停止自动换人")
    return rate(current["efficiency"], central) if current else 1


def _apply_swap(execution, support, options, central):
    route, level = execution.route, execution.level
    speed = _current_rate(options, support, level, central)
    schedule_speed = _current_rate(options, support, level)
    stats = _swap_candidates(execution, options)
    swapping = bool(route.get("swap_target")) and level < execution.plan["target_level"]
    correcting = support != route["operator"]
    if not swapping and not correcting:
        return execution.collect()
    if not stats and not correcting:
        return execution.collect(freeze=True)  # No reducers: normal roster limitation.
    panel = confirm_training_panel(execution.solver, execution.plan, level)
    seconds = max(0, (panel.countdown - datetime.now()).total_seconds())
    selected, delay = (
        select_swap_support(
            seconds * speed,
            speed,
            stats,
            (central, route["mastery_swap_buffer"]),
            schedule_rate=schedule_speed,
        )
        if swapping
        else (None, 0)
    )
    if correcting and (selected is None or delay > 5):
        # Do not remove a reducer that cannot earn five hours again.
        if support in REDUCERS and seconds < (300 + route["mastery_swap_buffer"]) * 60:
            execution.collect()
        else:
            execution.restore_first(
                options.get(route["operator"], {}).get(level), central
            )
    elif selected is not None:
        execution.handoff(selected, delay, central)
    else:
        if stats:
            notify_support_failure(
                execution.plan,
                level,
                "换入减半教官后的剩余训练不足 5 小时，已保留当前协助者，本阶段不再尝试替换",
            )
        execution.collect(freeze=True)


def _matches_training(plan, panel):
    from arknights_mower.solvers.mastery_reader import RoomState, _plan_matches_room

    return bool(
        panel
        and panel.countdown_state == "active"
        and panel.mastery_tier
        and panel.operator_name
        and panel.skill_name
        and _plan_matches_room(plan, RoomState("training", panel))
    )


def _prepare_swap_execution(solver, plan, panel):
    level = getattr(panel, "mastery_tier", None)
    if panel and panel.countdown_state == "zero":
        finish_support_swap(solver, plan, level)
        return None
    if not _matches_training(plan, panel):
        stop_support_swap(
            solver,
            plan,
            level,
            "训练室面板读取失败或与计划不符，停止换人并安排收取检查",
        )
        return None
    route = stage_for(plan, level)
    if not route:
        stop_support_swap(
            solver, plan, level, "当前阶段缺少协助方案，停止换人并安排收取检查"
        )
        return None
    return SwapExecution(solver, plan, level, route)


def perform_swap(solver, plan, panel, support):
    """The caller must have confirmed a reliable slot read before entering."""
    from arknights_mower.utils.csleep import MowerExit

    execution = _prepare_swap_execution(solver, plan, panel)
    if execution is None:
        return
    route = execution.route

    if support == route.get("swap_target"):
        refresh_end(plan, execution.level, panel.countdown)
        return execution.collect()
    try:
        options, central = candidates(
            plan["char_id"],
            include_dynamic=route.get("manual", False),
            inputs=TrainingInputs(schedule=schedule_context()),
        )
        _apply_swap(execution, support, options, central)
    except MowerExit:
        raise
    except Exception as exc:
        notify_support_failure(plan, execution.level, str(exc))
        execution.collect(freeze=True)
