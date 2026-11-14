import hashlib
import json

from arknights_mower.utils.maa_copilot import queue_key


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

    result = {}
    for kind, settings, load in (
        ("copilot", conf.copilot, record.load_maa_copilot_progress),
        ("paradox", conf.paradox, record.load_maa_paradox_progress),
        ("sss", conf.sss, record.load_maa_sss_progress),
    ):
        progress = load()
        result[kind] = {
            "completed": bool(settings.scripts)
            and progress.get("key") == queue_key(settings)
            and progress.get("next") == len(settings.scripts)
            and not progress.get("failed", False)
        }
    progress = record.load_maa_blackflow_progress()
    result["blackflow"] = {
        "completed": progress.get("key") == blackflow_start_run_key(conf.rogue)
        and progress.get("completed") is True
    }
    progress = record.load_maa_blackflow_progress(boss=True)
    result["blackflow_boss"] = {
        "completed": progress.get("key") == blackflow_boss_run_key(conf.rogue)
        and progress.get("completed") is True
    }
    return result
