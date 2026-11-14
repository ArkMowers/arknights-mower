"""Bounded I/O for serial-scoped preparation of only the default display size."""

import os
import re
import subprocess

from arknights_mower.utils.device.adb_client.server import run_adb
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.preflight_io import ProductionPreflightIO


def _input_surface(output: str) -> tuple[int, int]:
    """Accept matching default viewports in AOSP native and Java dumps.

    InputReader may repeat the same viewport for several input devices. An
    unknown format or conflicting default viewport cannot establish safe input.
    """
    frames = set()
    for line in output.splitlines():
        if not re.search(r"\b(?:DisplayViewport\{|Viewport\s+\w+:)", line):
            continue
        display_ids = re.findall(r"\bdisplayId=([^,}\s]+)", line)
        if "0" not in display_ids:
            continue
        if display_ids != ["0"]:
            raise ValueError("默认显示器的输入面标识不唯一")
        if "DisplayViewport{" in line:
            if re.findall(r"\btype=([^,}\s]+)", line) != ["INTERNAL"] or re.findall(
                r"\bvalid=([^,}\s]+)", line
            ) != ["true"]:
                raise ValueError("默认显示器的输入面无效")
            pattern = (
                r"logicalFrame=Rect\((-?\d+),\s*(-?\d+)\s*-\s*(-?\d+),\s*(-?\d+)\)"
            )
        else:
            if "Viewport INTERNAL:" not in line:
                raise ValueError("无法确认默认显示器的实体输入面")
            pattern = r"logicalFrame=\[(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\]"
        active = re.findall(r"\bisActive=([^,}\s]+)", line)
        if active and active not in (["true"], ["[1]"]):
            raise ValueError("默认显示器的输入面未激活")
        matches = re.findall(pattern, line)
        if len(matches) != 1 or len(re.findall(r"\blogicalFrame=", line)) != 1:
            raise ValueError("无法读取默认显示器的输入面尺寸")
        left, top, right, bottom = map(int, matches[0])
        if left != 0 or top != 0 or right <= 0 or bottom <= 0:
            raise ValueError("默认显示器的输入面不符合原点与尺寸要求")
        frames.add((right, bottom))
    if len(frames) != 1:
        raise ValueError("无法唯一确认默认显示器的输入面")
    return frames.pop()


class ProductionPreparationIO:
    def __init__(self, *, preflight=None, run=None, probe=None):
        self._preflight = preflight or ProductionPreflightIO()
        self._run = run
        self._probe = probe

    def devices(self, adb_path: str, serial: str) -> list[tuple[str, str]]:
        return self._preflight.devices(adb_path, serial)

    def display_size(self, adb_path: str, serial: str) -> str:
        return self._preflight.display_size(adb_path, serial)

    def _adb(self, adb_path: str, serial: str, args: list[str]) -> str:
        if not adb_path.strip() or not serial.strip():
            raise ValueError("临时整备要求明确的 ADB 程序和设备 serial")
        result = run_adb(
            [adb_path, "-s", serial, *args],
            run=self._run,
            probe=self._probe,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=io_timeout(10),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        result.check_returncode()
        if result.stderr.strip():
            raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
        return result.stdout.decode("utf-8", "replace").strip()

    def set_size(self, adb_path: str, serial: str, value: list[int] | None) -> None:
        if value is None:
            argument = "reset"
        elif (
            isinstance(value, list)
            and len(value) == 2
            and all(type(item) is int and item > 0 for item in value)
        ):
            argument = f"{value[0]}x{value[1]}"
        else:
            raise ValueError("临时整备尺寸必须是两个正整数或 reset")
        output = self._adb(adb_path, serial, ["shell", "wm", "size", argument])
        if output:
            raise RuntimeError(f"设备未确认尺寸写入：{output}")

    def input_surface(self, adb_path: str, serial: str) -> tuple[int, int]:
        return _input_surface(
            self._adb(adb_path, serial, ["shell", "dumpsys", "input"])
        )
