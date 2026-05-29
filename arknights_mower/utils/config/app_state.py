import json

from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path

STATE_FILE = get_path("@app/state.json")


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
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
