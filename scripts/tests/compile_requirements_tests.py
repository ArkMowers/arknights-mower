import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import compile_requirements  # noqa: E402


class TestCompileRequirements(unittest.TestCase):
    def test_rejects_non_python_312(self):
        calls = []

        with self.assertRaisesRegex(RuntimeError, "Python 3.12"):
            compile_requirements.compile_locks(
                version_info=(3, 11, 9),
                run=lambda *args, **kwargs: calls.append((args, kwargs)),
            )

        self.assertEqual(calls, [])

    def test_compiles_runtime_and_development_locks(self):
        calls = []

        compile_requirements.compile_locks(
            version_info=(3, 12, 0),
            run=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        root = Path(compile_requirements.__file__).resolve().parents[1]
        self.assertEqual(
            calls,
            [
                (
                    (
                        [
                            sys.executable,
                            "-m",
                            "piptools",
                            "compile",
                            "--no-strip-extras",
                            "--output-file=requirements.txt",
                            "requirements.in",
                        ],
                    ),
                    {"check": True, "cwd": root},
                ),
                (
                    (
                        [
                            sys.executable,
                            "-m",
                            "piptools",
                            "compile",
                            "--no-strip-extras",
                            "--output-file=requirements-dev.txt",
                            "requirements-dev.in",
                        ],
                    ),
                    {"check": True, "cwd": root},
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
