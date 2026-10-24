import json
from datetime import datetime, timedelta
from typing import Optional

from arknights_mower.data import agent_list
from arknights_mower.solvers.mastery_reader import (
    ARRANGING_RETRY_BUFFER,
    PROTECT_OPERATORS,
    RoomPanel,
    RoomState,
    _back_to_train_main,
    _close_room_detail,
    _count_lit_mastery_icons,
    _notify_at_target,
    _plan_label,
    _plan_matches_room,
    _plan_operator_matches,
    _read_panel_text,
    _read_slots_checked,
    _read_train_countdown,
    _read_train_countdown3,
    _schedule_collect,
    _target_label,
    _wait_for_training,
    read_main_panel,
)
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.log import logger
from arknights_mower.utils.mastery_support_types import (
    DEFAULT_SWAP_BUFFER_MINUTES,
    TrainingObservationError,
)
from arknights_mower.utils.scene import Scene

ARRANGING_DEADLINE = timedelta(minutes=5)
# ARRANGING_RETRY_BUFFER（2 分钟重排缓冲）从 mastery_reader 导入：读取器与 dispatch
# 两处都排「now/练完时刻 + 缓冲」，同步改一个常量，不再各写一份。
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
            "operator": "望",
            "efficiency": 70,
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
            "operator": "望",
            "efficiency": 70,
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
    from arknights_mower.utils.mastery_support_types import (
        configured_swap_buffer,
        swap_buffer_minutes,
    )

    # #91 修订：central_bonus（0/5）+ 缓冲统一从全局设置行读（默认 0 / 10），自定义与
    # DEFAULT_ROUTES 回退共用同一值——旧代码 hardcode 5、conf 值被忽略。
    settings = get_route_settings()
    configured = configured_swap_buffer(settings)
    buffer = swap_buffer_minutes(level, configured, central=settings["central_bonus"])
    route_data = get_route(profession_cn)
    if route_data:
        parsed = json.loads(route_data["supports"])
        config_entry = _route_entry_from_supports(parsed, level)
        if config_entry is not None:
            config_entry.update(
                central_bonus=settings["central_bonus"],
                mastery_swap_buffer=buffer,
                configured_swap_buffer=configured,
            )
            return config_entry

    default = DEFAULT_ROUTES.get(profession_cn)
    if default:
        entry = default.get(f"level_{level}")
        if entry:
            config_entry = dict(entry)
            config_entry.update(
                central_bonus=settings["central_bonus"],
                mastery_swap_buffer=buffer,
                configured_swap_buffer=configured,
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
    """预览按全程中枢加成计算当前协助者和减半干员。"""
    swap_total = 100 + 5 + (30 if job_match else 0) + central_bonus
    current_total = 100 + efficiency + 5 + central_bonus
    return swap_total, current_total


def calc_swap_threshold(
    current_efficiency: int,
    swap_job_match: bool,
    central_bonus: int,
    remaining_minutes: float,
    buffer: int = DEFAULT_SWAP_BUFFER_MINUTES,
    *,
    current_central: int | None = None,
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

    # 预览两边计入中枢；运行时可传入当前实际中枢加成。
    swap_total, current_total = _swap_speed_totals(
        swap_job_match, current_efficiency, central_bonus
    )
    if current_central is not None:
        current_total += current_central - central_bonus

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
    """SKILL_UPGRADE dispatch：共享读取器进房读全部 + #61 矩阵更新状态。

    读取器返回需要开始训练的计划时，由本入口执行开始（长动作）。
    不再依赖 DB 状态预判（铁律：先读房，截图为准）。

    # #74 第3段：任务带 plan_key 时解析其指定计划为 scan_plan——任何带 plan_key 的
    SKILL_UPGRADE 任务（扫描开始/收取/重检）在空闲×未保护格都会让该计划开始训练
    （2026-08-14 用户拍板「都去掉」：不再区分扫描标记；开始/继续一律当场）。房间状态
    决定分支：空闲→开始、待收取→收集+继续本级当场开、训练中→更新状态。
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
    try:
        plan, arrange_support, room = reconcile_and_act(solver, scan_plan=scan_plan)
    except (MowerExit, DeviceRecoveryError, TrainingObservationError):
        raise
    except Exception as exc:
        raise TrainingObservationError(
            "专精任务的训练室读取未完成，保留原任务"
        ) from exc
    if room is not None and (
        getattr(room, "read_failed", False) is True
        or room.state == "training"
        and (
            room.panel.countdown_state != "active"
            or room.panel.countdown is None
            or not room.panel.operator_name
            or not room.panel.skill_name
            or not room.panel.mastery_tier
        )
    ):
        raise TrainingObservationError("专精任务的训练室面板未确认，保留原任务")
    if plan:
        # 扫描派发时算出的本次安排步级（current_level+1，森空岛数据）——安排失败邮件
        # 需要「这次要练的专几」，不依赖现场图标（图标可能是占用者的）。
        step_level = getattr(task, "step_level", None) if task is not None else None
        # #93：reconcile 已进房读完全部状态（room），开始流程直接复用，不再重复进房。
        # 中途抛异常时状态还停在 arranging（铁律 9 要求置 failed）——统一在出口补写，
        # 处理完照旧上抛，排班主循环的通用兜底不受影响。
        try:
            _start_new_training(
                solver,
                plan,
                arrange_support=arrange_support,
                room=room,
                step_level=step_level,
            )
        except MowerExit:
            # 用户点了停止：不是安排失败，状态与异常都原样放行
            raise
        except Exception as exc:
            _fail_arranging(solver, plan, exc, step_level)
            raise


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
    send_message(f"{label} {reason}", level="ERROR", archive_screenshots=True)
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
        f"{label} ARRANGING 超时退出: {reason} | 诊断: 最后持续停留在『{scene_name}』页面 | "
        f"轨迹: {stats}"
    )
    send_message(
        f"{label}：开始训练超时，最后持续停留在『{scene_name}』页面，未能确认训练是否开始，"
        "已暂停，将在下次仓库扫描后重试",
        level="ERROR",
        archive_screenshots=True,
    )
    solver.back()


def _fail_arranging(solver, plan, exc, step_level=None):
    """ARRANGING 中途抛异常的统一出口（铁律 9：不得留在 arranging）。

    异常本来就在上抛路上——排班主循环的通用兜底负责记 traceback、跳任务、插纠错，
    本出口只补「把状态写对」这一件事：置 failed + 一次通知（按计划 id 去重）。
    不做类型映射，failed_reason 原样带上异常文本。

    标失败前先看一眼计划现在是什么状态：只有还停在 arranging 才说明这次真的没开成。
    已经是 training（收尾阶段出错）时训练正在跑，标 failed 只是 mower 自己记错，
    所以不标、不发，异常照旧上抛。这样「失败」就有了确定的意思——看到失败，就是
    这次训练没开起来。往后开始训练这段再加步骤也不会把正在跑的训练记错。

    边界：读状态读不出来（DB 异常 / 计划已删）时按「还停在 arranging」处理，照旧
    标失败——那种情况下计划很可能确实还停在 arranging，而「不得留在 arranging」
    是硬要求。

    通知与退出训练室各自兜底：报错现场可能已经让设备没法操作，这两步失败不得
    盖掉原始异常（调用方还要继续上抛）。
    """
    from arknights_mower.utils.mastery_db import get_plan_by_id, update_plan_status

    latest = get_plan_by_id(plan["id"])
    if latest is not None and latest.get("status") != "arranging":
        logger.warning(
            f"[mastery] 安排训练出错但计划 {plan['id']} 已是 "
            f"{latest.get('status')}，不改状态、不通知，照旧上抛：{exc}"
        )
        return
    update_plan_status(plan["id"], "failed", failed_reason=f"安排训练时出错：{exc}")
    try:
        from arknights_mower.utils.email import send_message
        from arknights_mower.utils.mastery_db import should_notify

        if should_notify("arrange_error", str(plan["id"])):
            send_message(
                f"{_plan_fail_label(plan, step_level)} 安排训练时出错：{exc}",
                level="ERROR",
            )
    except Exception as notify_exc:
        logger.warning(f"[mastery] 安排失败通知发送失败: {notify_exc}")
    try:
        solver.back()
    except Exception as back_exc:
        logger.warning(f"[mastery] 安排失败退出训练室失败: {back_exc}")


def _schedule_collect_checked(solver, plan, execute_time, tier=None) -> Optional[str]:
    """排到点收取任务；失败返回原因文案（不抛出）。

    训练已经在跑，排不上收取只是 mower 少一次顺路收取（下次进训练室照常收），
    不能因此把计划标成失败，所以这里吞掉异常、把原因交回调用方另发一封 WARNING。
    """
    try:
        _schedule_collect(solver, plan, execute_time, tier=tier)
    except Exception as e:
        logger.warning(f"[mastery] 到点收取任务安排失败 id={plan['id']}: {e}")
        return str(e)
    return None


def _notify_collect_unscheduled(plan, step_level, reason):
    """到点收取任务没排上：单独一封 WARNING（发生在开训邮件之后，没有别的邮件可承载）。

    按计划 id 去重；正文写清是哪一步失败——用户看到这封要知道「少了一次到点收取」，
    而不是以为训练出了问题（训练仍在跑）。

    通知与 `_fail_arranging` 同样各自兜底：发信失败只记日志，不得让「少排一次收取」
    这种小事反过来打断已经在跑的训练。
    """
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    try:
        if should_notify("collect_schedule", str(plan["id"])):
            send_message(
                f"{_plan_fail_label(plan, step_level)}：到点收取任务没能排上"
                f"（{reason}），稍后进训练室时会顺路收取",
                level="WARNING",
            )
    except Exception as notify_exc:
        logger.warning(f"[mastery] 到点收取未排上通知发送失败: {notify_exc}")


def _warn_training_room_group(plan):
    """未跟随排班时，提醒训练室绑组可能与专精换人冲突，但不阻断执行。"""
    from arknights_mower.utils import config

    if config.conf.assistant_follows_schedule:
        return

    from arknights_mower.utils.mastery_support_data import training_room_group_warning

    group_warning = training_room_group_warning()
    if not group_warning:
        return

    message = (
        f"{group_warning}。未勾选“训练室协助位总是跟随排班”，"
        "专精系统仍会自行更换协助位，可能与绑组排班冲突；本次继续执行"
    )
    logger.warning(f"[mastery] {message}")
    try:
        from arknights_mower.utils.email import send_message
        from arknights_mower.utils.mastery_db import should_notify

        if should_notify("training_group_warning", str(plan["id"])):
            send_message(f"{_plan_fail_label(plan)} {message}", level="WARNING")
    except Exception as notify_exc:
        # 警告本身不得反过来阻断开训或换人。
        logger.warning(f"[mastery] 训练室绑组通知发送失败: {notify_exc}")


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


def _exit_occupied(solver, plan, countdown, trigger="训练室占用", panel=None):
    """训练室现在不归 mower 支配（有人在练 / 练完没领）→ 保持 idle + 重排 + 退出。

    countdown 可读时重排到倒计时+缓冲；不可读（面板归属与计划不符 / 已到target
    档位读取失败）时重排到 now+缓冲，避免占用期间每轮 dispatch 空转重试。
    trigger 只进状态转换日志，用来区分退出原因——不进任务标签：重检任务不带计划
    编号，队列里所有重检任务其实是同一条，标签里写退出原因只会误导。

    panel：调用方在同一张图上真正读到的面板文字（主页面读倒计时时顺带读一下）。
    标签只写真正读到的东西——不再拿计划自己的干员/技能造一份面板，那会把「计划要练
    的干员」当成「房间里的干员」写到任务列表上。读不到人（219 技能选择页等）就只写
    「重读训练室状态」。
    """
    from arknights_mower.solvers.mastery_reader import (
        _occupancy_recheck_label,
        _occupant_label,
        _upsert_skill_upgrade_task,
    )
    from arknights_mower.utils.mastery_db import update_plan_status

    room = RoomState("training", panel or RoomPanel())
    logger.info(
        f"[mastery] 重读训练室状态 id={plan['id']} 原因={trigger} "
        f"房间内={_occupant_label(room.panel) or '未读到'}"
    )
    if countdown is not None and countdown > datetime.now():
        room.panel.countdown = countdown
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
    每次开始按路线安排协助位；减半继承由实读身份和出勤记录确认。
    减半换人由路线 swap_target 与后续训练决定。
    #93：room 是 dispatch 的 reconcile_and_act 已读的房间状态（截图权威，含槽位）——
    开始流程直接复用，不再重复 enter_room、不再开进驻详情浮窗重读槽位（消除重复进房
    与重复浮窗开关）。room=None（冷启动/直接调用）保持旧行为：进房 + 现读槽位。
    """
    from arknights_mower.solvers.mastery_reader import (
        _protected_trainee_matches,
        _read_slot_mastery_tier,
    )
    from arknights_mower.utils.mastery_db import update_plan_status
    from arknights_mower.utils.mastery_recommendation import (
        get_mastery_requirement_error,
    )
    from arknights_mower.utils.mastery_support import SupportPlanError
    from arknights_mower.utils.mastery_support_data import trainee_schedule_conflict

    if getattr(room, "amiya_form_waiting", False) is True:
        solver.back()
        return
    if room is not None and getattr(room, "protected", False):
        if not _protected_trainee_matches(plan, room):
            logger.info("训练室受保护，当前计划不是已确认的同一训练位干员，保持待执行")
            solver.back()
            return

    _warn_training_room_group(plan)

    trainee = _plan_char_label(plan)
    if not trainee or trainee == plan["char_id"]:
        logger.warning(
            f"[mastery] 暂不开始训练：无法解析 {plan['char_id']} 的干员名，"
            "排班冲突未复核；请更新游戏资源后重试"
        )
        return
    schedule_conflict = trainee_schedule_conflict(trainee)
    if schedule_conflict:
        logger.warning(f"[mastery] 暂不开始训练：{schedule_conflict}")
        try:
            from arknights_mower.utils.email import send_message
            from arknights_mower.utils.mastery_db import should_notify

            if should_notify("trainee_schedule_conflict", str(plan["id"])):
                send_message(
                    f"{_plan_fail_label(plan)}：{schedule_conflict}", level="WARNING"
                )
        except Exception as notify_exc:
            logger.warning(f"[mastery] 排班冲突通知发送失败: {notify_exc}")
        return

    requirement_error = get_mastery_requirement_error(plan["char_id"])
    if requirement_error:
        logger.warning(f"[mastery] 暂不开始训练：{requirement_error}")
        update_plan_status(plan["id"], "failed", failed_reason=requirement_error)
        return

    if not plan.get("expires_at") and not plan.get("support_runtime"):
        from arknights_mower.utils.mastery_db import get_all_plans
        from arknights_mower.utils.mastery_order import mastery_groups
        from arknights_mower.utils.mastery_recommendation import (
            auto_schedule_mastery_tasks,
            get_current_mastery_level,
        )

        siblings = [p for p in get_all_plans() if p["char_id"] == plan["char_id"]]
        levels = {
            (p["char_id"], p["skill_index"]): get_current_mastery_level(
                p["char_id"], p["skill_index"]
            )
            or 0
            for p in siblings
        }
        if mastery_groups(siblings, levels):
            admitted = auto_schedule_mastery_tasks().get("scheduled", [])
            if not any(
                entry["char_id"] == plan["char_id"]
                and entry["skill_index"] == plan["skill_index"]
                for entry in admitted
            ):
                logger.info("同干员联合专精尚未满足材料或顺序条件，保持待执行")
                return

    _log_transition(
        plan,
        "arranging",
        "定时任务",
        技能=plan["skill_index"] + 1,
        目标=plan["target_level"],
    )
    update_plan_status(plan["id"], "arranging")
    if plan.get("support_plan"):
        from arknights_mower.utils.mastery_db import get_plan_by_id

        # Editors use a status/runtime guard. Re-read after claiming arranging so
        # an edit saved immediately before dispatch cannot be lost to a stale row.
        latest = get_plan_by_id(plan["id"])
        if latest is None:
            return
        plan.update(latest)

    skill_index = plan["skill_index"] + 1  # 0-indexed to 1-indexed for display
    deadline = datetime.now() + ARRANGING_DEADLINE
    unknown_cnt = 0
    # #15 诊断粒度：各场景次数 / 最后场景 / 是否到过确认页 / 重进房次数 / 最大连续同场景
    tracker = _SceneTracker()
    checked_slot = False
    checked_target = False
    support_prepared = False
    support_level_to_prepare = None
    # #72：数星星前的身份/归属确认。只在 TRAIN_MAIN 训练位校验通过并主动点开技能
    # 选择页时置位；未置位就出现 219（重启停在技能选择页 / 手动进入）→ 219 分支保守退出。
    identity_confirmed = False
    unconfirmed_select_cnt = 0

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
            countdown_state, countdown = _read_train_countdown3(solver)
            if (
                countdown_state == "active"
                and countdown is not None
                and countdown > datetime.now()
            ):
                # 训练室使用中（#16 决议）：保持 idle，重排到倒计时+缓冲，退出。
                # 重检任务标签只写真正读到的房间里是谁——刚读过倒计时，同一张图上
                # 顺带读一次面板文字（成本只是再 OCR 一块区域），不再拿计划干员充数。
                _exit_occupied(
                    solver,
                    plan,
                    countdown,
                    trigger="训练室占用",
                    panel=_read_panel_text(solver),
                )
                return
            if countdown_state == "zero":
                # #211：00:00:00 待收取 → 训练位锁定，不能换人；保持 idle 重排退出。
                # 旧的 _read_train_countdown 把 zero 和没倒计时都折叠成 None，分不清
                # 待收取/空闲，会被误判空闲而换入锁定的训练位（原靠 train_slot_locked 兜底）。
                _exit_occupied(
                    solver,
                    plan,
                    None,
                    trigger="训练室待收取",
                    panel=_read_panel_text(solver),
                )
                return
            if support_level_to_prepare is not None:
                from arknights_mower.solvers.mastery_support_runtime import (
                    prepare_plan_supports,
                )

                try:
                    prepare_plan_supports(solver, plan, support_level_to_prepare)
                except SupportPlanError as exc:
                    _exit_failed(
                        solver, plan, str(exc), step_level=support_level_to_prepare
                    )
                    return
                support_prepared = True
                step_level = support_level_to_prepare
                support_level_to_prepare = None
                checked_target = False
            if not checked_slot:
                checked_slot = True
                # #93：复用 reconcile 读房已读的槽位（省重复浮窗开关）。#100：空串有两个
                # 来源——真空位与读浮窗失败；只有 reliable（_read_slots_checked 过了场景
                # 闸门）为真时，空串才是「确实没人」；读到名字＝确实有人。
                room_train_slot = getattr(room, "train_slot", None)
                room_slots_reliable = getattr(
                    room, "slots_reliable", bool(room_train_slot)
                )
                if room is not None and (room_train_slot or room_slots_reliable):
                    trainer_slot, slot_reliable = room_train_slot, room_slots_reliable
                else:
                    # 兜底重读走同一道闸门（#140 场景确认 + #100 读失败闸门），浮窗由
                    # reader 自己点关闭按钮关掉——不再有「裸读 get_agent_from_room」：
                    # 那既不看场景（非 205 的垃圾读也当依据），读后还会无条件多按一次 back。
                    _, trainer_slot, _, slot_reliable = _read_slots_checked(solver)
                char_name = _plan_char_label(plan)
                if not (trainer_slot or slot_reliable):
                    # 读不到训练位 → 不换人（读失败不得当真空位做 mutation，稳为先）：
                    # 保持 idle + 重排 + 退出，等下一轮重读，绝不盲点换人/开训。
                    logger.warning(
                        "[mastery] 训练位读取失败（真空位与读失败不可分），"
                        "跳过换人核验，保持 idle 重排"
                    )
                    _exit_occupied(solver, plan, None, trigger="训练位读取失败")
                    return
                if trainer_slot != char_name:
                    # 走到这里只剩「倒计时没读出来 + 训练位非计划干员（坐错人或为空）」：
                    # 倒计时读得出有效值/00:00:00 的两种占用情形上面已经 return 了。
                    # 换入计划干员。
                    slot_desc = trainer_slot or "空"
                    logger.info(f"训练位为 {slot_desc}，换入 {char_name}")
                    try:
                        _swap_into_wrong_slot(solver, plan)
                    except Exception as e:
                        logger.warning(f"换人失败: {e}")
                        _exit_failed(
                            solver,
                            plan,
                            f"训练位当前干员为（{trainer_slot}），换人失败",
                        )
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
                # （误开训练/误判完成，#70 只挡 None）→ 先尝试退回主界面重新核验，多次失败再保守退出。
                char_name = _plan_char_label(plan)
                logger.warning(
                    f"处于技能选择页，但未在主界面核验训练位是否为【{char_name}】"
                    "（无法确认当前技能归属），尝试返回训练室主界面重新核验"
                )
                if unconfirmed_select_cnt < 1:
                    unconfirmed_select_cnt += 1
                    _back_to_train_main(solver)
                    continue
                _exit_occupied(solver, plan, None, trigger="技能选择页归属未确认")
                return
            if not checked_target:
                from arknights_mower.solvers.mastery_reader import (
                    AMIYA_FORM_IDS,
                    read_amiya_skill_available,
                )

                if plan["char_id"] in AMIYA_FORM_IDS:
                    available = read_amiya_skill_available(solver, plan)
                    if available is not True:
                        _defer_amiya_form(solver, plan, room, available)
                        return
                # #63 已到target检测：读目标技能槽亮灯，≥target → 判 completed（防 false-fail）
                checked_target = True
                tier = _read_slot_mastery_tier(solver, plan["skill_index"])
                if tier is not None and tier >= plan["target_level"]:
                    logger.info(
                        f"{_plan_char_label(plan)} 技能{skill_index} 已在专{tier}，无需训练，判定完成"
                    )
                    _log_transition(plan, "completed", "已到target检测", 档位=tier)
                    update_plan_status(plan["id"], "completed")
                    _notify_at_target(solver, plan, tier)  # §10.2 ⑥
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
                if support_prepared and tier + 1 != step_level:
                    _exit_failed(solver, plan, "协助方案校验后专精档位发生变化，请重试")
                    return
                if plan.get("support_plan") and not support_prepared:
                    support_level_to_prepare = tier + 1
                    solver.back()  # The next TRAIN_MAIN iteration validates the route.
                    continue
                step_level = tier + 1
            height = (skill_index - 1) * 0.3 + 0.32
            solver.ctap((solver.recog.w * 0.33, solver.recog.h * height))
        elif scene == Scene.TRAIN_SKILL_UPGRADE:
            if plan.get("support_plan") and not support_prepared:
                _exit_failed(solver, plan, "尚未完成协助方案校验，停止开训")
                return
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


def _defer_amiya_form(solver, plan, room, available):
    from arknights_mower.solvers.mastery_reader import (
        AMIYA_FORM_WAIT_REASON,
        _schedule_amiya_form_recheck,
    )
    from arknights_mower.utils.mastery_db import update_plan_status

    # No assistant mutation has occurred before the skill-name check.
    if room is not None and room.slots_reliable:
        support, trainee, reliable = room.support_slot, room.train_slot, True
    else:
        _back_to_train_main(solver)
        support, trainee, _, reliable = _read_slots_checked(solver)
    holding = reliable and trainee == "阿米娅" and support in PROTECT_OPERATORS
    if holding:
        solver.amiya_pending_plan_id = plan["id"]
        if room is not None:
            room.amiya_form_waiting = True
    update_plan_status(plan["id"], "idle", failed_reason=AMIYA_FORM_WAIT_REASON)
    _schedule_amiya_form_recheck(solver, plan)
    _notify_amiya_form_wait(plan, available, holding)
    solver.back_to_infrastructure()


def _notify_amiya_form_wait(plan, available, holding):
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.device.recovery import DeviceRecoveryError
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    if available is False:
        message = (
            f"{_plan_fail_label(plan)}：训练室显示其他升变形态的技能，"
            "请在游戏内手动切换到对应升变形态"
        )
    else:
        message = f"{_plan_fail_label(plan)}：目标技能读取失败，暂不开始专精"
    if holding:
        message += "；保留当前减半干员，本轮跳过所有训练室操作，后续仍会进房检查"
    logger.warning(message)
    try:
        reason = "mismatch" if available is False else "unreadable"
        if should_notify("amiya_form", f"{plan['id']}:{reason}:{int(holding)}"):
            send_message(
                message,
                level="ERROR" if holding and available is False else "WARNING",
                archive_screenshots=True,
            )
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception as exc:
        logger.warning(f"阿米娅升变提醒发送失败：{exc}")


def _confirm_training_started(
    solver, plan, deadline, arrange_support=True, step_level=None
):
    """确认训练已开始（读到有效倒计时）→ 转入 TRAINING，然后安排协助位。

    并入 #15 的全局 10 分钟 deadline（由调用方传入），不单独分段计时。
    step_level：扫描派发算出的本次安排步级，供归属校验失败邮件报「本次要练的专几」。
    返回 "started" / "failed" / "timeout"：
    - started: 已转入 TRAINING，已安排后续任务或保留待确认的协助安排
    - failed: 材料不足 或 #69/B2 面板干员/技能与计划不符，已标记 failed + 通知 + 退出训练室
    - timeout: deadline 内未确认训练开始（含面板不可读无法校验归属），由调用方走统一超时出口
    #103：路线 operator 每次开始照常安排（2026-08-17 用户拍板，原 #63 减半守卫的
    arrange_support=False 已删——「收取后级联」也安排路线 operator，见 _start_new_training）。
    """
    from arknights_mower.solvers.mastery_support_state import enqueue_support_swap
    from arknights_mower.utils import config
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import update_plan_status

    backed_from_skill_select = False
    while datetime.now() < deadline:
        scene = solver.train_scene()
        # #89：219 是技能选择页，读不出倒计时。确认升级后游戏自动退回 219，必须先
        # back 一次回训练室主页面（217）再读倒计时（§5.2 第 3 步「再退出一次」）。
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
                if panel.operator_name not in agent_list or not panel.skill_name:
                    logger.debug(
                        "训练室已出有效倒计时但面板干员或技能不可确认，"
                        "暂不写入 training，等待归属可读"
                    )
                    solver.sleep(1)
                    continue
                if not _plan_matches_room(plan, RoomState("training", panel)):
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
                requested_level = step_level
                try:
                    step_level = _count_lit_mastery_icons(solver)
                except Exception:
                    step_level = None
                notes: list[str] = []
                try:
                    from arknights_mower.solvers.record import apply_mastery_inventory

                    paid_level = (
                        step_level
                        if type(step_level) is int and 1 <= step_level <= 3
                        else requested_level
                    )
                    apply_mastery_inventory(
                        plan["char_id"], plan["skill_index"], paid_level
                    )
                except Exception:
                    logger.exception("已确认专精开训，但材料库存扣减失败")
                    notes.append("材料库存扣减失败，请执行仓库识别校准库存")
                expires_at = execute_time.strftime("%Y-%m-%d %H:%M:%S")
                _log_transition(plan, "training", "倒计时确认", 完成时间=expires_at)
                update_plan_status(
                    plan["id"],
                    "training",
                    failed_reason="",
                    expires_at=expires_at,
                    swap_frozen=0,
                )
                plan.update(status="training", expires_at=expires_at, swap_frozen=0)
                # 训练已确认开始，后续协助安排失败保留独立换人任务，不重开训练。
                # 取消和设备恢复异常保存续行责任后透传；普通失败原因写入开训邮件。
                # #76：主面板专精图标在训练中 = 当前步目标级（亮 N 颗=专N）。确认开始
                # 后先读图标作当前步级，传给协助位/换人安排（专三计划专一/专二步用
                # level_1/2 路线减半换人）；同值复用作收取任务目标档位（原 tier）。
                # #89：走到这里已 back 回 217 主页面，图标可读。
                support_pending = False
                if arrange_support:
                    try:
                        arrange_error = _arrange_support(solver, plan, step_level)
                    except (MowerExit, DeviceRecoveryError):
                        recovery = enqueue_support_swap(
                            solver, plan, datetime.now(), "计划协助者"
                        )
                        recovery.mastery_swap_verify_only = True
                        raise
                    if isinstance(arrange_error, str) and arrange_error:
                        recovery = enqueue_support_swap(
                            solver, plan, datetime.now(), "计划协助者"
                        )
                        recovery.mastery_swap_verify_only = True
                        support_pending = True
                        notes.append(
                            f"协助位没能安排（{arrange_error}），已保留换人任务，"
                            "后续实读后继续安排"
                        )
                # 协助位安排后倒计时会变化；后续安排使用新读数，旧读数仅保留展示。
                fresh_execute_time = (
                    execute_time
                    if support_pending
                    else _re_read_train_countdown(solver)
                )
                if fresh_execute_time is None:
                    fresh_execute_time = execute_time
                    notes.append(
                        "换协助位后没能重新读到剩余时间，显示的完成时间暂用换人前读数"
                    )
                    if arrange_support and not config.conf.assistant_follows_schedule:
                        recovery = enqueue_support_swap(
                            solver, plan, datetime.now(), "计划协助者"
                        )
                        recovery.mastery_swap_verify_only = True
                        support_pending = True
                        notes.append("已保留换人任务，后续实读后继续安排")
                if plan.get("support_plan") and not support_pending:
                    from arknights_mower.solvers.mastery_support_state import (
                        refresh_end,
                    )

                    # 这条时间戳是「这位协助者这一次帮忙算到几点」，下一级用它算帮忙
                    # 满没满 5 小时（减半攒在上一级）；写不进去只影响下一级的减半估算。
                    try:
                        recorded = refresh_end(plan, step_level, fresh_execute_time)
                    except Exception as e:
                        recorded = False
                        logger.warning(
                            f"[mastery] 协助者出勤记录保存异常 id={plan['id']}: {e}"
                        )
                    if not recorded:
                        notes.append(
                            "协助者出勤记录没能保存，下一级开始时可能算不准减半时长"
                        )
                # §5.2：排了换人任务则不排收取；等 SWAP_SUPPORT 完成后重读倒计时再排收取。
                # #90：返回 SWAP 任务触发时刻（None=不换人），邮件完成时间据此分两情况。
                # 中途换人的目的是给下一级攒这 5 小时减半，不是加速这一级——排不上丢的是
                # 下一级的减半，这一级的训练照旧在跑，所以只报告、不标失败。
                try:
                    swap_time = (
                        None
                        if support_pending
                        else _schedule_swap_if_needed(
                            solver, plan, fresh_execute_time, step_level
                        )
                    )
                    swap_error = None
                except (MowerExit, DeviceRecoveryError):
                    recovery = enqueue_support_swap(
                        solver, plan, datetime.now(), "计划协助者"
                    )
                    recovery.mastery_swap_verify_only = True
                    raise
                except Exception as e:
                    logger.warning(f"[mastery] 安排中途换人失败 id={plan['id']}: {e}")
                    swap_time, swap_error = None, str(e)
                if swap_error is not None:
                    recovery = enqueue_support_swap(
                        solver, plan, datetime.now(), "计划协助者"
                    )
                    recovery.mastery_swap_verify_only = True
                    support_pending = True
                    notes.append(
                        f"没能安排中途换人（{swap_error}），已保留换人任务，"
                        "后续实读后继续安排"
                    )
                # #90：DB 里的 expires_at 也要用换协助位后的最终倒计时（安排前的倒计时
                # 基于旧效率、不是最终完成时间）；同值跳过 DB 写（#82 同款）。
                if fresh_execute_time != execute_time:
                    expires_text = fresh_execute_time.strftime("%Y-%m-%d %H:%M:%S")
                    # update_plan_status 自己吞异常，返回值是唯一的失败信号。这里不再
                    # 原样重试：同样的参数必然同样失败，白写一次没有意义。写不进去只
                    # 影响展示用的完成时间，下一次状态核对会拿屏幕上的读数纠正。
                    if not update_plan_status(
                        plan["id"], "training", expires_at=expires_text
                    ):
                        logger.warning(
                            f"[mastery] 完成时间写库失败 id={plan['id']} "
                            f"expires_at={expires_text}（下次状态核对会用屏幕读数纠正）"
                        )
                # #90：邮件移到协助位安排 + 换人判定之后发（此时效率/倒计时已确定）；
                # 真名 = plan["skill_name"]；档位 = 目标级（step_level，不加1），读不到
                # 显示「专精等级未知」（不回退 target_level）；完成时间两情况——无减半 =
                # 重读倒计时、有减半 = 换人任务时刻 + (300 + 缓冲) 分钟，附换入干员名。
                tier_text = f"专{step_level}" if step_level else "专精等级未知"
                if swap_time is not None:
                    # 取路线只为邮件里那句「将于 X 换入谁」和缓冲时长；失败就退回默认
                    # 缓冲、不写换入对象，报错邮件里已经说明换人是怎么失败的。
                    try:
                        route = _get_plan_route(plan, step_level)
                    except Exception as e:
                        logger.warning(
                            f"[mastery] 换人路线读取失败 id={plan['id']}: {e}"
                        )
                        route = None
                    swap_target = route.get("swap_target") if route else None
                    buffer = (
                        route.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES)
                        if route
                        else DEFAULT_SWAP_BUFFER_MINUTES
                    )
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
                if notes:
                    # 收尾哪几件没做成，如实写在末尾——训练确实开始了，级别仍是 INFO。
                    msg = f"{msg}；{'；'.join(notes)}"
                logger.info(msg)
                send_message(msg, level="INFO")
                if swap_time is None and not support_pending:
                    collect_error = _schedule_collect_checked(
                        solver, plan, fresh_execute_time, step_level
                    )
                    if collect_error:
                        _notify_collect_unscheduled(plan, step_level, collect_error)
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


def _arrange_support(solver, plan, step_level=None) -> Optional[str]:
    """训练确认开始后，安排协助位干员（复用 choose_train）

    #76：路线按当前步目标级加载（step_level，确认时读主面板图标）；
    step_level 读不到回退 target_level（保守用整体目标路线）。

    返回值：None = 这一级不用安排（跟随排班 / 路线没 operator）或已安排成功；
    错误文案 = 协助位尚未确认。调用方保留换人任务，并将原因补进开训邮件。
    """
    from arknights_mower.utils import config

    if config.conf.assistant_follows_schedule:
        return None
    try:
        route = _get_plan_route(plan, step_level)
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception as e:
        logger.warning(f"协助位路线读取失败: {e}")
        logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=路线读取失败 err={e}")
        return str(e)
    if route is None:
        return "当前阶段协助路线尚未确认"
    if not route.get("operator"):
        return None
    support_name = route["operator"]
    logger.info(f"安排协助位：{support_name}")
    logger.debug(f"[mastery] 协助位判定 id={plan['id']} 期望={support_name} 动作=安排")
    try:
        if plan.get("support_plan"):
            plan["swap_frozen"] = 0
            if "exclude_reducer" in route:
                from arknights_mower.solvers.mastery_support_state import save_runtime

                save_runtime(plan, route)
            from arknights_mower.solvers.mastery_support_swap import place_support

            place_support(solver, plan, step_level, support_name)
        else:
            solver.choose_train([support_name, "Current"])
        logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=ok")
        return None
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception as e:
        logger.warning(f"安排协助位失败: {e}")
        logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=失败 err={e}")
        return str(e)


def _re_read_train_countdown(solver) -> Optional[datetime]:
    """#90 §5.2 第7步「以当前读取为准」：协助位安排后重读倒计时。

    choose_train 换协助位后停在进驻详情浮窗（INFRA_DETAILS），先关浮窗回主页面再读
    （back() 内部 sleep→recog.update 已重置场景缓存，与 _swap_still_worthwhile/
    _schedule_collect_after_swap 同款关浮窗读法）。

    改用带重试的读法（最多 5 次，每次先确认在训练室主页面、浮窗先关，与换人路径
    _read_countdown_with_retry 同款）：换协助位刚把画面甩到浮窗/过渡态，读一次就放弃
    太早，完成时间会白白退回换人前的旧读数。仍读不到 → None，调用方退回安排前倒计时，
    并在开训邮件里说明这一点。
    """
    return _read_countdown_with_retry(solver)


def _schedule_swap_if_needed(
    solver, plan, execute_time, step_level=None
) -> Optional[datetime]:
    """训练开始后计算是否需要换人，需要则插入 SWAP_SUPPORT 任务。

    §5.2：返回 SWAP 任务触发时刻（None=不排换人）——排了换人则不排收取（等
    SWAP_SUPPORT 完成后重读倒计时再排收取）。立即换人（remaining ≤ threshold）也排
    任务（修旧 silent-drop）。#90 邮件「有减半」的完成时间 = 返回时刻 + (300+缓冲) 分。
    当前技能的后续阶段或同干员已达专一的下一技能需要减半时安排换人。
    步级未知或下一技能尚未专一时，最终阶段不安排减半换人。
    """
    from arknights_mower.utils import config
    from arknights_mower.utils.mastery_order import halving_successor
    from arknights_mower.utils.mastery_support_data import actual_central_bonus

    if not halving_successor(plan, step_level):
        return None

    if config.conf.assistant_follows_schedule:
        return None

    if plan.get("support_plan"):
        from arknights_mower.solvers.mastery_support_state import schedule_support_swap

        return schedule_support_swap(solver, plan, execute_time, step_level)

    route = _get_plan_route(plan, step_level)
    if route is None:
        raise TrainingObservationError("换人路线未确认，保留换人意图")
    if not route or not route.get("swap_target"):
        return None

    central_bonus = route.get("central_bonus", 0)
    buffer = route.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES)

    remaining = (execute_time - datetime.now()).total_seconds() / 60
    should_swap, threshold = calc_swap_threshold(
        route["efficiency"],
        route.get("job_match", False),
        central_bonus,
        remaining,
        buffer,
        current_central=actual_central_bonus(solver, central_bonus),
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

    # #230：档位显示当前步（当前级 → 步目标级，与收取标签同式），不写死计划最终
    # 目标 target_level；step_level 读不到时只留换入对象、不显示档位（不回退
    # target_level，避免任务列表误导为计划目标级）。
    if isinstance(step_level, int) and step_level >= 1:
        level_text = (
            f"{_target_label(max(0, step_level - 1))} → {_target_label(step_level)} "
        )
    else:
        level_text = ""
    current = getattr(solver, "task", None)
    retained = next(
        (
            task
            for task in solver.tasks
            if task is not current
            and task.type == TaskTypes.SWAP_SUPPORT
            and getattr(task, "plan_key", None) == str(plan["id"])
            and (
                getattr(task, "execution_failure", None)
                or getattr(task, "execution_retained", False)
            )
        ),
        None,
    )
    if retained is not None:
        return retained.time
    existing = next(
        (
            task
            for task in solver.tasks
            if task is not getattr(solver, "task", None)
            and task.type == TaskTypes.SWAP_SUPPORT
            and getattr(task, "plan_key", None) == str(plan["id"])
        ),
        None,
    )
    if existing is not None:
        existing.time = (
            min(existing.time, swap_time)
            if getattr(existing, "advance_support_swap", False)
            else swap_time
        )
    else:
        task = SchedulerTask(
            time=swap_time,
            task_type=TaskTypes.SWAP_SUPPORT,
            meta_data=f"{_plan_label(plan)} {level_text}换入{route['swap_target']}",
        )
        task.plan_key = str(plan["id"])
        solver.tasks.append(task)
    logger.info(f"已安排换人任务，预计 {swap_time.strftime('%H:%M:%S')} 执行")
    return swap_time


def _read_swap_panel(solver, plan):
    """未确认的训练状态交给调度器恢复，不能结束换人任务。"""
    try:
        scene = solver.train_scene()
        if scene == Scene.INFRA_DETAILS:
            _close_room_detail(solver)
            scene = solver.train_scene()
        if scene == Scene.TRAIN_FINISH:
            return scene, None
        if scene == Scene.TRAIN_MAIN:
            panel = read_main_panel(solver)
            if panel is not None and panel.countdown_state == "zero":
                return scene, panel
            if (
                panel is not None
                and panel.countdown_state == "active"
                and panel.countdown is not None
                and type(panel.mastery_tier) is int
                and 1 <= panel.mastery_tier <= 3
                and panel.operator_name
                and panel.skill_name
                and _plan_matches_room(plan, RoomState("training", panel))
            ):
                return scene, panel
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception as exc:
        raise TrainingObservationError("训练室面板读取失败，保留换人任务") from exc
    raise TrainingObservationError("训练室面板未确认，保留换人任务等待新实测")


def run_swap_support(solver):
    """确认训练与协助位后换人；读取或安排失败保留当前任务。"""
    from arknights_mower.utils import config
    from arknights_mower.utils.mastery_db import get_active_plan
    from arknights_mower.utils.mastery_support_data import actual_central_bonus

    logger.debug("[mastery] 训练室动作 触发源=定时任务 动作=swap")
    if not config.conf.enable_mastery:
        logger.debug("[mastery] 全自动专精已关闭，跳过换协助位")
        return
    if config.conf.assistant_follows_schedule:
        return

    if isinstance(getattr(solver, "amiya_pending_plan_id", None), int):
        from arknights_mower.solvers.mastery_reader import read_room_state

        room = read_room_state(solver)
        if room.amiya_form_waiting:
            solver.back_to_infrastructure()
            return

    plan = get_active_plan()
    if not plan or plan["status"] != "training":
        return
    task_plan = getattr(getattr(solver, "task", None), "plan_key", None)
    if task_plan is not None and str(task_plan) != str(plan["id"]):
        return
    from arknights_mower.utils.mastery_order import basic_mastery_successor

    solver.enter_room("train")
    scene, panel = _read_swap_panel(solver, plan)
    step_level = panel.mastery_tier if panel is not None else None
    if scene == Scene.TRAIN_FINISH or panel.countdown_state == "zero":
        _schedule_collect(solver, plan, datetime.now(), tier=step_level)
        solver.back()
        return
    countdown_active = bool(panel is not None and panel.countdown_state == "active")
    task = getattr(solver, "task", None)
    collect_pending = getattr(task, "mastery_collect_pending", False) is True
    collect_level = getattr(task, "mastery_collect_level", None)
    if collect_pending and type(collect_level) is int and collect_level != step_level:
        from arknights_mower.utils.mastery_db import update_plan_status

        if plan["swap_frozen"]:
            try:
                saved = update_plan_status(plan["id"], "training", swap_frozen=0)
            except (MowerExit, DeviceRecoveryError):
                raise
            except Exception as exc:
                raise TrainingObservationError("新训练阶段的协助位记录未保存") from exc
            if saved is False:
                raise TrainingObservationError("新训练阶段的协助位记录未保存")
            plan["swap_frozen"] = 0
        task.mastery_collect_pending = False
        task.__dict__.pop("mastery_collect_level", None)
        collect_pending = False
    if (
        collect_pending
        and collect_level == step_level
        or plan["swap_frozen"]
        and not basic_mastery_successor(plan, step_level)
    ):
        _schedule_collect_after_swap(solver, plan, tier=step_level)
        solver.back()
        return

    _warn_training_room_group(plan)

    route = _get_plan_route(plan, step_level)
    if route is None:
        raise TrainingObservationError("当前训练阶段的协助路线未确认，保留换人任务")
    if route:
        route["current_central"] = actual_central_bonus(
            solver, route.get("central_bonus", 0)
        )
    operator = route.get("operator") if route else None
    swap_target = route.get("swap_target") if route else None

    # #79 协助位确认：开进驻浮窗读实际协助位（_read_slots_checked 读后自动关浮窗回
    # 主页面）。协助位 ∉ {operator, swap_target}（陌生人/空位）→ 坐错人纠错成 operator
    # （#80）、空位一步定夺（#101）。只在倒计时 active（训练确认）时动协助位——
    # 00:00:00 收取边界不动（铁律 6）；读失败（reliable=False，OCR 坏名等）不动作
    # （稳为先：读不到就不动，防基于不可靠读撤销已减半）。
    if plan.get("support_plan"):
        from arknights_mower.solvers.mastery_support_dispatch import run_planned_swap

        run_planned_swap(solver, plan, panel)
        return
    if not operator and not swap_target:
        _schedule_collect_after_swap(solver, plan, tier=step_level)
        solver.back()
        return
    try:
        support_slot, _, _, reliable = _read_slots_checked(solver)
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception as exc:
        raise TrainingObservationError("训练室驻员读取失败，保留换人任务") from exc
    if not reliable:
        raise TrainingObservationError("训练室驻员未确认，保留换人任务等待新实测")
    if operator and reliable and support_slot not in (operator, swap_target):
        # #107 保护门（2026-08-17）：逻各斯/艾丽妮在协助位（非路线干员/减半对象）且
        # 剩余不足 5h+缓冲 → 不纠不换——她们本身是最优加成，路线干员+减半收益在这里
        # 赶不上；只排收取退出（expires_at 已由 B8 采纳门刷新）。剩余足够才照常纠错
        # 走减半流程。必须整段 return：否则落到 did_swap 会用路线效率(75)判值得、
        # 直接换减半对象，绕过「不换人」。
        if (
            support_slot in PROTECT_OPERATORS
            and not route.get("exclude_reducer")
            and panel is not None
            and panel.countdown is not None
        ):
            remaining_min = (panel.countdown - datetime.now()).total_seconds() / 60
            buffer_min = route.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES)
            if remaining_min < 300 + buffer_min:
                logger.info(
                    f"[mastery] #107 协助位保护：{support_slot} 剩余不足 "
                    f"{300 + buffer_min} 分钟，不纠错换人，仅排收取"
                )
                _schedule_collect_after_swap(solver, plan, tier=step_level)
                solver.back()
                return
        if not support_slot:
            # 先依据确认的剩余时间选择补位或减半；补位后再读取倒计时安排后继任务。
            if countdown_active:
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
                        route.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES),
                        current_central=actual_central_bonus(
                            solver, route.get("central_bonus", 0)
                        ),
                    )
                    place_swap_target = should_swap
                if place_swap_target:
                    # 已到减半时刻 → 直接换入 swap_target（等价于一次减半换人）
                    logger.info(f"协助位空着且已到减半时刻，直接换入 {swap_target}")
                    did_swap = _try_swap(solver, plan, swap_target, step_level)
                    if not did_swap:
                        did_swap = _retry_swap_in_place(
                            solver, plan, route, swap_target, step_level
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
                except (MowerExit, DeviceRecoveryError):
                    raise
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
                        did_swap = _try_swap(solver, plan, swap_target, step_level)
                        if not did_swap:
                            did_swap = _retry_swap_in_place(
                                solver, plan, route, swap_target, step_level
                            )
                    _schedule_collect_after_swap(solver, plan, tier=step_level)
                    solver.back()
                    return
                logger.debug(f"[mastery] 协助位补位 id={plan['id']} 结果=ok")
                # 补位消耗时间 → 重读倒计时（铁律 1 动作前先读房），排阈值时刻换人任务
                scene, panel = _read_swap_panel(solver, plan)
                if scene == Scene.TRAIN_FINISH or panel.countdown_state == "zero":
                    _schedule_collect(solver, plan, datetime.now(), tier=step_level)
                    solver.back()
                    return
                if panel is not None and panel.countdown is not None:
                    # 有换人目标 → 排阈值时刻任务（排了换人就不排收取，§5.2 等 SWAP
                    # 完成后重读再排）；专三/无减半目标 → 直接排收取
                    step_level = panel.mastery_tier if panel is not None else None
                    if (
                        _schedule_swap_if_needed(
                            solver, plan, panel.countdown, step_level
                        )
                        is None
                    ):
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
            except (MowerExit, DeviceRecoveryError):
                raise
            except Exception as e:
                logger.warning(f"协助位补位/纠错失败: {e}")
                logger.debug(
                    f"[mastery] 协助位补位/纠错 id={plan['id']} 结果=失败 err={e}"
                )
                _notify_swap_correction_failed(
                    solver, plan, support_slot, operator, fallback_swap=False
                )
                raise TrainingObservationError(
                    "训练室协助位纠错未完成，保留换人任务"
                ) from e
            else:
                logger.debug(f"[mastery] 协助位补位/纠错 id={plan['id']} 结果=ok")
                support_slot = operator
                # 纠错消耗时间 → 重读倒计时（铁律 1 动作前先读房）
                scene, panel = _read_swap_panel(solver, plan)
                if scene == Scene.TRAIN_FINISH or panel.countdown_state == "zero":
                    _schedule_collect(solver, plan, datetime.now(), tier=step_level)
                    solver.back()
                    return
                countdown_active = bool(
                    panel is not None and panel.countdown_state == "active"
                )
                step_level = panel.mastery_tier if panel is not None else None
                route = _get_plan_route(plan, step_level)
                if route is None:
                    raise TrainingObservationError(
                        "纠错后的训练路线未确认，保留换人任务"
                    )
                if route:
                    route["current_central"] = actual_central_bonus(
                        solver, route.get("central_bonus", 0)
                    )
                swap_target = route.get("swap_target") if route else None

    if (
        getattr(getattr(solver, "task", None), "mastery_swap_verify_only", False)
        is True
        and not getattr(solver.task, "advance_support_swap", False)
        and support_slot == operator
        and swap_target
    ):
        remaining = (panel.countdown - datetime.now()).total_seconds() / 60
        _, threshold = calc_swap_threshold(
            route["efficiency"],
            route.get("job_match", False),
            route.get("central_bonus", 0),
            remaining,
            route.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES),
            current_central=route.get("current_central", route.get("central_bonus", 0)),
        )
        if remaining > threshold:
            if _schedule_swap_if_needed(solver, plan, panel.countdown, step_level):
                solver.back()
                return

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
        did_swap = _try_swap(solver, plan, swap_target, step_level)
        if not did_swap:
            # #81：立刻原地重试（无 +5min 间隔），至多 SWAP_RETRY_LIMIT 次；放弃 → ⑧
            # 通知，不置 swap_frozen（接受下次进房重排，暂时性失败可被救回）
            did_swap = _retry_swap_in_place(
                solver, plan, route, swap_target, step_level
            )
    else:
        logger.info(
            "场景不在训练主页面或倒计时未确认，跳过减半换人"
            if not countdown_active
            else "当前步路线无换人目标、协助位已是减半对象或剩余不足，跳过减半换人"
        )
    # 完成换人或已确认无需换人后，再按新倒计时安排收取。
    _schedule_collect_after_swap(solver, plan, tier=step_level)
    if not did_swap:
        solver.back()


def _try_swap(solver, plan, swap_target, step_level=None) -> bool:
    """换入减半对象后记录收取续行，保存失败也不能重复已完成的换人。"""
    from arknights_mower.utils.mastery_db import update_plan_status

    try:
        solver.choose_train([swap_target, "Current"])
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception as e:
        logger.warning(f"换人失败: {e}")
        logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=失败 err={e}")
        return False
    task = getattr(solver, "task", None)
    if task is not None:
        task.mastery_collect_pending = True
        task.mastery_collect_level = step_level
    try:
        saved = update_plan_status(plan["id"], "training", swap_frozen=1)
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception as exc:
        raise TrainingObservationError(
            "换人已完成，协助位记录保存失败，保留收取规划"
        ) from exc
    if saved is False:
        raise TrainingObservationError("换人已完成，协助位记录保存失败，保留收取规划")
    logger.info("换人完成，协助位已冻结")
    logger.debug(f"[mastery] 协助位判定 id={plan['id']} 结果=ok")
    return True


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
            "已保留换人任务，等待相关新实测后重试"
        )
    send_message(msg, level="WARNING")


def _retry_swap_in_place(solver, plan, route, swap_target, step_level=None) -> bool:
    """有限恢复换人；确认收益窗口结束才终结，未完成安排保留原任务。"""
    retries = 0
    while retries < SWAP_RETRY_LIMIT:
        if not _swap_still_worthwhile(solver, plan, route):
            logger.info("剩余时间不足 5 小时，放弃减半换人（不减半，按全时长收取）")
            return False
        retries += 1
        logger.warning(f"换人失败，原地重试（{retries}/{SWAP_RETRY_LIMIT}）")
        solver.sleep(1)
        if _try_swap(solver, plan, swap_target, step_level):
            return True
    logger.warning("本次换人恢复已达上限，保留换人任务等待新实测")
    _notify_swap_giveup(solver, plan)
    raise TrainingObservationError("训练室协助位换人未完成，保留换人任务")


def _notify_swap_giveup(solver, plan):
    """通知本次恢复耗尽；原任务由相关新实测重新准入。"""
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    if not should_notify("swap_failed_giveup", str(plan["id"])):
        return
    label = _plan_fail_label(plan)
    msg = f"{label} 本次换人未完成，已保留任务，等待相关新实测后重试"
    send_message(msg, level="WARNING")


def _swap_worthwhileness(remaining_minutes, route) -> bool:
    """最后检查两边都计入中枢，预计剩余 ≥ 301 分钟才值得换人。

    与 calc_swap_threshold 的 real_time_after_swap 守卫一致；供 run_swap_support
    纠错/换人前用当前倒计时判定（#80：纠错不触发不该发生的减半换人）。
    """
    swap_total, current_total = _swap_speed_totals(
        route.get("job_match", False),
        route["efficiency"],
        route.get("central_bonus", 0),
    )
    current_total += route.get(
        "current_central", route.get("central_bonus", 0)
    ) - route.get("central_bonus", 0)
    real_time_after_swap = remaining_minutes * current_total / swap_total
    return real_time_after_swap >= 301


def _swap_still_worthwhile(solver, plan, route) -> bool:
    """恢复安排前重新确认剩余时间，未知读数不授权再次换人。"""
    countdown = _read_countdown_with_retry(solver)
    if countdown is None:
        raise TrainingObservationError("恢复换人前的倒计时未确认，保留换人任务")
    remaining = (countdown - datetime.now()).total_seconds() / 60
    return _swap_worthwhileness(remaining, route)


def _read_countdown_with_retry(solver) -> Optional[datetime]:
    """轻量倒计时读取 + 原地重试（至多 5 次）：先确认在训练室主页面（TRAIN_MAIN），
    浮窗先关再读；仍读不到 → None（调用方保守处理）。
    """
    countdown = None
    for attempt in range(5):
        try:
            scene = solver.train_scene()
            if scene == Scene.INFRA_DETAILS:
                _close_room_detail(solver)
                scene = solver.train_scene()
            if scene == Scene.TRAIN_FINISH:
                return datetime.now()
            if scene == Scene.TRAIN_MAIN:
                state, countdown = _read_train_countdown3(solver)
                if state == "zero":
                    return datetime.now()
                if countdown is not None:
                    break
        except (MowerExit, DeviceRecoveryError):
            raise
        except Exception:
            pass
        if attempt < 4:
            solver.sleep(1)
    return countdown


def _schedule_collect_after_swap(solver, plan, tier=None):
    """按新确认的训练完成时间安排收取；未知时保留原任务的收取续行。"""
    task = getattr(solver, "task", None)
    if task is not None:
        task.mastery_collect_pending = True
        task.mastery_collect_level = tier
    countdown = _read_countdown_with_retry(solver)
    if countdown is None:
        raise TrainingObservationError("换人后的训练倒计时未确认，保留收取规划")
    _schedule_collect(solver, plan, countdown, tier=tier)


def _get_plan_route(plan, step_level=None) -> dict | None:
    """获取计划对应的路线配置。

    #76：路线按「当前步目标级」加载（step_level），而非整体目标 plan["target_level"]——
    一个专三计划 专一→专二→专三 三步分别用 level_1/2/3 路线。step_level 缺省/读失败
    （None/0）时回退 plan["target_level"]（=旧行为，保守）。
    """
    level = step_level or plan["target_level"]
    from arknights_mower.solvers.mastery_support_runtime import (
        route_without_unusable_reducer,
    )
    from arknights_mower.utils.mastery_order import halving_successor

    successor = halving_successor(plan, step_level)
    if plan.get("support_plan"):
        from arknights_mower.utils.mastery_support import stage_for

        route = stage_for(plan, level)
        if route and not successor:
            route["swap_target"] = None
        return route_without_unusable_reducer(plan, step_level, route)
    try:
        from arknights_mower.utils.mastery_recommendation import get_skill_data

        char_data = get_skill_data().get("characters", {}).get(plan["char_id"], {})
        prof_en = char_data.get("profession", "")
        prof_cn = PROF_MAP.get(prof_en, prof_en)
        from arknights_mower.utils.mastery_support_types import route_swap_buffer

        route = get_route_config(prof_cn, level)
        if route:
            route = {**route, "mastery_swap_buffer": route_swap_buffer(route, level)}
            if not successor:
                route = {**route, "swap_target": None}
            elif level >= plan["target_level"] and not route.get("swap_target"):
                reducer = DEFAULT_ROUTES.get(prof_cn, {}).get("level_2", {})
                route = {
                    **route,
                    "swap_target": reducer.get("swap_target"),
                    "job_match": reducer.get("job_match", False),
                }
        return route_without_unusable_reducer(plan, step_level, route)
    except Exception as e:
        logger.error(f"获取路线配置失败: {e}")
        return None
