from __future__ import annotations

import time
from typing import Optional

from .client import Client
from .minitouch import MiniTouch
from .utils import config
from ..log import logger, save_screenshot


class Device(object):
    """ Android Device """

    def __init__(self, device_id: str = None, connect: str = None, touch_device: str = None) -> None:
        self.device_id = device_id
        self.connect = connect
        self.touch_device = touch_device
        self.client = None
        self.minitouch = None
        self.start()

    def start(self) -> None:
        self.client = Client(self.device_id, self.connect)
        self.minitouch = MiniTouch(self.client, self.touch_device)

    def run(self, cmd: str) -> Optional[bytes]:
        return self.client.run(cmd)

    def launch(self, app: str) -> None:
        """ launch the application """
        self.run(f'am start -n {app}')

    def send_keyevent(self, keycode: int) -> None:
        """ send a key event """
        logger.debug(f'keyevent: {keycode}')
        command = f'input keyevent {keycode}'
        self.run(command)

    def send_text(self, text: str) -> None:
        """ send a text """
        logger.debug(f'text: {repr(text)}')
        text = text.replace('"', '\\"')
        command = f'input text "{text}"'
        self.run(command)

    def screencap(self, save: bool = False) -> bytes:
        """ get a screencap """
        command = 'screencap -p'
        screencap = self.run(command)
        if save:
            save_screenshot(screencap)
        return screencap

    def current_focus(self) -> str:
        """ detect current focus app """
        command = 'dumpsys window | grep mCurrentFocus'
        line = self.run(command).decode('utf8')
        return line.strip()[:-1].split(' ')[-1]

    def display_frames(self) -> tuple[int, int, int]:
        """ get display frames if in compatibility mode"""
        if not config.COMPATIBILITY_MODE:
            return None

        command = 'dumpsys window | grep DisplayFrames'
        line = self.run(command).decode('utf8')
        """ eg. DisplayFrames w=1920 h=1080 r=3 """
        res = line.strip().replace('=', ' ').split(' ')
        return int(res[2]), int(res[4]), int(res[6])

    def tap(self, point: tuple[int, int]) -> None:
        """ tap """
        logger.debug(f'tap: {point}')
        self.minitouch.tap([point], self.display_frames())

    def swipe(self, points: list[tuple[int, int]], duration: int = 100, part: int = 10, fall: bool = True, lift: bool = True) -> None:
        """ swipe """
        logger.debug(f'swipe: {points}')
        points_num = len(points)
        duration //= points_num - 1
        self.minitouch.smooth_swipe(points, self.display_frames(), duration=duration, part=part, fall=fall, lift=lift)

    def check_current_focus(self):
        """ check if the application is in the foreground """
        if self.current_focus() != config.APPNAME:
            self.launch(config.APPNAME)
            # wait for app to finish launching
            time.sleep(10)
