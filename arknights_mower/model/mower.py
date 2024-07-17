from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .types import PackageEnum, ThemeEnum, TouchMethodEnum


class TapToLaunchGameConfig(BaseModel):
    enable: bool = Field(False, description="是否启用点击启动游戏")
    x: int = Field(0, description="点击坐标 X")
    y: int = Field(0, description="点击坐标 Y")


class SimulatorConfig(BaseModel):
    """
    虚拟机配置
    """

    name: str = Field("", description="模拟器名称")
    index: int = Field(-1, description="模拟器多开序号")
    simulator_folder: Optional[Path] = Field(None, description="模拟器文件夹路径")
    wait_time: int = Field(30, description="模拟器启动等待时间", ge=0)

    @field_validator("simulator_folder", mode="before")
    @classmethod
    def validate_simulator_folder(cls, value: str | Path | None) -> Optional[Path]:
        if value is None:
            return value
        if isinstance(value, str):
            if value == "":
                return None
            value = Path(value)
        if not value.exists():
            pass
            # logger.warning("指定的模拟器文件夹不存在")
        return value


class DroidCastConfig(BaseModel):
    """
    Droidcast 配置
    """

    enable: bool = Field(True, description="是否启用 Droidcast")
    rotate: bool = Field(False, description="是否旋转屏幕")


class CustomScreenshotConfig(BaseModel):
    """
    自定义截图配置
    """

    enable: bool = Field(False, description="是否启用自定义截图")
    command: str = Field(
        "adb -s 127.0.0.1:5555 shell screencap -p 2>/dev/null",
        description="自定义截图命令",
    )


class WebViewConfig(BaseModel):
    port: int = Field(58000, description="WebView 端口号", ge=1, le=65535)
    width: int = Field(1280, description="WebView 宽度", ge=1)
    height: int = Field(720, description="WebView 高度", ge=1)
    token: str = Field("", description="WebView Token")  # TODO: SecretStr
    scale: float = Field(1.0, description="WebView 缩放比例", ge=0)
    tray: bool = Field(False, description="是否启用 WebView 系统托盘")


class MowerConfig(BaseModel):
    """
    Arknight Mower 配置
    """

    package_type: PackageEnum = Field(PackageEnum.Official, description="服务器类型")
    adb: str = Field("127.0.0.1:62001", description="ADB 连接地址")
    adb_path: Optional[Path] = Field(None, description="ADB 路径", alias="maa_adb_path")
    touch_method: TouchMethodEnum = Field(
        TouchMethodEnum.Scrcpy, description="触控方案"
    )
    simulator: SimulatorConfig = Field(
        default_factory=SimulatorConfig, description="虚拟机配置"
    )
    tap_to_launch_game: TapToLaunchGameConfig = Field(
        default_factory=TapToLaunchGameConfig, description="点击启动游戏配置"
    )
    start_automatically: bool = Field(False, description="是否自动开始")
    exit_game_when_idle: bool = Field(True, description="空闲时退出游戏")
    close_simulator_when_idle: bool = Field(False, description="空闲时关闭模拟器")
    fix_mumu12_adb_disconnect: bool = Field(False, description="修复 MuMu 12 ADB 断开")
    droidcast: DroidCastConfig = Field(
        default_factory=DroidCastConfig, description="Droidcast 配置"
    )
    custom_screenshot: CustomScreenshotConfig = Field(
        default_factory=CustomScreenshotConfig, description="自定义截图配置"
    )
    screenshot_nums: int = Field(1, description="截图数量", ge=0, alias="screenshot")
    webview: WebViewConfig = Field(
        default_factory=WebViewConfig, description="WebView 配置"
    )
    theme: ThemeEnum = Field(ThemeEnum.Light, description="主题")
    daily_task_interval: float = Field(
        4, description="日常任务间隔，单位为 h", ge=0, alias="maa_gap"
    )

    @property
    def adb_host(self) -> str:
        """
        ADB 主机地址
        """
        return self.adb.split(":")[0]

    @property
    def adb_port(self) -> int:
        """
        ADB 端口号
        """
        return int(self.adb.split(":")[-1])

    @field_validator("adb", mode="after")
    @classmethod
    def validate_adb(cls, value: str) -> str:
        port = int(value.split(":")[-1])
        # 由于实时修改，这里可以能就会炸
        if port < 1 or port > 65535:
            raise ValueError("ADB 端口号范围应为 1-65535")
        return value
