import json as _json
import os as _os
from datetime import datetime, timedelta

from arknights_mower.utils.log import logger
from arknights_mower.utils.mastery_db import (
    get_all_plans,
    get_in_progress_plan,
    get_pending_only,
    get_route,
    has_train_group_plan,
    insert_plan,
    set_plan_status,
)
from arknights_mower.utils.mastery_recommendation import (
    PROF_MAP,
    _supports_from_dicts,
    get_skill_data,
)
from arknights_mower.utils.path import get_path
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


class MasterySync:
    def __init__(self, scheduler):
        self._scheduler = scheduler

    def sync_and_schedule(self):
        if has_train_group_plan():
            logger.info("MasterySync: 训练室已配置小组，跳过自动调度")
            return

        try:
            self._refresh_skland_data()
        except Exception as e:
            logger.warning(f"MasterySync: failed to refresh Skland data: {e}")

        # 用 Skland 数据同步 DB plan
        plan = get_in_progress_plan()
        if plan:
            from arknights_mower.solvers.player_info import player_info_cache

            latest = player_info_cache.get("latest", {})
            training = (
                latest.get("building_training") if isinstance(latest, dict) else None
            )
            logger.debug(f"MasterySync: building_training for sync: {training}")

            if training and isinstance(training.get("trainee"), dict):
                remain_secs = training.get("remainSecs", 0)
                slot_state = training.get("slotState", 0)
                trainee_char_id = training["trainee"]["charId"]

                # 训练已完成 → 跳过，由 refresh_skill_time 处理
                if remain_secs <= 0 or slot_state == 2:
                    logger.info(
                        f"MasterySync: training complete (remainSecs={remain_secs} slotState={slot_state}), skip sync"
                    )
                elif trainee_char_id != plan["char_id"]:
                    logger.warning(
                        f"MasterySync: trainee mismatch ({trainee_char_id} != {plan['char_id']}), marking failed"
                    )
                    insert_plan(
                        plan["char_id"],
                        plan["skill_index"],
                        "failed",
                        failed_reason="训练中断（干员不匹配）",
                    )
                    plan = None
                else:
                    # 更新 expires_at
                    expires_at_local = datetime.now() + timedelta(seconds=remain_secs)
                    from datetime import timezone

                    new_expires = (
                        datetime.now(timezone.utc) + timedelta(seconds=remain_secs)
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    old_expires = plan.get("expires_at")
                    if (
                        not old_expires
                        or abs(
                            datetime.fromisoformat(old_expires) - expires_at_local
                        ).total_seconds()
                        > 120
                    ):
                        set_plan_status(
                            plan["char_id"],
                            plan["skill_index"],
                            "in_progress",
                            level=plan.get("level", 1),
                            expires_at=new_expires,
                        )
                        logger.debug(
                            f"MasterySync: updated expires_at from API: {new_expires}"
                        )
            else:
                # API 没有训练数据 → 标记失败
                logger.warning(
                    "MasterySync: no building_training data, marking in_progress plan as failed"
                )
                insert_plan(
                    plan["char_id"],
                    plan["skill_index"],
                    "failed",
                    failed_reason="训练中断（未检测到进行中的训练）",
                )
                plan = None

            # cultivate.json 检测到已满级
            if plan:
                cultivate_path = get_path("@app/tmp/cultivate.json")
                if _os.path.exists(cultivate_path):
                    try:
                        with open(cultivate_path, "r", encoding="utf-8") as _f:
                            cdata = _json.load(_f)
                        for char in cdata.get("data", {}).get("characters", []):
                            if char.get("id") == plan["char_id"]:
                                skill_level = (
                                    char.get("skills", [{}])[plan["skill_index"]].get(
                                        "level", 0
                                    )
                                    or 0
                                )
                                if skill_level >= 3:
                                    logger.info(
                                        f"MasterySync: {plan['char_id']} skill already level {skill_level} >= 3, marking completed"
                                    )
                                    insert_plan(
                                        plan["char_id"],
                                        plan["skill_index"],
                                        "completed",
                                        level=skill_level,
                                    )
                                    plan = None
                                break
                    except Exception:
                        pass

        if plan:
            expires_at = plan.get("expires_at")
            if not expires_at or datetime.fromisoformat(expires_at) > datetime.now():
                # 队列中已存在 train REFRESH_TIME 时不重复插入，避免每轮空转产生重复任务
                existing = self._scheduler.find_next_task(
                    task_type=TaskTypes.REFRESH_TIME, meta_data="train"
                )
                if existing:
                    logger.debug(
                        "MasterySync: train REFRESH_TIME already in queue, skip add"
                    )
                    return
                logger.info("MasterySync: in_progress plan found, adding REFRESH_TIME")
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=datetime.now(),
                        task_type=TaskTypes.REFRESH_TIME,
                        meta_data="train",
                    )
                )
                return

        # 处理 in_progress 但 expires_at 已过的计划（重启断链兜底）
        from arknights_mower.solvers.player_info import player_info_cache

        for p in get_all_plans():
            if p.get("status") != "in_progress":
                continue
            expires_at = p.get("expires_at")
            if not expires_at:
                continue
            try:
                if datetime.fromisoformat(expires_at) > datetime.now():
                    continue
            except Exception:
                continue

            char_id = p["char_id"]
            skill_index = p["skill_index"]
            plan_level = p.get("level", 1)

            # 用 building_training API 数据确认训练是否已完成
            latest = player_info_cache.get("latest", {})
            training = (
                latest.get("building_training") if isinstance(latest, dict) else None
            )
            training_completed = False
            if training and isinstance(training.get("trainee"), dict):
                if (
                    training["trainee"]["charId"] == char_id
                    and (
                        training["trainee"]["targetSkill"] == -1
                        or training["trainee"]["targetSkill"] == skill_index
                    )
                    and (
                        training.get("remainSecs", 0) <= 0
                        or training.get("slotState", 0) == 2
                    )
                ):
                    training_completed = True
                    logger.info(
                        f"MasterySync: API confirms training completed for "
                        f"{char_id} skill{skill_index + 1}"
                    )

            if not training_completed:
                logger.warning(
                    f"MasterySync: expired plan but API shows training not complete, "
                    f"skipping: {char_id} skill{skill_index + 1}"
                )
                continue

            insert_plan(char_id, skill_index, "completed", level=plan_level)
            if plan_level < 3:
                insert_plan(char_id, skill_index, "pending", level=plan_level + 1)
                logger.info(
                    f"MasterySync: expired plan promoted: lv{plan_level} done "
                    f"→ pending(lv{plan_level + 1}) {char_id} skill{skill_index + 1}"
                )
            else:
                logger.info(
                    f"MasterySync: expired plan done: lv{plan_level} "
                    f"{char_id} skill{skill_index + 1}"
                )
        if self._scheduler.find_next_task(task_type=TaskTypes.SKILL_UPGRADE):
            logger.debug("MasterySync: queue already has SKILL_UPGRADE, skip cycle")
            return

        pending = get_pending_only()
        self._auto_complete_level3(pending)

        remaining = get_pending_only()
        if not remaining:
            logger.debug("MasterySync: no remaining pending plans")
            return

        self._schedule_next(remaining[0])

    def _refresh_skland_data(self):
        from arknights_mower.solvers.cultivate_depot import cultivate

        cultivate().start()
        from arknights_mower.solvers.player_info import PlayerInfoClient

        try:
            PlayerInfoClient().get_first_available_snapshot()
        except Exception as e:
            logger.debug(f"MasterySync: player_info snapshot failed: {e}")

    def _check_building_training(self):
        try:
            from arknights_mower.solvers.player_info import player_info_cache

            latest = player_info_cache.get("latest", {})
            training = (
                latest.get("building_training") if isinstance(latest, dict) else None
            )
            logger.debug(f"MasterySync: building_training data: {training}")
            if not training or not isinstance(training.get("trainee"), dict):
                if training is not None:
                    logger.debug(
                        f"MasterySync: building_training missing trainee, keys: {training.keys() if isinstance(training, dict) else type(training)}"
                    )
                return

            plan = get_in_progress_plan()
            if not plan:
                logger.info(
                    "MasterySync: building_training has trainee but no in_progress plan"
                )
                return
            expires_at = plan.get("expires_at")
            if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
                logger.info("MasterySync: in_progress plan expired")
                return

            char_table = get_skill_data().get("characters", {})
            char_info = char_table.get(plan["char_id"], {})
            prof_en = char_info.get("profession", "")
            prof_cn = PROF_MAP.get(prof_en, prof_en)
            route = get_route(prof_cn)
            if not route:
                return

            parsed = _json.loads(route["supports"])
            supports_list = (
                parsed.get("supports", []) if isinstance(parsed, dict) else parsed
            )
            supports = _supports_from_dicts(supports_list)
            level = plan.get("level", 1)
            support = next((s for s in supports if s.level == level), None)
            if not support:
                return

            self._scheduler.op_data.skill_upgrade_supports = supports

            if not self._scheduler.find_next_task(
                task_type=TaskTypes.REFRESH_TIME, meta_data="train"
            ):
                self._scheduler.tasks.append(
                    SchedulerTask(
                        time=datetime.now(),
                        task_type=TaskTypes.REFRESH_TIME,
                        meta_data="train",
                    )
                )

            # 从 building_training 数据或 op_data 获取当前助理
            current_assistant = self._scheduler.op_data.get_train_support()
            if current_assistant in {"逻各斯", "艾丽妮"}:
                logger.info("MasterySync: assistant already optimal, skip swap")
                return

            logger.info(
                f"MasterySync: assistant {current_assistant}, swap needed to {support.swap_name}"
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

        in_progress = [p for p in get_all_plans() if p["status"] == "in_progress"]
        if in_progress:
            for p in in_progress:
                key = f"{p['char_id']}_{p['skill_index']}"
                lvl = char_levels.get(key, 0)
                if lvl >= 3:
                    logger.info(
                        f"MasterySync: in_progress {key} level={lvl} >= 3, marking completed"
                    )
                    insert_plan(p["char_id"], p["skill_index"], "completed", level=lvl)

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
            plan_level = plan.get("level", 1)
            # 不在这里提前标记 in_progress：只有 skill_upgrade 真正读取到训练倒计时
            # （确认开始升级）后才会 set_plan_status(in_progress) 并写入 expires_at。
            # 否则训练尚未启动，MasterySync 会误判为进行中并反复添加 REFRESH_TIME。
            logger.debug(
                f"MasterySync: schedule plan char={char_id} skill={skill_index} level={plan_level}"
            )

            parsed = _json.loads(route["supports"])
            supports_list = (
                parsed.get("supports", []) if isinstance(parsed, dict) else parsed
            )
            from arknights_mower.utils.mastery_recommendation import (
                _supports_from_dicts,
            )

            supports = _supports_from_dicts(supports_list)
            self._scheduler.op_data.skill_upgrade_supports = supports

            name = char_info.get("name", char_id)
            sk = str(skill_index + 1)

            if supports and plan_level < 3:
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
            logger.exception(
                f"MasterySync: schedule failed for {char_id}_{skill_index}: {e}"
            )
            insert_plan(char_id, skill_index, "failed", failed_reason=str(e))
