from __future__ import annotations

import platform
import subprocess
import traceback

from arknights_mower.utils.device.adb_client import ADBClient

from ...log import logger


class Session(object):
    def __init__(self, client: ADBClient) -> None:
        try:
            self.process = subprocess.Popen(
                [
                    client.adb_bin,
                    "shell",
                    "CLASSPATH=/data/local/tmp/maatouch",
                    "app_process",
                    "/",
                    "com.shxyke.MaaTouch.App",
                ],
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
                if platform.system() == "Windows"
                else 0,
            )
            output_line = self.process.stdout.readline()
            logger.debug("maatouch output line 1: " + output_line.replace("\n", "\\n"))
            # ^ <max-contacts> <max-x> <max-y> <max-pressure>
            _, max_contacts, max_x, max_y, max_pressure, *_ = output_line.strip().split(
                " "
            )
            self.max_contacts = max_contacts
            self.max_x = max_x
            self.max_y = max_y
            self.max_pressure = max_pressure

            output_line = self.process.stdout.readline()
            logger.debug("maatouch output line 2: " + output_line.replace("\n", "\\n"))
            # $ <pid>
            _, pid = output_line.strip().split(" ")
            self.pid = pid
        except Exception:
            logger.error(traceback.format_exc())

        logger.debug(f"maatouch running, pid: {self.pid}")
        logger.debug(
            f"max_contact: {max_contacts}; max_x: {max_x}; max_y: {max_y}; max_pressure: {max_pressure}"
        )

    def __enter__(self) -> Session:
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.process.terminate()

    def send(self, content: str):
        self.process.stdin.write(content)
        self.process.stdin.flush()
