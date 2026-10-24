import os
import shutil
import subprocess
import sys
import tarfile
import unittest
import zipfile
from email.parser import Parser
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.requirements import Requirement

REPO_ROOT = Path(__file__).resolve().parents[2]


class PackagingMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = TemporaryDirectory(prefix=".packaging-", dir=REPO_ROOT)
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        (cls.root / ".git").mkdir()
        source = cls.root / "source"
        source.mkdir()
        for relative in (
            "setup.py",
            "MANIFEST.in",
            "README.md",
            "requirements.in",
            "arknights_mower/__init__.py",
            "arknights_mower/__main__.py",
            "arknights_mower/utils/__init__.py",
            "arknights_mower/utils/git_rev.py",
            "arknights_mower/templates/version.html",
        ):
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / relative, destination)
        (source / ".git").mkdir()
        (source / ".git/HEAD").write_text("1" * 40 + "\n", encoding="utf-8")

        cls.invocation = cls.root / "invocation"
        cls.invocation.mkdir()
        cls.original_dist = cls.root / "original-dist"
        cls.run_setup(
            source,
            "sdist",
            "--dist-dir",
            str(cls.original_dist),
            "bdist_wheel",
            "--dist-dir",
            str(cls.original_dist),
        )
        with tarfile.open(next(cls.original_dist.glob("*.tar.gz"))) as archive:
            cls.sdist_members = archive.getnames()
            archive.extractall(cls.root / "unpacked", filter="data")
        unpacked = next((cls.root / "unpacked").iterdir())
        cls.rebuilt_dist = cls.root / "rebuilt-dist"
        cls.run_setup(unpacked, "bdist_wheel", "--dist-dir", str(cls.rebuilt_dist))
        cls.original_metadata = cls.read_metadata(cls.original_dist)
        cls.rebuilt_metadata = cls.read_metadata(cls.rebuilt_dist)

    @classmethod
    def run_setup(cls, source, *arguments):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONUTF8"] = "1"
        result = subprocess.run(
            [sys.executable, str(source / "setup.py"), *arguments],
            cwd=cls.invocation,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
        if result.returncode:
            raise AssertionError(result.stdout)

    @staticmethod
    def read_metadata(directory):
        with zipfile.ZipFile(next(directory.glob("*.whl"))) as wheel:
            metadata_name = next(
                name
                for name in wheel.namelist()
                if name.endswith(".dist-info/METADATA")
            )
            return Parser().parsestr(wheel.read(metadata_name).decode("utf-8"))

    def test_wheel_dependencies_match_runtime_manifest(self):
        expected = {
            Requirement(line)
            for line in (REPO_ROOT / "requirements.in")
            .read_text(encoding="utf-8-sig")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for metadata in (self.original_metadata, self.rebuilt_metadata):
            with self.subTest(version=metadata["Version"]):
                self.assertEqual(
                    {Requirement(value) for value in metadata.get_all("Requires-Dist")},
                    expected,
                )

    def test_python_metadata_matches_supported_source_environment(self):
        for metadata in (self.original_metadata, self.rebuilt_metadata):
            with self.subTest(version=metadata["Version"]):
                self.assertEqual(metadata["Requires-Python"], ">=3.12,<3.13")
                self.assertEqual(
                    [
                        value
                        for value in metadata.get_all("Classifier")
                        if value.startswith("Programming Language :: Python ::")
                    ],
                    ["Programming Language :: Python :: 3.12"],
                )

    def test_sdist_contains_its_build_inputs(self):
        relative_members = {
            name.partition("/")[2] for name in self.sdist_members if "/" in name
        }
        self.assertTrue(
            {"setup.py", "README.md", "requirements.in", "PKG-INFO"} <= relative_members
        )
        self.assertFalse(any(".git" in Path(name).parts for name in self.sdist_members))

    def test_rebuilding_sdist_preserves_version(self):
        self.assertTrue(self.original_metadata["Version"].endswith("+1111111"))
        self.assertEqual(
            self.rebuilt_metadata["Version"], self.original_metadata["Version"]
        )

    def test_wheels_keep_the_package_template_and_console_entry(self):
        for directory in (self.original_dist, self.rebuilt_dist):
            with self.subTest(directory=directory):
                with zipfile.ZipFile(next(directory.glob("*.whl"))) as wheel:
                    self.assertTrue(
                        {
                            "arknights_mower/__init__.py",
                            "arknights_mower/__main__.py",
                            "arknights_mower/utils/git_rev.py",
                            "arknights_mower/templates/version.html",
                        }
                        <= set(wheel.namelist())
                    )
                    entry_points = next(
                        name
                        for name in wheel.namelist()
                        if name.endswith(".dist-info/entry_points.txt")
                    )
                    self.assertIn(
                        "arknights-mower = arknights_mower.__main__:main",
                        wheel.read(entry_points).decode("utf-8"),
                    )


if __name__ == "__main__":
    unittest.main()
