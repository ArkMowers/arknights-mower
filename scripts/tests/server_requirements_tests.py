import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "docker"))

import gen_server_requirements as generator  # noqa: E402


class ServerRequirementsTests(unittest.TestCase):
    def test_filters_desktop_packages_and_preserves_ocr_requirements(self):
        source = [
            "# OCR 依赖\n",
            "opencv-python-headless==4.11.0.86\n",
            "rapidocr==3.10.0\n",
            "ddddocr==1.5.6\n",
            "pywebview==5.1\n",
            "PyAutoGUI==0.9.54\n",
            "pystray==0.19.5\n",
            "pythonnet==3.0.5\n",
        ]
        self.assertEqual(list(generator.transform_lines(source)), source[:4])

    def test_does_not_replace_an_opencv_distribution(self):
        source = ["OpenCV-Python==4.11.0.86 # preserved input\n"]
        self.assertEqual(list(generator.transform_lines(source)), source)

    def test_cli_filters_a_bom_prefixed_first_line_and_writes_utf8(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "源依赖.in"
            output = root / "server.txt"
            source.write_text(
                "pywebview==5.1\n# 图像处理\nopencv-python-headless==4.11.0.86\n",
                encoding="utf-8-sig",
            )
            with (
                patch.object(sys, "argv", ["generator", str(source), str(output)]),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(generator.main(), 0)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "# 图像处理\nopencv-python-headless==4.11.0.86\n",
            )
            self.assertFalse(output.read_bytes().startswith(b"\xef\xbb\xbf"))


class DockerDependencyInstallTests(unittest.TestCase):
    def test_android_uses_shared_filter_without_opencv_reinstallation(self):
        dockerfile = (REPO_ROOT / "scripts/android-runtime.Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn("COPY docker/gen_server_requirements.py", dockerfile)
        self.assertIn(
            "python /tmp/gen_server_requirements.py /tmp/requirements.in "
            "/tmp/android-requirements.txt",
            dockerfile,
        )
        self.assertNotIn("text.replace", dockerfile)
        self.assertNotIn("pip uninstall", dockerfile)
        self.assertNotIn("--force-reinstall", dockerfile)
        install = dockerfile.index("-r /tmp/android-requirements.txt")
        check = dockerfile.index("python -m pip check")
        smoke = dockerfile.index("python /tmp/prune_opencv.py")
        self.assertLess(install, check)
        self.assertLess(check, smoke)
        self.assertIn("--no-deps pnnx==20260526", dockerfile)

    def test_server_installs_the_resolved_graph_before_checking_and_pruning(self):
        dockerfile = (REPO_ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
        install = next(
            line
            for line in dockerfile.splitlines()
            if "-r requirements-server.txt" in line
        )
        self.assertNotIn("--no-deps", install)
        self.assertLess(
            dockerfile.index("-r requirements-server.txt"),
            dockerfile.index("uv pip check --python /opt/venv/bin/python"),
        )
        self.assertLess(
            dockerfile.index("uv pip check --python /opt/venv/bin/python"),
            dockerfile.index("/opt/venv/bin/python scripts/prune_opencv.py"),
        )

    def test_legacy_packaging_image_checks_dependencies_before_pruning(self):
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertLess(
            dockerfile.index("pip install -r requirements.in"),
            dockerfile.index("python -m pip check"),
        )
        self.assertLess(
            dockerfile.index("python -m pip check"),
            dockerfile.index("python scripts/prune_opencv.py"),
        )


if __name__ == "__main__":
    unittest.main()
