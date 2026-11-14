"""Replace only the subprocess boundary in focused scheduler tests."""

import importlib
from pathlib import Path

from arknights_mower.utils.maa_runtime import resource_load_error
from arknights_mower.utils.maa_storage import load_options


def fake_sdk_worker(target, callback):
    target = Path(target)
    asst_type = importlib.import_module("asst.asst").Asst
    if not asst_type.load(**load_options(target)):
        raise resource_load_error(target)
    instance = asst_type(callback=callback)
    instance.instance_options = importlib.import_module("asst.utils").InstanceOptionType
    return instance
