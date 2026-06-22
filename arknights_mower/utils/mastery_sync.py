import json as _json
import os as _os
from datetime import datetime

from arknights_mower.utils.log import logger
from arknights_mower.utils.mastery_db import (
    get_pending_only,
    get_route,
    get_all_plans,
    has_train_group_plan,
    insert_plan,
)
from arknights_mower.utils.mastery_recommendation import (
    PROF_MAP,
    get_skill_data,
)
from arknights_mower.utils.path import get_path
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class MasterySync:
    def __init__(self, scheduler):
        self._scheduler = scheduler

    def sync_and_schedule(self):
        if self._scheduler.find_next_task(task_type=TaskTypes.SKILL_UPGRADE):
            logger.debug("MasterySync: queue already has SKILL_UPGRADE, skip cycle")
            return

        if has_train_group_plan():
            logger.info("MasterySync: 训练室已配置小组，跳过自动调度")
            return

        try:
            self._refresh_skland_data()
        except Exception as e:
            logger.warning(f"MasterySync: failed to refresh Skland data: {e}")

        pending = get_pending_only()

        self._auto_complete_level3(pending)

        self._check_building_training()

        remaining = get_pending_only()
        if not remaining:
            logger.debug("MasterySync: no remaining pending plans")
            return

        self._schedule_next(remaining[0])

    def _refresh_skland_data(self):
        from arknights_mower.solvers.cultivate_depot import cultivate

        cultivate().start()

    def _check_building_training(self):
        try:
            from arknights_mower.solvers.player_info import player_info_cache

            latest = player_info_cache.get("latest", {})
            training = latest.get("building_training") if isinstance(latest, dict) else None
            if training and isinstance(training.get("trainee"), dict):
                logger.info("MasterySync: building_training has trainee, inserting REFRESH_TIME")
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=datetime.now(),
                        task_type=TaskTypes.REFRESH_TIME,
                        meta_data="train",
                    )
                )
        except Exception as e:
            logger.warning(f"MasterySync: check building_training failed: {e}")

    def _auto_complete_level3(self, pending):
        cultivate_path = get_path("@app/tmp/cultivate.json")
        if not _os.path.exists(cultivate_path):
            return
        try:
            with open(cultivate_path, "r", encoding="utf-8") as f:
                cdata = _json.load(f)
        except Exception:
            return
        char_levels = {}
        for char in cdata.get("data", {}).get("characters", []):
            cid = char.get("id")
            for idx, s in enumerate(char.get("skills", [])):
                lvl = s.get("level", 0) or 0
                char_levels[f"{cid}_{idx}"] = lvl
        for p in pending:
            key = f"{p['char_id']}_{p['skill_index']}"
            lvl = char_levels.get(key, 0)
            if lvl >= 3:
                logger.info(f"MasterySync: {key} level={lvl} >= 3, marking completed")
                insert_plan(p["char_id"], p["skill_index"], "completed", level=lvl)

        in_progress = [
            p for p in get_all_plans()
            if p["status"] == "in_progress"
        ]
        if in_progress:
            active_trainee_id = None
            try:
                from arknights_mower.solvers.player_info import player_info_cache
                latest_info = player_info_cache.get("latest", {})
                training = latest_info.get("building_training") if isinstance(latest_info, dict) else None
                if training and isinstance(training.get("trainee"), dict):
                    active_trainee_id = training["trainee"].get("charId")
            except Exception:
                pass
            for p in in_progress:
                key = f"{p['char_id']}_{p['skill_index']}"
                lvl = char_levels.get(key, 0)
                if lvl >= 3:
                    logger.info(f"MasterySync: in_progress {key} level={lvl} >= 3, marking completed")
                    insert_plan(p["char_id"], p["skill_index"], "completed", level=lvl)
                elif active_trainee_id != p["char_id"]:
                    logger.warning(f"MasterySync: in_progress {key} no active training, marking failed")
                    insert_plan(p["char_id"], p["skill_index"], "failed",
                                failed_reason="训练中断（未检测到进行中的训练）")

    def _schedule_next(self, plan):
        char_id = plan["char_id"]
        skill_index = plan["skill_index"]
        char_table = get_skill_data().get("characters", {})
        char_info = char_table.get(char_id, {})
        profession_en = char_info.get("profession", "")
        prof_cn = PROF_MAP.get(profession_en, profession_en)

        route = get_route(prof_cn)
        if not route:
            msg = f"未配置 {prof_cn} 的专精路线"
            logger.warning(f"MasterySync: {msg}")
            insert_plan(char_id, skill_index, "failed", failed_reason=msg)
            return

        try:
            insert_plan(char_id, skill_index, "in_progress")

            parsed = _json.loads(route["supports"])
            supports_list = parsed.get("supports", []) if isinstance(parsed, dict) else parsed
            from arknights_mower.utils.mastery_recommendation import _supports_from_dicts
            supports = _supports_from_dicts(supports_list)
            self._scheduler.op_data.skill_upgrade_supports = supports

            name = char_info.get("name", char_id)
            sk = str(skill_index + 1)

            if supports:
                self._scheduler.tasks.append(
                    SchedulerTask(
                        task_plan={"train": [supports[0].name, name]},
                        meta_data="_mastery",
                    )
                )

            t = SchedulerTask(
                time=datetime.now(),
                task_type=TaskTypes.SKILL_UPGRADE,
                meta_data=f"{name} 技能{sk}",
                adjusted=True,
            )
            t.plan_key = f"{char_id}_{skill_index}"
            self._scheduler.tasks.insert(0, t)
            logger.info(f"MasterySync: scheduled {name} 技能{sk}")
        except Exception as e:
            logger.exception(f"MasterySync: schedule failed for {char_id}_{skill_index}: {e}")
            insert_plan(char_id, skill_index, "failed", failed_reason=str(e))
