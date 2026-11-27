import hashlib
import json
from dataclasses import dataclass

from arknights_mower.utils.maa_callback import rogue_boss_stop_reached
from arknights_mower.utils.maa_copilot import queue_key

_ROGUE_COMPLETION_EVENTS = {
    "investment": "RoguelikeInvestmentReachFull",
    "monthly": "MonthlySquadCompleted",
    "monthly_comms": "MonthlySquadCompleted",
    "exploration": "DeepExplorationCompleted",
}


def rogue_goals(conf):
    rogue = conf.rogue
    if rogue.mode == 0:
        goals = set()
        if rogue.stop_at_max_level:
            goals.add("level")
        if rogue.stop_at_final_boss and conf.maa_rg_theme not in (
            "Phantom",
            "BlackFlow",
        ):
            goals.add("boss")
        return goals
    if rogue.mode == 1 and rogue.investment_enabled and rogue.stop_when_investment_full:
        return {"investment"}
    if rogue.mode == 6 and rogue.monthly_squad_auto_iterate:
        return {"monthly_comms" if rogue.monthly_squad_check_comms else "monthly"}
    if rogue.mode == 7 and rogue.deep_exploration_auto_iterate:
        return {"exploration"}
    return set()


def automatic_rogue_completed(conf):
    from arknights_mower.solvers import record

    goals = rogue_goals(conf)
    return bool(
        goals and goals.intersection(record.completed_rogue_goals(conf.maa_rg_theme))
    )


@dataclass
class RogueGoalRun:
    task_id: int
    theme: str
    goals: set[str]
    manual: bool
    reached: str | None = None

    def record(self, msg, data):
        from arknights_mower.solvers import record

        if (
            data.get("taskchain") != "Roguelike"
            or type(data.get("taskid")) is not int
            or data["taskid"] != self.task_id
        ):
            return
        if msg == 10001 and self.manual:
            record.reopen_rogue_goals(self.theme, self.goals)
        elif msg in (10000, 10002, 10004):
            completed = self.reached if msg == 10002 else None
            if completed:
                record.mark_rogue_goal_complete(self.theme, completed)
            self.reached = None
            self.goals.clear()
            return completed
        elif msg == 20000 and "level" in self.goals:
            # MAA 以这次识别未命中判定满级，等同一任务链正常结束再保存。
            if (
                data.get("subtask") == "ProcessTask"
                and data.get("first") == ["Roguelike@CheckLevelMax"]
                and "what" not in data
            ):
                self.reached = "level"
        elif msg == 20003:
            for goal in self.goals:
                if goal == "boss" and rogue_boss_stop_reached(data, self.theme):
                    self.reached = goal
                elif (
                    goal in _ROGUE_COMPLETION_EVENTS
                    and data.get("what") == _ROGUE_COMPLETION_EVENTS[goal]
                ):
                    self.reached = goal


def blackflow_preserved_run(conf):
    if conf.mode == 30003:
        return "opening"
    if (
        conf.mode == 0
        and conf.stop_at_final_boss
        and not getattr(conf, "blackflow_fast_flight", False)
    ):
        return "boss"
    return None


def blackflow_boss_run_key(conf):
    settings = conf.model_dump(
        include={
            "blackflow_boss_run_id",
            "squad",
            "roles",
            "core_char",
            "core_char_list",
            "use_support",
            "use_nonfriend_support",
            "difficulty",
            "investment_enabled",
            "stop_at_max_level",
        }
    )
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


def blackflow_start_run_key(conf):
    settings = conf.model_dump(
        include={
            "blackflow_start_run_id",
            "blackflow_start_run_fast_flight",
            "blackflow_start_animals",
            "blackflow_start_rewards",
            "blackflow_start_utopia",
            "blackflow_start_reward_priority",
            "collectible_mode_squad",
            "collectible_mode_roles",
            "collectible_mode_core_char_list",
            "squad",
            "roles",
            "core_char",
            "core_char_list",
            "use_support",
            "use_nonfriend_support",
            "difficulty",
            "investment_enabled",
        }
    )
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


def completion_status(conf):
    from arknights_mower.solvers import record

    saved = record.load_long_task_progress()
    result = {}
    for kind, settings in (
        ("copilot", conf.copilot),
        ("paradox", conf.paradox),
        ("sss", conf.sss),
    ):
        progress = saved.get(kind, {})
        result[kind] = {
            "completed": bool(settings.scripts)
            and progress.get("key") == queue_key(settings)
            and progress.get("next") == len(settings.scripts)
            and not progress.get("failed", False)
        }
    progress = saved.get("blackflow", {})
    result["blackflow"] = {
        "completed": progress.get("key") == blackflow_start_run_key(conf.rogue)
        and progress.get("completed") is True
    }
    progress = saved.get("blackflow_boss", {})
    result["blackflow_boss"] = {
        "completed": progress.get("key") == blackflow_boss_run_key(conf.rogue)
        and progress.get("completed") is True
    }
    from arknights_mower.solvers.garrison.model import status

    result["garrison"] = status(conf, saved.get("garrison", {}))
    return result
