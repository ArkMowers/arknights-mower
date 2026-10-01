"""Strict observations shared by vendor-to-ADB identity checks."""

import os
import re
import subprocess

from arknights_mower.utils.device.adb_client.server import (
    adb_subprocess_options,
    emulator_connect_target,
    run_adb,
)
from arknights_mower.utils.device.manager_io import MAX_OUTPUT

BOOT_ID_COMMAND = "shell cat /proc/sys/kernel/random/boot_id"
AVD_PRESETS = frozenset({"macos.avd", "linux.avd"})
CONFIRMED_START_PRESETS = AVD_PRESETS | {"linux.redroid", "linux.genymotion"}
VERIFIED_ENDPOINT_PRESETS = (
    frozenset(
        {
            "windows.ldplayer9",
            "windows.ldplayer14",
            "windows.nox",
            "windows.bluestacks5",
            "macos.mumu_pro",
            "linux.waydroid",
        }
    )
    | CONFIRMED_START_PRESETS
)


class InstanceBindingError(ValueError):
    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = ["last_serial"] if fields is None else fields


class InstanceEndpointPending(InstanceBindingError):
    """VM identity is confirmed; no endpoint is yet safe to connect or recover."""


def run_endpoint_command(
    argv, *, timeout, run, probe, monotonic, adb=False, delegated_adb=False
):
    """One bounded command; callers own the complete verification deadline."""
    options = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=min(3, timeout),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if adb:
        result = run_adb(argv, run=run, probe=probe, monotonic=monotonic, **options)
    else:
        if delegated_adb:
            options.update(adb_subprocess_options())
        result = run(argv, **options)
    result.check_returncode()
    output, error = result.stdout, result.stderr or b""
    if isinstance(output, str):
        output = output.encode("utf-8")
    if isinstance(error, str):
        error = error.encode("utf-8")
    if len(output) + len(error) > MAX_OUTPUT:
        raise ValueError("实例验证输出超过 1 MiB。")
    if error.strip():
        raise ValueError(error.decode("utf-8", "replace").strip())
    return output


def parse_boot_id(output):
    text = output.decode("ascii", "replace").strip().lower()
    if re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", text):
        if text != "00000000-0000-0000-0000-000000000000":
            return text
    return None


def connect_endpoint_candidates(adb_path, candidates, command):
    """Register only supplied instance candidates; boot identity confirms them."""
    for serial in dict.fromkeys(candidate for candidate in candidates if candidate):
        endpoint = emulator_connect_target(serial)
        if endpoint is None:
            address = re.fullmatch(r"(?:\[[^\]\s]+\]|[^:\s]+):([0-9]+)", serial)
            if address is None or not 0 < int(address[1]) < 65536:
                continue
            endpoint = serial
        try:
            command([adb_path, "connect", endpoint], adb=True)
        except subprocess.CalledProcessError:
            continue


def parse_adb_devices(output):
    try:
        lines = output.decode("utf-8", "strict").splitlines()
    except UnicodeDecodeError as exc:
        raise InstanceBindingError(
            "endpoint_unresolved", "ADB 设备列表编码异常"
        ) from exc
    if not lines or lines[0].strip() != "List of devices attached":
        raise InstanceBindingError(
            "endpoint_unresolved", "所选 ADB 没有返回有效设备列表"
        )
    rows = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) < 2:
            raise InstanceBindingError("endpoint_unresolved", "ADB 设备列表格式异常")
        rows.setdefault(fields[0], []).append(fields[1])
    return rows
