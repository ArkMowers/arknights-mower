"""记录独立的运行展示观测；这些记录不参与任务调度。"""

from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from threading import RLock

_lock = RLock()
_KEYS = ("stage-plan", "annihilation", "mission", "depot")
_FIELDS = ("at", "runner", "outcome", "stage", "executed_runs", "reason")
_FACTS = ("stage", "executed_runs", "reason")
MAX_MAA_ACTIVITY_TASKS = 1024


def _known_observations(values):
    if not isinstance(values, dict):
        return {}
    return {
        key: {field: value[field] for field in _FIELDS if field in value}
        for key in _KEYS
        if isinstance(value := values.get(key), dict)
    }


def snapshot_observations(owner):
    with _lock:
        return _known_observations(getattr(owner, "display_observations", None))


def observe_activity(owner, key, runner, outcome, **facts):
    if not isinstance(key, str) or key not in _KEYS:
        return None
    observation = {
        "at": datetime.now().astimezone(),
        "runner": runner,
        "outcome": outcome,
        **{field: facts[field] for field in _FACTS if field in facts},
    }
    with _lock:
        owner.display_observations = {
            **snapshot_observations(owner),
            key: observation,
        }
    return observation


def finish_running_observations(
    owner, runner, *, key=None, outcome="stopped", reason=None
):
    with _lock:
        for name, value in snapshot_observations(owner).items():
            if (
                (key is None or key == name)
                and value.get("runner") == runner
                and value.get("outcome") == "running"
            ):
                facts = {
                    k: v
                    for k, v in value.items()
                    if k not in ("at", "runner", "outcome")
                }
                if reason is not None:
                    facts["reason"] = reason
                observe_activity(owner, name, runner, outcome, **facts)


def restore_observations(owner, values):
    with _lock:
        owner.display_observations = {
            key: {
                **value,
                **(
                    {"outcome": "stopped", "reason": "restored"}
                    if value.get("outcome") == "running"
                    else {}
                ),
            }
            for key, value in _known_observations(values).items()
        }


@contextmanager
def activity_observation(owner, key, runner, *, stopped_exceptions=()):
    observe_activity(owner, key, runner, "running")
    try:
        yield
    except BaseException as error:
        finish_running_observations(
            owner,
            runner,
            key=key,
            outcome="stopped"
            if isinstance(error, stopped_exceptions) or not isinstance(error, Exception)
            else "error",
            reason="cancelled"
            if isinstance(error, stopped_exceptions) or not isinstance(error, Exception)
            else "exception",
        )
        raise
    finish_running_observations(owner, runner, key=key, outcome="checked")


def observed_activity(key, runner, *, stopped_exceptions=()):
    def decorate(function):
        @wraps(function)
        def run(owner, *args, **kwargs):
            with activity_observation(
                owner, key, runner, stopped_exceptions=stopped_exceptions
            ):
                return function(owner, *args, **kwargs)

        return run

    return decorate


def remember_maa_activity(owner, task_id, chain, key, **facts):
    if (
        type(task_id) is not int
        or task_id <= 0
        or not isinstance(key, str)
        or key not in _KEYS
    ):
        return
    with _lock:
        tasks = getattr(owner, "_maa_activity_tasks", {})
        if task_id not in tasks and len(tasks) >= MAX_MAA_ACTIVITY_TASKS:
            return
        owner._maa_activity_tasks = {
            **tasks,
            task_id: {"chain": chain, "key": key, "facts": facts, "failed": False},
        }


def observe_maa_callback(owner, message, details, *, generation=None):
    if type(message) is not int or not isinstance(details, dict):
        return
    with _lock:
        if generation is not None and generation is not getattr(
            owner, "_maa_activity_generation", None
        ):
            return
        if message == 3:
            finish_running_observations(
                owner, "maa", outcome="checked", reason="queue_ended"
            )
            owner._maa_activity_tasks = {}
            return
        task_id = details.get("taskid")
        if type(task_id) is not int:
            return
        tasks = getattr(owner, "_maa_activity_tasks", {})
        task = tasks.get(task_id)
        if task is None or task["chain"] != details.get("taskchain"):
            return
        if message == 20000:
            task = {**task, "failed": True}
            owner._maa_activity_tasks = {**tasks, task_id: task}
        outcomes = {
            10001: "running",
            10002: "checked",
            10000: "error",
            10004: "stopped",
            20000: "incomplete",
        }
        if message in outcomes:
            outcome = outcomes[message]
            if message == 10002 and task["failed"]:
                outcome = "incomplete"
            observe_activity(owner, task["key"], "maa", outcome, **task["facts"])
        if message in (10000, 10002, 10004):
            owner._maa_activity_tasks = {
                key: value for key, value in tasks.items() if key != task_id
            }


def clear_maa_observations(owner):
    with _lock:
        finish_running_observations(owner, "maa")
        owner._maa_activity_tasks = {}
        owner._maa_activity_generation = None


def begin_maa_observations(owner):
    with _lock:
        clear_maa_observations(owner)
        owner._maa_activity_generation = object()
        return owner._maa_activity_generation
