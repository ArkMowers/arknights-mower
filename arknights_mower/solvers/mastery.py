import json
from datetime import datetime, timedelta

from arknights_mower.solvers.mastery_reader import (
    RoomPanel,
    RoomState,
    _count_lit_mastery_icons,
    _notify_at_target,
    _plan_label,
    _plan_matches_room,
    _read_panel_text,
    _read_slots,
    _read_train_countdown,
    _schedule_collect,
    _target_label,
    _wait_for_training,
    read_main_panel,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene

ARRANGING_DEADLINE = timedelta(minutes=5)
ARRANGING_RETRY_BUFFER = timedelta(minutes=2)
# #81（2026-08-15 用户拍板）：SWAP 换人失败最多重试次数（无 +5min 间隔，立刻原地重试；
# 每次重试都重读倒计时判还值不值得换，倒计时只会减少，终会到「不足 5 小时」放弃）
SWAP_RETRY_LIMIT = 5

DEFAULT_ROUTES = {
    "先锋": {
        "level_1": {
            "operator": "夜半",
            "efficiency": 75,
            "job_match": False,
            "swap_target": "逻各斯",
        },
        "level_2": {
            "operator": "缄默德克萨斯",
            "efficiency": 80,
            "job_match": False,
            "swap_target": "逻各斯",
        },
        "level_3": {
            "operator": "凛御银灰",
            "efficiency": 80,
            "job_match": False,
            "swap_target": None,
        },
    },
    "近卫": {
        "level_1": {
            "operator": "赤冬",
            "efficiency": 75,
            "job_match": True,
            "swap_target": "艾丽妮",
        },
        "level_2": {
            "operator": "燧石",
            "efficiency": 75,
            "job_match": True,
            "swap_target": "艾丽妮",
        },
        "level_3": {
            "operator": "百炼嘉维尔",
            "efficiency": 95,
            "job_match": True,
            "swap_target": None,
        },
    },
    "重装": {
        "level_1": {
            "operator": "极光",
            "efficiency": 75,
            "job_match": False,
            "swap_target": "逻各斯",
        },
        "level_2": {
            "operator": "暴雨",
            "efficiency": 75,
            "job_match": False,
            "swap_target": "逻各斯",
        },
        "level_3": {
            "operator": "星熊",
            "efficiency": 60,
            "job_match": False,
            "swap_target": None,
        },
    },
    "狙击": {
        "level_1": {
            "operator": "假日威龙陈",
            "efficiency": 95,
            "job_match": True,
            "swap_target": "艾丽妮",
        },
        "level_2": {
            "operator": "埃拉托",
            "efficiency": 75,
            "job_match": True,
            "swap_target": "艾丽妮",
        },
        "level_3": {
            "operator": "W",
            "efficiency": 95,
            "job_match": True,
            "swap_target": None,
        },
    },
    "术师": {
        "level_1": {
            "operator": "特米米",
            "efficiency": 75,
            "job_match": True,
            "swap_target": "逻各斯",
        },
        "level_2": {
            "operator": "薄绿",
            "efficiency": 75,
            "job_match": True,
            "swap_target": "逻各斯",
        },
        "level_3": {
            "operator": "死芒",
            "efficiency": 95,
            "job_match": True,
            "swap_target": None,
        },
    },
    "医疗": {
        "level_1": {
            "operator": "阿",
            "efficiency": 60,
            "job_match": False,
            "swap_target": "逻各斯",
        },
        "level_2": {
            "operator": "濯尘芙蓉",
            "efficiency": 75,
            "job_match": False,
            "swap_target": "逻各斯",
        },
        "level_3": {
            "operator": "阿",
            "efficiency": 60,
            "job_match": False,
            "swap_target": None,
        },
    },
    "辅助": {
        "level_1": {
            "operator": "铃兰",
            "efficiency": 60,
            "job_match": True,
            "swap_target": "逻各斯",
        },
        "level_2": {
            "operator": "铃兰",
            "efficiency": 60,
            "job_match": True,
            "swap_target": "逻各斯",
        },
        "level_3": {
            "operator": "浊心斯卡蒂",
            "efficiency": 95,
            "job_match": True,
            "swap_target": None,
        },
    },
    "特种": {
        "level_1": {
            "operator": "罗宾",
            "efficiency": 75,
            "job_match": False,
            "swap_target": "逻各斯",
        },
        "level_2": {
            "operator": "缄默德克萨斯",
            "efficiency": 80,
            "job_match": False,
            "swap_target": "逻各斯",
        },
        "level_3": {
            "operator": "归溟幽灵鲨",
            "efficiency": 95,
            "job_match": False,
            "swap_target": None,
        },
    },
}

PROF_MAP = {
    "PIONEER": "先锋",
    "WARRIOR": "近卫",
    "TANK": "重装",
    "SNIPER": "狙击",
    "CASTER": "术师",
    "MEDIC": "医疗",
    "SUPPORT": "辅助",
    "SPECIAL": "特种",
}


def get_route_config(profession_cn: str, level: int) -> dict | None:
    from arknights_mower.utils.mastery_db import get_route

    route_data = get_route(profession_cn)
    if route_data:
        parsed = json.loads(route_data["supports"])
        level_key = f"level_{level}"
        if level_key in parsed:
            config_entry = dict(parsed[level_key])
            config_entry["central_bonus"] = parsed.get("central_bonus", 5)
            return config_entry

    default = DEFAULT_ROUTES.get(profession_cn)
    if default:
        entry = default.get(f"level_{level}")
        if entry:
            config_entry = dict(entry)
            config_entry["central_bonus"] = 5
            return config_entry
    return None


def get_char_name(char_id: str) -> str:
    """从 char_id 获取干员显示名"""
    try:
        from arknights_mower.utils.mastery_recommendation import get_skill_data

        char_table = get_skill_data().get("characters", {})
        return char_table.get(char_id, {}).get("name", char_id)
    except Exception:
        return char_id


def _plan_char_label(plan) -> str:
    """邮件/日志里的干员标识：优先库里的 char_name，回退 get_char_name(char_id)。

    #53 根因3：旧文案用 skill_name（技能名，如「战地秘闻」）冒充干员名，
    邮件读不出练谁。计划经 add_mastery_plan 工具新增时 char_name 为 NULL，
    需要 get_char_name 兜底。
    """
    return plan.get("char_name") or get_char_name(plan["char_id"])


def calc_swap_threshold(
    current_efficiency: int,
    swap_job_match: bool,
    central_bonus: int,
    remaining_minutes: float,
    buffer: int = 10,
) -> tuple[bool, float]:
    """计算是否应该换入减半对象。

    Args:
        current_efficiency: 当前协助位效率百分比 (如 75)
        swap_job_match: 减半对象是否有职业匹配加成 (+30%)
        central_bonus: 中枢加成 (0 或 5)
        remaining_minutes: 当前倒计时剩余分钟数
        buffer: 缓冲时间(分钟)

    Returns:
        (should_swap, threshold_minutes)
        should_swap: 是否应该换人
        threshold_minutes: 换人阈值（倒计时降到这个值时执行换人）
    """
    target_minutes = 300 + buffer  # 5小时 + 缓冲

    swap_match_bonus = 30 if swap_job_match else 0
    swap_total = 100 + 5 + swap_match_bonus + central_bonus
    current_total = 100 + current_efficiency + 5 + central_bonus

    threshold = target_minutes * swap_total / current_total

    real_time_after_swap = remaining_minutes * current_total / swap_total
    if real_time_after_swap < 301:
        return False, threshold

    return remaining_minutes <= threshold, threshold


def _log_transition(plan, to_status, trigger, **fields):
    """#17 埋点①：状态机转换的结构化日志（统一 [mastery] 前缀）。

    仅记录不改变行为；真实状态更新仍走 update_plan_status。
    """
    parts = [
        f"id={plan['id']}",
        f"{plan.get('status')}→{to_status}",
        f"触发源={trigger}",
    ]
    parts.extend(f"{k}={v}" for k, v in fields.items())
    logger.info(f"[mastery] 状态转换 {' '.join(parts)}")


def run_mastery_task(solver):
    """SKILL_UPGRADE dispatch：共享读取器进房读全部 + #61 矩阵对账执行。

    读取器返回需要开始训练的计划时，由本入口执行开始（长动作）。
    不再依赖 DB 状态预判（铁律：先读房，截图为准）。

    # #74 第3段：任务带 plan_key 时解析其指定计划为 scan_plan——任何带 plan_key 的
    SKILL_UPGRADE 任务（扫描开始/收取/重检）在空闲×未保护格都会让该计划开始训练
    （2026-08-14 用户拍板「都去掉」：不再区分扫描标记；开始/继续一律当场）。房间状态
    决定分支：空闲→开始、待收取→收集+继续本级当场开、训练中→对账。
    """
    from arknights_mower.utils import config

    if not config.conf.enable_mastery:
        logger.debug("[mastery] 全自动专精已关闭，跳过训练室动作")
        return
    from arknights_mower.solvers.mastery_reader import reconcile_and_act
    from arknights_mower.utils.mastery_db import get_plan_by_id

    # 任务指定计划：plan_key=计划id 即该计划。计划是否仍 idle 由 `_reconcile` 空闲格
    # 统一判定（单一权威）。plan_key=None（占用重检）无指定计划，空闲格不开训练。
    scan_plan = None
    task = getattr(solver, "task", None)
    plan_key = getattr(task, "plan_key", None) if task is not None else None
    if plan_key is not None:
        try:
            scan_plan = get_plan_by_id(int(plan_key))
        except (TypeError, ValueError):
            scan_plan = None

    logger.debug("[mastery] 训练室动作 触发源=定时任务 动作=dispatch")
    plan, arrange_support = reconcile_and_act(solver, scan_plan=scan_plan)
    if plan:
        _start_new_training(solver, plan, arrange_support=arrange_support)


def _training_slots(solver):
    """读训练室两个槽位的干员名，返回 (协助位, 训练位)。

    槽位约定（与 choose_train 基类一致，#53 从实机 log 佐证）：
    - scan[0] = 上排 = 协助位；scan[1] = 下排 = 训练位
      （get_agent_from_room 与 operator_list_train 的 name_y 均为 上→下）
    - choose_train 内部 idx==0 走 choose_agent（协助位）、idx==1 走
      choose_train_ope（训练位），get_agent_from_room 的 scan 与之同序
    - 现有调用佐证：_arrange_support / run_swap_support 传
      choose_train([协助干员, "Current"])，都把 idx0 当协助位
    读不到名字的槽位返回 ""。
    """
    scan = solver.get_agent_from_room("train")
    if len(scan) < 2:
        return "", ""
    return scan[0].get("agent", ""), scan[1].get("agent", "")


def _swap_into_wrong_slot(solver, plan):
    """无倒计时 + 训练位坐错人：复用 choose_train 换人。

    #16 决议「协助位不动」：只换训练位，传 ["Current", 训练位目标]
    （idx0=Current 保持协助位原样，idx1=训练位换入计划干员）；
    开始训练前不改协助位（设计规范 §8）。
    以 choose_train 异常为唯一失败信号；失败由调用方统一走失败出口。
    """
    solver.choose_train(["Current", _plan_char_label(plan)])


def _exit_failed(solver, plan, reason):
    """ARRANGING 失败统一出口：标记 failed + 一次通知 + 退出训练室，不在 ARRANGING 内重试。"""
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import update_plan_status

    update_plan_status(plan["id"], "failed", failed_reason=reason)
    label = f"{_plan_char_label(plan)} 技能{plan['skill_index'] + 1} 专{plan['target_level']}"
    send_message(f"{label} {reason}", level="ERROR")
    solver.back()


def _exit_arranging_timeout(solver, plan, stats, stuck_scene):
    """#15 决议的统一超时出口：标记 failed + 可读失败原因 + 一次通知 + 结构化轨迹诊断。

    用户已定案（#19 实现时与 #15「置 idle」矛盾）：置 failed，避免 infra 主循环
    （base_schedule.py:705 对 idle 计划立即重派）导致每 10 分钟重复超时刷屏；
    等仓库扫描 retry_failed_plans() 重置。
    """
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import update_plan_status

    scene_name = _scene_name(stuck_scene) if stuck_scene is not None else "无"
    reason = "开始训练超时，未能确认训练是否开始"
    # #17 埋点⑤：超时兜底记录（#15 定纯墙钟、无加载豁免，字段恒 false 保留）
    logger.warning(
        f"[mastery] ARRANGING超时 id={plan['id']} 豁免加载=False 卡在={scene_name} "
        f"原因={reason}"
    )
    update_plan_status(plan["id"], "failed", failed_reason=reason)
    label = f"{_plan_char_label(plan)} 技能{plan['skill_index'] + 1} 专{plan['target_level']}"
    logger.warning(
        f"ARRANGING 超时退出: {reason} | 诊断: 最后持续停留在『{scene_name}』页面 | "
        f"轨迹: {stats}"
    )
    send_message(
        f"{label}：开始训练超时，最后持续停留在『{scene_name}』页面，未能确认训练是否开始，"
        "已暂停，将在下次仓库扫描后重试",
        level="ERROR",
    )
    solver.back()


class _SceneTracker:
    """ARRANGING 超时诊断的廉价轨迹计数器（#15 决议）。"""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.last = None
        self.consecutive = {"scene": None, "count": 0}
        self.max_consecutive = {"scene": None, "count": 0}
        self.reenter_cnt = 0
        self.reached_upgrade = False

    def record(self, scene):
        name = _scene_name(scene)
        self.counts[name] = self.counts.get(name, 0) + 1
        if scene != self.last:
            self.consecutive = {"scene": name, "count": 0}
            self.last = scene
        self.consecutive["count"] += 1
        if self.consecutive["count"] > self.max_consecutive["count"]:
            self.max_consecutive = dict(self.consecutive)

    def mark_upgrade(self):
        self.reached_upgrade = True

    def reenter(self):
        self.reenter_cnt += 1

    def last_scene(self):
        return self.last

    def stuck_scene(self):
        """最长连续停留的场景名，用于「卡在哪」的诊断。"""
        return self.max_consecutive["scene"]

    def format_stats(self) -> str:
        dominant = max(self.counts, key=self.counts.get) if self.counts else "无"
        return (
            f"各场景次数 {self.counts} | 最后场景 {self.consecutive['scene']} | "
            f"最大连续 {self.max_consecutive['scene']}×{self.max_consecutive['count']} | "
            f"到过确认页 {self.reached_upgrade} | 重进房 {self.reenter_cnt} | 主导 {dominant}"
        )


def _scene_name(scene) -> str:
    for key, value in Scene.__dict__.items():
        if not key.startswith("_") and value == scene:
            return key
    return str(scene)


def _exit_occupied(solver, plan, countdown, trigger="训练室占用"):
    """训练室被占用 → 保持 idle + 重排 + 退出（#16/#69/B4/#70 共用）。

    countdown 可读时重排到倒计时+缓冲；不可读（面板归属与计划不符 / 已到target
    档位读取失败）时重排到 now+缓冲，避免占用期间每轮 dispatch 空转重试。
    trigger 写进状态转换日志，区分退出原因。
    """
    from arknights_mower.solvers.mastery_reader import _upsert_skill_upgrade_task
    from arknights_mower.utils.mastery_db import update_plan_status

    if countdown is not None and countdown > datetime.now():
        _wait_for_training(
            solver, RoomState("training", RoomPanel(countdown=countdown))
        )
        reschedule = countdown + ARRANGING_RETRY_BUFFER
    else:
        reschedule = datetime.now() + ARRANGING_RETRY_BUFFER
        _upsert_skill_upgrade_task(solver, reschedule)
    _log_transition(plan, "idle", trigger, 重排到=reschedule.strftime("%H:%M:%S"))
    update_plan_status(plan["id"], "idle")
    solver.back()


def _start_new_training(solver, plan, arrange_support=True):
    """开始新一级训练：IDLE → ARRANGING → TRAINING

    #16 决议：进房先读倒计时定分支，不盲点技能按钮。
    #15 决议：全程纯墙钟 5 分钟 deadline，各分支短处理、超时走统一退出路径。
    #63 减半守卫：跨「收取→下一次开始」边界不动协助位（保留驻留/激活），
    调用方在「收取→下一次开始」边界传 arrange_support=False（收取后不重新安排协助位）。
    """
    from arknights_mower.solvers.mastery_reader import _read_slot_mastery_tier
    from arknights_mower.utils.mastery_db import update_plan_status

    _log_transition(
        plan,
        "arranging",
        "定时任务",
        技能=plan["skill_index"] + 1,
        目标=plan["target_level"],
    )
    update_plan_status(plan["id"], "arranging")

    skill_index = plan["skill_index"] + 1  # 0-indexed to 1-indexed for display
    deadline = datetime.now() + ARRANGING_DEADLINE
    unknown_cnt = 0
    # #15 诊断粒度：各场景次数 / 最后场景 / 是否到过确认页 / 重进房次数 / 最大连续同场景
    tracker = _SceneTracker()
    checked_slot = False
    checked_target = False
    # #72：数星星前的身份/归属确认。只在 TRAIN_MAIN 训练位校验通过并主动点开技能
    # 选择页时置位；未置位就出现 219（运行页被误判成 219 等）→ 219 分支保守退出。
    identity_confirmed = False

    solver.enter_room("train")

    while True:
        scene = solver.train_scene()
        tracker.record(scene)

        if scene == Scene.UNKNOWN:
            unknown_cnt += 1
            if unknown_cnt > 5:
                unknown_cnt = 0
                solver.back_to_infrastructure()
                solver.enter_room("train")
                tracker.reenter()
            else:
                solver.sleep()
        elif scene == Scene.CONNECTING:
            solver.sleep()
        elif scene == Scene.INFRA_MAIN:
            solver.enter_room("train")
        elif scene == Scene.INFRA_DETAILS:
            # 房间详情浮层（get_agent_from_room 会打开它）→ 关掉回房间主界面
            solver.back()
        elif scene == Scene.TRAIN_FINISH:
            solver.tap((solver.recog.w * 0.05, solver.recog.h * 0.95), interval=0.5)
        elif scene == Scene.TRAIN_MAIN:
            execute_time = _read_train_countdown(solver)
            if execute_time is not None and execute_time > datetime.now():
                # 训练室使用中（#16 决议）：保持 idle，重排到倒计时+缓冲，退出
                _exit_occupied(solver, plan, execute_time)
                return
            if not checked_slot:
                # 无倒计时：检查训练位是否坐错人（#16 决议）。
                # get_agent_from_room 会打开房间详情浮层，读完后关掉再回主界面。
                support_slot, trainer_slot = _training_slots(solver)
                checked_slot = True
                char_name = _plan_char_label(plan)
                if trainer_slot and trainer_slot != char_name:
                    # 无倒计时 + 训练位坐错人 → 换人；失败统一以 choose_train 异常为判据
                    logger.info(f"训练位坐着 {trainer_slot}，换入 {char_name}")
                    try:
                        _swap_into_wrong_slot(solver, plan)
                    except Exception as e:
                        logger.warning(f"换人失败: {e}")
                        _exit_failed(solver, plan, "训练位被占用且换人失败")
                        return
                solver.back()  # 关闭房间详情浮层，回到训练室主界面
                continue
            # 训练位已确认（空/已是计划干员）→ 身份确认成立，点开技能选择页。
            # #72：数星星前唯一合法的身份/归属确认点——经训练位校验后主动进入技能
            # 选择页；运行页被误判成 219（不经此路径）在 219 分支直接保守退出。
            identity_confirmed = True
            solver.tap((solver.recog.w * 0.05, solver.recog.h * 0.95), interval=0.5)
        elif scene == Scene.TRAIN_SKILL_SELECT:
            if not identity_confirmed:
                # #72：真技能选择页只有 SKILL_SLOT_PIPS 星星可读，没有倒计时、读不到
                # `[干员名]技能名`——不能在 219 上读主面板区域（COUNTDOWN/PANEL）当占用
                # 探针（那只在"运行页被误判成 219"时才成立）。未经过 TRAIN_MAIN 训练位
                # 校验就出现 219 → 数星星前无法确认干员身份，星星可能误读非零值
                # （误开训练/误判完成，#70 只挡 None）→ 保守保持 idle 重排退出。
                logger.info(
                    f"{_plan_char_label(plan)} 技能选择页未经过训练位确认，"
                    "无法确认星星归属，保持 idle 重排"
                )
                _exit_occupied(solver, plan, None, trigger="技能选择页归属未确认")
                return
            if not checked_target:
                # #63 已到target检测：读目标技能槽亮灯，≥target → 判 completed（防 false-fail）
                checked_target = True
                tier = _read_slot_mastery_tier(solver, plan["skill_index"])
                if tier is not None and tier >= plan["target_level"]:
                    logger.info(
                        f"{_plan_char_label(plan)} 技能{skill_index} 已在专{tier}，无需训练，判定完成"
                    )
                    _log_transition(plan, "completed", "已到target检测", 档位=tier)
                    update_plan_status(plan["id"], "completed")
                    _notify_at_target(solver, plan, tier)  # §16.9 ⑥
                    # #74 第2段：完成不再级联开始下一个 idle 计划（等扫描派发）
                    solver.back()
                    return
                if tier is None:
                    # #70/B5：档位读失败（无法判是否已到 target）→ 保守处理：保持
                    # idle 重排退出，绝不盲点技能行（可能重训已完成的档位）。
                    logger.info(
                        f"{_plan_char_label(plan)} 技能{skill_index} 专精档位读取失败，"
                        "无法确认是否已到目标档位，保持 idle 重排"
                    )
                    _exit_occupied(solver, plan, None, trigger="档位读取失败")
                    return
            height = (skill_index - 1) * 0.3 + 0.32
            solver.ctap((solver.recog.w * 0.33, solver.recog.h * height))
        elif scene == Scene.TRAIN_SKILL_UPGRADE:
            tracker.mark_upgrade()
            # #53 实机：确认按钮在 (1574,896)-(1870,968)，旧坐标 (0.87w,0.9h)=(1670,972)
            # 会点到按钮下方、把弹窗关掉退回技能选择页死循环。用 skill_confirm 模板
            # 定位按钮中心再点；找不到时退回旧坐标兜底。
            confirm = solver.find("skill_confirm")
            if confirm:
                solver.tap(confirm)
            else:
                solver.tap((solver.recog.w * 0.87, solver.recog.h * 0.9))
            solver.sleep(2)
            result = _confirm_training_started(solver, plan, deadline, arrange_support)
            if result == "started":
                return
            if result == "failed":
                return
        elif scene == Scene.TRAIN_SKILL_UPGRADE_ERROR:
            msg = f"{_plan_char_label(plan)} 技能{skill_index} 专{plan['target_level']} 材料不足"
            logger.warning(msg)
            _log_transition(plan, "failed", "材料不足")
            update_plan_status(plan["id"], "failed", failed_reason="材料不足")
            from arknights_mower.utils.email import send_message

            send_message(msg, level="ERROR")
            solver.back()
            return
        else:
            solver.sleep()

        if datetime.now() > deadline:
            _exit_arranging_timeout(
                solver, plan, tracker.format_stats(), tracker.stuck_scene()
            )
            return


def _confirm_training_started(solver, plan, deadline, arrange_support=True):
    """确认训练已开始（读到有效倒计时）→ 转入 TRAINING，然后安排协助位。

    并入 #15 的全局 10 分钟 deadline（由调用方传入），不单独分段计时。
    返回 "started" / "failed" / "timeout"：
    - started: 已转入 TRAINING 并完成协助位/收取安排
    - failed: 材料不足 或 #69/B2 面板干员/技能与计划不符，已标记 failed + 通知 + 退出训练室
    - timeout: deadline 内未确认训练开始（含面板不可读无法校验归属），由调用方走统一超时出口
    #63 减半守卫：arrange_support=False（收取后级联）不重新安排协助位。
    """
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import update_plan_status

    while datetime.now() < deadline:
        scene = solver.train_scene()
        # #53 实机：确认升级后训练已开始，但训练运行页会被识别成 TRAIN_SKILL_SELECT
        # （页面含协助位 training_support、不匹配 train_main）。#72 页面模型：这里出现
        # 的 219 是「运行页被误判」（物理上仍是主页面，倒计时/面板可读）——读倒计时是确认
        # 训练开始的正当读取，不是探针；真技能选择页无倒计时，读不到返回 now，
        # >now+30min 判定必为假 → 继续等（训练未开始），直到 deadline 走统一失败出口。
        if scene in (Scene.TRAIN_MAIN, Scene.TRAIN_SKILL_SELECT):
            execute_time = _read_train_countdown(solver)
            if execute_time and execute_time > datetime.now() + timedelta(minutes=30):
                # #69/B2 归属校验：写入 training 前，面板干员/技能必须与计划一致。
                # - 面板可读且不符 → 本次开始失败（绝不把陌生人的倒计时写进计划）；
                # - 面板可读且匹配 → 确认训练开始；
                # - 面板不可读（OCR 失败）→ 不写 training，继续等到 deadline（超时走
                #   统一失败出口），避免在无法确认归属时宣布"错误干员开始训练"。
                panel = _read_panel_text(solver)
                if panel.operator_name and not _plan_matches_room(
                    plan, RoomState("training", panel)
                ):
                    _exit_failed(
                        solver, plan, "训练室面板干员/技能与计划不符，未开始训练"
                    )
                    return "failed"
                if not panel.operator_name:
                    logger.debug(
                        "训练室已出有效倒计时但面板干员名不可读，暂不写入 training，等待归属可读"
                    )
                    solver.sleep(1)
                    continue
                expires_at = execute_time.strftime("%Y-%m-%d %H:%M:%S")
                _log_transition(plan, "training", "倒计时确认", 完成时间=expires_at)
                update_plan_status(
                    plan["id"],
                    "training",
                    expires_at=expires_at,
                    swap_frozen=0,
                )
                remaining_hours = (execute_time - datetime.now()).total_seconds() / 3600
                msg = (
                    f"{_plan_char_label(plan)} 技能{plan['skill_index'] + 1} "
                    f"专{plan['target_level']} 开始训练，预计 {remaining_hours:.1f} 小时后完成"
                )
                logger.info(msg)
                send_message(msg, level="INFO")

                # #76：主面板专精图标在训练中 = 当前步目标级（亮 N 颗=专N）。确认开始
                # 后先读图标作当前步级，传给协助位/换人安排（专三计划专一/专二步用
                # level_1/2 路线减半换人）；同值复用作收取任务目标档位（原 tier）。
                # 运行页会被识别成 TRAIN_SKILL_SELECT（#53/#72：含 training_support、
                # 不匹配 train_main），但物理上仍是主页面——此分支已确认倒计时有效，
                # 217/219 都在主页面，图标可读。
                step_level = None
                if scene in (Scene.TRAIN_MAIN, Scene.TRAIN_SKILL_SELECT):
                    try:
                        step_level = _count_lit_mastery_icons(solver)
                    except Exception:
                        step_level = None
                if arrange_support:
                    _arrange_support(solver, plan, step_level)
                # §16.10：排了换人任务则不排收取；等 SWAP_SUPPORT 完成后重读倒计时再排收取。
                swap_scheduled = _schedule_swap_if_needed(
                    solver, plan, execute_time, step_level
                )
                if not swap_scheduled:
                    _schedule_collect(solver, plan, execute_time, tier=step_level)
                return "started"
        elif scene == Scene.TRAIN_SKILL_UPGRADE_ERROR:
            msg = f"{_plan_char_label(plan)} 技能{plan['skill_index'] + 1} 专{plan['target_level']} 材料不足"
            _log_transition(plan, "failed", "材料不足")
            update_plan_status(plan["id"], "failed", failed_reason="材料不足")
            logger.warning(msg)
            send_message(msg, level="ERROR")
            solver.back()
            return "failed"
        solver.sleep(1)

    return "timeout"


def _arrange_support(solver, plan, step_level=None):
    """训练确认开始后，安排协助位干员（复用 choose_train）

    #76：路线按当前步目标级加载（step_level，确认时读主面板图标）；
    step_level 读不到回退 target_level（保守用整体目标路线）。
    """
    from arknights_mower.utils import config

    if config.conf.assistant_follows_schedule:
        return
    route = _get_plan_route(plan, step_level)
    if not route or not route.get("operator"):
        return
    support_name = route["operator"]
    logger.info(f"安排协助位：{support_name}")
    logger.debug(f"[mastery] 协助位判定 id={plan['id']} 期望={support_name} 动作=安排")
    try:
        solver.choose_train([support_name, "Current"])
        logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=ok")
    except Exception as e:
        logger.warning(f"安排协助位失败: {e}")
        logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=失败 err={e}")


def _schedule_swap_if_needed(solver, plan, execute_time, step_level=None) -> bool:
    """训练开始后计算是否需要换人，需要则插入 SWAP_SUPPORT 任务。

    §16.10：返回是否排了换人任务——排了则不排收取（等 SWAP_SUPPORT 完成后重读
    倒计时再排收取）。立即换人（remaining ≤ threshold）也排任务（修旧 silent-drop）。
    #76：路线按当前步目标级加载（step_level）；「专三不换人」由 level_3 路线
    swap_target=None 保证（铁律 7，用户 08-15 定案删显式 ==3 守卫、靠路线数据）。
    """
    from arknights_mower.utils import config

    if config.conf.assistant_follows_schedule:
        return False

    route = _get_plan_route(plan, step_level)
    if not route or not route.get("swap_target"):
        return False

    central_bonus = route.get("central_bonus", 5)
    buffer = config.conf.mastery_swap_buffer

    remaining = (execute_time - datetime.now()).total_seconds() / 60
    should_swap, threshold = calc_swap_threshold(
        route["efficiency"],
        route.get("job_match", False),
        central_bonus,
        remaining,
        buffer,
    )
    logger.info(
        f"[mastery] 换人公式 id={plan['id']} 效率={route['efficiency']} "
        f"匹配={route.get('job_match', False)} 加成={central_bonus} "
        f"剩余分钟={remaining:.0f} 阈值={threshold:.0f} 换人={should_swap}"
    )

    if should_swap:
        swap_time = datetime.now()
    elif remaining > threshold:
        swap_delay_seconds = (remaining - threshold) * 60
        if swap_delay_seconds <= 0:
            return False
        swap_time = datetime.now() + timedelta(seconds=swap_delay_seconds)
    else:
        return False

    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    task = SchedulerTask(
        time=swap_time,
        task_type=TaskTypes.SWAP_SUPPORT,
        meta_data=(
            f"{_plan_label(plan)} → {_target_label(plan['target_level'])} "
            f"换入{route['swap_target']}"
        ),
    )
    # #77 补排去重键（与 SKILL_UPGRADE 同形）：reconcile 恢复 / 重试都按 plan_key 去重
    task.plan_key = str(plan["id"])
    solver.tasks.append(task)
    logger.info(f"已安排换人任务，预计 {swap_time.strftime('%H:%M:%S')} 执行")
    return True


def run_swap_support(solver):
    """被 SWAP_SUPPORT 任务触发：换入减半对象

    #76：换人前进房读主面板专精图标 = 当前步目标级（亮 N 颗=专N），路线按当前步
    加载——专三计划的专一/专二步也减半换人，专三步由 level_3 路线 swap_target=None
    挡住（铁律 7，用户 08-15 定案靠路线数据）。SWAP 任务只为非专三步排（level_1/2
    路线有 swap_target），正常路径不会为专三步进房空转；跨步残留的旧 swap 按当前步
    判（自纠错）。读失败/不在训练主页面回退 target_level（保守不换）。
    #78 整合：换人前先读全（read_main_panel 一次截图）确认训练——场景必须在训练室
    主页面（TRAIN_MAIN，219=技能选择页读不出倒计时、不再放行）且倒计时非 0 非空
    （countdown_state=="active"）才算训练确认，才读图标/算路线/换人（铁律 1）。
    #79：读全后开进驻浮窗（_read_slots）读实际协助位——协助位 ∉ {operator,
    swap_target}（陌生人/坐错）先 choose_train 纠错成 operator，纠错成功重读倒计时
    （此时效率已知 = route["efficiency"]）才算换人；纠错失败 → 邮件通知 + 不换人 +
    排收取退出。协助位已 = swap_target（已减半）→ 不再换、不置 swap_frozen。
    换人公式/路线沿用稳定方案，只加协助位确认 + 倒计时门。
    """
    from arknights_mower.utils import config
    from arknights_mower.utils.mastery_db import get_active_plan

    logger.debug("[mastery] 训练室动作 触发源=定时任务 动作=swap")
    if not config.conf.enable_mastery:
        logger.debug("[mastery] 全自动专精已关闭，跳过换协助位")
        return
    if config.conf.assistant_follows_schedule:
        return

    plan = get_active_plan()
    if not plan or plan["status"] != "training":
        return
    if plan["swap_frozen"]:
        return

    # 进房读全：read_main_panel 一次截图读干员/技能/图标/倒计时。倒计时 active（读到
    # 非 0 秒）才算训练确认；zero(00:00:00 待收取)/failed(读失败) 都不换（DB 过期或
    # 空房）。场景只在训练室主页面才换——219 是技能选择页读不出倒计时，天然被门挡住。
    solver.enter_room("train")
    scene = solver.train_scene()
    if scene == Scene.INFRA_DETAILS:
        solver.back()
        scene = solver.train_scene()
    panel = None
    if scene == Scene.TRAIN_MAIN:
        try:
            panel = read_main_panel(solver)
        except Exception as e:
            logger.debug(f"主面板读取失败: {e}")
    countdown_active = bool(panel is not None and panel.countdown_state == "active")
    step_level = panel.mastery_tier if panel is not None else None

    route = _get_plan_route(plan, step_level)
    operator = route.get("operator") if route else None
    swap_target = route.get("swap_target") if route else None

    # #79 协助位确认：开进驻浮窗读实际协助位（_read_slots 读后自动关浮窗回主页面）。
    # 协助位 ∉ {operator, swap_target}（陌生人/读不到）→ 先纠错成 operator，换完再
    # 读一遍（此时效率已知 = route["efficiency"]）才算换人。
    support_slot, _ = _read_slots(solver)
    if support_slot and support_slot not in (operator, swap_target):
        logger.info(f"协助位坐着 {support_slot}，纠错为 {operator}")
        logger.debug(f"[mastery] 协助位纠错 id={plan['id']} 期望={operator} 动作=纠错")
        try:
            solver.choose_train([operator, "Current"])
        except Exception as e:
            logger.warning(f"协助位纠错失败: {e}")
            logger.debug(f"[mastery] 协助位纠错 id={plan['id']} 结果=失败 err={e}")
            _notify_swap_correction_failed(solver, plan, support_slot, operator)
            _schedule_collect_after_swap(solver, plan)
            solver.back()
            return
        logger.debug(f"[mastery] 协助位纠错 id={plan['id']} 结果=ok")
        support_slot = operator
        # 纠错消耗时间 → 重读倒计时（铁律 1 动作前先读房）
        scene = solver.train_scene()
        if scene == Scene.INFRA_DETAILS:
            solver.back()
            scene = solver.train_scene()
        panel = None
        if scene == Scene.TRAIN_MAIN:
            try:
                panel = read_main_panel(solver)
            except Exception as e:
                logger.debug(f"主面板重读失败: {e}")
        countdown_active = bool(panel is not None and panel.countdown_state == "active")
        step_level = panel.mastery_tier if panel is not None else None
        route = _get_plan_route(plan, step_level)
        swap_target = route.get("swap_target") if route else None

    # #80：换人前用当前倒计时判「值不值得换」（_swap_worthwhileness = calc_swap_threshold
    # 的 301 守卫，换后真实剩余 <5h 不值得）——纠错任务由 reconcile 排（排程时不做值得
    # 判定，专三/时间不足的步也纠），派发到这里仍要守住「纠错不触发不该发生的减半换人」
    # （#80 acceptance 2）；正常减半任务排程时已判值得，这里复查只更保守，无回归。
    worth_swap = True
    if panel is not None and panel.countdown is not None and route:
        remaining = (panel.countdown - datetime.now()).total_seconds() / 60
        worth_swap = _swap_worthwhileness(remaining, route)
    did_swap = bool(
        scene == Scene.TRAIN_MAIN
        and countdown_active
        and swap_target
        and support_slot != swap_target  # 已减半（协助位已是 swap_target）不再换
        and worth_swap
    )
    if did_swap:
        logger.info(f"执行换人：协助位换入 {swap_target}")
        logger.debug(
            f"[mastery] 协助位判定 id={plan['id']} 期望={swap_target} 动作=换入减半对象"
        )
        did_swap = _try_swap(solver, plan, swap_target)
        if not did_swap:
            # #81：立刻原地重试（无 +5min 间隔），至多 SWAP_RETRY_LIMIT 次；放弃 → ⑧
            # 通知，不置 swap_frozen（接受下次进房重排，暂时性失败可被救回）
            did_swap = _retry_swap_in_place(solver, plan, route, swap_target)
    else:
        logger.info(
            "场景不在训练主页面或倒计时未确认，跳过减半换人"
            if not countdown_active
            else "当前步路线无换人目标、协助位已是减半对象或剩余不足，跳过减半换人"
        )
    # §16.10：无论换人成功与否/是否跳过，重读倒计时再排收取——开始训练时「排了换人
    # 任务则不排收取」，收集只能靠这里补；跳过换人也补排（防读图标失败/不在主页面丢收集）。
    _schedule_collect_after_swap(solver, plan)
    if not did_swap:
        solver.back()


def _try_swap(solver, plan, swap_target) -> bool:
    """换入减半对象：choose_train + 置 swap_frozen。成功 True，抛异常 False。

    #81：run_swap_support 首试与 _retry_swap_in_place 重试共用同一换人动作与日志。
    """
    from arknights_mower.utils.mastery_db import update_plan_status

    try:
        solver.choose_train([swap_target, "Current"])
        update_plan_status(plan["id"], "training", swap_frozen=1)
        logger.info("换人完成，协助位已冻结")
        logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=ok")
        return True
    except Exception as e:
        logger.warning(f"换人失败: {e}")
        logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=失败 err={e}")
        return False


def _notify_swap_correction_failed(solver, plan, support_slot, operator):
    """#79 协助位纠错失败通知：换入 operator 失败，减半收益可能丢 + 协助位坐错人。

    去重按 plan id（同计划只通知一次）；异常时 fail open 照发（宁可多发不漏发）。
    """
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    if not should_notify("swap_correction_failed", str(plan["id"])):
        return
    label = f"{_plan_char_label(plan)} 技能{plan['skill_index'] + 1} 专{plan['target_level']}"
    msg = (
        f"{label} 协助位 {support_slot} 纠错失败（未能换入 {operator}），"
        "本次跳过减半换人，减半收益可能丢失"
    )
    send_message(msg, level="WARNING")


def _retry_swap_in_place(solver, plan, route, swap_target) -> bool:
    """#81：换人失败立刻原地重试（无 +5min 间隔），至多 SWAP_RETRY_LIMIT 次。

    每次重试前重读倒计时（_swap_still_worthwhile）判还值不值得换——换后真实剩余不足
    5 小时就不值得，放弃（不减半，按全时长收取，收取任务由 _schedule_collect_after_swap
    保证）。放弃（达上限/不足 5h）发⑧ 通知（去重按 plan id，WARNING），**不置
    swap_frozen=1**（#81 回滚 #77 的 give-up 分支）：reconcile（_maybe_recover_swap）
    下次进房会重新补排再试一轮，暂时性失败（减半干员当时忙/动画卡）会被救回；接受
    低频重试（reconcile 默认低频）。返回最终是否换人成功（成功 → 调用方不退出房间）。
    """
    retries = 0
    while retries < SWAP_RETRY_LIMIT:
        if not _swap_still_worthwhile(solver, plan, route):
            logger.info("剩余时间不足 5 小时，放弃减半换人（不减半，按全时长收取）")
            _notify_swap_giveup(solver, plan)
            return False
        retries += 1
        logger.warning(f"换人失败，原地重试（{retries}/{SWAP_RETRY_LIMIT}）")
        solver.sleep(1)
        if _try_swap(solver, plan, swap_target):
            return True
    logger.warning("换人重试已达上限，放弃减半换人（不减半，按全时长收取）")
    _notify_swap_giveup(solver, plan)
    return False


def _notify_swap_giveup(solver, plan):
    """⑧ 换人失败放弃通知（#81）：减半收益可能丢失。

    去重按 plan id（INSERT OR IGNORE，WARNING），与⑦ 纠错失败并列（doc §16.9）；
    异常时 fail open 照发（宁可多发不漏发）。
    """
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    if not should_notify("swap_failed_giveup", str(plan["id"])):
        return
    label = f"{_plan_char_label(plan)} 技能{plan['skill_index'] + 1} 专{plan['target_level']}"
    msg = f"{label} 换人失败已放弃，减半收益可能丢失"
    send_message(msg, level="WARNING")


def _swap_worthwhileness(remaining_minutes, route) -> bool:
    """「值不值得换」纯判定：换后真实剩余 ≥ 301 才值得（calc_swap_threshold 同式）。

    与 calc_swap_threshold 的 real_time_after_swap 守卫一致；供 run_swap_support
    纠错/换人前用当前倒计时判定（#80：纠错不触发不该发生的减半换人）。
    """
    central_bonus = route.get("central_bonus", 5)
    swap_total = 100 + 5 + (30 if route.get("job_match") else 0) + central_bonus
    current_total = 100 + route["efficiency"] + 5 + central_bonus
    real_time_after_swap = remaining_minutes * current_total / swap_total
    return real_time_after_swap >= 301


def _swap_still_worthwhile(solver, plan, route) -> bool:
    """重读倒计时判断换人后真实剩余时间是否 ≥ 301（不足 5 小时就不值得继续换）。

    读倒计时前先确认在训练室主页面（TRAIN_MAIN）；INFRA_DETAILS 先关浮窗再读。
    读不到/不在主页 → 保守按「还值得」继续重试（下次重试再判）。公式同式
    `_swap_worthwhileness`（calc_swap_threshold 的 real_time_after_swap 守卫）。
    """
    try:
        scene = solver.train_scene()
        if scene == Scene.INFRA_DETAILS:
            solver.back()
            scene = solver.train_scene()
        if scene != Scene.TRAIN_MAIN:
            return True
        countdown = _read_train_countdown(solver)
        if countdown is None:
            return True
        remaining = (countdown - datetime.now()).total_seconds() / 60
        return _swap_worthwhileness(remaining, route)
    except Exception:
        return True


def _schedule_collect_after_swap(solver, plan):
    """§16.10：SWAP_SUPPORT 完成后重读倒计时再排收取。

    读倒计时前先确认在训练室主页面（TRAIN_MAIN）；若是主页面带进驻详情浮窗
    （INFRA_DETAILS），先关浮窗再读。最多原地重试 5 次；仍读不到 → 保守重排到
    now+缓冲（下次进房再读）。
    """
    countdown = None
    for _ in range(5):
        try:
            scene = solver.train_scene()
            if scene == Scene.INFRA_DETAILS:
                solver.back()
                scene = solver.train_scene()
            if scene == Scene.TRAIN_MAIN:
                countdown = _read_train_countdown(solver)
                if countdown is not None:
                    break
        except Exception:
            pass
        solver.sleep(1)
    if countdown is None:
        countdown = datetime.now() + ARRANGING_RETRY_BUFFER
    _schedule_collect(solver, plan, countdown)


def _get_plan_route(plan, step_level=None) -> dict | None:
    """获取计划对应的路线配置。

    #76：路线按「当前步目标级」加载（step_level），而非整体目标 plan["target_level"]——
    一个专三计划 专一→专二→专三 三步分别用 level_1/2/3 路线。step_level 缺省/读失败
    （None/0）时回退 plan["target_level"]（=旧行为，保守）。
    """
    try:
        from arknights_mower.utils.mastery_recommendation import get_skill_data

        char_data = get_skill_data().get("characters", {}).get(plan["char_id"], {})
        prof_en = char_data.get("profession", "")
        prof_cn = PROF_MAP.get(prof_en, prof_en)
        return get_route_config(prof_cn, step_level or plan["target_level"])
    except Exception as e:
        logger.error(f"获取路线配置失败: {e}")
        return None
