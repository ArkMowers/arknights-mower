"""Application detection for Air, without inventing a VM or lifecycle API."""

from dataclasses import dataclass, field
from pathlib import Path

from arknights_mower.utils.device.preflight import PreflightError, PreflightResult
from arknights_mower.utils.path import resolve_config_path

AIR_PRESET = "macos.bluestacks_air"
AIR_ENDPOINT = "127.0.0.1:5555"
AIR_GUIDANCE = (
    "请手动打开 BlueStacks Air，进入设置（Settings）→ 高级（Advanced），"
    "开启 Android Debug Bridge（ADB）并保存更改，等待 Android 桌面出现后重试。"
    "如果仍无法连接，请填写设置中显示的 ADB 地址。"
    "一期仅检测应用与 ADB，不提供多实例管理或自动启动、停止、重启。"
)


@dataclass
class AirResult(PreflightResult):
    kind: str = "preflight"
    preset_id: str = AIR_PRESET
    guidance: str = AIR_GUIDANCE
    profile_patch: dict = field(default_factory=dict)


class BlueStacksAirDiscovery:
    def __init__(self, *, application_paths=None):
        self._application_paths = application_paths

    def _installation(self, profile):
        paths = (
            [Path(resolve_config_path(profile.installation_path))]
            if profile.installation_path.strip()
            else self._application_paths
            if self._application_paths is not None
            else (
                Path("/Applications/BlueStacks.app"),
                Path.home() / "Applications/BlueStacks.app",
            )
        )
        applications = []
        for path in paths:
            path = Path(path)
            if (
                path.name == "BlueStacks.app"
                and (path / "Contents/Info.plist").is_file()
                and (path / "Contents/MacOS").is_dir()
            ):
                resolved = str(path.resolve())
                if resolved not in applications:
                    applications.append(resolved)
        if len(applications) == 1:
            return applications[0]
        return ""

    def check(
        self,
        profile,
        preflight,
        *,
        confirmed_package=None,
        resolved_adb=None,
        prepare_capture=None,
    ):
        result = AirResult(False, preflight.host_platform(), "failed", "")
        if result.host_platform != "macos":
            result.error = PreflightError(
                "unsupported_host",
                "BlueStacks Air 只能在 macOS 主机检测。",
                fields=["preset_id"],
            )
            return result
        try:
            installation = self._installation(profile)
        except OSError:
            result.error = PreflightError(
                "discovery_permission_denied",
                "无法读取 BlueStacks Air 应用，请检查当前用户的访问权限后重试。",
                fields=["installation_path"],
            )
            return result
        if not installation:
            result.error = PreflightError(
                "missing_installation",
                "未找到唯一的 BlueStacks Air 应用，请安装应用或指定 BlueStacks.app 路径后重试。",
                fields=["installation_path"],
            )
            return result
        binding = {
            "preset_id": AIR_PRESET,
            "installation_path": installation,
            "manager_path": "",
            "config_path": "",
            "instance_id": "",
            "instance_name": "",
            "instance_uuid": "",
            "topology_fingerprint": "",
        }
        current = profile.model_copy(update=binding)
        if not current.last_serial.strip():
            # Observe the current list without probing an arbitrary device. A
            # fixed port is only a candidate, never a substitute for a choice
            # when several devices are already connected.
            listed = preflight.check(current, resolved_adb=resolved_adb)
            if listed.error.code not in {"target_required", "multiple_devices"}:
                return AirResult(**vars(listed))
            if listed.candidates and (
                len(listed.candidates) != 1
                or listed.candidates[0]["serial"] != AIR_ENDPOINT
            ):
                return AirResult(**vars(listed))
            resolved_adb = listed.adb_path
            current = current.model_copy(update={"last_serial": AIR_ENDPOINT})
        checked = preflight.check(
            current,
            confirmed_package=confirmed_package,
            resolved_adb=resolved_adb,
            require_unique_target=not profile.last_serial.strip(),
            **(
                {"prepare_capture": prepare_capture}
                if prepare_capture is not None
                else {}
            ),
        )
        result = AirResult(**vars(checked))
        result.observations["installation_path"] = installation
        if result.error and result.error.code in {
            "target_absent",
            "device_probe_failed",
        }:
            result.error = PreflightError(
                "air_adb_unavailable",
                "未能验证 BlueStacks Air 的 ADB 连接。" + AIR_GUIDANCE,
                fields=["last_serial"],
            )
        if result.ok:
            result.profile_patch = binding
        return result
