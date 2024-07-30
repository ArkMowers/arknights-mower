from pydantic import BaseModel, model_validator
from pydantic_core import PydanticUndefined


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


class ExtraPart(ConfModel):
    class WebViewConf(ConfModel):
        port: int = 58000
        "端口号"
        width: int = 2000
        "窗口宽度"
        height: int = 1000
        "窗口高度"
        token: str = ""
        "远程连接密钥"
        scale: float = 1
        "网页缩放"
        tray: bool = True
        "托盘图标"

    start_automatically: bool = False
    "启动后自动开始任务"
    webview: WebViewConf
    "GUI相关设置"
    theme: str = "light"
    "界面主题"
    screenshot: int = 200
    "截图数量"


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
        investment_enabled: bool = True
        "投资源石锭"
        stop_when_investment_full: bool = True
        "储备源石锭达到上限时停止"
        refresh_trader_with_dice: bool = False
        "刷新商店（指路鳞）"

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
    recruit_email_enable: bool = True
    "邮件通知"


class RegularTaskPart(ConfModel):
    class MaaDailyPlan(BaseModel):
        medicine: int = 0
        stage: list[str]
        weekday: str

    class MaaDailyPlan1(BaseModel):
        stage: str | list[str]
        周一: int
        周二: int
        周三: int
        周四: int
        周五: int
        周六: int
        周日: int

    check_mail_enable: bool = True
    "领取邮件奖励"
    maa_enable: bool = True
    "日常任务"
    maa_gap: float = 3
    "日常任务间隔"
    maa_expiring_medicine: bool = True
    "自动使用快要过期（约3天）的理智药"
    maa_eat_stone: bool = False
    "无限吃源石"
    maa_weekly_plan: list[MaaDailyPlan] = [
        {"medicine": 0, "stage": [""], "weekday": "周一"},
        {"medicine": 0, "stage": [""], "weekday": "周二"},
        {"medicine": 0, "stage": [""], "weekday": "周三"},
        {"medicine": 0, "stage": [""], "weekday": "周四"},
        {"medicine": 0, "stage": [""], "weekday": "周五"},
        {"medicine": 0, "stage": [""], "weekday": "周六"},
        {"medicine": 0, "stage": [""], "weekday": "周日"},
    ]
    "周计划"
    maa_weekly_plan1: list[MaaDailyPlan1] = [
        {
            "stage": ["点x删除"],
            "周一": 1,
            "周二": 1,
            "周三": 1,
            "周四": 1,
            "周五": 1,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["把鼠标放到问号上查看帮助"],
            "周一": 1,
            "周二": 1,
            "周三": 1,
            "周四": 1,
            "周五": 1,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["自定义关卡3"],
            "周一": 1,
            "周二": 1,
            "周三": 1,
            "周四": 1,
            "周五": 1,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["Annihilation"],
            "周一": 1,
            "周二": 1,
            "周三": 1,
            "周四": 1,
            "周五": 1,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["1-7"],
            "周一": 1,
            "周二": 1,
            "周三": 1,
            "周四": 1,
            "周五": 1,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["LS-6"],
            "周一": 1,
            "周二": 1,
            "周三": 1,
            "周四": 1,
            "周五": 1,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["CE-6"],
            "周一": 0,
            "周二": 1,
            "周三": 0,
            "周四": 1,
            "周五": 0,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["AP-5"],
            "周一": 1,
            "周二": 0,
            "周三": 0,
            "周四": 1,
            "周五": 0,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["SK-6"],
            "周一": 1,
            "周二": 0,
            "周三": 1,
            "周四": 0,
            "周五": 1,
            "周六": 1,
            "周日": 0,
        },
        {
            "stage": ["CA-5"],
            "周一": 0,
            "周二": 1,
            "周三": 1,
            "周四": 0,
            "周五": 1,
            "周六": 0,
            "周日": 1,
        },
        {
            "stage": ["PR-A-2"],
            "周一": 1,
            "周二": 0,
            "周三": 0,
            "周四": 1,
            "周五": 1,
            "周六": 0,
            "周日": 1,
        },
        {
            "stage": ["PR-A-2"],
            "周一": 1,
            "周二": 0,
            "周三": 0,
            "周四": 1,
            "周五": 1,
            "周六": 0,
            "周日": 1,
        },
        {
            "stage": ["PR-B-2"],
            "周一": 1,
            "周二": 1,
            "周三": 0,
            "周四": 0,
            "周五": 1,
            "周六": 1,
            "周日": 0,
        },
        {
            "stage": ["PR-B-1"],
            "周一": 1,
            "周二": 1,
            "周三": 0,
            "周四": 0,
            "周五": 1,
            "周六": 1,
            "周日": 0,
        },
        {
            "stage": ["PR-C-2"],
            "周一": 0,
            "周二": 0,
            "周三": 1,
            "周四": 1,
            "周五": 0,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["PR-C-1"],
            "周一": 0,
            "周二": 0,
            "周三": 1,
            "周四": 1,
            "周五": 0,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["PR-D-2"],
            "周一": 0,
            "周二": 1,
            "周三": 1,
            "周四": 0,
            "周五": 0,
            "周六": 1,
            "周日": 1,
        },
        {
            "stage": ["PR-D-1"],
            "周一": 0,
            "周二": 1,
            "周三": 1,
            "周四": 0,
            "周五": 0,
            "周六": 1,
            "周日": 1,
        },
    ]
    "周计划（新）"
    maa_depot_enable: bool = False
    "仓库物品混合读取"
    visit_friend: bool = True
    "访问好友"


class ReportPart(ConfModel):
    report_enable: bool = True
    "读取基报"
    send_report: bool = True
    "发送邮件"


class RIICPart(ConfModel):
    class RunOrderGrandetModeConf(ConfModel):
        enable: bool = True
        "葛朗台跑单开关"
        buffer_time: int = 15
        "缓冲时间"
        back_to_index: bool = False
        "跑单前返回基建首页"

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
        x: int = 0
        "横坐标"
        y: int = 0
        "纵坐标"

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
    exit_game_when_idle: bool = True
    "任务结束后退出游戏"
    close_simulator_when_idle: bool = False
    "任务结束后关闭模拟器"
    fix_mumu12_adb_disconnect: bool = False
    "关闭MuMu模拟器12时结束adb进程"
    touch_method: str = "scrcpy"
    "触控模式"
    droidcast: DroidCastConf
    "DroidCast截图设置"


class SKLandPart(ConfModel):
    class SKLandAccount(BaseModel):
        account: str = ""
        "账号"
        password: str = ""
        "密码"
        cultivate_select: bool = True
        "服务器"
        isCheck: bool = True
        "签到"
        sign_in_bilibili: bool = False
        "官服签到"
        sign_in_official: bool = False
        "B服签到"

    skland_enable: bool = False
    "森空岛签到"
    skland_info: list[SKLandAccount] = []
    "森空岛账号"


class Conf(
    CluePart,
    EmailPart,
    ExtraPart,
    LongTaskPart,
    MaaPart,
    RecruitPart,
    RegularTaskPart,
    ReportPart,
    RIICPart,
    SimulatorPart,
    SKLandPart,
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
