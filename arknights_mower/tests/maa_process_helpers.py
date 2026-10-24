"""Replace only the subprocess boundary in focused scheduler tests."""

import importlib
from pathlib import Path

from arknights_mower.utils.maa_runtime import resource_load_error


def fake_sdk_worker(target, callback):
    target = Path(target)
    asst_type = importlib.import_module("asst.asst").Asst
    if not asst_type.load(path=target, incremental_path=target / "cache"):
        raise resource_load_error(target)
    instance = asst_type(callback=callback)
    instance.instance_options = importlib.import_module("asst.utils").InstanceOptionType
    return instance
