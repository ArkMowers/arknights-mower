"""Finite, read-only BlueStacks 5 installation and product configuration sources."""

import re
import time
from pathlib import Path

from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.manager_io import MAX_INSTANCES, MAX_OUTPUT
from arknights_mower.utils.device.preflight import PreflightError
from arknights_mower.utils.device.windows_discovery import WindowsInstallationDiscovery
from arknights_mower.utils.path import resolve_config_path

INSTANCE_KEY = r"[A-Za-z][A-Za-z0-9_]*"


def configuration_error(message):
    return InstanceBindingError(
        "config_invalid",
        f"BlueStacks 配置无效：{message}。请在 BlueStacks 设置中检查 ADB，或重新检测配置路径。",
        ["config_path"],
    )


def read_bluestacks_config(path):
    """Only parse a bounded product file; never guess a default instance/port."""
    path = Path(resolve_config_path(str(path)))
    if path.name.casefold() != "bluestacks.conf":
        raise configuration_error("请选择数据目录中的 bluestacks.conf")
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_OUTPUT + 1)
    except PermissionError as exc:
        raise InstanceBindingError(
            "discovery_permission",
            "无法读取已绑定的 BlueStacks 配置文件，请检查配置路径及当前用户的读取权限后重试。",
            ["config_path"],
        ) from exc
    except FileNotFoundError as exc:
        raise InstanceBindingError(
            "missing_config",
            "找不到 BlueStacks 数据目录中的 bluestacks.conf，请修正产品配置路径后重试。",
            ["config_path"],
        ) from exc
    if len(content) > MAX_OUTPUT:
        raise configuration_error("配置超过 1 MiB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise configuration_error("配置不是 UTF-8") from exc
    values = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)="(.*)"', line.strip())
        if match is None or match[1] in values or "\x00" in line:
            raise configuration_error("字段格式错误或重复")
        values[match[1]] = match[2]
    instances = {}
    for key, value in values.items():
        if not key.startswith("bst.instance."):
            continue
        match = re.fullmatch(rf"bst\.instance\.({INSTANCE_KEY})\.(.+)", key)
        if not match:
            raise configuration_error("实例关键字无效")
        instances.setdefault(match[1], {})[match[2]] = value
    if not instances or len(instances) > MAX_INSTANCES:
        raise configuration_error("缺少实例或实例超过 64 个")
    return values, instances


def locate_bluestacks_player(candidate):
    path = Path(resolve_config_path(str(candidate))).resolve()
    player = path if path.suffix.lower() == ".exe" else path / "HD-Player.exe"
    if player.name.casefold() != "hd-player.exe" or not player.is_file():
        raise InstanceBindingError(
            "missing_installation",
            "找不到 BlueStacks 5 的 HD-Player.exe，请修正安装目录或重新检测。",
            ["installation_path"],
        )
    return player


class BlueStacksDiscoveryIO(WindowsInstallationDiscovery):
    product = "BlueStacks"

    def __init__(
        self, *, registry_installations=None, platform=None, monotonic=time.monotonic
    ):
        # This vendor has no manager command source, only the registry record.
        super().__init__(
            registry_paths=registry_installations,
            process_paths=lambda: [],
            fixed_paths=lambda: [],
            monotonic=monotonic,
            platform=platform,
        )

    @staticmethod
    def _read_registry_installations():
        for entry in WindowsInstallationDiscovery._iterate_registry_keys(
            "SOFTWARE",
            ("BlueStacks_nxt", "BlueStacks_nxt_cn"),
            BlueStacksDiscoveryIO._failure,
        ):
            if isinstance(entry, PreflightError):
                yield entry
                continue
            paths = []
            for field, repair in (
                ("InstallDir", "installation_path"),
                ("UserDefinedDir", "config_path"),
            ):
                try:
                    value = entry.get(field)
                except KeyError as exc:
                    raise InstanceBindingError(
                        "config_invalid",
                        f"BlueStacks 注册表缺少 {field}，请手动指定对应路径后重试。",
                        [repair],
                    ) from exc
                if not (
                    isinstance(value, str)
                    and value.strip()
                    and Path(value).is_absolute()
                ):
                    raise InstanceBindingError(
                        "config_invalid",
                        f"BlueStacks 注册表 {field} 不是有效的绝对路径，请修正后重试。",
                        [repair],
                    )
                paths.append(value)
            install, data = paths
            yield install, str(Path(data) / "bluestacks.conf")

    # Discovery resolves the registry source under the shared base name.
    _read_registry_paths = _read_registry_installations

    @classmethod
    def _failure(cls, exc):
        # This product reads a program directory and a data directory, so a read
        # failure names both; there is no manager command whose output could fail.
        repair = super()._failure(exc)
        if repair.code == "discovery_permission":
            return PreflightError(
                repair.code,
                repair.message,
                fields=["installation_path", "config_path"],
            )
        if repair.code == "manager_output":
            return PreflightError(
                "config_invalid",
                f"无法读取 BlueStacks 配置：{exc}",
                fields=["config_path"],
            )
        return repair

    def discover(self, profile):
        result = {"installations": [], "errors": []}
        if self._platform != "windows":
            return result
        deadline = self._monotonic() + 6
        sources = []
        if profile.preset_id == "windows.bluestacks5" and (
            profile.installation_path or profile.manager_path or profile.config_path
        ):
            sources.append(
                (profile.manager_path or profile.installation_path, profile.config_path)
            )
        try:
            for source in self._registry_paths():
                if self._monotonic() >= deadline:
                    raise TimeoutError
                if isinstance(source, PreflightError):
                    result["errors"].append(source)
                else:
                    sources.append(source)
        except (OSError, ValueError) as exc:
            result["errors"].append(self._failure(exc))
        seen = set()
        count = 0
        for program, config in sources:
            try:
                if self._monotonic() >= deadline:
                    raise TimeoutError
                player = locate_bluestacks_player(program)
                if not config:
                    raise InstanceBindingError(
                        "missing_config",
                        "请指定 BlueStacks 数据目录中的 bluestacks.conf。",
                        ["config_path"],
                    )
                config = Path(resolve_config_path(config)).resolve()
                identity = (str(player).casefold(), str(config).casefold())
                if identity in seen:
                    continue
                seen.add(identity)
                _, rows = read_bluestacks_config(config)
                instances = []
                for keyword, row in rows.items():
                    name = row.get("display_name", "").strip()
                    if not name:
                        raise configuration_error(f"{keyword} 缺少 display_name")
                    instances.append(
                        {
                            "instance_id": keyword,
                            "instance_name": name,
                            # Configuration is not evidence of a running VM.
                            "state": "unknown",
                            "serial": "",
                        }
                    )
                count += len(instances)
                if count > MAX_INSTANCES:
                    raise configuration_error("本次产品发现超过 64 个实例")
                if self._monotonic() >= deadline:
                    raise TimeoutError
                result["installations"].append(
                    {
                        "preset_id": "windows.bluestacks5",
                        "installation_path": str(player.parent),
                        "manager_path": str(player),
                        "config_path": str(config),
                        "instances": instances,
                    }
                )
            except (OSError, ValueError) as exc:
                result["errors"].append(self._failure(exc))
        return result
