from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from pydantic_core import to_jsonable_python
from yamlcore import CoreDumper, CoreLoader

from .email import EmailConfig
from .enum import DirectionEnum, PackageEnum, SimulatorEnum, ThemeEnum, TouchMethodEnum
from .maa import MaaConfig
from .plan import OldPlanConfig
from .recruit import RecruitConfig
from .skland import SKLandConfig
from .util import from_old_str_to_list, from_str_to_path


class SimulatorConfig(BaseModel):
    """
    模拟器配置
    """

    name: SimulatorEnum = SimulatorEnum.其他
    """
    模拟器名称

    传入一个字符串，将会自动转换为对应的枚举类型。
    例如：
        - 夜神
        - MuMu模拟器12
        - Waydroid
        - 雷电模拟器9
        - ReDroid
        - MuMu模拟器Pro
        - 其他
    """

    index: int = -1
    """
    模拟器多开编号，夜神单开使用 -1

    旧版配置传入字符串，将会自动转换为对应的整数类型。
    """

    simulator_folder: Optional[Path] = None

    wait_time: int = 30
    """
    模拟器启动等待时间
    
    单位为秒
    """

    @field_validator("simulator_folder", mode="before")
    def _simulator_folder(cls, v: str | Path | None) -> Optional[Path]:
        if v is None:
            return None
        return Path(v)


class WebViewConfig(BaseModel):
    port: int = 58000
    "WebView 端口号"
    width: int = 1280
    "WebView 宽度"
    height: int = 720
    "WebView 高度"
    token: str = ""
    "WebView Token"
    scale: float = 1.0
    "WebView 缩放比例"
    tray: bool = False
    "是否启用 WebView 系统托盘"


class TapToLaunchGameConfig(BaseModel):
    enable: bool = False
    "是否启用点击启动游戏"
    x: int = 0
    "点击坐标 X"
    y: int = 0
    "点击坐标 Y"


class DroidCastConfig(BaseModel):
    """
    Droidcast 配置
    """

    enable: bool = True
    "是否启用 Droidcast"
    rotate: bool = False
    "是否旋转屏幕"


class CustomScreenshotConfig(BaseModel):
    """
    自定义截图配置
    """

    enable: bool = False
    "是否启用自定义截图"
    command: str = "adb -s 127.0.0.1:5555 shell screencap -p 2>/dev/null"
    "自定义截图命令"


class RunOrderGrandetModeConfig(BaseModel):
    enable: bool = True
    "是否启用葛朗台跑单模式"
    buffer_time: int = 30
    """
    葛朗台跑单模式缓冲时间
    
    单位为秒
    """
    back_to_index: bool = True
    "是否返回主页"


class PushPlusConfig(BaseModel):
    enable: bool = False
    "是否启用 PushPlus 推送"
    token: str = ""
    "PushPlus Token"


class SignInConfig(BaseModel):
    """
    签到活动配置
    """

    enable: bool = True


class CreditFightConfig(BaseModel):
    squad: Literal[1, 2, 3, 4] = 1
    """
    编队

    分别对应 1-4 编队
    """

    operator: str = "风笛"
    "干员"
    x: int = 5
    "放置坐标 X"
    y: int = 3
    direction: DirectionEnum = DirectionEnum.Right


class Config(MaaConfig, EmailConfig, OldPlanConfig, RecruitConfig):
    """
    Arknights Mower 总配置文件

    对于一些看似可以合并的配置项，通过继承的方式来实现。
    例如：
        - MaaConfig
        - EmailConfig

    对于旧的 PLAN 配置，因为不能确定是否需要保留，所以通过继承的方式来实现。
    """

    adb: str = "127.0.0.1:62001"
    """
    ADB 连接地址
    
    接受形如 IP:PORT 或是 HOSTNAME:PORT 的字符串，或是设备 ID。
    例如：
        - 127.0.0.1:62001
        - my_custom_domain:62001
        - emulator-5554
    """

    drone_count_limit: int = 92
    "无人机使用阈值"

    drone_room: Optional[str] = None  # 在代码中实现为 is None，因此不能直接填空。
    """
    无人机使用房间

    如果为空，则无人机将会在任意房间中使用。
    例如：
        - None
        - B101
    """

    drone_interval: float = 4
    """
    无人机加速间隔

    单位为小时
    """

    enable_party: bool = True
    "是否启用线索收集"

    leifeng_mode: bool = True
    """
    是否启用雷锋模式

    开启时，向好友赠送多余的线索；关闭则超过9个线索才送好友。
    """

    simulator: SimulatorConfig = Field(
        default_factory=SimulatorConfig, description="模拟器配置"
    )
    "模拟器配置"

    free_blacklist: list[str] = []
    """
    宿舍黑名单

    不希望进行填充宿舍的干员。
    一个字符串列表。为了兼容老配置，也可以传入一个字符串自动序列化。
    """

    check_mail_enable: bool = True
    "是否领取邮件奖励"

    report_enable: bool = True
    "是否发送邮件（每日任务）"

    send_report: bool = True
    "是否发送邮件（基建报告）"

    mail_enable: bool = True
    "是否启用邮件提醒"

    max_resting_count: int = 8
    "最大组人数"

    package_type: PackageEnum = PackageEnum.Official
    """
    服务器类型

    1 为官服，2 为B服。
    传入一个整数，将会自动转换为对应的枚举类型。
    """

    planFile: Optional[Path] = None
    """
    计划文件路径

    传入一个字符串，将会自动转换为对应的 Path 类型。
    TODO: 是否需要一致使用下划线命名
    """

    reload_room: str = ""
    """
    搓玉补货房间

    例如：
        - B101
        - B203
    """

    run_order_delay: float = 10
    """
    跑单前置延时

    单位为分钟，可填入小数。
    """

    start_automatically: bool = False
    """
    是否启动后自动开始任务
    """

    webview: WebViewConfig = Field(default_factory=WebViewConfig)
    "WebView 配置"

    tap_to_launch_game: TapToLaunchGameConfig = Field(
        default_factory=TapToLaunchGameConfig
    )
    "点击启动游戏配置"

    exit_game_when_idle: bool = True
    "空闲时退出游戏"

    close_simulator_when_idle: bool = False
    "空闲时关闭模拟器"

    resting_threshold: float = 0.5
    "心情阈值"

    theme: ThemeEnum = ThemeEnum.Light
    """
    主题

    传入一个字符串，将会自动转换为对应的枚举类型。
    例如：
        - Light
        - Dark
    """

    screenshot: int = 200
    "截图数量"

    skland_enable: bool = False
    "是否启用森空岛"

    skland_info: list[SKLandConfig] = []
    "森空岛账号信息"

    run_order_grandet_mode: RunOrderGrandetModeConfig = Field(
        default_factory=RunOrderGrandetModeConfig
    )
    "葛朗台跑单模式配置"

    server_push_enable: bool = False
    "是否启用 ServerChan 推送"

    sendKey: str = ""
    "ServerChan SendKey"

    pushplus: PushPlusConfig = Field(default_factory=PushPlusConfig)

    fix_mumu12_adb_disconnect: bool = False
    "修复 MuMu 模拟器 12 adb 断开"

    touch_method: TouchMethodEnum = TouchMethodEnum.Scrcpy
    """
    触控方式

    传入一个字符串，将会自动转换为对应的枚举类型。
    例如：
        - maatouch
        - scrcpy
    """

    free_room: bool = False
    """
    宿舍不养闲人

    干员心情回满后，立即释放宿舍空位
    """

    sign_in: SignInConfig = Field(default_factory=SignInConfig)
    "签到活动配置"

    droidcast: DroidCastConfig = Field(default_factory=DroidCastConfig)

    visit_friend: bool = True
    "是否访问好友"

    custom_screenshot: CustomScreenshotConfig = Field(
        default_factory=CustomScreenshotConfig
    )

    @staticmethod
    def load_conf(file: Path | str = Path("./conf.yml")) -> "Config":
        with open(file, "r", encoding="utf-8") as f:
            return Config.model_validate(yaml.load(f, Loader=CoreLoader))

    def save_conf(self, file: Path | str = Path("./conf.yml")) -> None:
        with open(file, "w", encoding="utf-8") as f:
            yaml.dump(
                to_jsonable_python(self.model_dump()),
                f,
                Dumper=CoreDumper,
                encoding="utf-8",
                default_flow_style=False,
                allow_unicode=True,
            )

    """
    +===================+
    |   向上兼容老 conf   |
    +===================+
    """

    model_config = ConfigDict(extra="allow")

    # def __getitem__(self, item: str) -> Any:
    #     return getattr(self, item)

    _conf_old_to_new = field_validator("free_blacklist", mode="before")(
        from_old_str_to_list
    )
    _conf_to_path = field_validator("planFile", mode="before")(from_str_to_path)

    _old_plan_conf_old_to_new = field_validator(
        "exhaust_require",
        "workaholic",
        "rest_in_full",
        "resting_priority",
        mode="before",
    )(from_old_str_to_list)


config = Config.load_conf()
