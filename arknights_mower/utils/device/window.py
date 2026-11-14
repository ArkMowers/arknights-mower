"""Simulator window control and boss key invocation."""

import threading
import time

from arknights_mower.utils.log import logger


def parse_hotkey_keys(hotkey: str) -> list[str]:
    """Parse hotkey string like 'ctrl+alt+w' or 'alt+q' into a normalized key list."""
    if not hotkey or not isinstance(hotkey, str):
        return []
    raw = hotkey.replace(";", "+").replace(",", "+")
    keys = []
    alias_map = {
        "control": "ctrl",
        "command": "command",
        "cmd": "command",
        "windows": "win",
        "winleft": "win",
        "winright": "win",
    }
    for piece in raw.split("+"):
        k = piece.strip().lower()
        if k:
            keys.append(alias_map.get(k, k))
    return keys


def trigger_simulator_boss_key(hotkey: str | None = None, delay: float = 0.0) -> dict:
    """Trigger simulator boss key shortcut via PyAutoGUI.

    Supports optional delayed execution to allow the emulator process window to initialize.
    """
    keys = parse_hotkey_keys(hotkey or "")
    if not keys:
        return {"ok": False, "message": "未配置有效的模拟器老板键快捷键"}

    def _execute():
        if delay > 0:
            time.sleep(delay)
        try:
            import pyautogui

            hotkey_repr = "+".join(keys)
            pyautogui.hotkey(*keys)
            # The line reports the keystroke only after it was sent: a message
            # printed before the call claims an action that may still fail.
            logger.info(f"已触发模拟器老板键（{hotkey_repr}）")
            return {"ok": True, "message": f"已触发模拟器老板键（{hotkey_repr}）"}
        except Exception as exc:
            logger.warning(f"触发模拟器老板键失败：{exc}")
            return {"ok": False, "message": f"触发模拟器老板键失败：{exc}"}

    if delay > 0:
        threading.Thread(target=_execute, daemon=True, name="mower-boss-key").start()
        return {"ok": True, "message": f"已安排触发模拟器老板键（{'+'.join(keys)}）"}

    return _execute()
