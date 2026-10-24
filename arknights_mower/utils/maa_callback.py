"""Translate MAA callback messages into readable progress lines.

MAA reports every task chain, sub task and recognition result through a single C
callback carrying an ``AsstMsg`` code and a JSON detail payload. The scheduler
hands the device to MAA for the whole run, so these messages are the only
progress signal a MAA run contributes to the runtime log.

``MaaCallbackLog.describe`` maps one callback to the line worth showing, and
``MaaCallbackLog.heartbeat`` supplies the periodic progress line that replaces a
per-poll "still running" message. Callers perform the logging so the records keep
the screenshot archive policy of the module that owns the MAA run.

Wording and severity follow the MAA desktop client's callback handler. The tables
cover the task chains this scheduler submits — StartUp, Fight, Mall, Award,
Recruit, Roguelike, SSSCopilot, Reclamation and SwitchTheme — and carry other
known chains so an unexpected one still reads as a name rather than a code.

One consequence is worth knowing: an ERROR line logged from the scheduler module
also archives surrounding screenshots, so every client-level error carries that
side effect here.
"""

import json
import logging
import time
from typing import NamedTuple

# 心跳间隔：MAA 运行时调度循环每 5 秒轮询一次，逐次播报会淹没日志。
HEARTBEAT_INTERVAL = 60.0
# 超过该时长没有收到任何回调时，心跳额外说明 MAA 已静默。
STALL_AFTER = 180.0
# 单条公招结论最多列出的干员数，避免日志行过长。
RECRUIT_OPER_LIMIT = 8
# 核心要求客户端代发的 HTTP 请求，此处不产出日志行，由上传模块处理。
REPORT_REQUEST = 30000

TASK_CHAIN_TEXT = {
    "StartUp": "开始唤醒",
    "CloseDown": "关闭游戏",
    "Fight": "理智作战",
    "Mall": "信用收支",
    "Recruit": "自动公招",
    "Infrast": "基建换班",
    "Award": "领取奖励",
    "Roguelike": "自动肉鸽",
    "Copilot": "自动战斗",
    "SSSCopilot": "SSS 自动战斗",
    "ParadoxCopilot": "悖论模拟",
    "Depot": "仓库识别",
    "OperBox": "干员识别",
    "Reclamation": "生息演算",
    "SwitchTheme": "更换主题",
    "DepotMaintain": "库存保持",
    "UserDataUpdate": "更新数据",
    "Custom": "自定任务",
    "SingleStep": "单步任务",
    "VideoRecognition": "视频识别",
    "Debug": "调试",
}

# 上传失败原因由 MAA 以英文短语回传，此处转为中文结论。
REPORT_WHY_TEXT = {
    "recognition error": "识别错误",
    "refresh count reached the limit": "刷新次数达到上限",
    "UnknownStage": "未识别关卡",
    "NotThreeStars": "非三星结算",
    "UnknownTimes": "未识别关卡次数",
    "UnknownDropType": "未识别掉落类型",
    "UnknownDrops": "未识别掉落物",
}

# 连接信息。周期回传的截图耗时没有可读结论，因此不在此表内（原始负载仍在调试日志）；
# 模拟器帧率等其余遥测只保留在调试日志里。
CONNECTION_TEXT = {
    "ConnectFailed": (logging.ERROR, "MAA 连接失败"),
    "UnsupportedResolution": (logging.ERROR, "MAA 不支持当前模拟器分辨率"),
    "ResolutionError": (logging.ERROR, "MAA 获取分辨率失败"),
    "ResolutionChanged": (
        logging.ERROR,
        "模拟器分辨率已变更，连接已断开，请重新开始任务以应用新分辨率",
    ),
    "TouchModeNotAvailable": (
        logging.ERROR,
        "MAA 触控模式不可用，请切换其他触控模式",
    ),
    "Disconnect": (logging.ERROR, "MAA 重连失败，连接已断开"),
    "ScreencapFailed": (
        logging.ERROR,
        "MAA 截图失败，如反复出现请尝试重启或更换模拟器",
    ),
    "Reconnecting": (logging.ERROR, "MAA 连接断开，正在重连"),
    "Reconnected": (logging.INFO, "MAA 重连成功，继续任务"),
    "ResolutionGot": (logging.DEBUG, "MAA 已获取分辨率"),
    "ResolutionInfo": (logging.DEBUG, "MAA 已获取分辨率"),
    "UuidGot": (logging.DEBUG, "MAA 已获取设备唯一码"),
    "Connected": (logging.DEBUG, "MAA 已连接设备"),
    "FastestWayToScreencap": (logging.DEBUG, "MAA 已测出最快截图方式"),
    "EmulatorFPS": (logging.DEBUG, "MAA 已上报模拟器帧率"),
    "MuMuExtrasInputStatus": (logging.DEBUG, "MAA 已上报 MuMu 触控增强状态"),
}

# SubTaskExtraInfo 的 what 字段。表项为 (日志级别, 文本)；文本可以是取 details 的函数。
SUB_TASK_INFO = {
    # 战斗与关卡
    "StageDrops": (logging.INFO, lambda details: _stage_drops(details)),
    "StageInfo": (
        logging.INFO,
        lambda details: f"开始战斗：{_inner(details).get('name', '')}",
    ),
    "StageInfoError": (logging.ERROR, "MAA 关卡识别错误"),
    "StageQueueMissionCompleted": (
        logging.INFO,
        lambda details: (
            f"关卡队列：{_inner(details).get('stage_code', '')} - "
            f"{_inner(details).get('stars', '')} ★"
        ),
    ),
    "StageQueueUnableToAgent": (
        logging.INFO,
        lambda details: (
            f"关卡队列：{_inner(details).get('stage_code', '')} 无法使用代理指挥"
        ),
    ),
    "UnsupportedLevel": (
        logging.ERROR,
        lambda details: f"MAA 不支持该关卡：{_inner(details).get('level', '')}",
    ),
    # 公招
    "RecruitTagsDetected": (
        logging.INFO,
        lambda details: f"公招识别到标签：{_tag_list(details)}",
    ),
    "RecruitTagsSelected": (
        logging.INFO,
        lambda details: f"公招已选择标签：{_tag_list(details)}",
    ),
    "RecruitSpecialTag": (
        logging.INFO,
        lambda details: f"公招识别到特殊标签：{_inner(details).get('tag', '')}",
    ),
    "RecruitPreservedTag": (
        logging.INFO,
        lambda details: f"公招保留标签：{_inner(details).get('tag', '')}",
    ),
    "RecruitResult": (logging.INFO, lambda details: _recruit_result(details)),
    "RecruitSupportOperator": (
        logging.INFO,
        lambda details: f"编入助战干员：{_inner(details).get('name', '')}",
    ),
    "RecruitTagsRefreshed": (
        logging.INFO,
        lambda details: (
            f"公招刷新标签：{_inner(details).get('count', 0)}/"
            f"{_inner(details).get('refresh_limit', 0)}"
        ),
    ),
    "RecruitNoPermit": (
        logging.INFO,
        lambda details: (
            "公招没有招聘许可"
            + ("，继续刷新标签" if _inner(details).get("continue") else "，已返回")
        ),
    ),
    "RecruitPermitReserved": (
        logging.INFO,
        lambda details: (
            f"招聘许可剩余 {_inner(details).get('current', 0)}，跳过当前 3 星招募"
        ),
    ),
    "RecruitPermitCountRecognitionFailed": (
        logging.WARNING,
        "招聘许可数量识别失败，已跳过当前 3 星招募",
    ),
    "RecruitError": (logging.WARNING, "MAA 公招识别错误"),
    # 信用收支：只买折扣是配置出来的正常行为，不是需要用户处理的异常。
    "CreditFullOnlyBuyDiscount": (
        logging.INFO,
        lambda details: (
            "只购买折扣商品让信用点数溢出了，剩余信用点数："
            f"{_inner(details).get('credit', 0)}"
        ),
    ),
    # 基建
    "ProductIncorrect": (logging.ERROR, "基建产物与配置不相符"),
    "ProductUnknown": (logging.ERROR, "无法识别的基建产物"),
    "ProductChangeFail": (logging.ERROR, "基建产物切换失败"),
    "ProductChanged": (logging.INFO, "基建产物已切换"),
    "NotEnoughStaff": (
        logging.ERROR,
        lambda details: f"{_facility(details)} 可用干员不足",
    ),
    # 肉鸽
    "ExceededLimit": (
        logging.INFO,
        lambda details: (
            f"任务 {_inner(details).get('task', '')} 达到执行上限"
            f"（{_inner(details).get('exec_times', 0)}/"
            f"{_inner(details).get('max_times', 0)}）"
        ),
    ),
    # 保全派驻
    "SSSStage": (
        logging.INFO,
        lambda details: f"保全派驻当前关卡：{_inner(details).get('stage', '')}",
    ),
    "SSSGamePass": (logging.INFO, "保全派驻通关"),
    "SSSSettlement": (logging.INFO, lambda details: str(details.get("why", ""))),
    # 生息演算
    "ReclamationProcedureStart": (
        logging.INFO,
        lambda details: f"生息演算已开始行动 {_inner(details).get('times', 0)} 次",
    ),
    "ReclamationSmeltGold": (
        logging.INFO,
        lambda details: f"生息演算锻造赤金 {_inner(details).get('times', 0)} 次",
    ),
    "ReclamationReport": (logging.INFO, lambda details: _reclamation_report(details)),
    # 更换主题
    "SwitchThemeSkipped": (logging.INFO, "未填写主题名称，跳过更换主题"),
    "SwitchThemeNotFound": (
        logging.ERROR,
        lambda details: f"未找到主题：{_inner(details).get('theme', '')}",
    ),
    # 识别过程；设施进出沿用客户端的常规级别。
    "EnterFacility": (
        logging.INFO,
        lambda details: f"MAA 进入{_facility(details)}",
    ),
    "ProductOfFacility": (
        logging.DEBUG,
        lambda details: (
            f"MAA 收取{_facility(details)}的{_inner(details).get('product', '')}"
        ),
    ),
    "DepotInfo": (
        logging.DEBUG,
        lambda details: "MAA 仓库识别完成" if _inner(details).get("done") else "",
    ),
    "OperBoxInfo": (
        logging.DEBUG,
        lambda details: "MAA 干员识别完成" if _inner(details).get("done") else "",
    ),
}

# ProcessTask 的原子动作。识别动作每秒多次回传，未列出的节点不产生日志行。
PROCESS_TASK_START = {
    "StartButton2": (logging.INFO, "开始战斗"),
    "AnnihilationConfirm": (logging.INFO, "开始剿灭行动"),
    "MedicineConfirm": (logging.INFO, "使用理智药"),
    "StoneConfirm": (
        logging.INFO,
        lambda details: f"已使用源石 {_inner(details).get('exec_times', 0)} 次",
    ),
    "AbandonAction": (logging.ERROR, "代理指挥失误"),
    "FightMissionFailedAndStop": (
        logging.ERROR,
        "代理失败次数已达上限，任务已停止",
    ),
    "OfflineConfirm": (logging.ERROR, lambda details: _offline_confirm(details)),
    "OfflineConfirmAfterBattle": (
        logging.ERROR,
        lambda details: _offline_confirm(details),
    ),
    "CheckEncounter-Uncollected": (
        logging.WARNING,
        "MAA 已停止自动探索，请返回游戏完成战斗",
    ),
    "DeepExplorationNotUnlockedComplain": (logging.WARNING, "深入调查未解锁"),
    "PNS-Resume": (
        logging.ERROR,
        "当前使用无存档任务模式，请手动删除现有存档后再试",
    ),
    "PIS-Commence": (logging.ERROR, "当前任务模式需要拥有可合成道具的存档"),
    "RecruitRefreshConfirm": (logging.INFO, "已刷新公招标签"),
    "RecruitConfirm": (logging.INFO, "已确认招募"),
    "RecruitNowConfirm": (logging.INFO, "使用加急许可"),
    "InfrastDormDoubleConfirmButton": (
        logging.INFO,
        "检测到干员已进驻其他设施，已自动确认将其调动",
    ),
    "ExitThenAbandon": (logging.INFO, "已放弃本次探索"),
    "MissionCompletedFlag": (logging.INFO, "肉鸽战斗完成"),
    "MissionFailedFlag": (logging.ERROR, "肉鸽战斗失败"),
    "GamePass": (logging.INFO, "肉鸽通关"),
    # 肉鸽节点在不同 MAA 版本间改过名，两种拼写都列出来。
    "StageTrader": (logging.INFO, "肉鸽节点：诡意行商"),
    "StageTraderEnter": (logging.INFO, "肉鸽节点：诡意行商"),
    "StageTraderInvestConfirm": (logging.INFO, "肉鸽投资源石锭"),
    "StageTraderInvestSystemFull": (logging.INFO, "肉鸽投资达到上限"),
    "StageTraderSpecialShoppingAfterRefresh": (
        logging.INFO,
        "已购买肉鸽特殊商品",
    ),
    "StageSafeHouse": (logging.INFO, "肉鸽节点：安全的角落"),
    "StageSafeHouseEnter": (logging.INFO, "肉鸽节点：安全的角落"),
    "StageFilterTruth": (logging.INFO, "肉鸽节点：去伪存真"),
    "StageEncounterEnter": (logging.INFO, "肉鸽节点：不期而遇"),
    "StageCombatOps": (logging.INFO, "肉鸽关卡：普通作战"),
    "StageCombatOpsEnter": (logging.INFO, "肉鸽关卡：普通作战"),
    "StageEmergencyOps": (logging.INFO, "肉鸽关卡：紧急作战"),
    "StageDreadfulFoe": (logging.INFO, "肉鸽关卡：险路恶敌"),
    "StageDreadfulFoe-5": (logging.INFO, "肉鸽关卡：险路恶敌"),
}

# ProcessTask 的完成动作，按 (任务链, 节点) 区分。
PROCESS_TASK_COMPLETED = {
    ("Infrast", "UnlockClues"): (logging.INFO, "已开启线索交流"),
    ("Roguelike", "StartExplore"): (
        logging.INFO,
        lambda details: f"肉鸽已开始探索 {_inner(details).get('exec_times', 0)} 次",
    ),
    ("Mall", "StageDrops-Stars-3"): (logging.INFO, "借助战打 OF-1 赚信用完成"),
    ("Mall", "VisitLimited"): (logging.INFO, "访问好友完成"),
    ("Mall", "VisitNextBlack"): (logging.INFO, "访问好友完成"),
    ("SwitchTheme", "SwitchThemeByNameConfirmTheme"): (
        logging.INFO,
        lambda details: f"已更换主题：{_theme_name(details)}",
    ),
    ("SwitchTheme", "SwitchThemeByNameAlreadySet"): (
        logging.INFO,
        lambda details: f"目标已是当前主题：{_theme_name(details)}，无需更换",
    ),
    ("SwitchTheme", "SwitchThemeByNameLockedTheme"): (
        logging.ERROR,
        lambda details: f"主题未解锁，无法更换：{_theme_name(details)}",
    ),
}

# SubTaskError 的 subtask 字段。未列出的子任务给出通用出错行。
SUB_TASK_ERROR = {
    "StartGameTask": (logging.ERROR, "MAA 打开客户端失败，请检查客户端配置"),
    "StopGameTask": (logging.ERROR, "MAA 关闭游戏失败"),
    "CheckStageValid": (logging.ERROR, "无奖励关卡，已停止"),
    "RecognizeDrops": (logging.ERROR, "MAA 掉落识别错误"),
    "AutoRecruitTask": (
        logging.ERROR,
        lambda details: f"MAA 公招出错：{_why_text(details)}，已返回",
    ),
    # 上报跳过沿用客户端的告警级别；客户端对剿灭另有平静文案，此处不区分。
    "ReportToPenguinStats": (
        logging.WARNING,
        lambda details: f"{_why_text(details)}，放弃上传企鹅物流",
    ),
    "ReportToYituliu": (
        logging.WARNING,
        lambda details: f"{_why_text(details)}，放弃上传一图流",
    ),
}


class MaaLogLine(NamedTuple):
    """One ready-to-log line derived from a MAA callback."""

    level: int
    text: str


def parse_details(raw) -> dict:
    """Decode a callback detail payload.

    MAA sends no payload for some codes and an empty string for others, so a
    missing or unparsable payload yields an empty mapping instead of failing
    inside the C callback.
    """
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _key(value) -> str:
    """Payload fields index translation tables, so they must be plain strings."""
    return value if isinstance(value, str) else ""


def _mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def _sequence(value) -> list:
    return value if isinstance(value, list) else []


def _inner(details: dict) -> dict:
    """Sub-task payloads nest their fields under ``details``; require an object."""
    return _mapping(details.get("details"))


def _chain(details: dict) -> str:
    name = _key(details.get("taskchain"))
    return TASK_CHAIN_TEXT.get(name, name) or "MAA"


def _tag_list(details: dict) -> str:
    return "、".join(str(tag) for tag in _sequence(_inner(details).get("tags")))


def _facility(details: dict) -> str:
    inner = _inner(details)
    return f"{inner.get('facility', '')} {inner.get('index', '')}".strip()


def _theme_name(details: dict) -> str:
    return str(_mapping(_inner(details).get("result")).get("text", ""))


def _why_text(details: dict) -> str:
    raw = _key(details.get("why"))
    return REPORT_WHY_TEXT.get(raw, raw) or "出现错误"


def _stage_drops(details: dict) -> str:
    inner = _inner(details)
    stage = _key(_mapping(inner.get("stage")).get("stageCode")) or "关卡"
    items = "、".join(
        f"{drop.get('itemName') or drop.get('itemId', '?')}×{drop.get('quantity', 0)}"
        for drop in (_mapping(drop) for drop in _sequence(inner.get("drops")))
    )
    return f"{stage} 作战结束，掉落：{items}" if items else f"{stage} 作战结束，无掉落"


def _recruit_result(details: dict) -> str:
    inner = _inner(details)
    names = list(
        dict.fromkeys(
            oper["name"]
            for combo in (_mapping(combo) for combo in _sequence(inner.get("result")))
            for oper in (_mapping(oper) for oper in _sequence(combo.get("opers")))
            # 干员名可能缺失或不是字符串；哈希与拼接都只接受字符串。
            if _key(oper.get("name"))
        )
    )
    text = f"公招识别到 {inner.get('level', 0)} 星组合"
    if not names:
        return text
    shown = "、".join(names[:RECRUIT_OPER_LIMIT])
    if len(names) > RECRUIT_OPER_LIMIT:
        shown += f" 等 {len(names)} 名干员"
    return f"{text}：{shown}"


def _offline_confirm(details: dict) -> str:
    """开始唤醒链本来就要在游戏未启动时接管，只有运行中的掉线才需要用户处理。"""
    if _key(details.get("taskchain")) == "StartUp":
        return ""
    return "游戏掉线，任务已停止"


def _routing_restart(details: dict) -> str:
    # TaskChainExtraInfo 把 what / why / node_cost 放在顶层，与子任务消息的嵌套不同。
    return f"前方战斗数：{details.get('node_cost', '?')}，重开路线"


def _reclamation_report(details: dict) -> str:
    inner = _inner(details)
    return (
        f"生息演算结束：繁荣证章 {inner.get('total_badges', 0)}"
        f"(+{inner.get('badges', 0)})，建造点数 "
        f"{inner.get('total_construction_points', 0)}"
        f"(+{inner.get('construction_points', 0)})"
    )


def _entry_line(entry, details: dict) -> MaaLogLine | None:
    """Render one table entry; entries hold literal text or a details reader."""
    if entry is None:
        return None
    level, value = entry
    text = value(details) if callable(value) else value
    return MaaLogLine(level, text) if text else None


class MaaCallbackLog:
    """State of one MAA run: the readable lines it produces and its heartbeat."""

    def __init__(
        self,
        *,
        interval: float = HEARTBEAT_INTERVAL,
        stall_after: float = STALL_AFTER,
        clock=time.monotonic,
    ) -> None:
        self._interval = interval
        self._stall_after = stall_after
        self._clock = clock
        self._started = clock()
        self._last_heartbeat = self._started
        self._last_event = self._started
        self.taskchain = ""

    def describe(self, message: int, details: dict) -> MaaLogLine | None:
        """Return the line to log for one callback, or None when it carries none."""
        self._last_event = self._clock()
        details = _mapping(details)
        if message == 0:
            return MaaLogLine(logging.ERROR, "MAA 内部错误")
        if message == 1:
            what = details.get("what", "")
            why = details.get("why", "")
            text = f"MAA 初始化失败：{what}"
            return MaaLogLine(logging.ERROR, f"{text}（{why}）" if why else text)
        if message == 2:
            return _entry_line(CONNECTION_TEXT.get(_key(details.get("what"))), details)
        if message == 3:
            self.taskchain = ""
            return MaaLogLine(
                logging.INFO, f"MAA 全部任务完成（最后：{_chain(details)}）"
            )
        if message == 4:
            return self._async_call(details)
        if 10000 <= message <= 10004:
            return self._task_chain(message, details)
        if 20000 <= message <= 20004:
            return self._sub_task(message, details)
        return None

    def heartbeat(self) -> MaaLogLine | None:
        """Return the periodic progress line, or None until the interval elapses."""
        now = self._clock()
        if now - self._last_heartbeat < self._interval:
            return None
        self._last_heartbeat = now
        stage = TASK_CHAIN_TEXT.get(self.taskchain, self.taskchain)
        facts = [f"已运行 {_duration(now - self._started)}"]
        silence = now - self._last_event
        if silence >= self._stall_after:
            facts.append(f"最近 {_duration(silence)} 没有收到 MAA 回调")
        scope = f"：{stage}" if stage else ""
        return MaaLogLine(logging.INFO, f"MAA 运行中{scope}（{'，'.join(facts)}）")

    @staticmethod
    def _async_call(details: dict) -> MaaLogLine | None:
        inner = _inner(details)
        if inner.get("error") or inner.get("ret") is False:
            return MaaLogLine(
                logging.WARNING,
                f"MAA 异步调用 {details.get('what', '')} 失败：{inner.get('error', '')}",
            )
        return None

    def _task_chain(self, message: int, details: dict) -> MaaLogLine | None:
        self.taskchain = _key(details.get("taskchain")) or self.taskchain
        chain = _chain(details)
        if message == 10001:
            return MaaLogLine(logging.INFO, f"开始任务：{chain}")
        if message in (10002, 10004):
            # 任务链结束后不再声称它仍在运行；下一条链开始时重新写入。
            # 停止多为调度器自己发起，用 INFO 记录链路终止，避免日志里出现没有下文的链。
            self.taskchain = ""
            verb = "完成任务" if message == 10002 else "已停止任务"
            return MaaLogLine(logging.INFO, f"{verb}：{chain}")
        if message == 10000:
            error = _inner(details).get("error", "")
            if error == "OutOfMemory":
                return MaaLogLine(
                    logging.ERROR,
                    f"{chain}任务因内存不足停止，请关闭部分程序或重启 MAA 后重试",
                )
            suffix = f"（{error}）" if error else ""
            return MaaLogLine(logging.ERROR, f"任务出错：{chain}{suffix}")
        # 10003：其余额外信息没有可读结论。
        if details.get("what") == "RoutingRestart":
            return MaaLogLine(logging.WARNING, _routing_restart(details))
        return None

    @staticmethod
    def _sub_task(message: int, details: dict) -> MaaLogLine | None:
        subtask = _key(details.get("subtask"))
        if message == 20000:
            entry = SUB_TASK_ERROR.get(subtask)
            if entry is None:
                entry = (logging.WARNING, f"{_chain(details)}：{subtask} 出错")
            return _entry_line(entry, details)
        if message == 20003:
            return _entry_line(SUB_TASK_INFO.get(_key(details.get("what"))), details)
        # 子任务开始与完成只播报 ProcessTask 白名单里的节点。
        if subtask != "ProcessTask":
            return None
        task = _key(_inner(details).get("task"))
        if message == 20001:
            return _entry_line(PROCESS_TASK_START.get(task), details)
        if message == 20002:
            key = (_key(details.get("taskchain")), task)
            return _entry_line(PROCESS_TASK_COMPLETED.get(key), details)
        return None
