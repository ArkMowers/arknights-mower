"""Collapse sklearn recognition models into sklearn-free numpy dictionaries.

Run this in the development environment after retraining the source models:

    python scripts/collapse_recognition_models.py

The three files are verified against their sklearn predictors before they are
atomically replaced in place, so their existing runtime and packaging paths do
not change.
"""

import argparse
import lzma
import os
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arknights_mower.utils import vision_np  # noqa: E402

MODEL_NAMES = ("svm.model", "CONSUME.pkl", "NORMAL.pkl")


def load_model(path: Path):
    with lzma.open(path, "rb") as f:
        return pickle.load(f)


def collapse_svm(model) -> vision_np.LinearSvcModel:
    scaler = model.named_steps["standardscaler"]
    classifier = model.named_steps["linearsvc"]
    coefficient = classifier.coef_[0]
    weight = coefficient / scaler.scale_
    bias = classifier.intercept_[0] - np.sum(coefficient * scaler.mean_ / scaler.scale_)
    return {"w": weight, "b": float(bias)}


def collapse_knn(model) -> vision_np.Knn1Model:
    return {
        "X": np.asarray(model._fit_X, dtype=np.float32),
        "y": np.asarray(model._y),
        "classes": np.asarray(model.classes_),
    }


def verify_svm(source, collapsed: vision_np.LinearSvcModel) -> None:
    # 用生产预测函数校验，确保折叠结果在真正的调用路径上与 sklearn 一致。
    rng = np.random.default_rng(0)
    probes = rng.uniform(0, 1, (10_000, collapsed["w"].shape[0]))
    expected = source.predict(probes).astype(bool)
    actual = np.asarray(
        [
            vision_np.linear_svc_predict(probe, collapsed["w"], collapsed["b"])
            for probe in probes
        ]
    )
    np.testing.assert_array_equal(actual, expected)


def verify_knn(source, collapsed: vision_np.Knn1Model) -> None:
    rng = np.random.default_rng(0)
    random_probes = rng.uniform(0, 1, (100, collapsed["X"].shape[1]))
    probes = np.concatenate((source._fit_X, random_probes))
    expected = source.predict(probes)
    actual = np.asarray(
        [
            vision_np.knn1_predict(
                probe, collapsed["X"], collapsed["y"], collapsed["classes"]
            )
            for probe in probes
        ]
    )
    np.testing.assert_array_equal(actual, expected)


def dump_atomic(path: Path, model: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with lzma.open(temporary, "wb") as f:
            pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def collapse_models(models_dir: Path) -> None:
    paths = {name: models_dir / name for name in MODEL_NAMES}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing model files: {', '.join(missing)}")

    sources = {name: load_model(path) for name, path in paths.items()}
    collapsed = {}

    svm = sources["svm.model"]
    if isinstance(svm, dict):
        if set(svm) != {"w", "b"}:
            raise SystemExit("svm.model has an unknown dictionary schema.")
        print(f"Already collapsed: {paths['svm.model']}")
    else:
        collapsed["svm.model"] = collapse_svm(svm)
        verify_svm(svm, collapsed["svm.model"])

    for name in ("CONSUME.pkl", "NORMAL.pkl"):
        source = sources[name]
        if isinstance(source, dict):
            if set(source) != {"X", "y", "classes"}:
                raise SystemExit(f"{name} has an unknown dictionary schema.")
            print(f"Already collapsed: {paths[name]}")
            continue
        collapsed[name] = collapse_knn(source)
        verify_knn(source, collapsed[name])

    for name, model in collapsed.items():
        dump_atomic(paths[name], model)
        print(f"Collapsed {paths[name]} ({paths[name].stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "arknights_mower" / "models",
        help="directory containing svm.model, CONSUME.pkl, and NORMAL.pkl",
    )
    args = parser.parse_args()
    collapse_models(args.models_dir.resolve())


if __name__ == "__main__":
    main()
