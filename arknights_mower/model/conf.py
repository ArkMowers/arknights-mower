from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic_core import to_jsonable_python
from yamlcore import CoreDumper, CoreLoader

from .MIGRATION import MOWER_MIGRATION_CONFS
from .mower import MowerConfig


class Config(BaseModel):
    """
    Arknights Mower 总配置文件
    """

    # adb: str = Field("127.0.0.1:62001", description="ADB 连接地址")
    # drone_count_limit: int = Field(92, description="无人机使用阈值", ge=0, le=120)
    # drone_room: str = Field("", description="无人机使用房间，留空为任意贸易站")
    # drone_interval: float = Field(4, description="无人机使用间隔", ge=0)
    # enable_party: bool = Field(True, description="是否启用线索收集")
    # leifeng_mode: bool = Field(False, description="是否启用雷锋模式")
    # simulator: SimulatorConfig = Field(
    #     default_factory=SimulatorConfig, description="模拟器配置"
    # )
    # # exhaust_require: str
    # # workaholic: str
    # free_blacklist: list[str] = Field([], description="宿舍黑名单")
    # # ling_xi: int
    # check_mail_enable: bool = Field(True, description="是否检查游戏邮件")
    # report_enable: bool = Field(True, description="是否读取基建报告")
    # send_report_enable: bool = Field(True, description="是否发送邮件")
    # email: EMailConfig = Field(default_factory=EMailConfig, description="邮箱配置")
    # package_type: PackageEnum = Field(
    #     PackageEnum.Official, description="服务器类型, 1 为官服, 2 为 B 服"
    # )
    # plan_file: Path = Field(
    #     Path("./plan.json"),
    #     description="计划文件路径",
    #     alias="planFile",  # 设置了别名，准备 deprecated
    # )
    # reload_room: list[str] = Field([], description="#TODO: 看不懂这个是什么")
    # # rest_in_full: list[str]
    # # resting_priority: list[str]
    # run_order_delay: int = Field(10, description="跑单延迟", ge=0)
    # start_automatically: bool = Field(False, description="是否自动开始")
    # webview: WebViewConfig = Field(
    #     default_factory=WebViewConfig, description="WebView 配置"
    # )
    # exit_game_when_idle: bool = Field(True, description="空闲时退出游戏")
    # maa: MaaConfig = Field(default_factory=MaaConfig, description="MAA 配置")、

    mower: MowerConfig = Field(default_factory=MowerConfig, description="Mower 配置")

    ...  # other configurations

    # @field_validator("plan_file", mode="before")
    # @classmethod
    # def validate_plan_file(cls, value: str | Path | None) -> Path:
    #     if value is None:
    #         return value
    #     if isinstance(value, str):
    #         if value == "":
    #             return None
    #         value = Path(value)
    #     if not value.exists():
    #         logger.warning("指定的计划文件不存在")
    #     return value

    @staticmethod
    def load_conf(file: Path | str = Path("./conf.yml")) -> "Config":
        with open(file, "r", encoding="utf-8") as f:
            return Config.model_validate(yaml.load(f, Loader=CoreLoader))

    def save_conf(
        self, file: Path | str = Path("./conf.yml"), old: bool = False
    ) -> None:
        with open(file, "w", encoding="utf-8") as f:
            yaml.dump(
                to_jsonable_python(
                    self.__pydantic_extra__
                    if old
                    else self.model_dump(exclude=set(self.__pydantic_extra__.keys()))
                ),
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

    # _old_to_new = field_validator("free_blacklist", "reload_room", mode="before")(
    #     from_old_str_to_list
    # )

    @model_validator(mode="before")
    @classmethod
    def _(cls: "Config", data: dict[str, Any]) -> Any:
        # mower
        mower = data.get("mower", {})
        for key in MOWER_MIGRATION_CONFS:
            if key in data:
                mower[key] = data[key]
        data["mower"] = mower
        return data

    # TODO 等搞完就删了

    model_config = ConfigDict(extra="allow")

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def my_copy(self, update_json: dict[str, Any] = None) -> "Config":
        conf = self.model_copy(update=update_json)
        conf.mower = self.mower.model_validate(
            {k: v for k, v in update_json.items() if k in MOWER_MIGRATION_CONFS}
        )
        return conf
