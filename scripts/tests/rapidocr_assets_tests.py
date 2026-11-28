import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

import build_assets

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_FILES = (
    "config.yaml",
    "default_models.yaml",
    "models/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
)
TINY_HASHES = {
    "PP-OCRv6_det_tiny.onnx": (
        1829618,
        "f42c0fbd294d95eac1a550e131b277dac97462c8025fa4b6c3cec1b7894bd3d5",
    ),
    "PP-OCRv6_rec_tiny.onnx": (
        4489813,
        "e16e242de5937ad92609223f19bc2aff3727ee40b095f996907c24749bad251b",
    ),
}


class RapidOCRAssetsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sdk_dir = self.root / "rapidocr"
        for relative in (*SDK_FILES, "models/PP-OCRv6_det_small.onnx"):
            path = self.sdk_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"asset")
        sdk = ModuleType("rapidocr")
        sdk.__file__ = str(self.sdk_dir / "__init__.py")
        self.modules = {"rapidocr": sdk}

    def test_sdk_collection_keeps_required_files_and_excludes_unused_models(self):
        with patch.dict(sys.modules, self.modules):
            datas = build_assets.get_rapidocr_datas()
        self.assertEqual(
            {
                (Path(source).relative_to(self.sdk_dir).as_posix(), destination)
                for source, destination in datas
            },
            {
                ("config.yaml", "rapidocr"),
                ("default_models.yaml", "rapidocr"),
                (
                    "models/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
                    "rapidocr/models",
                ),
            },
        )

    def test_missing_sdk_asset_rejects_build(self):
        for relative in SDK_FILES:
            with self.subTest(relative=relative):
                path = self.sdk_dir / relative
                path.unlink()
                try:
                    with patch.dict(sys.modules, self.modules):
                        with self.assertRaisesRegex(FileNotFoundError, path.name):
                            build_assets.get_rapidocr_datas()
                finally:
                    path.write_bytes(b"asset")

    def test_missing_tiny_asset_rejects_build(self):
        model_dir = self.root / "arknights_mower/models/rapidocr"
        model_dir.mkdir(parents=True)
        for filename in TINY_HASHES:
            (model_dir / filename).write_bytes(b"asset")
        for filename in TINY_HASHES:
            with self.subTest(filename=filename):
                path = model_dir / filename
                path.unlink()
                try:
                    with (
                        patch.dict(sys.modules, self.modules),
                        patch.object(build_assets, "PROJECT_ROOT", self.root),
                    ):
                        with self.assertRaisesRegex(FileNotFoundError, filename):
                            build_assets.get_rapidocr_datas()
                finally:
                    path.write_bytes(b"asset")

    def test_collected_tiny_models_match_release_bytes(self):
        collected = {
            (Path(destination) / Path(source).name).as_posix(): Path(source)
            for source, destination in build_assets._collect_arknights_mower_datas()
        }
        for filename, (size, expected_hash) in TINY_HASHES.items():
            with self.subTest(filename=filename):
                source = collected[f"arknights_mower/models/rapidocr/{filename}"]
                self.assertEqual(source.stat().st_size, size)
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash
                )

    def test_desktop_specs_pass_selected_models_to_analysis(self):
        import scripts.bundled_linux_adb as linux_adb
        import scripts.prepare_macos_adb as macos_adb

        hooks = ModuleType("PyInstaller.utils.hooks")
        hooks.collect_submodules = lambda name: []
        modules = {**self.modules, "PyInstaller.utils.hooks": hooks, "gi": None}

        class AnalysisReached(Exception):
            pass

        for filename in (
            "webui_zip.spec",
            "webui_zip_for_linux.spec",
            "webui_zip_for_macos.spec",
        ):
            with self.subTest(filename=filename):
                captured = {}

                def analysis(*args, **kwargs):
                    captured.update(kwargs)
                    raise AnalysisReached

                path = REPO_ROOT / filename
                with (
                    patch.dict(sys.modules, modules),
                    patch.object(build_assets, "ensure_frontend_built"),
                    patch.object(linux_adb, "linux_adb_assets", return_value=([], [])),
                    patch.object(
                        macos_adb, "prepare_macos_adb", return_value=self.root
                    ),
                ):
                    with self.assertRaises(AnalysisReached):
                        exec(
                            compile(
                                path.read_text(encoding="utf-8"), str(path), "exec"
                            ),
                            {"__file__": str(path), "Analysis": analysis},
                        )
                onnx_destinations = {
                    (Path(destination) / Path(source).name).as_posix()
                    for source, destination in captured["datas"]
                    if Path(source).suffix == ".onnx"
                }
                self.assertTrue(
                    {
                        "arknights_mower/models/rapidocr/PP-OCRv6_det_tiny.onnx",
                        "arknights_mower/models/rapidocr/PP-OCRv6_rec_tiny.onnx",
                        "rapidocr/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
                    }
                    <= onnx_destinations
                )
                self.assertFalse(
                    any("small.onnx" in name for name in onnx_destinations)
                )
                self.assertIn("rapidocr.main", captured["hiddenimports"])


if __name__ == "__main__":
    unittest.main()
