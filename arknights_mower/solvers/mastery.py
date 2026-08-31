import json
from datetime import datetime, timedelta
from typing import Optional

from arknights_mower.solvers.mastery_reader import (
    PROTECT_OPERATORS,
    RoomPanel,
    RoomState,
    _close_room_detail,
    _count_lit_mastery_icons,
    _notify_at_target,
    _plan_label,
    _plan_matches_room,
    _plan_operator_matches,
    _read_panel_text,
    _read_slots_checked,
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


def _route_entry_from_array(entry: dict) -> dict:
    """前端数组条目 → 路线入口。

    #91：前端存自定义路线 supports 为 JSON 数组
    [{name, skill_level, efficiency, swap, swap_name, match}, ...]，与后端消费的
    {operator, efficiency, job_match, swap_target} 字段名不同。swap=false（或
    swap_name 空）→ swap_target=None；match 兼容 bool 与 'yes'/'no' 字符串。
    central_bonus / mastery_swap_buffer 由 get_route_config 统一从全局设置行填。
    """
    match = entry.get("match", False)
    return {
        "operator": entry.get("name", ""),
        "efficiency": entry.get("efficiency", 60),
        "job_match": match is True or match == "yes",
        "swap_target": (entry.get("swap_name") or None) if entry.get("swap") else None,
    }


def _match_array_entry(entries: list, level: int) -> dict | None:
    """数组里按 skill_level 找当前步级条目并转路线入口（裸数组/包装对象共用）。"""
    for entry in entries:
        if isinstance(entry, dict) and entry.get("skill_level") == level:
            return _route_entry_from_array(entry)
    return None


def _route_entry_from_supports(parsed, level: int) -> dict | None:
    """从 supports JSON 取当前步级（level_N）的路线入口。

    #91 主因：旧代码把 supports 当 {"level_N": {}} 字典读，数组（前端实际产出）上
    "level_1" in parsed 恒 False → 自定义路线永远回退 DEFAULT_ROUTES。现按三种形态
    解析：数组（前端产出）、包装对象 {"supports": [...], ...}（agent set_route 文档
    形态）、旧字典 {"level_N": {...}}。数组按 skill_level 匹配当前步级（#76 语义：
    step_level = 当前步目标级，不加 1）。
    """
    if isinstance(parsed, list):
        return _match_array_entry(parsed, level)
    if not isinstance(parsed, dict):
        return None
    wrapped_supports = parsed.get("supports")
    if isinstance(wrapped_supports, list):
        return _match_array_entry(wrapped_supports, level)
    level_key = f"level_{level}"
    if level_key in parsed:
        return dict(parsed[level_key])
    return None


def validate_route_supports(supports_json: str) -> str | None:
    """写入端校验路线 supports JSON（#114）：合法 JSON 且形态是数组/包装对象/旧字典之一。

    读取端 json.loads 故意无 try/except（#91 review 决策——防坏数据静默回退
    DEFAULT_ROUTES、掩盖「自定义路线从未生效」的症状），校验只能放写入端：
    不合法拒绝保存并报错，坏数据不得进库（否则该职业全无路线 operator/减半）。
    旧字典形态的 level_N 值须为对象——非 dict 值（如字符串）能过 json.loads 却在
    读取端 `dict(parsed[level_key])` 抛 ValueError，被 _get_plan_route 吞掉静默回退。
    """
    try:
        parsed = json.loads(supports_json)
    except (TypeError, ValueError):
        return "supports 不是合法 JSON"
    if isinstance(parsed, list):
        return None
    if isinstance(parsed, dict):
        if isinstance(parsed.get("supports"), list):
            return None
        if any(isinstance(parsed.get(f"level_{lvl}"), dict) for lvl in (1, 2, 3)):
            return None
    return "supports 形态需为数组/包装对象/旧字典"


def get_route_config(profession_cn: str, level: int) -> dict | None:
    from arknights_mower.utils.mastery_db import get_route, get_route_settings

    # #91 修订：central_bonus（0/5）+ 缓冲统一从全局设置行读（默认 0 / 10），自定义与
    # DEFAULT_ROUTES 回退共用同一值——旧代码 hardcode 5、conf 值被忽略。
    settings = get_route_settings()
    route_data = get_route(profession_cn)
    if route_data:
        parsed = json.loads(route_data["supports"])
        config_entry = _route_entry_from_supports(parsed, level)
        if config_entry is not None:
            config_entry.update(
                central_bonus=settings["central_bonus"],
                mastery_swap_buffer=settings["mastery_swap_buffer"],
            )
            return config_entry

    default = DEFAULT_ROUTES.get(profession_cn)
    if default:
        entry = default.get(f"level_{level}")
        if entry:
            config_entry = dict(entry)
            config_entry.update(
                central_bonus=settings["central_bonus"],
                mastery_swap_buffer=settings["mastery_swap_buffer"],
            )
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


def _fmt_completion_time(dt: datetime) -> str:
    """#90：邮件完成时间展示——当天 HH:MM，跨天带日期（防跨午夜歧义）。"""
    if dt.date() == datetime.now().date():
        return dt.strftime("%H:%M")
    return dt.strftime("%m-%d %H:%M")


def _swap_speed_totals(job_match, efficiency, central_bonus) -> tuple[float, float]:
    """换人公式速率口径（#142 保守）：swap_total 含中枢（减半对象）、current_total 不含
    （路线协助干员）。calc_swap_threshold / _swap_worthwhileness 共用——改口径只改一处。
    """
    swap_total = 100 + 5 + (30 if job_match else 0) + central_bonus
    current_total = 100 + efficiency + 5
    return swap_total, current_total


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

    # #142（用户拍板保守口径）：中枢 +5% 只给减半对象（swap_total），不给路线协助干员
    # （current_total）。中枢加成干员（阿斯卡纶/烛煌/斩业星熊）不一定在上班，屏幕倒计时
    # 反映实际速度而公式用固定 central_bonus——静态设置与实际对不上时，换人时机偏晚。
    # 保守口径让换人**只早不晚**：艾丽妮累计 ≥ 5h 稳定触发下一级减半（代价是中枢真开着
    # 时换人提前几分钟、邮件完成时间差 ~10 分钟，无害）。
    swap_total, current_total = _swap_speed_totals(
        swap_job_match, current_efficiency, central_bonus
    )

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
    plan, arrange_support, room = reconcile_and_act(solver, scan_plan=scan_plan)
    if plan:
        # 扫描派发时算出的本次安排步级（current_level+1，森空岛数据）——安排失败邮件
        # 需要「这次要练的专几」，不依赖现场图标（图标可能是占用者的）。
        step_level = getattr(task, "step_level", None) if task is not None else None
        # #93：reconcile 已进房读完全部状态（room），开始流程直接复用，不再重复进房。
        _start_new_training(
            solver,
            plan,
            arrange_support=arrange_support,
            room=room,
            step_level=step_level,
        )


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


def _plan_fail_label(plan, step_level=None) -> str:
    """失败/超时邮件的计划标签：技能真名 + 实际步级。

    不用「技能{序号} + target_level」——后者是最终目标（专三计划每步都写专三），
    实际在排的步级（专一→专二→专三）才是用户该看到的。步级未知时不写档位
    （占用者非本计划干员 / 图标读失败时，任何档位数字都是误导，宁缺毋滥）。
    """
    skill = plan.get("skill_name") or f"技能{plan['skill_index'] + 1}"
    base = f"{_plan_char_label(plan)} {skill}"
    return f"{base} 专{step_level}" if step_level else base


def _exit_failed(solver, plan, reason, step_level=None):
    """ARRANGING 失败统一出口：标记 failed + 一次通知 + 退出训练室，不在 ARRANGING 内重试。"""
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import update_plan_status

    update_plan_status(plan["id"], "failed", failed_reason=reason)
    label = _plan_fail_label(plan, step_level)
    send_message(f"{label} {reason}", level="ERROR")
    solver.back()


def _exit_arranging_timeout(solver, plan, stats, stuck_scene, step_level=None):
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
    label = _plan_fail_label(plan, step_level)
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
    #153：重检任务（plan_key=None）带描述性 meta_data——计划干员+技能+「占用中」，
    任务列表不再只显示类型名；档位未知（本路径读不到面板图标）不带专N。
    """
    from arknights_mower.solvers.mastery_reader import (
        _occupancy_recheck_label,
        _upsert_skill_upgrade_task,
    )
    from arknights_mower.utils.mastery_db import update_plan_status

    panel = RoomPanel(operator_name=plan["char_name"], skill_name=plan["skill_name"])
    room = RoomState("training", panel)
    if countdown is not None and countdown > datetime.now():
        panel.countdown = countdown
        _wait_for_training(solver, room)
        reschedule = countdown + ARRANGING_RETRY_BUFFER
    else:
        reschedule = datetime.now() + ARRANGING_RETRY_BUFFER
        _upsert_skill_upgrade_task(
            solver, reschedule, meta_data=_occupancy_recheck_label(room)
        )
    _log_transition(plan, "idle", trigger, 重排到=reschedule.strftime("%H:%M:%S"))
    update_plan_status(plan["id"], "idle")
    solver.back()


def _start_new_training(solver, plan, arrange_support=True, room=None, step_level=None):
    """开始新一级训练：IDLE → ARRANGING → TRAINING

    step_level：扫描派发算出的本次安排步级（current_level+1）；None=非扫描路径
    （collect 续练/重检），失败邮件回落现场图标/占用者判断。

    #16 决议：进房先读倒计时定分支，不盲点技能按钮。
    #15 决议：全程纯墙钟 5 分钟 deadline，各分支短处理、超时走统一退出路径。
    #103：路线 operator 每次开始照常安排（2026-08-17 用户拍板）——原 #63 减半守卫在
    「收取→下一次开始」边界传 arrange_support=False、不动协助位，把「专三不换减半对象」
    过度实现成「完全不动协助位」（路线 operator 也没放，专三只留上一级减半干员）；
    减半与否由路线 swap_target + _schedule_swap_if_needed 管，与 arrange_support 无关。
    #93：room 是 dispatch 的 reconcile_and_act 已读的房间状态（截图权威，含槽位）——
    开始流程直接复用，不再重复 enter_room、不再开进驻详情浮窗重读槽位（消除重复进房
    与重复浮窗开关）。room=None（冷启动/直接调用）保持旧行为：进房 + 现读槽位。
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
    # 选择页时置位；未置位就出现 219（重启停在技能选择页 / 手动进入）→ 219 分支保守退出。
    identity_confirmed = False

    if room is None:
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
            # 房间详情浮层（get_agent_from_room 会打开它）→ 点关闭按钮回房间主界面
            _close_room_detail(solver)
        elif scene == Scene.TRAIN_FINISH:
            solver.tap((solver.recog.w * 0.05, solver.recog.h * 0.95), interval=0.5)
        elif scene == Scene.TRAIN_MAIN:
            execute_time = _read_train_countdown(solver)
            if execute_time is not None and execute_time > datetime.now():
                # 训练室使用中（#16 决议）：保持 idle，重排到倒计时+缓冲，退出
                _exit_occupied(solver, plan, execute_time)
                return
            if not checked_slot:
                checked_slot = True
                # #93：复用 reconcile 读房已读的槽位（省重复浮窗开关）。槽位读到空串时
                # 无法区分「真空」与「读浮窗失败」——重读一次兜底（读失败恢复换人校验、
                # 真空重读仍空无害）。冷启动（room=None）保持旧行为现读。
                if room is not None and room.train_slot:
                    trainer_slot = room.train_slot
                else:
                    trainer_slot = _training_slots(solver)[1]
                    solver.back()  # 关闭 _training_slots 打开的房间详情浮层
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
                continue
            # 训练位已确认（空/已是计划干员）→ 身份确认成立，点开技能选择页。
            # #72：数星星前唯一合法的身份/归属确认点——经训练位校验后主动进入技能
            # 选择页；未置位就出现 219 在 219 分支直接保守退出。
            identity_confirmed = True
            solver.tap((solver.recog.w * 0.05, solver.recog.h * 0.95), interval=0.5)
        elif scene == Scene.TRAIN_SKILL_SELECT:
            if not identity_confirmed:
                # #72：真技能选择页只有 SKILL_SLOT_PIPS 星星可读，没有倒计时、读不到
                # `[干员名]技能名`——不能在 219 上读主面板区域（COUNTDOWN/PANEL）当占用
                # 探针（219 上没有主面板，读了也读不到）。未经过 TRAIN_MAIN 训练位
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
            result = _confirm_training_started(
                solver, plan, deadline, arrange_support, step_level=step_level
            )
            if result == "started":
                return
            if result == "failed":
                return
        elif scene == Scene.TRAIN_SKILL_UPGRADE_ERROR:
            msg = f"{_plan_fail_label(plan)} 材料不足"
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


def _confirm_training_started(
    solver, plan, deadline, arrange_support=True, step_level=None
):
    """确认训练已开始（读到有效倒计时）→ 转入 TRAINING，然后安排协助位。

    并入 #15 的全局 10 分钟 deadline（由调用方传入），不单独分段计时。
    step_level：扫描派发算出的本次安排步级，供归属校验失败邮件报「本次要练的专几」。
    返回 "started" / "failed" / "timeout"：
    - started: 已转入 TRAINING 并完成协助位/收取安排
    - failed: 材料不足 或 #69/B2 面板干员/技能与计划不符，已标记 failed + 通知 + 退出训练室
    - timeout: deadline 内未确认训练开始（含面板不可读无法校验归属），由调用方走统一超时出口
    #103：路线 operator 每次开始照常安排（2026-08-17 用户拍板，原 #63 减半守卫的
    arrange_support=False 已删——「收取后级联」也安排路线 operator，见 _start_new_training）。
    """
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import update_plan_status

    backed_from_skill_select = False
    while datetime.now() < deadline:
        scene = solver.train_scene()
        # #89：219 是技能选择页，读不出倒计时。确认升级后游戏自动退回 219，必须先
        # back 一次回训练室主页面（217）再读倒计时（§16.10 第 3 步「再退出一次」）。
        # 旧注释「运行页被误判成 219」写反语义：219 左下角是协助位天赋文本，会被 OCR
        # 当倒计时反复读（卡 ~15 秒），甚至偶然读出类时间文本 → 假确认开始。
        # 只允许 back 一次：back 后再读到 219 是动画/识别抖动，继续 back 会把已在
        # 主页面（217）的误读成 219 而误退训练室（超时假失败）。
        if scene == Scene.TRAIN_SKILL_SELECT:
            if not backed_from_skill_select:
                backed_from_skill_select = True
                logger.info(
                    f"{_plan_char_label(plan)} 确认后回到技能选择页，退出回主页面再读倒计时"
                )
                solver.back()
            continue
        if scene == Scene.TRAIN_MAIN:
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
                    # 面板可读但与计划不符：占用者的干员/技能/档位都读出来，一并告知
                    # 用户实际占房者（面板信息不该浪费）。占用者即本计划干员（仅技能名
                    # 不符，如 OCR 噪声）时，档位可作计划步级写进标签；占用者是路人时
                    # 档位属于路人，只出现在「实际占用」里，不作计划步级。
                    tier = None
                    try:
                        tier = _count_lit_mastery_icons(solver)
                    except Exception:
                        tier = None
                    actual = f"{panel.operator_name}（{panel.skill_name or '技能未知'}"
                    actual += f"，专{tier}）" if tier else "）"
                    # 计划步级：优先扫描带的本安排步级（最可靠，森空岛 current_level+1）；
                    # 无则占用者即本计划干员时读图标回退；占用者是路人时步级未知（不作
                    # 计划步级，只出现在「实际占用」）。
                    plan_step = step_level
                    if plan_step is None and _plan_operator_matches(
                        plan, panel.operator_name
                    ):
                        plan_step = tier
                    _exit_failed(
                        solver,
                        plan,
                        f"训练室面板干员/技能与计划不符，实际占用：{actual}",
                        step_level=plan_step,
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
                # #76：主面板专精图标在训练中 = 当前步目标级（亮 N 颗=专N）。确认开始
                # 后先读图标作当前步级，传给协助位/换人安排（专三计划专一/专二步用
                # level_1/2 路线减半换人）；同值复用作收取任务目标档位（原 tier）。
                # #89：走到这里已 back 回 217 主页面，图标可读。
                step_level = None
                try:
                    step_level = _count_lit_mastery_icons(solver)
                except Exception:
                    step_level = None
                if arrange_support:
                    _arrange_support(solver, plan, step_level)
                # #90 §16.10 第7步「以当前读取为准」：协助位安排（换效率干员）后倒计时
                # 会变，重读一次——换人/收取/邮件完成时间都以此为准；读不到回退安排前值。
                fresh_execute_time = _re_read_train_countdown(solver) or execute_time
                # §16.10：排了换人任务则不排收取；等 SWAP_SUPPORT 完成后重读倒计时再排收取。
                # #90：返回 SWAP 任务触发时刻（None=不换人），邮件完成时间据此分两情况。
                swap_time = _schedule_swap_if_needed(
                    solver, plan, fresh_execute_time, step_level
                )
                # #90：DB 里的 expires_at 也要用换协助位后的最终倒计时（安排前的倒计时
                # 基于旧效率、不是最终完成时间）；同值跳过 DB 写（#82 同款）。
                if fresh_execute_time != execute_time:
                    update_plan_status(
                        plan["id"],
                        "training",
                        expires_at=fresh_execute_time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                # #90：邮件移到协助位安排 + 换人判定之后发（此时效率/倒计时已确定）；
                # 真名 = plan["skill_name"]；档位 = 目标级（step_level，不加1），读不到
                # 显示「专精等级未知」（不回退 target_level）；完成时间两情况——无减半 =
                # 重读倒计时、有减半 = 换人任务时刻 + (300 + 缓冲) 分钟，附换入干员名。
                tier_text = f"专{step_level}" if step_level else "专精等级未知"
                if swap_time is not None:
                    route = _get_plan_route(plan, step_level)
                    swap_target = route.get("swap_target") if route else None
                    buffer = route.get("mastery_swap_buffer", 10) if route else 10
                    completion = swap_time + timedelta(minutes=300 + buffer)
                    swap_clause = (
                        f"，将于 {_fmt_completion_time(swap_time)} 换入{swap_target}"
                        if swap_target
                        else ""
                    )
                else:
                    completion = fresh_execute_time
                    swap_clause = ""
                msg = (
                    f"{_plan_char_label(plan)} {plan['skill_name']} {tier_text} "
                    f"开始训练{swap_clause}，预计 {_fmt_completion_time(completion)} 完成"
                )
                logger.info(msg)
                send_message(msg, level="INFO")
                if swap_time is None:
                    _schedule_collect(solver, plan, fresh_execute_time, tier=step_level)
                return "started"
        elif scene == Scene.TRAIN_SKILL_UPGRADE_ERROR:
            msg = f"{_plan_fail_label(plan)} 材料不足"
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


def _re_read_train_countdown(solver) -> Optional[datetime]:
    """#90 §16.10 第7步「以当前读取为准」：协助位安排后重读倒计时。

    choose_train 换协助位后停在进驻详情浮窗（INFRA_DETAILS），先关浮窗回主页面再读
    （back() 内部 sleep→recog.update 已重置场景缓存，与 _swap_still_worthwhile/
    _schedule_collect_after_swap 同款关浮窗读法）；不在训练室主页面 / 读失败 → None
    （调用方回退安排前倒计时）。
    """
    try:
        scene = solver.train_scene()
        if scene == Scene.INFRA_DETAILS:
            _close_room_detail(solver)
            scene = solver.train_scene()
        if scene != Scene.TRAIN_MAIN:
            return None
        return _read_train_countdown(solver)
    except Exception:
        return None


def _schedule_swap_if_needed(
    solver, plan, execute_time, step_level=None
) -> Optional[datetime]:
    """训练开始后计算是否需要换人，需要则插入 SWAP_SUPPORT 任务。

    §16.10：返回 SWAP 任务触发时刻（None=不排换人）——排了换人则不排收取（等
    SWAP_SUPPORT 完成后重读倒计时再排收取）。立即换人（remaining ≤ threshold）也排
    任务（修旧 silent-drop）。#90 邮件「有减半」的完成时间 = 返回时刻 + (300+缓冲) 分。
    #76：路线按当前步目标级加载（step_level）；「专三不换人」由 level_3 路线
    swap_target=None 保证（铁律 7，用户 08-15 定案删显式 ==3 守卫、靠路线数据）。
    """
    from arknights_mower.utils import config

    if config.conf.assistant_follows_schedule:
        return None

    route = _get_plan_route(plan, step_level)
    if not route or not route.get("swap_target"):
        return None

    central_bonus = route.get("central_bonus", 0)
    buffer = route.get("mastery_swap_buffer", 10)

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
            return None
        swap_time = datetime.now() + timedelta(seconds=swap_delay_seconds)
    else:
        return None

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
    return swap_time


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
    #79：读全后开进驻浮窗（_read_slots_checked）读实际协助位——协助位 ∉ {operator,
    swap_target}（陌生人/坐错）先 choose_train 纠错成 operator，纠错成功重读倒计时
    （此时效率已知 = route["efficiency"]）才算换人；纠错失败 → 邮件通知 + 不换人 +
    排收取退出。协助位已 = swap_target（已减半）→ 不再换、不置 swap_frozen。
    #101：协助位**空着**一步定夺（当前效率已知=0）——calc_swap_threshold(0,...) 判
    「放 operator 还是 swap_target」：should_swap（含 301 值得门）→ 直接换入减半对象
    （不先放 operator 再立刻换的浪费；仅剩余≤阈值不够——低剩余窗 swap_target 速率 ≤
    路线 operator）；should_swap=False（剩余 > 阈值 / 值得门不满足 / 倒计时读失败）→
    放路线 operator 拿前半程加成，**不立刻换**（重读倒计时排阈值时刻的换人任务；重读
    失败 → 轻量重试读重排阈值，防丢减半）。只在倒计时 active 或 failed 时动（00:00:00
    收取边界不动，铁律 6）且读协助位可靠（reliable，OCR 坏名读失败不算空，稳为先）；
    空位补位失败 → 不阻塞减半（直接尝试换入 swap_target）。
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
        _close_room_detail(solver)
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

    # #79 协助位确认：开进驻浮窗读实际协助位（_read_slots_checked 读后自动关浮窗回
    # 主页面）。协助位 ∉ {operator, swap_target}（陌生人/空位）→ 坐错人纠错成 operator
    # （#80）、空位一步定夺（#101）。只在倒计时 active（训练确认）时动协助位——
    # 00:00:00 收取边界不动（铁律 6）；读失败（reliable=False，OCR 坏名等）不动作
    # （稳为先：读不到就不动，防基于不可靠读撤销已减半）。
    support_slot, _, _, reliable = _read_slots_checked(solver)
    if operator and reliable and support_slot not in (operator, swap_target):
        # #107 保护门（2026-08-17）：逻各斯/艾丽妮在协助位（非路线干员/减半对象）且
        # 剩余不足 5h+缓冲 → 不纠不换——她们本身是最优加成，路线干员+减半收益在这里
        # 赶不上；只排收取退出（expires_at 已由 B8 采纳门刷新）。剩余足够才照常纠错
        # 走减半流程。必须整段 return：否则落到 did_swap 会用路线效率(75)判值得、
        # 直接换减半对象，绕过「不换人」。
        if (
            support_slot in PROTECT_OPERATORS
            and panel is not None
            and panel.countdown is not None
        ):
            remaining_min = (panel.countdown - datetime.now()).total_seconds() / 60
            buffer_min = route.get("mastery_swap_buffer", 10)
            if remaining_min < 300 + buffer_min:
                logger.info(
                    f"[mastery] #107 协助位保护：{support_slot} 剩余不足 "
                    f"{300 + buffer_min} 分钟，不纠错换人，仅排收取"
                )
                _schedule_collect_after_swap(solver, plan, tier=step_level)
                solver.back()
                return
        if not support_slot:
            # #101 空位一步定夺（当前效率已知=0）：calc_swap_threshold(0,...) 判
            # 「放 operator 还是 swap_target」——should_swap（含 301 值得门）→ 直接放
            # 减半对象；否则（剩余 > 阈值 / 值得门不满足 / 倒计时读失败）→ 放 operator
            # 拿前半程加成，不立刻换（重排阈值时刻的换人任务，阈值时机不丢）。只在训练
            # 确认（countdown active）或读失败（failed，保守补 operator）时动；00:00:00
            # （zero，收取边界）不动（铁律 6）。
            if countdown_active or (
                panel is not None and panel.countdown_state == "failed"
            ):
                remaining = None
                if panel is not None and panel.countdown is not None:
                    remaining = (panel.countdown - datetime.now()).total_seconds() / 60
                place_swap_target = False
                if remaining is not None and swap_target:
                    # should_swap 含 301 值得门（real_time_after_swap≥301）——低剩余窗口
                    # swap_target 速率 ≤ 路线 operator，直接换入比补 operator 更慢且错置
                    # swap_frozen=1（#101 review 修复；仅 remaining<=threshold 会踩该窗）
                    should_swap, _ = calc_swap_threshold(
                        0,
                        route.get("job_match", False),
                        route.get("central_bonus", 0),
                        remaining,
                        route.get("mastery_swap_buffer", 10),
                    )
                    place_swap_target = should_swap
                if place_swap_target:
                    # 已到减半时刻 → 直接换入 swap_target（等价于一次减半换人）
                    logger.info(f"协助位空着且已到减半时刻，直接换入 {swap_target}")
                    did_swap = _try_swap(solver, plan, swap_target)
                    if not did_swap:
                        did_swap = _retry_swap_in_place(
                            solver, plan, route, swap_target
                        )
                    _schedule_collect_after_swap(solver, plan, tier=step_level)
                    if not did_swap:
                        solver.back()
                    return
                # 剩余 > 阈值（或倒计时读失败）→ 放路线 operator，不立刻换
                logger.info(f"协助位空着，补位为 {operator}")
                logger.debug(
                    f"[mastery] 协助位补位 id={plan['id']} 期望={operator} 动作=补位"
                )
                try:
                    solver.choose_train([operator, "Current"])
                except Exception as e:
                    logger.warning(f"协助位补位失败: {e}")
                    logger.debug(
                        f"[mastery] 协助位补位 id={plan['id']} 结果=失败 err={e}"
                    )
                    # #100 语义：空位补位失败 → 不阻塞减半，直接尝试换入 swap_target
                    _notify_swap_correction_failed(
                        solver, plan, "", operator, fallback_swap=True
                    )
                    did_swap = False
                    if swap_target:
                        did_swap = _try_swap(solver, plan, swap_target)
                        if not did_swap:
                            did_swap = _retry_swap_in_place(
                                solver, plan, route, swap_target
                            )
                    _schedule_collect_after_swap(solver, plan, tier=step_level)
                    solver.back()
                    return
                logger.debug(f"[mastery] 协助位补位 id={plan['id']} 结果=ok")
                # 补位消耗时间 → 重读倒计时（铁律 1 动作前先读房），排阈值时刻换人任务
                scene = solver.train_scene()
                if scene == Scene.INFRA_DETAILS:
                    _close_room_detail(solver)
                    scene = solver.train_scene()
                panel = None
                if scene == Scene.TRAIN_MAIN:
                    try:
                        panel = read_main_panel(solver)
                    except Exception as e:
                        logger.debug(f"主面板重读失败: {e}")
                if panel is not None and panel.countdown is not None:
                    # 有换人目标 → 排阈值时刻任务（排了换人就不排收取，§16.10 等 SWAP
                    # 完成后重读再排）；专三/无减半目标 → 直接排收取
                    step_level = panel.mastery_tier if panel is not None else None
                    if (
                        _schedule_swap_if_needed(
                            solver, plan, panel.countdown, step_level
                        )
                        is None
                    ):
                        _schedule_collect_after_swap(solver, plan, tier=step_level)
                else:
                    # 重读失败 → 轻量倒计时重试读（_read_countdown_with_retry）重排阈值
                    # 任务——#101 合并后阈值任务已被本 dispatch 消费，重读失败只排收取会
                    # 丢减半（review 修复）；重试也读不到 → 保守排收取（下次进房再读）
                    countdown = _read_countdown_with_retry(solver)
                    step_level = panel.mastery_tier if panel is not None else None
                    if (
                        countdown is not None
                        and route
                        and route.get("swap_target")
                        and _schedule_swap_if_needed(
                            solver, plan, countdown, step_level
                        )
                        is not None
                    ):
                        pass  # 已重排换人任务，不排收取
                    else:
                        _schedule_collect_after_swap(solver, plan, tier=step_level)
                solver.back()
                return
        elif countdown_active:
            # 陌生人（协助位非空且不是 operator/swap_target）→ 纠错成 operator（#79/#80）
            logger.info(f"协助位坐着 {support_slot}，纠错为 {operator}")
            logger.debug(
                f"[mastery] 协助位纠错 id={plan['id']} 期望={operator} 动作=纠错"
            )
            try:
                solver.choose_train([operator, "Current"])
            except Exception as e:
                logger.warning(f"协助位补位/纠错失败: {e}")
                logger.debug(
                    f"[mastery] 协助位补位/纠错 id={plan['id']} 结果=失败 err={e}"
                )
                _notify_swap_correction_failed(
                    solver, plan, support_slot, operator, fallback_swap=False
                )
                # #79 坐错人纠错失败 → 维持语义：不换人、排收取退出
                _schedule_collect_after_swap(solver, plan, tier=step_level)
                solver.back()
                return
            else:
                logger.debug(f"[mastery] 协助位补位/纠错 id={plan['id']} 结果=ok")
                support_slot = operator
                # 纠错消耗时间 → 重读倒计时（铁律 1 动作前先读房）
                scene = solver.train_scene()
                if scene == Scene.INFRA_DETAILS:
                    _close_room_detail(solver)
                    scene = solver.train_scene()
                panel = None
                if scene == Scene.TRAIN_MAIN:
                    try:
                        panel = read_main_panel(solver)
                    except Exception as e:
                        logger.debug(f"主面板重读失败: {e}")
                countdown_active = bool(
                    panel is not None and panel.countdown_state == "active"
                )
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
        and reliable  # #107/#117：读协助位失败（reliable=False）不盲目换——槽位未知，
        # 可能坐着受保护干员/已减半对象，「稳为先：读不到就不动」
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
    _schedule_collect_after_swap(solver, plan, tier=step_level)
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


def _notify_swap_correction_failed(
    solver, plan, support_slot, operator, fallback_swap=False
):
    """#79 协助位纠错失败通知：换入 operator 失败 + 协助位坐错人/空。

    #100：support_slot 空（协助位空着补位失败）时显示「空」；空位补位失败会落到
    did_swap 直接尝试换入 swap_target（**不跳过减半**）→ fallback_swap=True 时文案
    如实改为「将尝试直接换入减半对象」（否则「跳过减半」与实际行为矛盾）。
    去重按 plan id（同计划只通知一次）；异常时 fail open 照发（宁可多发不漏发）。
    """
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    if not should_notify("swap_correction_failed", str(plan["id"])):
        return
    label = _plan_fail_label(plan)
    if fallback_swap:
        msg = (
            f"{label} 协助位 {support_slot or '空'} 补位失败（未能换入 {operator}），"
            "将尝试直接换入减半对象"
        )
    else:
        msg = (
            f"{label} 协助位 {support_slot or '空'} 补位/纠错失败（未能换入 {operator}），"
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
    label = _plan_fail_label(plan)
    msg = f"{label} 换人失败已放弃，减半收益可能丢失"
    send_message(msg, level="WARNING")


def _swap_worthwhileness(remaining_minutes, route) -> bool:
    """「值不值得换」纯判定：换后真实剩余 ≥ 301 才值得（calc_swap_threshold 同式）。

    与 calc_swap_threshold 的 real_time_after_swap 守卫一致；供 run_swap_support
    纠错/换人前用当前倒计时判定（#80：纠错不触发不该发生的减半换人）。
    """
    swap_total, current_total = _swap_speed_totals(
        route.get("job_match", False),
        route["efficiency"],
        route.get("central_bonus", 0),
    )
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
            _close_room_detail(solver)
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


def _read_countdown_with_retry(solver) -> Optional[datetime]:
    """轻量倒计时读取 + 原地重试（至多 5 次）：先确认在训练室主页面（TRAIN_MAIN），
    浮窗先关再读；仍读不到 → None（调用方保守处理）。
    """
    countdown = None
    for _ in range(5):
        try:
            scene = solver.train_scene()
            if scene == Scene.INFRA_DETAILS:
                _close_room_detail(solver)
                scene = solver.train_scene()
            if scene == Scene.TRAIN_MAIN:
                countdown = _read_train_countdown(solver)
                if countdown is not None:
                    break
        except Exception:
            pass
        solver.sleep(1)
    return countdown


def _schedule_collect_after_swap(solver, plan, tier=None):
    """§16.10：SWAP_SUPPORT 完成后重读倒计时再排收取。

    #150：与训练开始路径（_confirm_training_started）一致，收取任务档位标签用实际
    读到的面板图标档位（tier=panel.mastery_tier，run_swap_support 进房已读），读不到
    （None/0）回退 target_level——不再恒为专三。读倒计时前先确认在训练室主页面
    （TRAIN_MAIN）；若是主页面带进驻详情浮窗（INFRA_DETAILS），先关浮窗再读。最多
    原地重试 5 次；仍读不到 → 保守重排到 now+缓冲（下次进房再读）。
    """
    countdown = _read_countdown_with_retry(solver)
    if countdown is None:
        countdown = datetime.now() + ARRANGING_RETRY_BUFFER
    _schedule_collect(solver, plan, countdown, tier=tier)


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
