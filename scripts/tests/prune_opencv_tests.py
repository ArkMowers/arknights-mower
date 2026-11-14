import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib import metadata
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import prune_opencv as opencv_pruner  # noqa: E402
from prune_opencv import find_candidates, prune_opencv  # noqa: E402


class TestPruneOpenCv(unittest.TestCase):
    def make_distributions(self, root: Path, names):
        for index, name in enumerate(names):
            info = root / f"package-{index}.dist-info"
            info.mkdir()
            (info / "METADATA").write_text(
                f"Metadata-Version: 2.1\nName: {name}\nVersion: 4.11.0.86\n",
                encoding="utf-8",
            )
        return list(metadata.distributions(path=[str(root)]))

    def test_cli_rejects_multiple_distributions_even_with_the_same_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            distributions = self.make_distributions(
                Path(temporary), ["OpenCV_Python", "opencv.python.headless"]
            )
            with (
                patch.object(sys, "argv", ["prune_opencv.py"]),
                patch.object(metadata, "distributions", return_value=distributions),
                patch.object(opencv_pruner, "find_cv2_root") as find,
                patch.object(
                    opencv_pruner, "prune_opencv", return_value=([], 0)
                ) as prune,
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(
                    SystemExit, "exactly one OpenCV distribution"
                ) as error,
            ):
                opencv_pruner.main()

            self.assertIn("opencv-python==4.11.0.86", str(error.exception))
            self.assertIn("opencv-python-headless==4.11.0.86", str(error.exception))
            find.assert_not_called()
            prune.assert_not_called()

    def test_cli_rejects_missing_distribution_before_finding_or_pruning_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            distributions = self.make_distributions(Path(temporary), ["numpy"])
            with (
                patch.object(sys, "argv", ["prune_opencv.py"]),
                patch.object(metadata, "distributions", return_value=distributions),
                patch.object(opencv_pruner, "find_cv2_root") as find,
                patch.object(
                    opencv_pruner, "prune_opencv", return_value=([], 0)
                ) as prune,
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(SystemExit, "found 0"),
            ):
                opencv_pruner.main()

            find.assert_not_called()
            prune.assert_not_called()

    def test_cli_accepts_each_single_distribution_with_normalized_name(self):
        for name in (
            "OpenCV_Python",
            "opencv.python.headless",
            "OpenCV__Contrib.Python",
            "OPENCV.contrib_python..HEADLESS",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                distributions = self.make_distributions(root, [name, "numpy"])
                cv2_root = self.make_package(root)
                output = io.StringIO()
                with (
                    patch.object(sys, "argv", ["prune_opencv.py", "--dry-run"]),
                    patch.object(metadata, "distributions", return_value=distributions),
                    patch.object(opencv_pruner, "find_cv2_root", return_value=cv2_root),
                    redirect_stdout(output),
                ):
                    opencv_pruner.main()

                self.assertIn("Would remove", output.getvalue())
                self.assertEqual(len(find_candidates(cv2_root)), 3)

    def test_cli_runs_core_smoke_even_when_no_optional_assets_remain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            distributions = self.make_distributions(root, ["opencv-python-headless"])
            cv2_root = root / "cv2"
            cv2_root.mkdir()
            with (
                patch.object(sys, "argv", ["prune_opencv.py"]),
                patch.object(metadata, "distributions", return_value=distributions),
                patch.object(opencv_pruner, "find_cv2_root", return_value=cv2_root),
                patch.object(opencv_pruner, "smoke_test_core_apis") as smoke,
                redirect_stdout(io.StringIO()),
            ):
                opencv_pruner.main()
                smoke.assert_called_once_with()
                smoke.side_effect = RuntimeError("native API failed")
                with self.assertRaisesRegex(RuntimeError, "native API failed"):
                    opencv_pruner.main()

    def make_package(self, root: Path) -> Path:
        cv2_root = root / "cv2"
        data = cv2_root / "data"
        libraries = root / "opencv_python.libs"
        data.mkdir(parents=True)
        libraries.mkdir()
        (data / "haarcascade.xml").write_bytes(b"cascade")
        (cv2_root / "opencv_videoio_ffmpeg490_64.dll").write_bytes(b"dll")
        (libraries / "opencv_videoio_ffmpeg.so").write_bytes(b"plugin")
        (libraries / "libavcodec-required.so.59").write_bytes(b"required")
        return cv2_root

    def test_prunes_optional_plugins_and_data_but_keeps_linked_libraries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cv2_root = self.make_package(root)
            smoke_calls = []

            candidates, removed_bytes = prune_opencv(
                cv2_root, smoke_test=lambda: smoke_calls.append(True)
            )

            self.assertEqual(smoke_calls, [True])
            self.assertEqual(
                removed_bytes, len(b"cascade") + len(b"dll") + len(b"plugin")
            )
            self.assertEqual(len(candidates), 3)
            self.assertFalse((cv2_root / "data").exists())
            self.assertFalse((cv2_root / "opencv_videoio_ffmpeg490_64.dll").exists())
            self.assertFalse(
                (root / "opencv_python.libs" / "opencv_videoio_ffmpeg.so").exists()
            )
            self.assertTrue(
                (root / "opencv_python.libs" / "libavcodec-required.so.59").is_file()
            )

    def test_restores_every_candidate_when_smoke_test_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cv2_root = self.make_package(root)

            with self.assertRaisesRegex(RuntimeError, "smoke failed"):
                prune_opencv(
                    cv2_root,
                    smoke_test=lambda: (_ for _ in ()).throw(
                        RuntimeError("smoke failed")
                    ),
                )

            self.assertEqual(len(find_candidates(cv2_root)), 3)
            self.assertTrue(
                (root / "opencv_python.libs" / "libavcodec-required.so.59").is_file()
            )

    def test_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            cv2_root = self.make_package(Path(temporary))
            prune_opencv(cv2_root, smoke_test=None)

            candidates, removed_bytes = prune_opencv(cv2_root, smoke_test=None)

            self.assertEqual(candidates, [])
            self.assertEqual(removed_bytes, 0)

    def test_rejects_library_root_linked_outside_site_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cv2_root = root / "site-packages" / "cv2"
            external = root / "external-libraries"
            cv2_root.mkdir(parents=True)
            external.mkdir()
            library_link = cv2_root.parent / "opencv_python.libs"
            try:
                library_link.symlink_to(external, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")

            with self.assertRaisesRegex(RuntimeError, "linked OpenCV library root"):
                find_candidates(cv2_root)

    def test_incomplete_rollback_attempts_all_restores_and_keeps_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cv2_root = self.make_package(root)
            staging = root / "preserved-staging"
            staging.mkdir()
            real_move = opencv_pruner.shutil.move
            failed_once = False

            def fail_one_restore(source, destination):
                nonlocal failed_once
                if Path(source).parent == staging and not failed_once:
                    failed_once = True
                    raise OSError("restore blocked")
                return real_move(source, destination)

            with (
                patch.object(
                    opencv_pruner.tempfile, "mkdtemp", return_value=str(staging)
                ),
                patch.object(
                    opencv_pruner.shutil, "move", side_effect=fail_one_restore
                ),
                self.assertRaisesRegex(RuntimeError, "rollback is incomplete"),
            ):
                prune_opencv(
                    cv2_root,
                    smoke_test=lambda: (_ for _ in ()).throw(
                        RuntimeError("smoke failed")
                    ),
                )

            self.assertTrue(any(staging.iterdir()))
            restored = find_candidates(cv2_root)
            self.assertEqual(len(restored), 2)


if __name__ == "__main__":
    unittest.main()
