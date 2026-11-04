"""Run configuration imports in a real model worker with an offline SDK seam."""

import importlib.abc
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace


class ModelLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        from arknights_mower.utils import config, path

        observed = {
            "conf_path": str(config.conf_path),
            "plan_path": str(config.plan_path),
            "instance": str(path.get_path("@app")),
            "internal": str(path.get_path("@internal")),
            "install": str(path.get_path("@install")),
            "disk_model": config.conf.ai_model,
        }

        def build_llm(api_key, **kwargs):
            assert api_key == "offline-instance-key"
            assert kwargs["max_retries"] == 0
            observed["runtime_model"] = config.conf.ai_model
            return SimpleNamespace(
                invoke=lambda _: SimpleNamespace(content=json.dumps(observed)),
                root_client=SimpleNamespace(close=lambda: None),
            )

        module.build_llm = build_llm


class ModelFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "arknights_mower.agent.agent":
            return importlib.util.spec_from_loader(fullname, ModelLoader())
        return None


def isolated_model(*args):
    finder = ModelFinder()
    sys.meta_path.insert(0, finder)
    try:
        from arknights_mower.agent.navigation_process import _model_worker

        _model_worker(*args)
    finally:
        sys.meta_path.remove(finder)


def main():
    root, space = Path(sys.argv[1]), sys.argv[2]
    os.environ["MOWER_DATA_DIR"] = str(root / "data")
    os.environ["MOWER_MANAGED"] = "0"
    os.chdir(root / "cwd")
    repository = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(repository))
    from arknights_mower.agent import navigation_process
    from arknights_mower.utils import path

    path._data_dir = root / "data"
    path._internal_dir = repository
    path._install_dir = repository
    path.global_space = space
    from arknights_mower.utils import config

    config.conf.ai_model = "runtime-instance-model"
    navigation_process._model_worker = isolated_model
    try:
        result = navigation_process.invoke_navigation_model("offline-instance-key", [])
        report = {"result": json.loads(result.content)}
    except Exception as error:
        report = {"error": str(error)}
    print(json.dumps(report))


if __name__ == "__main__":
    main()
