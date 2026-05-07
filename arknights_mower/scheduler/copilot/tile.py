class TileSystem:
    def __init__(self, stage_name: str, layout: dict | None = None) -> None:
        self._stage_name = stage_name
        self._layout = layout or {}

    def tile_to_pixel(self, row: int, col: int) -> tuple[float, float]:
        if self._layout:
            x = self._layout.get("base_x", 0) + col * self._layout.get("tile_w", 128)
            y = self._layout.get("base_y", 0) + row * self._layout.get("tile_h", 128)
            return (x / 1920, y / 1080)
        return (0.0, 0.0)

    def pixel_to_tile(self, x: float, y: float) -> tuple[int, int]:
        px, py = int(x * 1920), int(y * 1080)
        row = (py - self._layout.get("base_y", 0)) // self._layout.get("tile_h", 128)
        col = (px - self._layout.get("base_x", 0)) // self._layout.get("tile_w", 128)
        return (row, col)
