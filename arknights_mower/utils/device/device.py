from typing import Union

from .client import Client
from .minitouch import MiniTouch
from ..log import logger


class Device(object):
    """ Android Device """

    def __init__(self, device_id: str = None, connect: str = None) -> None:
        self.device_id = device_id
        self.connect = connect
        self.client = None
        self.minitouch = None
        self.start()

    def start(self) -> None:
        self.client = Client(self.device_id, self.connect)
        self.minitouch = MiniTouch(self.client)

    def run(self, cmd: str) -> Union[None, bytes]:
        return self.client.run(cmd)

    def launch(self, app) -> None:
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

    def screencap(self) -> bytes:
        """ get a screencap """
        command = 'screencap -p'
        return self.run(command)

    def current_focus(self) -> str:
        """ detect current focus app """
        command = 'dumpsys window | grep mCurrentFocus'
        line = self.run(command).decode('utf8')
        return line.strip()[:-1].split(' ')[-1]

    def tap(self) -> None:
        """ tap """
        raise NotImplementedError  # TODO

    def swipe(self) -> None:
        """ swipe """
        raise NotImplementedError  # TODO
