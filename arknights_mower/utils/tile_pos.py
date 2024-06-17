import lzma
import math
import pickle
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np
import numpy.typing as npt

from arknights_mower import __rootdir__


@dataclass
class Tile:
    heightType: int
    buildableType: int


@dataclass
class Vector3:
    x: float
    y: float
    z: float

    def clone(self) -> "Vector3":
        return Vector3(self.x, self.y, self.z)


@dataclass
class Vector2:
    x: float
    y: float

    def clone(self) -> "Vector2":
        return Vector2(self.x, self.y)


@dataclass
class Level:
    stageId: str
    code: str
    levelId: str
    name: str
    height: int
    width: int
    tiles: List[List[Tile]] = None
    view: List[List[int]] = None

    @classmethod
    def from_json(cls, json_data: dict[Any, Any]) -> "Level":
        raw_tiles = json_data["tiles"]
        tiles = []
        for row in raw_tiles:
            row_tiles = []
            for tile in row:
                row_tiles.append(Tile(tile["heightType"], tile["buildableType"]))
            tiles.append(row_tiles)

        return cls(
            stageId=json_data["stageId"],
            code=json_data["code"],
            levelId=json_data["levelId"],
            name=json_data["name"],
            height=json_data["height"],
            width=json_data["width"],
            tiles=tiles,
            view=json_data["view"],
        )

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height

    def get_tile(self, row: int, col: int) -> Optional[Tile]:
        if 0 <= row <= self.height and 0 <= col <= self.width:
            return self.tiles[row][col]
        return None


class Calc:
    screen_width: int
    screen_height: int
    ratio: float

    view: Vector3
    view_side: Vector3
    level: Level

    matrix_p: npt.NDArray[np.float32]
    matrix_x: npt.NDArray[np.float32]
    matrix_y: npt.NDArray[np.float32]

    def __init__(self, screen_width: int, screen_height: int, level: Level):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.ratio = screen_height / screen_width
        self.level = level
        self.matrix_p = np.array(
            [
                [self.ratio / math.tan(math.pi * 20 / 180), 0, 0, 0],
                [0, 1 / math.tan(math.pi * 20 / 180), 0, 0],
                [0, 0, -(1000 + 0.3) / (1000 - 0.3), -(1000 * 0.3 * 2) / (1000 - 0.3)],
                [0, 0, -1, 0],
            ]
        )
        self.matrix_x = np.array(
            [
                [1, 0, 0, 0],
                [0, math.cos(math.pi * 30 / 180), -math.sin(math.pi * 30 / 180), 0],
                [0, -math.sin(math.pi * 30 / 180), -math.cos(math.pi * 30 / 180), 0],
                [0, 0, 0, 1],
            ]
        )
        self.matrix_y = np.array(
            [
                [math.cos(math.pi * 10 / 180), 0, math.sin(math.pi * 10 / 180), 0],
                [0, 1, 0, 0],
                [-math.sin(math.pi * 10 / 180), 0, math.cos(math.pi * 10 / 180), 0],
                [0, 0, 0, 1],
            ]
        )
        self.view = Vector3(level.view[0][0], level.view[0][1], level.view[0][2])
        self.view_side = Vector3(level.view[1][0], level.view[1][1], level.view[1][2])

    def adapter(self) -> Tuple[float, float]:
        fromRatio = 9 / 16
        toRatio = 3 / 4
        if self.ratio < fromRatio - 0.00001:
            return 0, 0
        t = (self.ratio - fromRatio) / (toRatio - fromRatio)
        return -1.4 * t, -2.8 * t

    def get_focus_offset(self, tile_x: int, tile_y: int) -> Vector3:
        x = tile_x - (self.level.width - 1) / 2
        y = (self.level.height - 1) / 2 - tile_y
        return Vector3(x, y, 0)

    def get_character_world_pos(self, tile_x: int, tile_y: int) -> Vector3:
        x = tile_x - (self.level.width - 1) / 2
        y = (self.level.height - 1) / 2 - tile_y
        tile = self.level.get_tile(tile_y, tile_x)
        assert tile is not None
        z = tile.heightType * -0.4
        return Vector3(x, y, z)

    def get_with_draw_world_pos(self, tile_x: int, tile_y: int) -> Vector3:
        ret = self.get_character_world_pos(tile_x, tile_y)
        ret.x -= 1.3143386840820312
        ret.y += 1.314337134361267
        ret.z = -0.3967874050140381
        return ret

    def get_skill_world_pos(self, tile_x: int, tile_y: int) -> Vector3:
        ret = self.get_character_world_pos(tile_x, tile_y)
        ret.x += 1.3143386840820312
        ret.y -= 1.314337134361267
        ret.z = -0.3967874050140381
        return ret

    def get_character_screen_pos(
        self, tile_x: int, tile_y: int, side: bool = False, focus: bool = False
    ) -> Vector2:
        if focus:
            side = True
        world_pos = self.get_character_world_pos(tile_x, tile_y)
        if focus:
            offset = self.get_focus_offset(tile_x, tile_y)
        else:
            offset = Vector3(0.0, 0.0, 0.0)
        return self.world_to_screen_pos(world_pos, side, offset)

    def get_with_draw_screen_pos(self, tile_x: int, tile_y: int) -> Vector2:
        world_pos = self.get_with_draw_world_pos(tile_x, tile_y)
        offset = self.get_focus_offset(tile_x, tile_y)
        return self.world_to_screen_pos(world_pos, True, offset)

    def get_skill_screen_pos(self, tile_x: int, tile_y: int) -> Vector2:
        world_pos = self.get_skill_world_pos(tile_x, tile_y)
        offset = self.get_focus_offset(tile_x, tile_y)
        return self.world_to_screen_pos(world_pos, True, offset)

    def world_to_screen_matrix(
        self, side: bool = False, offset: Optional[Vector3] = None
    ) -> npt.NDArray[np.float32]:
        if offset is None:
            offset = Vector3(0.0, 0.0, 0.0)
        adapter_y, adapter_z = self.adapter()
        if side:
            x, y, z = self.view_side.x, self.view_side.y, self.view_side.z
        else:
            x, y, z = self.view.x, self.view.y, self.view.z
        x += offset.x
        y += offset.y + adapter_y
        z += offset.z + adapter_z
        raw = np.array(
            [
                [1, 0, 0, -x],
                [0, 1, 0, -y],
                [0, 0, 1, -z],
                [0, 0, 0, 1],
            ],
            np.float32,
        )
        if side:
            matrix = np.dot(self.matrix_x, self.matrix_y)
            matrix = np.dot(matrix, raw)
        else:
            matrix = np.dot(self.matrix_x, raw)
        return np.dot(self.matrix_p, matrix)

    def world_to_screen_pos(
        self, pos: Vector3, side: bool = False, offset: Optional[Vector3] = None
    ) -> Vector2:
        matrix = self.world_to_screen_matrix(side, offset)
        x, y, _, w = np.dot(matrix, np.array([pos.x, pos.y, pos.z, 1]))
        x = (1 + x / w) / 2
        y = (1 + y / w) / 2
        return Vector2(x * self.screen_width, (1 - y) * self.screen_height)


LEVELS: List[Level] = []
with lzma.open(f"{__rootdir__}/models/levels.pkl", "rb") as f:
    level_table = pickle.load(f)
for data in level_table:
    LEVELS.append(Level.from_json(data))


def find_level(code: Optional[str], name: Optional[str]) -> Optional[Level]:
    for level in LEVELS:
        if code is not None and code == level.code:
            return level
        if name is not None and name == level.name:
            return level
    return None
