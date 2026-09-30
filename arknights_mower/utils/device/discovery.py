"""User-requested discovery policy; results never persist a session endpoint."""

import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Protocol

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.bluestacks_air import (
    AIR_PRESET,
    BlueStacksAirDiscovery,
)
from arknights_mower.utils.device.endpoint_identity import (
    AVD_PRESETS,
    VERIFIED_ENDPOINT_PRESETS,
    InstanceBindingError,
)
from arknights_mower.utils.device.genymotion import GENYMOTION_PRESET, genymotion_repair
from arknights_mower.utils.device.mumu_pro import MUMU_PRO_PRESET
from arknights_mower.utils.device.preflight import (
    PreflightError,
    PreflightResult,
    PreflightService,
    mumu_pro_manual_error,
)
from arknights_mower.utils.device.redroid import REDROID_PRESET, redroid_repair
from arknights_mower.utils.device.session import Simulator
from arknights_mower.utils.device.waydroid import WAYDROID_PRESET, waydroid_repair


class DiscoveryIO(Protocol):
    def discover(self, profile: DeviceProfile) -> dict: ...


# One provider sweep keeps the Windows branch's whole-product budget.
VENDOR_DISCOVERY_BUDGET = 6


@dataclass
class DiscoveryResult:
    host_platform: str
    ok: bool = False
    kind: str = "discovery"
    status: str = "failed"
    candidates: list[dict] = field(default_factory=list)
    selected_key: str | None = None
    errors: list[PreflightError] = field(default_factory=list)
    error: PreflightError | None = None

    def to_dict(self):
        return asdict(self)


def _concurrent(operations):
    """Run every provider concurrently and keep results in the caller's order.

    Host providers are independent products: one slow or failing manager never
    removes another product's candidates, and the order stays stable.
    """
    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        futures = [
            executor.submit(copy_context().run, operation) for operation in operations
        ]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except MowerExit:
                raise
            except Exception:
                results.append(None)
        return results


class DiscoveryService:
    def __init__(
        self,
        io: DiscoveryIO,
        simulator: Simulator | None = None,
        *,
        air=None,
        avd=None,
        waydroid=None,
        redroid=None,
        genymotion=None,
    ):
        self._io = io
        self._simulator = simulator
        self._air = air or BlueStacksAirDiscovery()
        self._avd = avd
        self._waydroid = waydroid
        self._redroid = redroid
        self._genymotion = genymotion

    def check_binding(
        self,
        profile: DeviceProfile,
        preflight: PreflightService,
        *,
        confirmed_package=None,
        resolved_adb=None,
        prepare_capture=None,
    ) -> PreflightResult:
        """Read only the saved instance; never enumerate or start during detection."""
        capture_options = (
            {"prepare_capture": prepare_capture} if prepare_capture is not None else {}
        )
        if profile.preset_id == AIR_PRESET:
            return self._air.check(
                profile,
                preflight,
                confirmed_package=confirmed_package,
                resolved_adb=resolved_adb,
                **capture_options,
            )
        if profile.preset_id == MUMU_PRO_PRESET and not profile.topology_fingerprint:
            if preflight.host_platform() != "macos":
                return PreflightResult(
                    False,
                    preflight.host_platform(),
                    "failed",
                    profile.last_serial,
                    error=PreflightError(
                        "unsupported_host",
                        "MuMu Pro 只能在 macOS 上检测。",
                        fields=["preset_id"],
                    ),
                )
            return preflight.check(
                profile,
                confirmed_package=confirmed_package,
                resolved_adb=resolved_adb,
                **capture_options,
            )
        result = PreflightResult(False, preflight.host_platform(), "failed", "")
        avd = profile.preset_id in AVD_PRESETS
        waydroid = profile.preset_id == WAYDROID_PRESET
        redroid = profile.preset_id == REDROID_PRESET
        genymotion = profile.preset_id == GENYMOTION_PRESET
        mumu_pro = profile.preset_id == MUMU_PRO_PRESET
        if (
            (avd and profile.preset_id != f"{result.host_platform}.avd")
            or ((waydroid or redroid or genymotion) and result.host_platform != "linux")
            or (mumu_pro and result.host_platform != "macos")
            or (
                not avd
                and not waydroid
                and not redroid
                and not genymotion
                and not mumu_pro
                and result.host_platform != "windows"
            )
        ):
            result.error = PreflightError(
                "unsupported_host",
                "请在预设对应的主机平台验证此实例绑定。",
                fields=["preset_id"],
            )
            return result
        if profile.preset_id in VERIFIED_ENDPOINT_PRESETS:
            try:
                resolved_adb = resolved_adb or preflight.resolve_adb(profile)
            except ValueError as exc:
                result.error = PreflightError(
                    "missing_adb", str(exc), fields=["adb_path"]
                )
                return result
            profile = profile.model_copy(update={"adb_path": resolved_adb})
        try:
            if self._simulator is None:
                raise ValueError("未配置模拟器管理器")
            instance = self._simulator.inspect(profile, 10 if resolved_adb else 3)
        except MowerExit:
            raise
        except SharedADBError as exc:
            result.error = PreflightError(
                "adb_server_unavailable", str(exc), fields=["adb_path"]
            )
            return result
        except (TimeoutError, subprocess.TimeoutExpired):
            result.error = PreflightError(
                "manager_timeout",
                "实例验证响应超时，请检查管理程序与 ADB 后重试。",
                fields=["manager_path"],
            )
            return result
        except PermissionError:
            result.error = PreflightError(
                "discovery_permission_denied",
                "无法读取管理程序，请选择当前用户可访问的路径。",
                fields=["manager_path"],
            )
            return result
        except Exception as exc:
            if isinstance(exc, InstanceBindingError):
                result.error = (
                    waydroid_repair(exc)
                    if waydroid
                    else redroid_repair(exc)
                    if redroid
                    else genymotion_repair(exc)
                    if genymotion
                    else PreflightError(exc.code, str(exc), fields=exc.fields)
                )
                return result
            result.error = PreflightError(
                "binding_failed",
                f"无法确认已绑定的实例，请修正绑定或重新检测：{exc}",
                fields=["manager_path", "instance_id"],
            )
            return result
        if instance.state == "stopped":
            result.status = "absent"
            result.error = PreflightError(
                "start_confirmation_required"
                if avd or redroid or genymotion
                else "instance_stopped",
                "MuMu Pro 实例尚未启动。可检测并启动所选实例，也可在模拟器中手动启动后测试连接。"
                if mumu_pro
                else "已绑定的实例尚未启动，请确认启动后重新检测。"
                if avd or redroid or genymotion
                else "已绑定的实例尚未启动。可以点“启动并测试连接”让 mower 启动它，也可以手动启动后重新检测；开始任务时 mower 同样会启动这个实例。",
                "confirm"
                if avd or redroid or genymotion
                else "start"
                if waydroid
                else "retry",
            )
            return result
        if (
            waydroid or redroid or (mumu_pro and not instance.serial)
        ) and instance.state == "starting":
            result.status = "booting"
            result.error = PreflightError(
                "boot_incomplete", "所选实例尚在启动，请等待启动完成后重试。"
            )
            return result
        if not instance.serial or (
            instance.state not in {"running", "starting"}
            and profile.preset_id != "windows.bluestacks5"
        ):
            result.error = PreflightError(
                "endpoint_unresolved",
                "管理器未返回已绑定实例的当前端点，请等待实例启动并检查 ADB 后重试。",
                fields=["manager_path"],
            )
            return result
        current = profile.model_copy(update={"last_serial": instance.serial})
        return preflight.check(
            current,
            confirmed_package=confirmed_package,
            resolved_adb=resolved_adb,
            **capture_options,
        )

    def discover(
        self, profile: DeviceProfile, host: str, preflight=None
    ) -> DiscoveryResult | PreflightResult:
        if profile.preset_id == MUMU_PRO_PRESET:
            if host != "macos":
                return DiscoveryResult(
                    host,
                    error=PreflightError(
                        "unsupported_host",
                        "MuMu Pro 只能在 macOS 上检测。",
                        fields=["preset_id"],
                    ),
                )
            if not hasattr(self._simulator, "discover_mumu_pro"):
                return DiscoveryResult(host, error=mumu_pro_manual_error())
        if (
            host == "linux"
            and profile.preset_id == "manual.other"
            and not profile.last_serial
            and (
                self._waydroid is not None
                or self._redroid is not None
                or self._genymotion is not None
            )
        ):
            return self._discover_linux(profile, preflight)
        if (
            profile.preset_id in {WAYDROID_PRESET, REDROID_PRESET, GENYMOTION_PRESET}
            and host != "linux"
        ):
            return DiscoveryResult(
                host,
                error=PreflightError(
                    "unsupported_host",
                    "此环境预设只能在 Linux 主机检测。",
                    fields=["preset_id"],
                ),
            )
        if (
            host == "macos"
            and profile.preset_id == "manual.other"
            and not profile.last_serial
            and self._avd is not None
            and preflight is not None
        ):
            return self._discover_macos(profile, preflight)
        is_avd = profile.preset_id in AVD_PRESETS or (
            host == "linux"
            and profile.preset_id == "manual.other"
            and not profile.last_serial
        )
        if (
            host == "macos"
            and preflight is not None
            and not is_avd
            and profile.preset_id != MUMU_PRO_PRESET
        ):
            if profile.preset_id != AIR_PRESET:
                profile = profile.model_copy(
                    update={
                        "preset_id": AIR_PRESET,
                        "installation_path": "",
                        "manager_path": "",
                        "last_serial": "",
                        "game_package_confirmed": False,
                    }
                )
            return self._air.check(profile, preflight)
        result = DiscoveryResult(host)
        if profile.preset_id == MUMU_PRO_PRESET:
            try:
                observations = self._simulator.discover_mumu_pro(profile)
            except MowerExit:
                raise
            except InstanceBindingError as exc:
                return DiscoveryResult(
                    host, error=PreflightError(exc.code, str(exc), "manual", exc.fields)
                )
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                return DiscoveryResult(
                    host,
                    error=PreflightError(
                        "mumu_pro_discovery_failed",
                        f"无法读取 MuMu Pro 实例：{exc}",
                        "manual",
                        ["manager_path"],
                    ),
                )
        elif profile.preset_id == WAYDROID_PRESET and self._waydroid is not None:
            observations = self._waydroid.discover(profile, host)
        elif profile.preset_id == REDROID_PRESET and self._redroid is not None:
            observations = self._redroid.discover(profile, host)
        elif profile.preset_id == GENYMOTION_PRESET and self._genymotion is not None:
            observations = self._genymotion.discover(profile, host)
        elif is_avd and host in {"macos", "linux"} and self._avd is not None:
            observations = self._avd.discover(profile, host)
        elif host == "windows" and not is_avd:
            observations = self._io.discover(profile)
        else:
            result.error = PreflightError(
                "discovery_unavailable",
                "当前主机暂未提供自动发现，请使用手动配置。",
                fields=["preset_id"],
            )
            return result
        result.errors = observations["errors"]
        for installation in observations["installations"]:
            for instance in installation["instances"]:
                binding = {
                    "preset_id": installation.get("preset_id", "windows.mumu12"),
                    "installation_path": installation["installation_path"],
                    "manager_path": installation["manager_path"],
                    "instance_id": instance["instance_id"],
                    "instance_name": instance["instance_name"],
                    "last_serial": "",
                    "game_package_confirmed": False,
                }
                if binding["preset_id"] in {"windows.nox", MUMU_PRO_PRESET}:
                    binding["topology_fingerprint"] = instance["topology_fingerprint"]
                if binding["preset_id"] == "windows.nox":
                    binding.update(
                        instance_uuid=instance["instance_uuid"],
                    )
                if binding["preset_id"] in {
                    "windows.bluestacks5",
                    WAYDROID_PRESET,
                    REDROID_PRESET,
                }:
                    binding["config_path"] = installation["config_path"]
                manager_identity = installation["manager_path"].replace("\\", "/")
                if host == "windows":
                    manager_identity = manager_identity.casefold()
                identity = manager_identity + "\0" + instance["instance_id"]
                if binding["preset_id"] == MUMU_PRO_PRESET:
                    identity += "\0" + instance["topology_fingerprint"]
                if installation.get("config_path"):
                    identity += "\0" + (
                        installation["config_path"].replace("\\", "/").casefold()
                        if host == "windows"
                        else installation["config_path"]
                    )
                result.candidates.append(
                    {
                        **binding,
                        "key": sha256(identity.encode()).hexdigest(),
                        "state": instance["state"],
                        "serial": instance["serial"],
                        "binding": binding,
                        "preflight": None,
                        "error": None,
                    }
                )
        if result.candidates:
            result.ok = not result.errors
            result.status = "selection_required"
            changed_nox_topology = profile.preset_id == "windows.nox" and any(
                item["preset_id"] == "windows.nox"
                and profile.topology_fingerprint
                and item["binding"]["topology_fingerprint"]
                != profile.topology_fingerprint
                for item in result.candidates
            )
            if (
                len(result.candidates) == 1
                and not result.errors
                and not changed_nox_topology
            ):
                result.status = "discovered"
                result.selected_key = result.candidates[0]["key"]
            if result.errors:
                result.error = result.errors[0]
            elif changed_nox_topology:
                result.error = PreflightError(
                    "topology_changed",
                    "夜神 VM 拓扑已变化，请重新选择并确认实例。",
                    "select",
                )
            return result
        if result.errors:
            result.error = result.errors[0]
            return result
        if observations["installations"]:
            result.error = PreflightError(
                "no_avd" if is_avd else "instance_required",
                "SDK 未列出 AVD，请在 Android Studio Device Manager 中创建后重试。"
                if is_avd
                else "管理器未返回实例，请在多开管理器中创建实例后重新检测。",
            )
            return result
        result.error = PreflightError(
            "missing_installation",
            "未找到有效的模拟器安装，请选择产品并填写安装目录，或在高级设置指定管理程序。",
            fields=["installation_path"],
        )
        return result

    def _discover_linux(self, profile, preflight):
        """Offer the available Linux providers through the same instance selector."""
        presets = []
        if self._waydroid is not None:
            presets.append(WAYDROID_PRESET)
        if self._avd is not None:
            presets.append("linux.avd")
        if self._redroid is not None:
            presets.append(REDROID_PRESET)
        if self._genymotion is not None:
            presets.append(GENYMOTION_PRESET)
        result = DiscoveryResult("linux")
        missing = []
        # Providers run concurrently under this call's single six-second budget.
        operations = [
            (
                lambda preset=preset: self.discover(
                    profile.model_copy(update={"preset_id": preset}),
                    "linux",
                    preflight,
                )
            )
            for preset in presets
        ]
        for detected in _concurrent(operations):
            if detected is None:
                continue
            result.candidates.extend(detected.candidates)
            for error in detected.errors:
                if error.code in {
                    "missing_installation",
                    "missing_sdk",
                    "no_avd",
                    "no_redroid",
                    "no_genymotion",
                }:
                    missing.append(error)
                else:
                    result.errors.append(error)
        if not result.candidates:
            result.errors.extend(missing)
        result.ok = bool(result.candidates) and not result.errors
        if result.candidates:
            result.status = "selection_required"
            if len(result.candidates) == 1 and not result.errors:
                result.status = "discovered"
                result.selected_key = result.candidates[0]["key"]
        if result.errors:
            result.error = result.errors[0]
        if not result.candidates and missing:
            result.error = PreflightError(
                "missing_installation",
                "未发现可用的 Linux 环境，请选择产品并补充对应路径，或进入手动配置。",
                fields=["preset_id"],
            )
        return result

    def _discover_macos(self, profile, preflight):
        """Offer both primary products without silently preferring Air or AVD."""
        empty_binding = {
            "installation_path": "",
            "manager_path": "",
            "last_serial": "",
            "instance_id": "",
            "instance_name": "",
            "game_package_confirmed": False,
        }
        avd, air = _concurrent(
            (
                lambda: self.discover(
                    profile.model_copy(update={"preset_id": "macos.avd"}),
                    "macos",
                    preflight,
                ),
                lambda: self._air.check(
                    profile.model_copy(
                        update={**empty_binding, "preset_id": AIR_PRESET}
                    ),
                    preflight,
                ),
            )
        )
        if air is None:
            # A failed Air probe is not AVD's failure; keep its own result.
            return avd
        if not avd.candidates:
            return (
                avd if air.error and air.error.code == "missing_installation" else air
            )
        if air.ok:
            binding = {
                **air.profile_patch,
                "last_serial": "",
                "game_package_confirmed": False,
            }
            avd.candidates.append(
                {
                    **binding,
                    "key": sha256(
                        (AIR_PRESET + binding["installation_path"]).encode()
                    ).hexdigest(),
                    "state": "running",
                    "serial": "",
                    "binding": binding,
                    "preflight": None,
                    "error": None,
                }
            )
            avd.selected_key = None
            avd.status = "selection_required"
        elif air.error and air.error.code != "missing_installation":
            avd.ok = False
            avd.errors.append(air.error)
            avd.error = air.error
            avd.selected_key = None
            avd.status = "selection_required"
        return avd
