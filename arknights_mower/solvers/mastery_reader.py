"""共享训练室状态读取器（#63 / #73）。

训练室**一次进房读全部状态**，在自然触发点（SKILL_UPGRADE dispatch、排班房间
循环、仓库扫描）顺路调用，并按 #61/#73 状态矩阵执行对账动作。

铁律：
- training 状态永远先读房（主页面面板干员名），`expires_at` 只是调度提示；
- DB 与截图冲突**以截图为准**；
- 一次进房做完全部动作（读+动作不拆两次）；短动作（核实/帮收/重置/对账）可排班路径
  内联，长动作（开始训练）返回给调用方（SKILL_UPGRADE dispatch）执行。

#73 重设计（doc/mastery-constraints.md §16）：
- 三态倒计时（有值 / 00:00:00 / 读失败），不再把读失败和 00:00:00 都压成 now；
- 状态矩阵（倒计时×干员/技能存在×图标亮点），OCR 失败组合原地重试 5 次；
- 待收取 7 格动作（图标×协助位×计划）、保护检查（逻各斯/艾丽妮）、恢复流程、
  材料门控、逐轮结构化判定日志。

读取能力（坐标已钉，见 #61）：
- 主页面面板（主读取器）：`[干员名]技能名`、倒计时、专精图标（亮 N 颗 = 在专N/专N完成）；
- 进驻详情浮窗：协助位/训练位干员（保护检查用）；
- 技能选择页 lit_zones 按 DB skill_index 直接读对应槽（已到target检测）；
- 收集页只截图不读文本。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from arknights_mower.utils import config
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.skill_label import (
    format_skill_label,
    panel_skill_matches,
    resolve_panel_skill,
)

# 主页面面板坐标（#61 已钉）
PANEL_REGION = ((239, 878), (776, 977))  # `[干员名]技能名`
COUNTDOWN_REGION = ((236, 978), (380, 1020))  # 训练位倒计时
MASTERY_ICON_REGION = ((337, 833), (373, 866))  # 专精图标（亮N颗=在专N/专N完成）
# 主面板专精图标区内三颗星（1080p 实测校准）。点亮顺序 顶→右下→左下。
MASTERY_ICON_PIPS = [
    ((346, 835), (358, 847)),  # 专一（顶）
    ((353, 848), (365, 860)),  # 专二（右下）
    ((338, 848), (350, 860)),  # 专三（左下）
]

ARRANGING_RETRY_BUFFER = timedelta(minutes=2)

# §16.5 保护检查：协助位是这些干员时训练室受保护（不能被排班/mower 改动）
PROTECT_OPERATORS = ("逻各斯", "艾丽妮")

# 技能选择页目标技能槽的专精星（已到target检测）。实机坐标已校准：
# 每个技能 3 颗星，三角排列，点亮顺序 顶→右下→左下：专一=顶、专二=右下、
# 专三=左下（专N 亮前 N 颗）。键为 skill_index（0/1/2）。
SKILL_SLOT_PIPS = {
    0: [
        ((596, 167), (631, 202)),  # 专一（顶）
        ((618, 203), (653, 238)),  # 专二（右下）
        ((575, 203), (610, 238)),  # 专三（左下）
    ],
    1: [
        ((596, 483), (631, 518)),
        ((618, 518), (653, 553)),
        ((575, 518), (610, 553)),
    ],
    2: [
        ((596, 799), (631, 834)),
        ((618, 835), (653, 870)),
        ((575, 835), (610, 870)),
    ],
}
# 单颗星判亮阈值（在框内缩进 PIP_INSET 的内核区域统计，避开抗锯齿边缘/框线）
PIP_BRIGHTNESS = 150
PIP_LIT_RATIO = 0.45
PIP_INSET = 2


@dataclass
class RoomPanel:
    """主页面面板读取结果（全部信息源）。"""

    operator_name: str = ""
    skill_name: str = ""
    mastery_tier: int = 0  # 专精图标亮灯计数 0-3
    # 三态倒计时（§16.8）：
    # - "active"：countdown = 结束时刻（读到非 0 秒）；
    # - "zero"：读到 00:00:00（countdown=None）；
    # - "failed"：读失败（countdown=None）。不再把读失败和 00:00:00 都压成 now。
    countdown: Optional[datetime] = None
    countdown_state: str = "failed"


@dataclass
class RoomState:
    """训练室房间状态（截图权威）。"""

    state: str = "empty"  # "training" | "waiting_collect" | "empty"
    panel: RoomPanel = field(default_factory=RoomPanel)
    support_slot: str = ""  # 协助位干员（进驻详情浮窗，§16.1）
    train_slot: str = ""  # 训练位干员（进驻详情浮窗，§16.1）
    protected: bool = False  # §16.5 保护检查（逻各斯/艾丽妮）
    read_failed: bool = False  # 状态矩阵 OCR 失败 5 次仍不一致 → 保守训练中

    @property
    def locked(self) -> bool:
        """训练位是否锁定（gate 用）：🔴 训练中 / 🟡 待收取 都算锁定。"""
        return self.state in ("training", "waiting_collect")


# --- 纯函数：技能名/面板解析/像素计数/状态分类 ---


def _parse_panel_text(text):
    """`[干员名]技能名` → (干员名, 技能名)。无方括号视为纯技能名。"""
    if not text:
        return "", ""
    t = str(text).strip()
    if t.startswith("[") and "]" in t:
        name, _, rest = t[1:].partition("]")
        return name.strip(), rest.strip()
    return "", t


def _box_is_lit(img, box, brightness=None, lit_ratio=None, inset=PIP_INSET):
    """单颗专精星判亮：在框内缩进 inset 像素的内核区域统计亮像素占比。

    35x35 的框只装一颗圆（占框约六成），缩进避开圆的抗锯齿边缘和框线；
    亮像素占比 ≥ lit_ratio 计为点亮。
    """
    import numpy as np

    (x0, y0), (x1, y1) = box
    x0, y0 = x0 + inset, y0 + inset
    x1, y1 = x1 - inset, y1 - inset
    if x1 <= x0 or y1 <= y0:
        return False
    seg = img[y0:y1, x0:x1]
    if seg.size == 0:
        return False
    brightness = brightness if brightness is not None else PIP_BRIGHTNESS
    lit_ratio = lit_ratio if lit_ratio is not None else PIP_LIT_RATIO
    if seg.ndim == 3:
        gray = np.mean(seg.astype(np.float32), axis=2)
    else:
        gray = seg.astype(np.float32)
    return float((gray > brightness).mean()) >= lit_ratio


def classify_room_state(scene, countdown_state, identity_present, icon_lit) -> str:
    """纯函数：场景 + 三态倒计时 + 干员/技能存在性 + 图标亮点 → 房间状态（§16.2）。

    - TRAIN_FINISH → 🟡 waiting_collect
    - TRAIN_MAIN：
      - 倒计时为 0（00:00:00）→ 🟡 waiting_collect（完成房间不再被当空房重置重开）
      - 倒计时为空 + 无名无亮点 → ⚪ empty（空闲）
      - 倒计时非 0 + 名存在 + 有亮点 → 🔴 training（训练中）
      - 其余 6 种不一致组合 → "ocr_fail"（读取器原地重试 5 次，仍不一致保守训练中）
    - 其他房内场景保守视为占用（🔴）。
    """
    if scene == Scene.TRAIN_FINISH:
        return "waiting_collect"
    if scene == Scene.TRAIN_MAIN:
        if countdown_state == "zero":
            return "waiting_collect"
        if countdown_state == "active":
            if identity_present and icon_lit:
                return "training"
            return "ocr_fail"
        # countdown_state == "failed"（倒计时为空）
        if not identity_present and not icon_lit:
            return "empty"
        return "ocr_fail"
    return "training"


# --- 读取原语 ---


def _read_train_countdown3(solver):
    """三态倒计时读取（§16.8）：返回 (state, end_time)。

    - state="active"：读到非 0 秒，end_time=结束时刻；
    - state="zero"：读到 00:00:00，end_time=None；
    - state="failed"：读失败（OCR 无结果），end_time=None。
    不再把读失败和 00:00:00 都压成 now（旧 double_read_time 三态缺失）。
    """
    try:
        seconds = solver.read_time(COUNTDOWN_REGION, None)
    except Exception as e:
        logger.debug(f"倒计时读取异常: {e}")
        return "failed", None
    if seconds is None:
        return "failed", None
    if seconds <= 0:
        return "zero", None
    return "active", datetime.now() + timedelta(seconds=seconds)


def _read_train_countdown(solver) -> Optional[datetime]:
    """兼容旧契约（start 流程/占用判定用）：仅返回「有值」的结束时刻；为0/读失败 → None。"""
    state, end = _read_train_countdown3(solver)
    return end if state == "active" else None


def _count_lit_mastery_icons(solver, img=None) -> int:
    if img is None:
        img = getattr(getattr(solver, "recog", None), "img", None)
    if img is None:
        return 0
    return sum(1 for box in MASTERY_ICON_PIPS if _box_is_lit(img, box))


def _read_slot_mastery_tier(solver, skill_index):
    """读技能选择页目标技能槽的专精档位（亮灯计数），用于已到target检测。

    按 SKILL_SLOT_PIPS[skill_index] 的三颗星（专一顶/专二右下/专三左下）逐框
    判亮计数 → 0-3。读失败（无此技能/无截图/异常）→ 返回 None，#70 起调用方
    保守处理：保持 idle 重排退出，绝不盲点技能行（可能重训已到 target 的档位）。
    """
    boxes = SKILL_SLOT_PIPS.get(skill_index)
    if boxes is None:
        return None
    try:
        img = getattr(getattr(solver, "recog", None), "img", None)
        if img is None:
            return None
        return sum(1 for box in boxes if _box_is_lit(img, box))
    except Exception:
        # 读不到（非数组/越界等）→ 返回 None，调用方保守处理（保持 idle 重排）
        return None


def _read_panel_text(solver, img=None) -> RoomPanel:
    """读主面板 `[干员名]技能名` 文本；OCR 不可读 → 空面板（operator_name=""）。

    只读文本、不读图标/倒计时，供确认开始等轻量归属校验用（避免依赖像素读取）。
    """
    if img is None:
        try:
            solver.recog.update()
            img = solver.recog.img
        except Exception as e:
            logger.debug(f"面板截图失败: {e}")
            return RoomPanel()
    try:
        text = solver.read_screen(img, type="text", cord=PANEL_REGION)
    except Exception as e:
        logger.debug(f"面板 OCR 失败: {e}")
        return RoomPanel()
    operator_name, skill_name = _parse_panel_text(text)
    return RoomPanel(operator_name=operator_name, skill_name=skill_name)


def read_main_panel(solver, img=None) -> RoomPanel:
    """读主页面面板：干员名/技能名/专精图标档位/三态倒计时。"""
    if img is None:
        solver.recog.update()
        img = solver.recog.img
    panel = _read_panel_text(solver, img)
    panel.mastery_tier = _count_lit_mastery_icons(solver, img)
    state, countdown = _read_train_countdown3(solver)
    panel.countdown_state = state
    panel.countdown = countdown
    return panel


def _close_room_detail(solver, max_retries=3):
    """关进驻详情浮窗回训练室主界面：点浮窗关闭按钮（arrange_check_in_on）。

    205 是基建放大视角，back() 会退到基建主界面而非训练室主界面（graph.py:
    INFRA_DETAILS→INFRA_MAIN），专精流程一律用点关闭按钮的方式关浮窗。
    浮窗开着时画面出现 arrange_check_in_on（浮窗上的关闭按钮），点它关浮窗。
    """
    for _ in range(max_retries):
        pos = solver.find("arrange_check_in_on")
        if pos:
            solver.tap(pos, interval=0.5)
            return True
        solver.sleep(0.5)
    return False


def _settle_in_room(solver, max_iters=15) -> int:
    """把场景稳定到房内可判定状态（TRAIN_MAIN / TRAIN_FINISH / 其他房内场景）。

    瞬态场景（未连接/未知/基建首页/详情浮层）循环收敛；稳定房内场景立即返回。
    """
    transient = (
        Scene.INFRA_MAIN,
        Scene.INFRA_DETAILS,
        Scene.CONNECTING,
        Scene.UNKNOWN,
    )
    for _ in range(max_iters):
        scene = solver.train_scene()
        if scene not in transient:
            return scene
        if scene == Scene.INFRA_MAIN:
            solver.enter_room("train")
        elif scene == Scene.INFRA_DETAILS:
            _close_room_detail(solver)
        else:
            solver.sleep()
    return solver.train_scene()


def _read_slots(solver, want_mood=False):
    """读进驻详情浮窗：返回 (协助位, 训练位)。读后关浮窗回训练室主界面。

    want_mood=True 时返回 ((协助位, 训练位), mood_data)，mood_data 为浮窗槽位扫描
    （get_agent_from_room 返回值，含 mood，对齐 agent_get_mood 的 mood_info 数据源）。
    槽位约定：scan[0]=上排=协助位，scan[1]=下排=训练位（与 choose_train 一致）。
    读失败/无两人 → ("", "")；want_mood 时 mood_data 为空列表。
    """
    try:
        scan = solver.get_agent_from_room("train")
    except Exception as e:
        logger.debug(f"进驻详情读取失败: {e}")
        scan = []
    try:
        if solver.train_scene() == Scene.INFRA_DETAILS:
            _close_room_detail(solver)
    except Exception:
        pass
    if len(scan) < 2:
        slots = "", ""
    else:
        slots = scan[0].get("agent", ""), scan[1].get("agent", "")
    if want_mood:
        return slots, scan
    return slots


def _train_slot_has_mastery(solver) -> bool:
    """§16.4 空闲保护深读：进技能选择页读训练位干员所有技能。

    有专一/专二 → True（保护，不能动）；全专三或专0 → False（可动）；
    进不去技能页 / 读不到档位 → 保守 True（保护）。
    """
    try:
        scene = solver.train_scene()
        if scene == Scene.TRAIN_MAIN:
            solver.tap((solver.recog.w * 0.05, solver.recog.h * 0.95), interval=0.5)
        elif scene != Scene.TRAIN_SKILL_SELECT:
            return True
        if solver.train_scene() != Scene.TRAIN_SKILL_SELECT:
            return True
        has = False
        for idx in (0, 1, 2):
            tier = _read_slot_mastery_tier(solver, idx)
            if tier is None:
                return True  # 读不到 → 保守保护
            if tier in (1, 2):
                has = True
        try:
            solver.back()
        except Exception:
            pass
        return has
    except Exception:
        return True


def _compute_protected(solver, room) -> bool:
    """§16.5 保护检查（现读现判）：协助位为逻各斯/艾丽妮时房间受保护。

    - 待收取：仅非专三（链未走完）保护；专三完成 → §16.3 第1格「无论如何不保护 → 可排班」；
    - 空闲 + 训练位有人 → 深读技能页，有专一/专二 → 保护；全专三/专0 → 可动；
    - 空闲 + 训练位没人 → 可排班。
    每次排班进训练室重读重判，条件一变自动解除；enable_mastery OFF 时保护全停（§16.11）。
    """
    if not config.conf.enable_mastery:
        return False
    if room.support_slot not in PROTECT_OPERATORS:
        return False
    if room.state == "waiting_collect":
        return room.panel.mastery_tier != 3
    if room.state == "empty":
        if not room.train_slot:
            return False
        return _train_slot_has_mastery(solver)
    return False


def _classify_panel(solver, panel) -> str:
    """主面板 → 状态矩阵分类（含 training_completed 模板兜底）。"""
    state = classify_room_state(
        Scene.TRAIN_MAIN,
        panel.countdown_state,
        bool(panel.operator_name and panel.skill_name),
        panel.mastery_tier > 0,
    )
    if state == "empty" and solver.find("training_completed"):
        # "刚完成"的 TRAIN_MAIN（训练完成横幅）→ 🟡 待收取
        state = "waiting_collect"
    return state


def _fill_slots_and_protection(solver, room, want_mood=False):
    # enable_mastery OFF：槽位/保护无人消费（reconcile 被 gate、_compute_protected 恒 False），
    # 不白开进驻浮窗（§16.11 防卡检查只看 locked，面板态即可）。
    if config.conf.enable_mastery:
        if want_mood:
            (room.support_slot, room.train_slot), mood = _read_slots(
                solver, want_mood=True
            )
        else:
            room.support_slot, room.train_slot = _read_slots(solver)
            mood = None
    else:
        mood = None
    room.protected = _compute_protected(solver, room)
    return mood


def _retry_ocr(solver) -> RoomState:
    """§16.2：OCR/亮点计算失败 → 原地重试 5 次（重读截图，不点动画）。

    仍不一致 → 保守训练中（不动、重排到 now+2min、记日志）。
    """
    first = None
    for i in range(5):
        panel = _safe_read_panel(solver)
        if first is None:
            first = panel
        state = _classify_panel(solver, panel)
        if state != "ocr_fail":
            room = RoomState(state, panel)
            if state in ("waiting_collect", "empty"):
                _fill_slots_and_protection(solver, room)
            return room
        logger.warning(f"[mastery] 训练室状态不一致（第{i + 1}次），重读截图")
    logger.warning("[mastery] 训练室状态 5 次读取仍不一致，保守按训练中处理")
    return RoomState("training", first or RoomPanel(), read_failed=True)


def read_room_state(solver, enter=True, want_mood=False):
    """进房读全部状态。enter=False 表示已在房内（排班 gate 用）。

    §16.1 读全：进驻详情浮窗（协助位/训练位）+ 左下角（干员/技能/倒计时/图标）；
    按 §16.2 状态矩阵判定；OCR 失败组合原地重试 5 次，仍不一致保守训练中。
    房间停留在 TRAIN_MAIN / TRAIN_FINISH；返回 RoomState（截图权威）。

    want_mood=True 时浮窗读槽位顺带收集心情，返回 (RoomState, mood_data)——mood_data
    为进驻浮窗槽位扫描（get_agent_from_room 返回值，含 mood，供 agent_get_mood 格式化
    mood_info）；心情取不到的状态返回空列表 []（TRAIN_FINISH 横幅页浮窗不可靠 /
    OCR 失败保守训练中只读面板）。否则返回 RoomState（不破坏现有调用）。
    """
    if enter:
        solver.enter_room("train")
    scene = _settle_in_room(solver)
    if scene == Scene.TRAIN_FINISH:
        # 完成横幅页：只读左下角面板供收取，不读进驻详情/不算保护（该页 get_agent_from_room
        # 不可靠）。保护判定等收取完成回 TRAIN_MAIN 后再读（§16.1 读全以主页面为主）。
        room = RoomState("waiting_collect", _safe_read_panel(solver))
        return (room, []) if want_mood else room
    if scene == Scene.TRAIN_MAIN:
        panel = read_main_panel(solver)
        state = _classify_panel(solver, panel)
        if state == "ocr_fail":
            room = _retry_ocr(solver)
            # OCR 失败路径（含重试成功后的槽位填，未带心情）→ 心情取不到
            return (room, []) if want_mood else room
        room = RoomState(state, panel)
        if want_mood or state in ("waiting_collect", "empty"):
            mood = _fill_slots_and_protection(solver, room, want_mood=want_mood)
            return (room, mood) if want_mood else room
        return room
    # 其他房内场景（技能选择/确认/未知）→ 保守视为占用，面板尽力读
    room = RoomState("training", _safe_read_panel(solver))
    return (room, []) if want_mood else room


def _safe_read_panel(solver) -> RoomPanel:
    try:
        return read_main_panel(solver)
    except Exception as e:
        logger.debug(f"面板读取失败: {e}")
        return RoomPanel()


# --- 计划匹配（截图权威） ---


def _plan_operator_matches(plan, operator_name: str) -> bool:
    if not operator_name:
        return False
    return operator_name == plan.get("char_name") or operator_name == plan.get(
        "char_id"
    )


def _plan_matches_room(plan, room: RoomState) -> bool:
    """active 计划与截图是否一致：干员名必须匹配；技能名可读时须 ⊂ 计划 skill_name。

    干员名/技能名不可读（OCR 失败）时不判不一致，防误重置（铁律：截图为准，稳为先）。
    """
    if not room.panel.operator_name:
        return True
    if not _plan_operator_matches(plan, room.panel.operator_name):
        return False
    sk = room.panel.skill_name
    if not sk:
        return True
    resolved = resolve_panel_skill(room.panel.operator_name, sk)
    if resolved is not None:
        return resolved == plan.get("skill_index")
    return panel_skill_matches(sk, plan.get("skill_name"))


def _match_plan(plans, room: RoomState):
    """截图 (干员,技能) → 非终态计划命中；未命中返回 None。"""
    op = room.panel.operator_name
    if not op:
        return None
    sk = room.panel.skill_name
    for p in plans:
        if p["status"] in ("completed", "failed"):
            continue
        if not _plan_operator_matches(p, op):
            continue
        if sk:
            resolved = resolve_panel_skill(op, sk)
            if resolved is not None:
                if resolved != p.get("skill_index"):
                    continue
            elif not panel_skill_matches(sk, p.get("skill_name")):
                continue
        return p
    return None


def _can_adopt_expiry(plan, room: RoomState) -> bool:
    """B8：倒计时采纳门——面板**干员名与技能名都可读且匹配**才采纳倒计时。

    复用 `_plan_matches_room`（干员匹配 + 技能匹配）再叠加「两者都可读」：
    与 reset/通知守卫的「不可读=匹配」（C-36）语义相反——任一名不可读 → 不采纳
    （幻影/外人倒计时不得「祝福」计划，也不能认不可读的技能）。
    """
    return (
        bool(room.panel.operator_name)
        and bool(room.panel.skill_name)
        and _plan_matches_room(plan, room)
    )


def _plan_label(plan) -> str:
    name = plan.get("char_name") or plan.get("char_id")
    return f"{name} {plan.get('skill_name') or format_skill_label(plan.get('skill_index', 0))}"


# --- 调度原语 ---


def _find_plan_task(solver, plan_key):
    """队列中该 plan_key 的一条 SKILL_UPGRADE 任务（排除当前 dispatch），无则 None。

    `_upsert_skill_upgrade_task` 用它找改期目标（按 plan_key 去重，每计划恒 ≤1 条）。
    防御：solver.tasks 可能不可迭代（测试 MagicMock）或读失败 → 按无任务处理（调用方
    走兜底/新建，不崩）。
    """
    current = getattr(solver, "task", None)
    try:
        tasks = solver.tasks
        return next(
            (
                t
                for t in tasks
                if t.type == TaskTypes.SKILL_UPGRADE
                and t is not current
                and getattr(t, "plan_key", None) == plan_key
            ),
            None,
        )
    except (AttributeError, TypeError):
        return None


def _find_swap_task(solver, plan_key):
    """队列中该计划的一条 SWAP_SUPPORT 任务（排除当前 dispatch），无则 None。

    #77 补排去重用：SWAP 任务带 plan_key=计划ID（与 SKILL_UPGRADE 同形），避免
    reconcile 每轮进房重复补排。防御：solver.tasks 可能不可迭代 → 按无任务处理。
    """
    current = getattr(solver, "task", None)
    try:
        tasks = solver.tasks
        return next(
            (
                t
                for t in tasks
                if t.type == TaskTypes.SWAP_SUPPORT
                and t is not current
                and getattr(t, "plan_key", None) == plan_key
            ),
            None,
        )
    except (AttributeError, TypeError):
        return None


def _upsert_skill_upgrade_task(solver, target_time, meta_data="", plan_key=None):
    """入队/改期一条 SKILL_UPGRADE 任务，队列恒 ≤1 条同形任务（#62 Q3 收敛）。

    - plan_key=None：占用重检（meta_data 留空，任务列表仅显示类型名）；
    - plan_key=计划ID：某计划的到点收取任务 或 仓库扫描驱动的「开始训练」任务
      （meta_data 均为描述性标签，无逻辑标记；去重按 plan_key，房间状态决定开始/收集）。
      keepalive 已删（#74 第3段），不再有「DB 有计划就自动入队 now-task」。
    """
    task = _find_plan_task(solver, plan_key)
    if task is None:
        task = SchedulerTask(
            time=target_time, task_type=TaskTypes.SKILL_UPGRADE, meta_data=meta_data
        )
        task.plan_key = plan_key
        solver.tasks.append(task)
    else:
        task.time = target_time
        if meta_data:
            task.meta_data = meta_data


def _target_label(level: int) -> str:
    """专精等级中文标签：0→未专精、1→专一、2→专二、3→专三。"""
    return ("未专精", "专一", "专二", "专三")[level]


def _schedule_collect(solver, plan, execute_time, tier=None):
    """安排某计划到点收取任务；同计划已有一条时原地改时间（#62 Q3 收敛：统一入队原语）。

    去重按 plan_key=计划ID；meta_data 存描述性标签，如
    `焰狐龙梓兰 二技能·飞翔瞪射 专一 → 专二`（当前 → 目标）。
    图标亮灯数即目标等级（亮 2 颗 = 专一→专二），可读时作目标来源，
    否则回退计划 target_level；当前档位 = 目标 - 1。
    """
    target = tier if isinstance(tier, int) and tier >= 1 else plan["target_level"]
    current = max(0, target - 1)
    label = f"{_plan_label(plan)} {_target_label(current)} → {_target_label(target)}"
    _upsert_skill_upgrade_task(
        solver, execute_time, meta_data=label, plan_key=str(plan["id"])
    )


def _schedule_scan_start(solver, plan, step_level=None):
    """#74 第3段：仓库扫描确认材料后，为材料足够的 idle 计划入队「开始训练」任务。

    时间=now（扫描完尽快开练）；plan_key=计划ID 定位 + 复用 TASK-01 按 plan_key 去重
    （每计划恒 ≤1 条 SKILL_UPGRADE，重复扫描原地刷新不新增）。开始/收取/重检任务
    同形（均 plan_key 定位，房间状态决定行为：空闲→开始、待收取→收集），故无专门
    标记。计划开始训练后该任务按 plan_key 原位升级为收取任务（_schedule_collect 去重命中）。

    step_level：扫描算出的本次安排步级（current_level+1，森空岛数据），存在任务上，
    供 dispatch 传给安排流程——失败邮件要报「这次要练的专几」，不依赖现场图标。
    """
    _upsert_skill_upgrade_task(
        solver,
        datetime.now(),
        meta_data=f"{_plan_label(plan)} 开始训练",
        plan_key=str(plan["id"]),
    )
    task = _find_plan_task(solver, str(plan["id"]))
    if task is not None:
        task.step_level = step_level


# --- 矩阵动作 ---


def _queue_has_mastery_task(solver):
    """队列是否已有任一 SKILL_UPGRADE 任务（排除当前 dispatch）。

    #75 方案 C：gate 用——待收取格只要队列有专精任务就跳过本次收集、留给队列任务收。
    不区分任务属于哪个计划（任何 SKILL_UPGRADE dispatch 进房都会收待收取格，
    _reconcile_waiting_collect 的 hit/帮收分支均收集，与任务自身 plan_key 无关），
    plan_key=None 的占用重检同理。队列空 → 照常收集（恢复兜底）。
    防御：solver.tasks 可能不可迭代（测试 MagicMock）→ 按无任务处理。
    """
    current = getattr(solver, "task", None)
    try:
        return any(
            t.type == TaskTypes.SKILL_UPGRADE and t is not current for t in solver.tasks
        )
    except (AttributeError, TypeError):
        return False


def _log_judgment(solver, room, state, action, **extra):
    """逐轮结构化判定日志：读到什么 → 判定什么 → 动作什么（§16「日志」）。

    读 = 三态倒计时 / 干员 / 技能 / 档位 / 协助位 / 训练位；判 = 状态矩阵结果；
    动作 = 本轮的执行动作。便于定位错误来源（读到异常 → 判错 → 做错）。
    """
    c = room.panel.countdown
    countdown_str = c.strftime("%H:%M:%S") if c else room.panel.countdown_state
    read = (
        f"倒计时={countdown_str} 干员={room.panel.operator_name or '空'} "
        f"技能={room.panel.skill_name or '空'} 档位={room.panel.mastery_tier} "
        f"协助位={room.support_slot or '空'} 训练位={room.train_slot or '空'}"
    )
    tail = " ".join(f"{k}={v}" for k, v in extra.items())
    logger.info(f"[mastery] 判定 读[{read}] → 判[{state}] → 动作[{action}] {tail}")


def _reset_to_idle(solver, plan):
    """重置计划为 idle。退出训练室由调用方统一处理（dispatch 或排班 gate）。"""
    from arknights_mower.utils.mastery_db import update_plan_status

    logger.warning(f"Plan {plan['id']} 异常状态，重置为 idle")
    update_plan_status(plan["id"], "idle")


def _reset_fake(solver, plan, room):
    """假记录：DB active 与截图不一致 → 重置该计划 idle + 通知②。"""
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify, update_plan_status

    update_plan_status(plan["id"], "idle")
    if should_notify("fake_reset", str(plan["id"])):
        msg = (
            f"专精计划 {_plan_label(plan)} 与训练室实际状态不符，"
            f"已重置为待执行（截图：{room.panel.operator_name or '空房'}）"
        )
        send_message(msg, level="WARNING")


def _update_expiry(solver, plan, room):
    """training×🔴 一致：重读倒计时、更新 expires_at（同值跳过 DB 写）。

    B8：本函数不校验采纳条件——两个调用点（active/hit）都先过 `_can_adopt_expiry`
    （面板干员名+技能名可读且匹配）。任一采纳漏掉该门，不可读的外人倒计时会持续
    「祝福」计划、或把 waiting_collect 无校验降回 training。
    #82：拆出「排收取」——只写 expires_at（同值不重写，进房不再无谓写 DB），
    收取由调用方在换人判定后决定（排了换人则不排收取，§16.10 半重叠消除）。
    """
    from arknights_mower.utils.mastery_db import update_plan_status

    countdown = room.panel.countdown
    if countdown is None:
        return
    expires_at = countdown.strftime("%Y-%m-%d %H:%M:%S")
    if plan.get("expires_at") != expires_at:
        update_plan_status(plan["id"], "training", expires_at=expires_at)


def _refresh_training_plan(solver, plan, room):
    """training×一致（采纳门通过）：B8 采纳倒计时 + #82 半重叠消除。

    先写 expires_at（同值跳过 DB 写），再跑换人判定（_maybe_recover_swap：重启补排 /
    #80 陌生人纠错）；排了换人（或队列已有换人任务）就不排收取，没排换人才排收取——
    消除「收取+换人两任务同队列」的中间态（§16.10，排了换人等 SWAP 完成后重读再排收取）。
    """
    _update_expiry(solver, plan, room)
    if not _maybe_recover_swap(solver, plan, room):
        countdown = room.panel.countdown
        if countdown is not None:
            _schedule_collect(solver, plan, countdown, tier=room.panel.mastery_tier)


def _maybe_recover_swap(solver, plan, room) -> bool:
    """#77：重启恢复 training×一致 时补排丢失的 SWAP_SUPPORT；#80：陌生人协助位纠错。

    只补排任务（短动作，不碰房间、不退出）；实际读协助位/纠错/换人由 SWAP dispatch
    的 #79 `run_swap_support` 完成——补排直接复用 `_schedule_swap_if_needed`，
    换人公式/路线判定口径与正常排程完全一致，不重复实现。
    门控（照搬 run_swap_support / _schedule_swap_if_needed）：
    - enable_mastery 开、非跟随排班（协助位归排班系统管）；
    - swap_frozen=1（换人已完成）→ 跳过；
    - 队列已有同计划 SWAP 任务 → 跳过（去重，重启恢复的队列可能还留着旧任务）；
    - 倒计时可读且 `calc_swap_threshold` 判剩余够（<5h 不补排）→ 补排 SWAP 任务。
    #80：判陌生人时**自己读协助位**（作为读房的一部分，铁律 3 一次进房做完全部；
    不依赖排班读心情的数据——数据未留存、时间点不可控）——协助位 ∉ {operator,
    swap_target}（陌生人/坐错）且队列无换人任务 → 排一个纠错任务（派发走
    run_swap_support：先纠成路线 operator，重读倒计时判值不值得再换 swap_target）。
    专三/时间不足的步也纠（swap_target=None / <5h 只是不换减半对象，协助位仍要纠成
    路线人）。已减半（协助位 == swap_target）→ 不再排换人，只排收取。
    返回 True = 已排换人任务（或队列已有）→ 调用方不排收取。
    """
    from arknights_mower.utils import config

    if not config.conf.enable_mastery:
        return False
    if config.conf.assistant_follows_schedule:
        return False
    if plan.get("swap_frozen"):
        return False
    if _find_swap_task(solver, str(plan["id"])) is not None:
        return True  # 已有换人任务在队列 → 调用方不排收取（该任务完成时会排收取）
    countdown = room.panel.countdown
    if countdown is None:
        return False
    # 当前步目标级 = 主面板专精图标（亮 N 颗=专N，#76），读不到回退 target_level
    step_level = room.panel.mastery_tier or None
    from arknights_mower.solvers.mastery import (
        _get_plan_route,
        _schedule_swap_if_needed,
    )

    route = _get_plan_route(plan, step_level)
    if route and route.get("operator"):
        operator = route["operator"]
        swap_target = route.get("swap_target")
        support_slot, _ = _read_slots(solver)
        if support_slot and support_slot not in (operator, swap_target):
            # 陌生人/坐错 → 排纠错任务（纠成 operator；减半与否由 dispatch 时再判）
            _schedule_correction_swap(solver, plan, operator)
            return True
        if support_slot == swap_target:
            # 已减半（协助位已是 swap_target）→ 不再排换人，调用方排收取
            return False

    if _schedule_swap_if_needed(solver, plan, countdown, step_level) is not None:
        logger.info(f"[mastery] #77 重启恢复：补排换人任务 id={plan['id']}")
        return True
    return False


def _schedule_correction_swap(solver, plan, operator):
    """#80：陌生人协助位纠错——排一条立即执行的 SWAP_SUPPORT 纠错任务。

    派发走 run_swap_support：先纠成路线 operator → 重读倒计时 → calc_swap_threshold
    判值不值得 → 值得才换 swap_target，不值只排收取。任务带 plan_key 去重键
    （与 SWAP 任务同形），reconcile 不重复补排。
    """
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    task = SchedulerTask(
        time=datetime.now(),
        task_type=TaskTypes.SWAP_SUPPORT,
        meta_data=f"{_plan_label(plan)} 协助位纠错为 {operator}",
    )
    task.plan_key = str(plan["id"])
    solver.tasks.append(task)
    logger.info(
        f"[mastery] #80 陌生人协助位纠错：排换人任务 id={plan['id']} 期望={operator}"
    )


def _wait_for_training(solver, room):
    """idle×🔴 命中：保持 idle，静默等它练完（重排到倒计时+2min），级联靠后续收取。"""
    countdown = room.panel.countdown
    if countdown is None:
        return
    logger.info(
        f"训练室使用中，计划保持待执行，任务重排到 {countdown + ARRANGING_RETRY_BUFFER}"
    )
    _upsert_skill_upgrade_task(solver, countdown + ARRANGING_RETRY_BUFFER)


def _notify_blocked(solver, room):
    """① 队列被计划外训练阻塞至X + mower会帮忙收取（各一次）。"""
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    countdown = room.panel.countdown
    if countdown is None:
        key = "unknown"
        tail = ""
    else:
        key = countdown.strftime("%Y-%m-%d %H:%M:%S")
        tail = f"至 {key}"
    if should_notify("blocked", key):
        op = room.panel.operator_name or "未知干员"
        msg = (
            f"训练室被计划外训练占用{tail}（{op}），"
            "mower 会在其完成后帮忙收取，期间队列保持待执行"
        )
        send_message(msg, level="WARNING")


def _notify_help_collect(solver, room):
    """④ 帮收：非专三收取 + 干员/技能不在计划 → 通知「mower 帮忙收取」（§16.9）。"""
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    op = room.panel.operator_name or "未知干员"
    key = f"{op}:{room.panel.skill_name or ''}"
    if should_notify("help_collect", key):
        tier = room.panel.mastery_tier
        tier_text = f"专{tier}" if tier else "专精等级未知"
        msg = (
            f"训练室 {op}（{room.panel.skill_name or '技能未知'}）{tier_text} 训练完成，"
            "不在专精计划中，mower 已帮忙收取"
        )
        send_message(msg, level="INFO")


def _notify_protected(solver, room):
    """⑤ 训练室受保护（逻各斯/艾丽妮）、mower 无法开始训练（§16.9）。"""
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    key = f"{room.support_slot}:{room.train_slot}"
    if should_notify("protected", key):
        msg = (
            f"训练室受保护（协助位 {room.support_slot or '未知'}），"
            "mower 无法开始新的专精训练，计划保持待执行"
        )
        send_message(msg, level="WARNING")


def _notify_at_target(solver, plan, tier):
    """⑥ 已到target：开始训练时发现技能已到目标档位 → 邮件 + DB 标完成（§16.9）。"""
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    if should_notify("at_target", str(plan["id"])):
        msg = f"{_plan_label(plan)} 已到目标档位（专{tier}），无需训练，已标记完成"
        send_message(msg, level="INFO")


def _promote_plan(solver, plan):
    """§16.6 恢复流程：计划「插队」到 idle 队列最前。

    先看是否已最前；不是则把最前基准让给本计划、原最前计划们后移一位
    （其他计划优先级按需变动），避免无限负漂移。
    """
    from arknights_mower.utils.mastery_db import get_all_plans, update_plan_priority

    idle = [p for p in get_all_plans() if p["status"] == "idle"]
    if not idle:
        return
    min_p = min(p["priority"] for p in idle)
    if plan["priority"] <= min_p:
        logger.info(f"[mastery] {_plan_label(plan)} 已在 idle 队列最前，无需排前")
        return
    update_plan_priority(plan["id"], min_p)
    for p in idle:
        if p["id"] != plan["id"] and p["priority"] == min_p:
            update_plan_priority(p["id"], p["priority"] + 1)
    logger.info(
        f"[mastery] {_plan_label(plan)} 恢复流程：插队到 idle 队列最前（优先级 {min_p}）"
    )


# --- 收取流程（#61 定死） ---


def _tap_finish_mark(solver):
    """点左下角完成标记进收取页：优先模板定位，兜底旧坐标。

    旧坐标 (0.05w,0.95h) 实机疑似打不中（#63 待实现细节），模板命中时优先。
    """
    for tpl in ("skill_collect_confirm", "training_completed"):
        pos = solver.find(tpl)
        if pos:
            solver.tap(pos, interval=0.5)
            return
    solver.tap((solver.recog.w * 0.05, solver.recog.h * 0.95), interval=0.5)


def _tap_collect_confirm(solver):
    """收取后点勾确认收尾：优先 confirm_train 模板。位置实机校准待办。"""
    pos = solver.find("confirm_train")
    if pos:
        solver.tap(pos, interval=0.5)
    else:
        solver.tap((solver.recog.w * 0.5, solver.recog.h * 0.85), interval=0.5)
    for _ in range(6):
        scene = solver.train_scene()
        if scene in (Scene.TRAIN_MAIN, Scene.INFRA_MAIN):
            return
        solver.sleep(1)


def collect_flow(solver, plan, panel: RoomPanel):
    """#61 定死收取流程。plan 可为 None（未命中纯收取）。返回收集页截图。

    1. 主页面已读（panel，全部信息源）
    2. 点左下角完成标记 → 进收取页（动画）
    3. sleep ~2s
    4. 点任意处 → 跳过动画 → 稳定页
    5. 截图（收集页不读文本）
    6. 档位==专3 → 邮件（截图 + 第1步信息）
    7. 对账（用第1步档位）：档位==target completed级联 / ≠target 继续（#67，见 _reconcile_after_collect）
    8. 点勾确认
    """
    from arknights_mower.utils.email import send_message
    from arknights_mower.utils.mastery_db import should_notify

    _tap_finish_mark(solver)
    solver.sleep(2)
    solver.tap((solver.recog.w * 0.5, solver.recog.h * 0.5), interval=1)
    solver.recog.update()
    screenshot = solver.recog.img

    tier = panel.mastery_tier
    if tier == 3 and plan is not None:
        if should_notify("m3_collect", str(plan["id"])):
            body = (
                f"{_plan_label(plan)} 专精三级完成收取\n"
                f"干员：{panel.operator_name}｜技能：{panel.skill_name}｜档位：专{tier}"
            )
            send_message(body, level="INFO", attach_image=screenshot)
    # 8. 点勾确认收尾
    _tap_collect_confirm(solver)
    return screenshot


def _reconcile_after_collect(solver, plan, panel: RoomPanel):
    """收集后对账：档位==target completed（不级联，等扫描）/ ≠target 继续本级。

    #67/B6：档位**高于**计划目标时，本次收取不属于该计划（计划早已满足），
    不按"专{target} 完成"记账，保持 idle——由已到target检测按真实档位正确完成，
    防止"专二收取关掉专一计划"的错记。返回需要开始的计划或 None：继续本级返回
    本级（当场开与否由调用方按「扫描链记号」判定，#74 第3段 Q2）；收取完成返回
    None 等扫描，不再级联开始下一个计划。
    """
    from arknights_mower.utils.mastery_db import update_plan_status

    if plan is None:
        return None
    tier = panel.mastery_tier
    if tier == plan["target_level"]:
        logger.info(
            f"{_plan_label(plan)} 专{plan['target_level']} 完成（收集档位 专{tier}）"
        )
        update_plan_status(plan["id"], "completed")
        return None
    if tier > plan["target_level"]:
        logger.warning(
            f"{_plan_label(plan)} 收集档位 专{tier} 高于目标专{plan['target_level']}，"
            "不将本次收取记为该计划完成"
        )
    else:
        logger.info(
            f"{_plan_label(plan)} 收集档位 专{tier} < 目标专{plan['target_level']}，继续下一级"
        )
    update_plan_status(plan["id"], "idle")
    return plan


def _collect_plan(solver, plan, room: RoomState):
    """命中计划：收集 + 对账。返回继续本级需要开始的计划或 None（收取完成不级联）。"""
    collect_flow(solver, plan, room.panel)
    return _reconcile_after_collect(solver, plan, room.panel)


def _collect_silent(solver, room: RoomState):
    """未命中计划纯收取：非专三且面板可读 → 通知④帮收（§16.3）；专三/面板不可读 → 静默。

    面板不可读（OCR 失败，干员名空）时不发④——档位可能误读为 0（如 TRAIN_FINISH
    完成页主面板区域不可读），专三完成会被错发「帮收」；稳为先：不可读则静默。
    """
    if room.panel.mastery_tier != 3 and room.panel.operator_name:
        _notify_help_collect(solver, room)
    collect_flow(solver, None, room.panel)


def _next_idle_to_start(solver):
    from arknights_mower.utils.mastery_db import get_next_idle_plan

    return get_next_idle_plan()


# --- 状态矩阵对账（#61 / #73） ---


def reconcile_and_act(solver, scan_plan=None):
    """共享读取器主入口：进房读全部 + 状态矩阵对账执行。

    返回 (start_plan, arrange_support, room)：
    - start_plan：需要开始训练的计划（长动作由 SKILL_UPGRADE dispatch 执行），无则 None；
    - arrange_support：False 表示是「收取→下一次开始」边界（减半守卫：不重排协助位）；
    - room：本次进房读取的 RoomState（截图权威）。dispatch 把它传给 _start_new_training，
      开始流程直接复用已读的槽位/面板，不再重复进房、重复开浮窗（#93）。
    一次进房做完全部动作；无开始计划时保证离开训练室。

    scan_plan：任务 plan_key 指定的开始计划（#74 第3段）——任何带 plan_key 的
    SKILL_UPGRADE 任务（扫描开始/收取/重检）都会解析其指定计划；plan_key=None（占用
    重检）无指定计划。空闲×未保护格只在 scan_plan 非 None（且计划仍 idle）时返回该
    计划开始训练，其他情况交还排班。材料判断在扫描时完成（auto_schedule 的 scheduled
    结果），不违背「删材料门控」。
    """
    from arknights_mower.utils.mastery_db import get_active_plan, get_all_plans

    if not config.conf.enable_mastery:
        return None, True, None
    room = read_room_state(solver)
    active = get_active_plan()
    plans = get_all_plans()
    plan, arrange_support = _reconcile(solver, room, active, plans, scan_plan=scan_plan)
    if plan is None:
        # 各矩阵路径已 back 的不会重复退出；收集后无级联 / 空房无计划时在此退出
        try:
            scene = solver.train_scene()
            if scene in (Scene.TRAIN_MAIN, Scene.TRAIN_FINISH):
                solver.back()
        except Exception:
            pass
    return plan, arrange_support, room


def _reconcile(
    solver, room: RoomState, active, plans, scan_plan=None, defer_collect=False
):
    """#61/#73 状态矩阵。行=DB 状态，列=截图房间状态。

    返回 (start_plan, arrange_support)：start_plan 为需要开始训练的计划或 None；
    arrange_support=False 表示「收取→下一次开始」边界（减半守卫：不重排协助位）。

    §16.2 矩阵：待收取/空闲/训练中；OCR 失败 5 次仍不一致 → 保守训练中。
    scan_plan：任务 plan_key 指定的开始计划（#74 第3段）；None 表示无指定（plan_key=None）。
    defer_collect（#75 方案 C）：排班 gate（reconcile_short）传 True 时待收取格跳过
    「队列已有专精任务」的计划的收集（见 _reconcile_waiting_collect）；dispatch 恒 False。
    """
    from arknights_mower.utils.mastery_db import update_plan_status

    # arranging × 任何列 → 重置 idle
    if active is not None and active["status"] == "arranging":
        _reset_to_idle(solver, active)
        active = None

    # §16.2 OCR 失败 5 次仍不一致 → 保守训练中：不动 + 记日志。
    # 用户 08-15 定案：读不出不排重检——等排班系统下次自然进房重读。
    if room.read_failed:
        _log_judgment(
            solver, room, "ocr_fail", "保守训练中，不排重检（等排班自然重读）"
        )
        return None, True

    if room.state == "empty":
        # ⚪ 空闲：DB active 与截图冲突 → 截图权威重置 idle；受保护 → mower 不能开始。
        if active is not None:
            logger.info(
                f"训练室为空但计划 {active['id']} 显示 {active['status']}，重置 idle 重开"
            )
            update_plan_status(active["id"], "idle")
        if room.protected:
            idle = _next_idle_to_start(solver)
            if idle is not None:
                # §16.5 保护挡住 mower 自己开始训练 → 通知⑤ + 保持 idle。
                # 不主动轮询：保护解除靠「每次排班进训练室重读重判」（§16.5 解除时机）。
                _notify_protected(solver, room)
            return None, True
        # §16.4 空闲×未保护：scan_plan（任务 plan_key 指定的计划，仍 idle）→ 返回该
        # 开始计划。任何带 plan_key 的 SKILL_UPGRADE 任务（扫描开始/收取/重检）在空闲格
        # 都会返回其指定计划开始（#74 第3段，2026-08-14 用户拍板「都去掉」：不再区分
        # 扫描标记；开始/继续一律当场，重启后不再保守等扫描）。
        if scan_plan is not None and scan_plan["status"] == "idle":
            return scan_plan, True
        return None, True

    if room.state == "training":
        return _reconcile_training(solver, room, active, plans)

    return _reconcile_waiting_collect(
        solver, room, active, plans, defer_collect=defer_collect
    )


def _reconcile_training(solver, room, active, plans):
    """§16.4 训练中（倒计时非 0）：
    跟随排班 → 训练位冻结（gate 负责）；未开跟随排班 + 计划匹配 → 静默重读+重排收取
    （保护训练室）；不匹配 → 通知① blocked（不动房间，下次排班再看）。

    B8：采纳倒计时（`_update_expiry`）只在 `_can_adopt_expiry` 通过时发生——面板
    干员名+技能名任一不可读 → 不采纳（不刷新、不改写状态）、不排重检，静默等排班
    系统下次自然进房重读（用户 08-15 定案）。
    """
    hit = _match_plan(plans, room)
    if active is not None:
        if _can_adopt_expiry(active, room):
            _log_judgment(solver, room, "training", "训练中×一致，静默更新到期时间")
            _refresh_training_plan(solver, active, room)
            return None, True
        if not _plan_matches_room(active, room):
            # 干员/技能可读但不匹配 → 假记录 → 重置 + 通知②
            _reset_fake(solver, active, room)
        else:
            # B8：面板名/技能名不可读 → 不采纳、不重置、不重检——让排班下次自然进房重读
            logger.debug("训练室占用但面板不可读，不采纳倒计时，静默等待")
            return None, True

    if hit is not None:
        if hit["status"] == "idle":
            if room.panel.skill_name:
                # idle×🔴 命中：静默等它练完（级联靠后续收取），不打断
                _wait_for_training(solver, room)
            else:
                # B8：命中但技能不可读 → 不排重检，静默等排班下次自然进房重读
                logger.debug("命中计划但面板技能不可读，不排重检，静默等待")
            return None, True
        if _can_adopt_expiry(hit, room):
            # hit 为另一条 active 状态计划（active 重置后），面板可读且匹配 → 采纳
            _refresh_training_plan(solver, hit, room)
            return None, True
        # hit 技能名不可读 → 不采纳（不判计划外、不重检），静默等待
        logger.debug("命中计划但面板技能不可读，不采纳倒计时，静默等待")
        return None, True

    if room.panel.operator_name:
        # 计划外训练 → 通知① + #66/B1 未来重检（倒计时结束 + 缓冲），否则 dispatch
        # 删除当前任务后队列空，计划外训练要等到下次排班进房才被注意到。
        # _upsert_skill_upgrade_task 按 plan_key 去重，多轮不新增。
        _notify_blocked(solver, room)
        countdown = room.panel.countdown
        if countdown is not None:
            _wait_for_training(solver, room)
        else:
            _upsert_skill_upgrade_task(solver, datetime.now() + ARRANGING_RETRY_BUFFER)
    else:
        # 干员名不可读（B8）：不判计划外、不排重检，静默等排班下次自然进房重读
        logger.debug("训练室占用但面板干员名不可读，不排重检，静默等待")
    return None, True


def _reconcile_waiting_collect(solver, room, active, plans, defer_collect=False):
    """§16.3 待收取（00:00:00）7 格动作：图标（专三/非专三）× 协助位（逻各斯/艾丽妮）× 计划。

    返回 (start_plan, arrange_support)。「可排班/不可排班」由 gate 读 room.protected 决定；
    §16.4 空闲保护（训练位有人+有专一/专二）由 read_room_state 预先算好 protected。

    defer_collect（#75 方案 C）：排班 gate（reconcile_short）传 True——命中计划且队列
    已有任一 SKILL_UPGRADE 任务时跳过本次收集，留给队列任务收（任何 dispatch 进房都
    会收待收取格，收完被消费 → 无残留任务）；队列空（如缓存清零重启丢了）→ 照常收集
    （恢复兜底）。专三同样纳入 skip（2026-08-14 用户撤回例外：gate 不抢收，由任务收完
    训练室再回归排班）。dispatch（reconcile_and_act）defer 恒 False 永不跳过。
    """
    hit = _match_plan(plans, room)  # 干员+技能都在计划
    tier = room.panel.mastery_tier
    # 日志用真实保护状态（_compute_protected 已按档位/状态算好）：专三待收取即使协助位
    # 是逻各斯/艾丽妮也不保护（§16.3 第1格），只看协助位会误报保护=True。
    protective = room.protected

    # 截图权威：DB active 与待收取房内干员不一致 → 假记录重置
    if active is not None and not _plan_matches_room(active, room):
        _reset_fake(solver, active, room)
        active = None
    if hit is None and active is not None and _plan_matches_room(active, room):
        # 干员名/技能名 OCR 不可读时 _match_plan 判不了命中，但 active 计划视为
        # 匹配（稳为先，铁律），照常对账收取——否则 active 计划会永远停在 training
        hit = active

    if defer_collect and hit is not None and _queue_has_mastery_task(solver):
        _log_judgment(
            solver,
            room,
            "waiting_collect",
            "队列已有专精任务，跳过本次收集（留给任务收）",
            计划=hit["id"],
            协助位=room.support_slot,
            保护=protective,
        )
        return None, True

    if tier == 3:
        # 专三：正常收取 → 邮件③（截图）→ 无论如何不保护 → 可排班
        _log_judgment(
            solver,
            room,
            "waiting_collect",
            "专三完成，正常收取",
            协助位=room.support_slot,
            保护=protective,
        )
        if hit is not None:
            return _collect_plan(solver, hit, room), False
        _collect_silent(solver, room)
        return None, True

    if hit is not None:
        # 干员+技能都在计划（非专三）：恢复流程（§16.6）——正常收取 → 优先级排前 +
        # 置 idle → 继续本级**当场开下一级**（2026-08-14 用户拍板「都去掉」：不再区分
        # 扫描链/重启，一律当场开；重启后也不保守等扫描）。减半守卫：跨「收取→下一次
        # 开始」边界不动协助位。
        _log_judgment(
            solver,
            room,
            "waiting_collect",
            "都在计划，恢复流程（收取→排前→idle→当场开）",
            协助位=room.support_slot,
            保护=protective,
        )
        plan = _collect_plan(solver, hit, room)
        if plan is not None and plan["id"] == hit["id"]:
            _promote_plan(solver, plan)  # 非专三继续本级 → 排前
            return plan, False
        # 收取完成（档位==target）不级联，等扫描
        return plan, False

    # 干员不在计划 / 干员在技能不在：收取 + 通知④帮收（非专三，无论保护与否）
    _log_judgment(
        solver,
        room,
        "waiting_collect",
        "非专三不在计划，帮收（通知④）",
        协助位=room.support_slot,
        保护=protective,
    )
    _collect_silent(solver, room)
    return None, True


def reconcile_short(solver, room_state: RoomState, defer_collect=False):
    """排班路径顺路短动作（#61）：核实/帮收/重置/对账，不开始训练、不退出房间。

    供 agent_arrange_room 的 gate 在所有房间状态上调用（#74 gate L0 先读再判：
    空闲格也据截图修正 DB）；开始训练（长动作）留给 SKILL_UPGRADE dispatch。
    退出训练室由调用方（gate）统一负责。

    defer_collect（#75 方案 C）：gate 传 True——待收取格跳过「队列已有专精任务」的
    收集，留给队列任务收；dispatch 不经由本函数。
    """
    from arknights_mower.utils.mastery_db import get_active_plan, get_all_plans

    _reconcile(
        solver,
        room_state,
        get_active_plan(),
        get_all_plans(),
        defer_collect=defer_collect,
    )


# --- 排班 gate 复用（#59） ---


def train_slot_locked(solver) -> bool:
    """训练位是否锁定（choose_train D4 用）。

    详情开着时按确定化流程：确认详情渲染完成后关回 TRAIN_MAIN 读倒计时，
    再重开详情，防止动画中误退房（#59）。#73：00:00:00（待收取）也算锁定。
    """
    scene = solver.train_scene()
    if scene == Scene.INFRA_DETAILS:
        _close_room_detail(solver)
        scene = solver.train_scene()
    if scene == Scene.TRAIN_FINISH:
        return True
    if scene == Scene.TRAIN_MAIN:
        state, _ = _read_train_countdown3(solver)
        locked = state in ("active", "zero")
        if not locked and solver.find("training_completed"):
            locked = True
        # 重开详情供调用方继续（仅当原本在详情里）
        solver.turn_on_room_detail("train")
        return locked
    # 其他房内场景保守视为锁定
    return True
