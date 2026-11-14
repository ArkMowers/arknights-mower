"""MuMu manager JSON shapes, explicit instance selection, and TCP endpoints."""

import ipaddress
import json
import re
import subprocess

from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    ManagerQueryTimeout,
)
from arknights_mower.utils.device.manager_io import MAX_INSTANCES, MAX_OUTPUT


def mumu_entries(output):
    if len(output.encode("utf-8") if isinstance(output, str) else output) > MAX_OUTPUT:
        raise ValueError("MuMu 管理器输出超过 1 MiB，请检查管理器后重试。")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("MuMu 管理器返回重复字段，无法确认实例身份。")
            result[key] = value
        return result

    try:
        payload = json.loads(output, object_pairs_hook=unique_object)
    except RecursionError as exc:
        raise ValueError("MuMu 管理器输出嵌套过深，无法确认实例信息。") from exc
    if isinstance(payload, dict) and "index" in payload:
        return [(str(payload["index"]), payload)]
    if isinstance(payload, dict):
        return list(payload.items())
    if isinstance(payload, list):
        return [
            (str(entry.get("index", "")), entry)
            if isinstance(entry, dict)
            else ("", entry)
            for entry in payload
        ]
    raise ValueError("MuMu 管理器没有返回有效的实例列表。")


def select_mumu_instance(output, instance_id, instance_name=""):
    """Require an explicit index or unique name; supplied identities must agree."""
    target = str(instance_id).strip() if instance_id is not None else ""
    name = instance_name or ""
    if not target and not name:
        raise ValueError("MuMu IPC 无法确认已选择实例：请选择实例索引或名称。")
    entries = mumu_entries(output)
    if len(entries) > MAX_INSTANCES:
        raise ValueError("MuMu 实例超过 64 个，请缩小检测范围。")
    matches = [
        (key, entry)
        for key, entry in entries
        if isinstance(entry, dict)
        and (key == target if target else entry.get("name") == name)
    ]
    if len(matches) != 1:
        raise ValueError("MuMu IPC 无法确认已选择实例。")
    key, entry = matches[0]
    if (
        not re.fullmatch(r"0|[1-9][0-9]*", key)
        or ("index" in entry and str(entry["index"]) != key)
        or (name and entry.get("name") != name)
        or entry.get("error_code", 0) != 0
    ):
        raise ValueError("MuMu 实例身份不一致，请重新查找并选择实例。")
    return key, entry


def mumu_endpoint(entry):
    port = entry.get("adb_port")
    if (
        isinstance(port, bool)
        or not re.fullmatch(r"[0-9]{1,5}", str(port))
        or not 0 < int(port) < 65536
    ):
        raise ValueError("MuMu 实例没有有效 ADB 端口。")
    host = entry.get("adb_host_ip") or "127.0.0.1"
    host = "127.0.0.1" if host == "localhost" else str(ipaddress.ip_address(host))
    return f"[{host}]:{int(port)}" if ":" in host else f"{host}:{int(port)}"


def normalize_mumu_endpoint(serial):
    host, port = serial.rsplit(":", 1)
    host = host.strip("[]")
    if host != "localhost":
        host = str(ipaddress.ip_address(host))
    if host in {"localhost", "127.0.0.1", "::1"}:
        host = "127.0.0.1"
    return host, int(port)


def mumu_created_timestamp(entry):
    value = entry.get("created_timestamp")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    value = str(value)
    if (
        not value.isascii()
        or not value.isdecimal()
        or len(value) > 20
        or int(value) <= 0
    ):
        return ""
    return str(int(value))


def verify_mumu_created_timestamp(entry, instance_id, expected):
    created = mumu_created_timestamp(entry)
    if expected and created != expected:
        raise InstanceBindingError(
            "binding_changed",
            f"MuMu 实例 {instance_id} 的创建时间已变化或无法读取，请重新选择实例并确认地址。",
            ["instance_id", "instance_name"],
        )
    return created


class MuMuEndpointUnavailable(InstanceBindingError):
    def __init__(self, instance_id, detail=""):
        super().__init__(
            "mumu_endpoint_unavailable",
            f"无法确认 MuMu 实例 {instance_id} 的 ADB 端口或连接地址。"
            f"{detail}"
            "请检查 MuMu 的 ADB 端口及管理程序配置后重新检测；"
            "也可选择实例后手动填写地址。手动地址无法自动核验归属，不能使用 MuMu IPC。",
            ["manager_path", "mumu_manual_serial"],
        )


def _parse_mumu_address(output):
    if isinstance(output, bytes):
        output = output.decode("utf-8")
    if len(output) > 512:
        raise ValueError("MuMu ADB 地址输出过长")
    match = re.fullmatch(r"(\[[^\]\r\n]+\]|[^:\s]+):([0-9]{1,5})", output.strip())
    if not match:
        raise ValueError("MuMu ADB 地址输出无效")
    return mumu_endpoint(
        {"adb_host_ip": match.group(1).strip("[]"), "adb_port": match.group(2)}
    )


def validate_mumu_manual_serial(manual_serial, instance_id):
    if not manual_serial:
        return ""
    try:
        return _parse_mumu_address(manual_serial)
    except (ValueError, TypeError) as exc:
        raise MuMuEndpointUnavailable(instance_id, "手动填写的地址无效。") from exc


def mumu_endpoint_with_fallback(
    entry, instance_id, manager, run, manual_serial="", *, verify_conflicts=False
):
    """返回所选实例的地址和已核验的创建时间，手动地址只作为最后选择。"""
    manual_endpoint = validate_mumu_manual_serial(manual_serial, instance_id)

    def require_manual_match(endpoint):
        if manual_endpoint and normalize_mumu_endpoint(
            endpoint
        ) != normalize_mumu_endpoint(manual_endpoint):
            raise MuMuEndpointUnavailable(
                instance_id, "手动地址与管理器报告的地址不一致。"
            )
        return endpoint

    port = entry.get("adb_port")
    missing = not isinstance(port, bool) and port in (None, "", 0, "0")
    if not missing:
        try:
            endpoint = require_manual_match(mumu_endpoint(entry))
        except MuMuEndpointUnavailable:
            raise
        except (ValueError, TypeError) as exc:
            raise MuMuEndpointUnavailable(instance_id) from exc
        if not manual_endpoint and not verify_conflicts:
            return endpoint, mumu_created_timestamp(entry)
    else:
        if (
            entry.get("is_process_started") is not True
            or entry.get("is_android_started") is not True
        ):
            raise MuMuEndpointUnavailable(instance_id)
        if run is None:
            raise MuMuEndpointUnavailable(instance_id)
        try:
            endpoint = _parse_mumu_address(run([manager, "adb", "-v", instance_id]))
        except ManagerQueryTimeout:
            raise
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise ManagerQueryTimeout("MuMu 管理程序查询超时，请稍后重试。") from exc
        except (
            ValueError,
            UnicodeError,
            subprocess.SubprocessError,
            FileNotFoundError,
            PermissionError,
            RuntimeError,
        ) as exc:
            if not manual_endpoint:
                raise MuMuEndpointUnavailable(instance_id) from exc
            endpoint = manual_endpoint
        else:
            endpoint = require_manual_match(endpoint)

    if run is None:
        raise MuMuEndpointUnavailable(instance_id)

    # The index can be reused while the query runs. Re-read the inventory before
    # trusting this address, and reject an address already reported by another VM.
    try:
        fresh_output = run([manager, "info", "-v", "all"])
        _, fresh = select_mumu_instance(
            fresh_output, instance_id, entry.get("name", "")
        )
        if (
            any(
                key in entry and fresh.get(key) != entry[key]
                for key in ("name", "created_timestamp", "pid", "headless_pid")
            )
            or fresh.get("is_process_started") is not True
            or fresh.get("is_android_started") is not True
        ):
            raise ValueError("实例身份或运行状态发生变化")
        if fresh.get("adb_port"):
            try:
                fresh_endpoint = mumu_endpoint(fresh)
            except (ValueError, TypeError) as exc:
                raise MuMuEndpointUnavailable(
                    instance_id, "管理器返回的端口无效。"
                ) from exc
            if normalize_mumu_endpoint(fresh_endpoint) != normalize_mumu_endpoint(
                endpoint
            ):
                raise MuMuEndpointUnavailable(instance_id, "管理器返回了不同的端口。")
        for key, other in mumu_entries(fresh_output):
            if key == instance_id or not isinstance(other, dict):
                continue
            if other.get("is_process_started") is not True or not other.get("adb_port"):
                continue
            try:
                other_endpoint = mumu_endpoint(other)
            except (ValueError, TypeError):
                continue
            if normalize_mumu_endpoint(other_endpoint) == normalize_mumu_endpoint(
                endpoint
            ):
                raise MuMuEndpointUnavailable(
                    instance_id, "该端口同时被其他运行中的实例报告。"
                )
    except ManagerQueryTimeout:
        raise
    except (TimeoutError, subprocess.TimeoutExpired) as exc:
        raise ManagerQueryTimeout("MuMu 管理程序查询超时，请稍后重试。") from exc
    except InstanceBindingError:
        raise
    except (ValueError, TypeError) as exc:
        raise InstanceBindingError(
            "binding_changed",
            f"无法确认 MuMu 实例 {instance_id} 的身份或端口，请重新检测并选择实例：{exc}",
            ["instance_id", "instance_name", "last_serial"],
        ) from exc
    except (
        subprocess.SubprocessError,
        FileNotFoundError,
        PermissionError,
        RuntimeError,
    ) as exc:
        raise MuMuEndpointUnavailable(instance_id) from exc
    return endpoint, mumu_created_timestamp(fresh)
