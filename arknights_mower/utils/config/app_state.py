import json

from arknights_mower.utils.config import app_state_path, atomic_write
from arknights_mower.utils.log import logger

STATE_FILE = app_state_path


def read_app_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception as exc:
        logger.error("failed to read state.json: %s", exc)
        return {}
    if isinstance(data, dict):
        return data
    logger.error("state.json root is not an object, ignore invalid content")
    return {}


def write_app_state(data: dict):
    def dump(file):
        json.dump(data, file, ensure_ascii=False, indent=2)

    atomic_write(STATE_FILE, dump)
