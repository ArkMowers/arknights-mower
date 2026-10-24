"""手动任务的队列执行、执行器选择及依赖释放，不访问设备。"""

from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask

from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scheduler_task import (
    MANUAL_TASK_TYPES,
    SchedulerTask,
    TaskTypes,
)

scheduler = recovery.scheduler


@pytest.fixture
def manual(scheduler, monkeypatch):
    from arknights_mower.solvers import manual_tasks

    monkeypatch.setattr(manual_tasks, "datetime", scheduler.clock)
    monkeypatch.setattr(scheduler.module.config, "conf", Conf())
    solver = scheduler.solver
    monkeypatch.setattr(scheduler.module.config, "wake_scheduler", Event())
    monkeypatch.setattr(scheduler.module.config, "stop_maa", Event())
    solver.last_execution = {"maa": None, "recruit": None}
    solver.maa_plan_solver = Mock(return_value=True)
    solver.mower_plan_solver = Mock()
    return SimpleNamespace(**vars(scheduler), manual=manual_tasks)


def queue(manual, kind, minutes=60):
    task = SchedulerTask(manual.clock.now(), task_type=kind)
    later = SchedulerTask(manual.clock.now() + timedelta(minutes=minutes))
    manual.solver.tasks, manual.solver.task = [task, later], task
    return task, later


@pytest.mark.parametrize("kind", list(MANUAL_TASK_TYPES))
def test_task_route_accepts_each_type_clears_roster_and_wakes(
    manual, monkeypatch, kind
):
    from arknights_mower.views import task as route

    app = Flask(__name__)
    app.token = "test-token"
    app.register_blueprint(route.task_bp)
    worker = Mock()
    worker.is_alive.return_value = True
    monkeypatch.setattr(route, "mower_thread", worker)
    manual.module.config.wake_scheduler.clear()
    body = {
        "task": {
            "time": "2026-10-01T02:00:00.000Z",
            "plan": {"train": ["陈"]},
            "task_type": kind.display_value,
            "meta_data": "stale",
        }
    }
    client = app.test_client()
    for token in (None, "wrong"):
        headers = {} if token is None else {"token": token}
        assert client.post("/task", json=body, headers=headers).status_code == 403
        assert manual.solver.tasks == []
        assert not manual.module.config.wake_scheduler.is_set()
        assert client.get("/task", headers=headers).status_code == 403
    result = client.post("/task", json=body, headers={"token": "test-token"})
    assert result.text == "添加任务成功！"
    (created,) = manual.solver.tasks
    assert created.type == kind
    assert created.plan == {}
    assert created.meta_data == ""
    assert manual.module.config.wake_scheduler.is_set()
    assert (
        client.get("/task", headers={"token": "test-token"}).json[0]["display_name"]
        == kind.display_value
    )
    manual.module.config.wake_scheduler.clear()


@pytest.mark.parametrize(
    "kind, module, name",
    [
        (TaskTypes.RECRUIT, "recruit", "RecruitSolver"),
        (TaskTypes.MAIL, "mail", "MailSolver"),
        (TaskTypes.REPORT, "report", "ReportSolver"),
        (TaskTypes.MISSION, "mission", "MissionSolver"),
        (TaskTypes.VISIT_FRIEND, "credit", "CreditSolver"),
        (TaskTypes.CREDIT_SHOP, "shop", "CreditShop"),
    ],
)
def test_infra_dispatch_runs_single_task_even_with_automatic_setting_disabled(
    manual, monkeypatch, kind, module, name
):
    import importlib

    monkeypatch.setattr(
        manual.module.config,
        "conf",
        Conf(
            recruit_enable=False,
            check_mail_enable=False,
            report_enable=False,
            visit_friend_enable=False,
            visit_friend_mode="mower",
            maa_mall_enable=False,
            maa_mall_mode="mower",
        ),
    )
    action = Mock()
    monkeypatch.setattr(
        importlib.import_module(f"arknights_mower.solvers.{module}"), name, action
    )
    task, later = queue(manual, kind)
    manual.solver.infra_main()
    action.return_value.run.assert_called_once_with()
    assert manual.solver.tasks == [later]
    assert task.manual_steps == []
    manual.io.assert_not_called()


@pytest.mark.parametrize(
    "kind, args, kwargs",
    [
        (
            TaskTypes.CREDIT_SHOP,
            (["Mall"],),
            {"manual": True, "mall_action": "shopping"},
        ),
        (
            TaskTypes.VISIT_FRIEND,
            (["Mall"],),
            {"manual": True, "mall_action": "visit_friends"},
        ),
        (TaskTypes.STAGE_PLAN, (["Fight", "Award"],), {"manual": True}),
        (TaskTypes.ROGUELIKE, ([],), {"manual": True, "long_task": "rogue"}),
        (TaskTypes.SSS, ([],), {"manual": True, "long_task": "sss"}),
        (TaskTypes.RECLAMATION, ([],), {"manual": True, "long_task": "rcl"}),
        (TaskTypes.RA, ([],), {"manual": True, "long_task": "ra"}),
        (TaskTypes.SECRET_FRONT, ([],), {"manual": True, "long_task": "sf"}),
    ],
)
def test_manual_selection_routes_to_only_the_chosen_executor(
    manual, kind, args, kwargs
):
    task, later = queue(manual, kind)
    manual.solver.infra_main()
    manual.solver.maa_plan_solver.assert_called_once_with(*args, **kwargs)
    assert manual.solver.tasks == [later]


def test_sign_in_dispatch_updates_daily_marker(manual):
    task, later = queue(manual, TaskTypes.SKLAND)
    manual.solver.skland_plan_solver = Mock(return_value=True)
    manual.solver.infra_main()
    manual.solver.skland_plan_solver.assert_called_once_with()
    assert manual.solver.tasks == [later]
    assert manual.solver.daily_skland == manual.manual.get_server_time().date()


def test_unchanged_dependency_retains_task_time_then_releases_on_completion(
    manual, monkeypatch
):
    task, later = queue(manual, TaskTypes.STAGE_PLAN, minutes=4)
    original_time = task.time
    manual.solver.infra_main()
    manual.solver.maa_plan_solver.assert_not_called()
    assert task.execution_failure
    assert task.time == original_time
    manual.clock.current += timedelta(minutes=2)
    for _ in range(3):
        manual.solver._resume_failed_tasks()
        assert task.execution_failure
    manual.solver.tasks.remove(later)
    manual.solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert task.time == original_time
    manual.solver.task = task
    manual.solver.infra_main()
    manual.solver.maa_plan_solver.assert_called_once_with(
        ["Fight", "Award"], manual=True
    )
    assert manual.solver.tasks == []


def test_daily_preserves_finished_steps_when_next_task_becomes_due(manual, monkeypatch):
    monkeypatch.setattr(
        manual.module.config,
        "conf",
        Conf(
            report_enable=True,
            skland_enable=False,
            check_mail_enable=False,
            recruit_enable=False,
            visit_friend_enable=False,
            maa_mall_enable=False,
            maa_credit_fight=False,
            stage_plan_enable=False,
        ),
    )
    from arknights_mower.solvers import mission, report

    reader, reward = Mock(), Mock()
    monkeypatch.setattr(report, "ReportSolver", reader)
    monkeypatch.setattr(mission, "MissionSolver", reward)
    task, later = queue(manual, TaskTypes.DAILY, minutes=6)
    reader.return_value.run.side_effect = lambda: (
        setattr(manual.clock, "current", manual.clock.now() + timedelta(minutes=2))
        or True
    )
    manual.solver.infra_main()
    assert task.manual_steps == ["领取任务奖励"]
    reward.assert_not_called()
    manual.solver.tasks.remove(later)
    manual.solver._resume_failed_tasks()
    manual.solver.task = task
    manual.solver.infra_main()
    reader.return_value.run.assert_called_once_with()
    reward.return_value.run.assert_called_once_with()
    assert manual.solver.tasks == []


def actual_maa(manual):
    solver = manual.solver
    solver.maa_plan_solver = manual.module.BaseSchedulerSolver.maa_plan_solver.__get__(
        solver
    )
    engine = Mock()
    solver.MAA = None
    engine.running.return_value = False
    engine.get_version.return_value = "v6.17.3"
    solver.initialize_maa = Mock(side_effect=lambda: setattr(solver, "MAA", engine))
    solver.back_to_index = Mock()
    solver.rest_until_next_task = Mock()
    solver.restore_maa_theme = Mock()
    solver.to_reclamation = Mock()
    solver.stages = []
    solver.local_operation_followup_time = None
    solver.report_maa_progress = Mock()
    return solver, engine


@pytest.mark.parametrize(
    "kind, action",
    [(TaskTypes.CREDIT_SHOP, "shopping"), (TaskTypes.VISIT_FRIEND, "visit_friends")],
)
def test_actual_maa_mall_runs_only_selected_action_and_does_not_sleep(
    manual, monkeypatch, kind, action
):
    monkeypatch.setattr(manual.module, "send_message", Mock())
    monkeypatch.setattr(
        manual.module.config,
        "conf",
        Conf(maa_mall_enable=False, visit_friend_enable=False),
    )
    task, later = queue(manual, kind)
    solver, engine = actual_maa(manual)
    assert manual.manual.run_manual_task(solver, task)
    name, params = engine.append_task.call_args.args
    assert name == "Mall"
    assert params["shopping"] is (action == "shopping")
    assert params["visit_friends"] is (action == "visit_friends")
    assert params["credit_fight"] is False
    engine.start.assert_called_once()
    engine.close.assert_called_once()
    assert solver.MAA is None
    assert solver.last_execution["maa"] is None
    solver.rest_until_next_task.assert_not_called()
    assert solver.tasks == [task, later]


@pytest.mark.parametrize(
    "kind, expected",
    [(TaskTypes.ROGUELIKE, "Roguelike"), (TaskTypes.RECLAMATION, "Reclamation")],
)
def test_actual_long_selection_ignores_other_automatic_long_type(
    manual, monkeypatch, kind, expected
):
    monkeypatch.setattr(manual.module, "send_message", Mock())
    monkeypatch.setattr(
        manual.module.config, "conf", Conf(maa_rg_enable=True, maa_long_task_type="sss")
    )
    task, _ = queue(manual, kind)
    solver, engine = actual_maa(manual)
    assert manual.manual.run_manual_task(solver, task)
    assert [item.args[0] for item in engine.append_task.call_args_list] == [expected]
    engine.close.assert_called_once()
    solver.rest_until_next_task.assert_not_called()


def test_actual_maa_yields_when_new_task_arrives_without_three_minute_sleep(
    manual, monkeypatch
):
    monkeypatch.setattr(manual.module, "send_message", Mock())
    task, later = queue(manual, TaskTypes.CREDIT_SHOP)
    solver, engine = actual_maa(manual)
    engine.running.side_effect = [True, False]
    solver.recog.update.side_effect = lambda: setattr(
        later, "time", manual.clock.now() + timedelta(minutes=3)
    )
    solver.sleep = Mock()
    assert manual.manual.run_manual_task(solver, task) is False
    engine.stop.assert_called_once()
    solver.sleep.assert_not_called()
    assert task.execution_failure
    assert task.manual_steps == ["信用购物"]
    assert solver.tasks == [task, later]


def test_manual_deadline_excludes_self_and_does_not_move_with_clock(manual):
    task, later = queue(manual, TaskTypes.ROGUELIKE)
    manual.solver.tasks.remove(later)
    deadline = manual.manual.manual_task_deadline(manual.solver)
    manual.clock.current += timedelta(hours=1)
    assert manual.manual.manual_task_deadline(manual.solver) == deadline


def test_manual_sss_uses_configured_copilot(manual, monkeypatch, tmp_path):
    monkeypatch.setattr(manual.module, "send_message", Mock())
    copilot = tmp_path / "sss.json"
    copilot.write_text("{}")
    monkeypatch.setattr(manual.module, "get_path", lambda _: copilot)
    monkeypatch.setattr(manual.module.config, "conf", Conf(sss={"type": 1, "ec": 1}))
    task, _ = queue(manual, TaskTypes.SSS)
    solver, engine = actual_maa(manual)
    solver.to_sss = Mock(return_value=False)
    assert manual.manual.run_manual_task(solver, task)
    engine.append_task.assert_called_once_with(
        "SSSCopilot", {"filename": str(copilot), "loop_times": 9999999}
    )
    engine.close.assert_called_once()


@pytest.mark.parametrize(
    "kind, name",
    [(TaskTypes.RA, "ReclamationAlgorithm"), (TaskTypes.SECRET_FRONT, "SecretFront")],
)
def test_native_long_tasks_receive_next_queue_deadline(manual, monkeypatch, kind, name):
    monkeypatch.setattr(manual.module, "send_message", Mock())
    action = Mock()
    monkeypatch.setattr(manual.module, name, action)
    task, later = queue(manual, kind)
    solver, engine = actual_maa(manual)
    assert manual.manual.run_manual_task(solver, task)
    action.return_value.run.assert_called_once_with(later.time - manual.clock.now())
    engine.append_task.assert_not_called()
    solver.rest_until_next_task.assert_not_called()


def test_daily_maa_does_not_start_enabled_automatic_long_task(manual, monkeypatch):
    monkeypatch.setattr(manual.module, "send_message", Mock())
    monkeypatch.setattr(
        manual.module.config,
        "conf",
        Conf(
            maa_rg_enable=True,
            maa_long_task_type="rogue",
            stage_plan_enable=False,
            maa_mall_enable=False,
            maa_credit_fight=False,
            maa_mail=True,
            check_mail_enable=False,
            recruit_enable=False,
            skland_enable=False,
            report_enable=False,
            visit_friend_enable=False,
        ),
    )
    from arknights_mower.solvers import mission

    monkeypatch.setattr(mission, "MissionSolver", Mock())
    task, _ = queue(manual, TaskTypes.DAILY)
    solver, engine = actual_maa(manual)
    assert manual.manual.run_manual_task(solver, task)
    assert [item.args[0] for item in engine.append_task.call_args_list] == [
        "StartUp",
        "Award",
    ]


def test_local_stage_selection_uses_mower(manual, monkeypatch):
    monkeypatch.setattr(
        manual.module.config,
        "conf",
        Conf(stage_plan_runner="mower", stage_plan_enable=False),
    )
    task, _ = queue(manual, TaskTypes.STAGE_PLAN)
    assert manual.manual.run_manual_task(manual.solver, task)
    manual.solver.mower_plan_solver.assert_called_once_with(manual=True)
    manual.solver.maa_plan_solver.assert_not_called()
