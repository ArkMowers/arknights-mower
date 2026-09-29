"""MuMu manager JSON shapes, explicit instance selection, and TCP endpoints."""

import ipaddress
import json
import re

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
