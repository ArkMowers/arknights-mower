from typing import Union

from arknights_mower import __rootdir__
from arknights_mower.utils import config
from arknights_mower.utils.device.adb_client.core import Client as ADBClient
from arknights_mower.utils.device.maatouch.command import CommandBuilder
from arknights_mower.utils.device.maatouch.session import Session
from arknights_mower.utils.log import logger

MNT_PATH = "/data/local/tmp/maatouch"


class Client:
    """Use maatouch to control Android devices easily"""

    def __init__(self, client: ADBClient) -> None:
        self.client = client
        self.start()

    def start(self) -> None:
        self.__install()

    def __del__(self) -> None:
        pass

    def __install(self) -> None:
        """install maatouch for android devices"""
        if self.__is_mnt_existed():
            logger.debug(f"maatouch already existed in {self.client.device_id}")
        else:
            self.__download_mnt()

    def __is_mnt_existed(self) -> bool:
        """check if maatouch is existed in the device"""
        file_list = self.client.cmd_shell("ls /data/local/tmp", True)
        return "maatouch" in file_list

    def __download_mnt(self) -> None:
        """download maatouch"""
        mnt_path = f"{__rootdir__}/vendor/maatouch/maatouch"

        # push and grant
        self.client.cmd_push(mnt_path, MNT_PATH)
        logger.info("maatouch already installed in {MNT_PATH}")

    def check_adb_alive(self) -> bool:
        """check if adb server alive"""
        return self.client.check_server_alive()

    def convert_coordinate(
        self,
        point: tuple[int, int],
        display_frames: tuple[int, int, int],
        max_x: int,
        max_y: int,
    ) -> tuple[int, int]:
        """
        check compatibility mode and convert coordinate
        see details: https://github.com/Konano/arknights-mower/issues/85
        """
        if not config.MNT_COMPATIBILITY_MODE:
            return point
        x, y = point
        w, h, r = display_frames
        if r == 1:
            return [(h - y) * max_x // h, x * max_y // w]
        if r == 3:
            return [y * max_x // h, (w - x) * max_y // w]
        logger.debug(
            f"warning: unexpected rotation parameter: display_frames({w}, {h}, {r})"
        )
        return point

    def tap(
        self,
        points: list[tuple[int, int]],
        display_frames: tuple[int, int, int],
        pressure: int = 100,
        duration: int = None,
        lift: bool = True,
    ) -> None:
        """
        tap on screen with pressure and duration

        :param points: list[int], look like [(x1, y1), (x2, y2), ...]
        :param display_frames: tuple[int, int, int], which means [weight, high, rotation] by "adb shell dumpsys window | grep DisplayFrames"
        :param pressure: default to 100
        :param duration: in milliseconds
        :param lift: if True, "lift" the touch point
        """
        self.check_adb_alive()

        builder = CommandBuilder()
        points = [list(map(int, point)) for point in points]
        with Session(self.client) as conn:
            for id, point in enumerate(points):
                x, y = self.convert_coordinate(
                    point, display_frames, int(conn.max_x), int(conn.max_y)
                )
                builder.down(id, x, y, pressure)
            builder.commit()

            if duration:
                builder.wait(duration)
                builder.commit()

            if lift:
                for id in range(len(points)):
                    builder.up(id)

            builder.publish(conn)

    def __swipe(
        self,
        points: list[tuple[int, int]],
        display_frames: tuple[int, int, int],
        pressure: int = 100,
        duration: Union[list[int], int] = None,
        up_wait: int = 0,
        fall: bool = True,
        lift: bool = True,
    ) -> None:
        """
        swipe between points one by one, with pressure and duration

        :param points: list, look like [(x1, y1), (x2, y2), ...]
        :param display_frames: tuple[int, int, int], which means [weight, high, rotation] by "adb shell dumpsys window | grep DisplayFrames"
        :param pressure: default to 100
        :param duration: in milliseconds
        :param up_wait: in milliseconds
        :param fall: if True, "fall" the first touch point
        :param lift: if True, "lift" the last touch point
        """
        self.check_adb_alive()

        points = [list(map(int, point)) for point in points]
        if not isinstance(duration, list):
            duration = [duration] * (len(points) - 1)
        assert len(duration) + 1 == len(points)

        builder = CommandBuilder()
        with Session(self.client) as conn:
            if fall:
                x, y = self.convert_coordinate(
                    points[0], display_frames, int(conn.max_x), int(conn.max_y)
                )
                builder.down(0, x, y, pressure)
                builder.publish(conn)

            for idx, point in enumerate(points[1:]):
                x, y = self.convert_coordinate(
                    point, display_frames, int(conn.max_x), int(conn.max_y)
                )
                builder.move(0, x, y, pressure)
                if duration[idx - 1]:
                    builder.wait(duration[idx - 1])
                builder.commit()
            builder.publish(conn)

            if lift:
                builder.up(0)
                if up_wait:
                    builder.wait(up_wait)
                builder.publish(conn)

    def swipe(
        self,
        points: list[tuple[int, int]],
        display_frames: tuple[int, int, int],
        pressure: int = 100,
        duration: Union[list[int], int] = None,
        up_wait: int = 0,
        part: int = 10,
        fall: bool = True,
        lift: bool = True,
    ) -> None:
        """
        swipe between points one by one, with pressure and duration
        it will split distance between points into pieces

        :param points: list, look like [(x1, y1), (x2, y2), ...]
        :param display_frames: tuple[int, int, int], which means [weight, high, rotation] by "adb shell dumpsys window | grep DisplayFrames"
        :param pressure: default to 100
        :param duration: in milliseconds
        :param up_wait: in milliseconds
        :param part: default to 10
        :param fall: if True, "fall" the first touch point
        :param lift: if True, "lift" the last touch point
        """
        points = [list(map(int, point)) for point in points]
        if not isinstance(duration, list):
            duration = [duration] * (len(points) - 1)
        assert len(duration) + 1 == len(points)

        new_points = [points[0]]
        new_duration = []
        for id in range(1, len(points)):
            pre_point = points[id - 1]
            cur_point = points[id]
            offset = (
                (cur_point[0] - pre_point[0]) // part,
                (cur_point[1] - pre_point[1]) // part,
            )
            new_points += [
                (pre_point[0] + i * offset[0], pre_point[1] + i * offset[1])
                for i in range(1, part + 1)
            ]
            if duration[id - 1] is None:
                new_duration += [None] * part
            else:
                new_duration += [duration[id - 1] // part] * part
        self.__swipe(
            new_points, display_frames, pressure, new_duration, up_wait, fall, lift
        )
