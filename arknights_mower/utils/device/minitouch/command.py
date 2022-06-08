from __future__ import annotations

import time

from ...log import logger
from .session import Session

DEFAULT_DELAY = 0.05


class CommandBuilder(object):
    """ Build command str for minitouch """

    def __init__(self) -> None:
        self.content = ''
        self.delay = 0

    def append(self, new_content: str) -> None:
        self.content += new_content + '\n'

    def commit(self) -> None:
        """ add minitouch command: 'c\n' """
        self.append('c')

    def wait(self, ms: int) -> None:
        """ add minitouch command: 'w <ms>\n' """
        self.append(f'w {ms}')
        self.delay += ms

    def up(self, contact_id: int) -> None:
        """ add minitouch command: 'u <contact_id>\n' """
        self.append(f'u {contact_id}')

    def down(self, contact_id: int, x: int, y: int, pressure: int) -> None:
        """ add minitouch command: 'd <contact_id> <x> <y> <pressure>\n' """
        self.append(f'd {contact_id} {x} {y} {pressure}')

    def move(self, contact_id: int, x: int, y: int, pressure: int) -> None:
        """ add minitouch command: 'm <contact_id> <x> <y> <pressure>\n' """
        self.append(f'm {contact_id} {x} {y} {pressure}')

    def publish(self, session: Session):
        """ apply current commands to device """
        self.commit()
        logger.debug('send operation: %s' % self.content.replace('\n', '\\n'))
        session.send(self.content)
        time.sleep(self.delay / 1000 + DEFAULT_DELAY)
        self.reset()

    def reset(self):
        """ clear current commands """
        self.content = ''
