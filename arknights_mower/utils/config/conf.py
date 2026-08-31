from pathlib import Path

from pydantic import BaseModel, model_validator
from pydantic_core import PydanticUndefined

from arknights_mower import __rootdir__

DEFAULT_LAUNCH_COMMAND = (
    "input keyevent KEYCODE_WAKEUP; "
    "wm dismiss-keyguard; "
    "am start -n {package}/{activity}"
)


class ConfModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def nested_defaults(cls, data):
        for name, field in cls.model_fields.items():
            if name not in data:
                if field.default is PydanticUndefined:
                    data[name] = field.annotation()
                else:
                    data[name] = field.default
        return data


class CluePart(ConfModel):
    class CreditFightConf(ConfModel):
        direction: str = "Right"
        "部署方向"
        operator: str = "风笛"
        "使用干员"
        squad: int = 1
        "编队序号"
        x: int = 5
        "横坐标"
        y: int = 3
        "纵坐标"

    maa_credit_fight: bool = True
    "信用作战开关"
    credit_fight: CreditFightConf
    "信用作战设置"
    enable_party: int = 1
    "线索收集"
    leifeng_mode: int = 1
    "雷锋模式"
    maa_mall_blacklist: str = "加急许可,碳,碳素,家具零件"
    "黑名单"
    maa_mall_buy: str = "招聘许可,技巧概要·卷2"
    "优先购买"
    maa_mall_ignore_blacklist_when_full: bool = False
    "信用溢出时无视黑名单"


class EmailPart(ConfModel):
    class CustomSMTPServerConf(ConfModel):
        enable: bool = False
        "启用自定义邮箱"
        server: str = ""
        "SMTP服务器"
        encryption: str = "starttls"
        "加密方式"
        ssl_port: int = 587
        "端口号"

    mail_enable: int = 0
    "邮件提醒"
    account: str = ""
    "邮箱用户名"
    pass_code: str = ""
    "邮箱密码"
    recipient: list[str] = []
    "收件人"
    custom_smtp_server: CustomSMTPServerConf
    "自定义邮箱"
    mail_subject: str = "[Mower通知]"
    "标题前缀"
    notification_level: str = "INFO"
    "邮件通知等级"
    timezone_offset: int = 0
    "时差修正"


class ExtraPart(ConfModel):
    class WebViewConf(ConfModel):
        port: int = 58000
        "端口号"
        width: int = 1450
        "窗口宽度"
        height: int = 850
        "窗口高度"
        token: str = ""
        "远程连接密钥"
        scale: float = 1
        "网页缩放"
        tray: bool = True
        "托盘图标"

    class WaitingSceneConf(ConfModel):
        CONNECTING: tuple[int, int] = (1, 10)
        UNKNOWN: tuple[int, int] = (1, 10)
        LOADING: tuple[int, int] = (2, 30)
        LOGIN_LOADING: tuple[int, int] = (3, 10)
        LOGIN_MAIN_NOENTRY: tuple[int, int] = (3, 10)
        OPERATOR_ONGOING: tuple[int, int] = (10, 30)

    start_automatically: bool = False
    "启动后自动开始任务"
    webview: WebViewConf
    "GUI相关设置"
    theme: str = "light"
    "界面主题"
    screenshot_interval: int = 500
    "截图最短间隔（毫秒）"
    screenshot: float = 0.02
    "截图保留时长（小时）"
    check_for_updates: bool = True
    "检查更新"
    waiting_scene: WaitingSceneConf
    "等待时间"


class LongTaskPart(ConfModel):
    class RogueConf(ConfModel):
        squad: str = ""
        "分队"
        roles: str = ""
        "职业"
        core_char: str = ""
        "干员"
        use_support: bool = False
        "开局干员使用助战"
        use_nonfriend_support: bool = False
        "开局干员使用非好友助战"
        mode: int = 1
        "策略"
        refresh_trader_with_dice: bool = False
        "刷新商店（指路鳞）"
        expected_collapsal_paradigms: list[str] = [
            "目空一些",
            "睁眼瞎",
            "图像损坏",
            "一抹黑",
        ]
        "需要刷的坍缩范式"

    class SSSConf(ConfModel):
        type: int = 1
        "关卡"
        ec: int = 1
        "导能单元"

    class ReclamationAlgorithmConf(ConfModel):
        timeout: int = 30
        "生息演算和隐秘战线的超时时间"

    class SecretFrontConf(ConfModel):
        target: str = "结局A"
        "隐秘战线结局"

    class RclConf(ConfModel):
        mode: int = 0
        "模式（0=Tales无存档/1=Tales有存档/16=RA1/32=RA15/48=RA4）"
        tools_to_craft: list[str] = ["荧光棒"]
        "自动制造的物品（仅Tales有效）"
        increment_mode: int = 0
        "点击类型（0=连点/1=长按，仅Tales有效）"
        num_craft_batches: int = 16
        "单次最大制造轮数（仅Tales有效）"

    class SignInConf(ConfModel):
        enable: bool = True
        "签到活动开关"

    maa_rg_enable: int = 0
    "大型任务"
    maa_long_task_type: str = "rogue"
    "大型任务类型"
    maa_rg_sleep_max: str = "0:00"
    "开始时间"
    maa_rg_sleep_min: str = "0:00"
    "停止时间"
    maa_rg_theme: str = "Mizuki"
    "肉鸽主题"
    maa_rcl_theme: str = "Tales"
    "生息演算主题（Tales/Fire/RelaunchAnchor）"
    rcl: RclConf
    "生息演算设置"
    rogue: RogueConf
    "肉鸽设置"
    sss: SSSConf
    "保全设置"
    reclamation_algorithm: ReclamationAlgorithmConf
    "生息演算"
    secret_front: SecretFrontConf
    "隐秘战线结局"
    sign_in: SignInConf
    "签到活动"


class MaaPart(ConfModel):
    maa_path: str = "D:\\MAA-v4.13.0-win-x64"
    maa_conn_preset: str = "General"
    maa_touch_option: str = "maatouch"
    maa_startup_check: bool = False
    "Mower启动及每次初始化Maa前测试连接"


class RecruitPart(ConfModel):
    recruit_enable: bool = True
    "公招开关"
    recruit_robot: bool = True
    "保留支援机械标签"
    recruitment_permit: int = 30
    "三星招募阈值"
    recruit_gap: float = 9
    "启动间隔"
    recruit_auto_5: int = 1
    "五星招募策略，1自动，2手动"
    recruit_auto_only5: bool = False
    "五星词条组合唯一时自动选择"


class RegularTaskPart(ConfModel):
    class MaaDailyPlan(BaseModel):
        medicine: int = 0
        sanity_threshold: int = 0
        stage: list[str]
        weekday: str

    check_mail_enable: bool = True
    "领取邮件奖励"
    maa_enable: bool = True
    "日常任务"
    maa_gap: float = 3
    "日常任务间隔"
    maa_expiring_medicine: bool = True
    "自动使用将要过期（约3天）的理智药"
    exipring_medicine_on_weekend: bool = False
    "仅在周末使用将要过期的理智药"
    ap_fallback: int = 0
    "关卡体力消耗默认值（数据中找不到关卡时的兜底，0 表示不启用）"
    maa_eat_stone: bool = False
    "无限吃源石"
    maa_weekly_plan: list[MaaDailyPlan] = [
        {"medicine": 0, "sanity_threshold": 0, "stage": [""], "weekday": "周一"},
        {"medicine": 0, "sanity_threshold": 0, "stage": [""], "weekday": "周二"},
        {"medicine": 0, "sanity_threshold": 0, "stage": [""], "weekday": "周三"},
        {"medicine": 0, "sanity_threshold": 0, "stage": [""], "weekday": "周四"},
        {"medicine": 0, "sanity_threshold": 0, "stage": [""], "weekday": "周五"},
        {"medicine": 0, "sanity_threshold": 0, "stage": [""], "weekday": "周六"},
        {"medicine": 0, "sanity_threshold": 0, "stage": [""], "weekday": "周日"},
    ]
    "周计划"
    maa_depot_enable: bool = False
    "仓库物品混合读取"
    visit_friend: bool = True
    "访问好友"
    report_enable: bool = True
    "读取基报"


class WorkShopItem(ConfModel):
    item_names: list[str] = []
    "材料名称"
    children_lower_limit: int = 20
    "子项下限"
    self_upper_limit: int = 30
    "自己上限"


class RIICPart(ConfModel):
    class RunOrderGrandetModeConf(ConfModel):
        enable: bool = True
        "葛朗台跑单开关"
        buffer_time: int = 15
        "缓冲时间"
        back_to_index: bool = False
        "跑单前返回基建首页"

    class WorkShopSetting(ConfModel):
        items: list[WorkShopItem] = []
        "材料列表"
        operator: str = ""
        "干员"
        enabled: bool = True
        "启用"

    drone_count_limit: int = 100
    "无人机使用阈值"
    drone_room: str = ""
    "无人机使用房间"
    drone_interval: float = 3
    "无人机加速间隔"
    free_blacklist: str = ""
    "宿舍黑名单"
    reload_room: str = ""
    "搓玉补货房间"
    run_order_delay: float = 3
    "跑单前置延时"
    resting_threshold: float = 0.65
    "心情阈值"
    run_order_grandet_mode: RunOrderGrandetModeConf
    "葛朗台跑单"
    free_room: bool = False
    "宿舍不养闲人模式"
    fia_fool: bool = True
    "菲亚防呆"
    fia_threshold: float = 0.9
    "菲亚阈值"
    rescue_threshold: float = 0.75
    "急救阈值"
    favorite: str = ""
    "替换组心情监视"
    workshop_settings: list[WorkShopSetting] = []
    "工作室设置"
    t5_operators: list[str] = ["年"]
    "自动专精 T5 加工干员"
    book_operators: list[str] = ["司霆惊蛰"]
    "自动专精 技巧概要加工干员"
    fodder_operators: list[str] = ["九色鹿"]
    "自动专精 非 T5 材料加工干员"
    merge_interval: float = 10
    "不养闲人合并间隔"
    dorm_order: str = ""
    "宿舍优先级"
    refresh_backup_plan_after_mood: bool = False
    "缓存清零重启后读取心情并按载入心情数据模式重启"
    assistant_follows_schedule: bool = False
    "协助位跟随排班（专精时协助位不固定，由排班系统管理）"
    enable_mastery: bool = True
    "全自动专精全局开关：OFF 时禁用全部训练室动作/通知/守卫，仅保留仓库材料扫描"
    # 中枢加成（0/5）与换人缓冲时间已迁到路线配置全局设置行（#91 修订），不再存 conf


class SimulatorPart(ConfModel):
    class SimulatorConf(ConfModel):
        name: str = ""
        "名称"
        index: str | int = "-1"
        "多开编号"
        simulator_folder: str = ""
        "文件夹"
        wait_time: int = 30
        "启动时间"
        hotkey: str = ""
        "老板键"

    class CustomScreenshotConf(ConfModel):
        command: str = "adb -s 127.0.0.1:5555 shell screencap -p 2>/dev/null"
        "截图命令"
        enable: bool = False
        "是否启用自定义截图"

    class TapToLaunchGameConf(ConfModel):
        enable: bool = False
        "点击屏幕启动游戏"
        mode: str | None = None
        "启动游戏方式"
        x: int = 0
        "横坐标"
        y: int = 0
        "纵坐标"
        command: str = DEFAULT_LAUNCH_COMMAND
        "自定义启动命令"

        @model_validator(mode="after")
        def normalize_mode(self):
            if self.mode not in {"adb", "tap", "custom"}:
                self.mode = "tap" if self.enable else "adb"
            self.enable = self.mode == "tap"
            if not self.command:
                self.command = DEFAULT_LAUNCH_COMMAND
            return self

    class DroidCastConf(ConfModel):
        enable: bool = True
        "使用DroidCast截图"
        rotate: bool = False
        "将截图旋转180度"

    adb: str = "127.0.0.1:16384"
    "ADB连接地址"
    simulator: SimulatorConf
    "模拟器"
    maa_adb_path: str = "D:\\Program Files\\Nox\\bin\\adb.exe"
    "ADB路径"
    close_simulator_when_idle: bool = False
    "任务结束后关闭游戏"
    package_type: int = 1
    "游戏服务器"
    custom_screenshot: CustomScreenshotConf
    "自定义截图"
    tap_to_launch_game: TapToLaunchGameConf
    "点击屏幕启动游戏"
    exit_game_when_idle: bool = False
    "任务结束后退出游戏"
    return_home_when_idle: bool = False
    "任务结束后返回首页"
    close_simulator_when_idle: bool = False
    "任务结束后关闭模拟器"
    fix_mumu12_adb_disconnect: bool = False
    "关闭MuMu模拟器12时结束adb进程"
    touch_method: str = "scrcpy"
    "触控模式"
    droidcast: DroidCastConf
    "DroidCast截图设置"
    mumu12IPC: bool = False
    "MuMu12IPC截图设置"


class SKLandPart(ConfModel):
    class SKLandAccount(BaseModel):
        account: str = ""
        "账号"
        password: str = ""
        "密码"
        cultivate_select: bool = True
        "服务器"
        arknights_isCheck: bool = True
        "明日方舟签到"
        endfield_isCheck: bool = True
        "终末地签到"
        sign_in_official: bool = False
        "官服签到"
        sign_in_bilibili: bool = False
        "B服签到"
        sign_in_endfield_official: bool = False
        "终末地官服签到"
        sign_in_endfield_bilibili: bool = False
        "终末地b服签到"

    skland_enable: bool = False
    "森空岛签到"
    skland_info: list[SKLandAccount] = []
    "森空岛账号"


class AIAgentPart(ConfModel):
    ai_type: str = ""
    "名称"
    ai_key: str = ""
    "密钥"

    @property
    def resolved_ai_key(self) -> str:
        if self.ai_key:
            return self.ai_key
        token_path = Path(__rootdir__).parent / "token.txt"
        if token_path.exists():
            return token_path.read_text(encoding="utf-8").strip()
        return ""


class MaaRewardPart(ConfModel):
    maa_mail: bool = False
    "领取所有邮件奖励"
    maa_recruit: bool = False
    "进行限定池赠送的每日免费单抽"
    maa_orundum: bool = False
    "领取幸运墙的每日合成玉奖励"
    maa_mining: bool = False
    "领取限时开采许可的每日合成玉奖励"
    maa_specialaccess: bool = False
    "领取五周年赠送月卡奖励"


class Conf(
    CluePart,
    EmailPart,
    ExtraPart,
    LongTaskPart,
    MaaPart,
    RecruitPart,
    RegularTaskPart,
    RIICPart,
    SimulatorPart,
    SKLandPart,
    MaaRewardPart,
    AIAgentPart,
):
    @property
    def APPNAME(self):
        return (
            "com.hypergryph.arknights"
            if self.package_type == 1
            else "com.hypergryph.arknights.bilibili"
        )

    @property
    def RG(self):
        return self.maa_rg_enable == 1 and self.maa_long_task_type == "rogue"

    @property
    def SSS(self):
        return self.maa_rg_enable == 1 and self.maa_long_task_type == "sss"

    @property
    def RA(self):
        return self.maa_rg_enable == 1 and self.maa_long_task_type == "ra"

    @property
    def SF(self):
        return self.maa_rg_enable == 1 and self.maa_long_task_type == "sf"

    @property
    def RCL(self):
        return self.maa_rg_enable == 1 and self.maa_long_task_type == "rcl"

    @property
    def run_order_buffer_time(self):
        """
        >  0 葛朗台跑单的缓冲时间
        <= 0 无人机跑单
        """
        if self.run_order_grandet_mode.enable:
            return self.run_order_grandet_mode.buffer_time
        return -1
