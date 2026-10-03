import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import prune_opencv as opencv_pruner  # noqa: E402
from prune_opencv import find_candidates, prune_opencv  # noqa: E402


class TestPruneOpenCv(unittest.TestCase):
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
