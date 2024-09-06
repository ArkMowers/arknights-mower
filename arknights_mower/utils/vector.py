from arknights_mower.utils import typealias as tp


def va(a: tp.Coordinate, b: tp.Coordinate) -> tp.Coordinate:
    """向量加法，vector add"""
    return a[0] + b[0], a[1] + b[1]


def vs(a: tp.Coordinate, b: tp.Coordinate) -> tp.Coordinate:
    """向量减法，vector subtract"""
    return a[0] - b[0], a[1] - b[1]


def sa(scope: tp.Scope, vector: tp.Coordinate) -> tp.Scope:
    """区域偏移，scope add"""
    return va(scope[0], vector), va(scope[1], vector)
