"""Persist one manual snapshot for an automatic mastery crafting session."""

import json
from collections import Counter
from threading import RLock

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import RIICPart
from arknights_mower.utils.path import get_path

workshop_lock = RLock()
_STATE_FIELDS = (
    "workshop_manual_backup",
    "workshop_preset_migrated",
    "workshop_generation",
)


def _settings(entries, source=None):
    result = []
    for entry in entries:
        value = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
        if source is not None:
            value["source"] = source
        result.append(RIICPart.WorkShopSetting(**value))
    return result


def _migrate_preset(conf):
    if conf.workshop_preset_migrated:
        return
    path = get_path("@app/tmp/workshop_preset.json")
    if conf.workshop_manual_backup is None and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("settings") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise ValueError("已保存的合成配置格式错误，保留现有配置及备份")
        conf.workshop_manual_backup = _settings(entries, "manual")
    conf.workshop_preset_migrated = True


def _restore(conf):
    if conf.workshop_manual_backup is None:
        return False
    conf.workshop_settings = _settings(conf.workshop_manual_backup, "manual")
    conf.workshop_manual_backup = None
    conf.workshop_generation += 1
    return True


def _save(conf):
    """Commit snapshot, source, settings and generation in one atomic config write."""
    previous = config.conf
    if conf == previous:
        return
    config.conf = conf
    try:
        config.save_conf()
    except Exception:
        config.conf = previous
        raise


def save_user_config(req):
    """The browser owns editable settings; backup state stays on the server."""
    with workshop_lock:
        current = config.conf
        req = dict(req)
        for key in _STATE_FIELDS:
            req[key] = getattr(current, key)
        req.setdefault("workshop_deer_fodder", current.workshop_deer_fodder)
        incoming = req.get("workshop_settings", [])
        # A browser can remain open across scan/takeover/restore. Its next
        # unrelated autosave must not put an obsolete crafting list back.
        if req.pop("workshop_settings_generation", 0) != current.workshop_generation:
            req["workshop_settings"] = current.workshop_settings
        elif current.workshop_manual_backup is not None:
            req["workshop_settings"] = _settings(incoming, "mastery")
        elif any(entry.get("source") == "mastery" for entry in incoming):
            req["workshop_settings"] = current.workshop_settings
        conf = config.Conf(**req)
        if not conf.enable_mastery:
            _restore(conf)
        _save(conf)


def _materials_ready(plans, recommendations):
    """Confirm the whole queue's remaining costs, without spending shared stock twice.

    Missing BOX/costs are unknown, never evidence that crafting has finished.
    This runs only after a depot scan or an explicit auto-config request.
    """
    from arknights_mower.utils import mastery_recommendation as rec

    if not recommendations.get("has_data"):
        return None
    path = rec.get_path("@app/tmp/cultivate.json")
    data = json.loads(path.read_text(encoding="utf-8"))["data"]
    names = rec.get_skill_data().get("items", {})
    inventory = Counter(
        {
            names.get(item["id"], {}).get("name", item["id"]): int(item["count"])
            for item in data["items"]
        }
    )
    levels = {
        (char["id"], index): skill.get("level", 0)
        for char in data["characters"]
        for index, skill in enumerate(char.get("skills", []))
    }
    skills = {
        (op["char_id"], skill["skill_index"]): skill
        for op in recommendations.get("operators", [])
        for skill in op.get("recommendations", [])
    }
    demand = Counter()
    for plan in plans:
        key = plan["char_id"], plan["skill_index"]
        if levels.get(key, 0) >= plan["target_level"]:
            continue
        skill = skills.get(key)
        if skill is None:
            return None
        stages = skill.get("stages")
        if stages:
            if rec._workshop_lookahead_active(plan):
                stages = stages[1:]  # This training step has already been paid.
            materials = [
                mat
                for stage in stages
                if stage["to_level"] - 7 <= plan["target_level"]
                for mat in stage.get("needed_materials", [])
            ]
        else:
            materials = skill.get("chain_needed_materials")
            if materials is None:
                return None
        for material in materials:
            demand[material["name"]] += material["count"]
    return all(inventory[name] >= count for name, count in demand.items())


def update_workshop_config(**operators):
    """Take over once, retain the backup while waiting, restore on completion."""
    from arknights_mower.utils import mastery_recommendation as rec
    from arknights_mower.utils.mastery_db import get_all_plans

    with workshop_lock:
        conf = config.conf.model_copy(deep=True)
        _migrate_preset(conf)
        plans = get_all_plans() if conf.enable_mastery else []
        ready = not plans
        settings = None
        if plans:
            recommendations = rec.get_mastery_recommendations()
            ready = _materials_ready(plans, recommendations)
            if ready is False:
                settings = rec.compute_workshop_config(
                    **{
                        key: operators.get(key, getattr(conf, key))
                        for key in (
                            "fodder_operators",
                            "t5_operators",
                            "book_operators",
                        )
                    },
                    plans=plans,
                    recommendations=recommendations,
                )
        restored = False
        if ready:
            restored = _restore(conf)
        elif settings is not None:
            if settings and conf.workshop_manual_backup is None:
                # Never back up generated entries, even after partial upgrades.
                conf.workshop_manual_backup = _settings(
                    [s for s in conf.workshop_settings if s.source != "mastery"]
                )
            if conf.workshop_manual_backup is not None:
                generated = _settings(settings, "mastery")
                if generated != conf.workshop_settings:
                    conf.workshop_settings = generated
                    conf.workshop_generation += 1
        _save(conf)
        active = conf.workshop_manual_backup is not None
        return {
            "workshop_settings": [s.model_dump() for s in conf.workshop_settings],
            "workshop_generation": conf.workshop_generation,
            "automatic": active,
            "restored": restored,
            "t3_summary": [],
        }


def restore_if_no_plans():
    from arknights_mower.utils.mastery_db import get_all_plans

    with workshop_lock:
        if config.conf.workshop_manual_backup is None or get_all_plans():
            return
        conf = config.conf.model_copy(deep=True)
        _restore(conf)
        _save(conf)


def stamp_workshop_task(task):
    if config.conf.workshop_manual_backup is not None:
        task.workshop_generation = config.conf.workshop_generation


def workshop_task_current(task):
    generation = getattr(task, "workshop_generation", None)
    return generation is None or (
        config.conf.workshop_manual_backup is not None
        and generation == config.conf.workshop_generation
    )
