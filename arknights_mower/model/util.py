from pathlib import Path
from typing import Optional


def from_old_str_to_list(value: list[str] | str) -> list[str]:
    if isinstance(value, str):
        return value.replace("，", ",").split(",")
    return value


def from_str_to_path(value: str | Path | None) -> Optional[Path]:
    if isinstance(value, str):
        return Path(value)
    return value


def empty_str_to_none(value: str) -> Optional[str]:
    if value == "":
        return None
    return value
