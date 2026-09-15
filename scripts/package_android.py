"""Package Mower application files for an existing Android host (no APK/runtime)."""

import argparse
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Bump only when the embedded Python dependencies or host API must change.
# Ordinary Mower code, WebUI and resource releases keep the same runtime API.
RUNTIME_API = 1
ROOTS = (
    "arknights_mower",
    "ui/dist",
    "server.py",
    "LICENSE",
    "CHANGELOG.md",
    "logo.png",
    "requirements.txt",
)
REQUIRED = (
    "arknights_mower/__init__.py",
    "arknights_mower/data/version.json",
    "ui/dist/index.html",
    "server.py",
    "LICENSE",
    "requirements.txt",
    "CHANGELOG.md",
)


def package(root: Path, output: Path, version: str, revision: str) -> Path:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-alpha\.\d+)?", version):
        raise ValueError("invalid release version")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("invalid commit revision")
    for name in REQUIRED:
        if not (root / name).is_file():
            raise ValueError(f"missing build input: {name}")
    if not (root / "CHANGELOG.md").read_text(encoding="utf-8").strip():
        raise ValueError("empty build input: CHANGELOG.md")
    source = (root / "arknights_mower/__init__.py").read_text()
    if f'__version__ = "{version}"' not in source:
        raise ValueError("package version does not match injected Mower version")
    manifest = {
        "kind": "mower-android",
        "format": 1,
        "version": version,
        "revision": revision,
        "runtime_api": RUNTIME_API,
        "python": "3.12",
        "platform": "android",
        "arch": "arm64",
    }
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"arknights-mower_{version}_android_arm64.zip"
    temporary = target.with_suffix(".tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6
        ) as z:
            z.writestr("mower-android.json", json.dumps(manifest, indent=2) + "\n")
            for name in ROOTS:
                base = root / name
                for path in sorted(base.rglob("*")) if base.is_dir() else [base]:
                    relative = path.relative_to(root)
                    if any(
                        p in ("tests", "__pycache__", ".pytest_cache")
                        for p in relative.parts
                    ):
                        continue
                    if path.is_symlink():
                        raise ValueError(f"unexpected symlink: {relative}")
                    if not path.is_file() or path.suffix in (".pyc", ".pyo"):
                        continue
                    if relative.as_posix() == "arknights_mower/utils/git_revision":
                        continue
                    z.write(path, "mower/" + relative.as_posix())
            z.writestr("mower/arknights_mower/utils/git_revision", revision)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    print(package(ROOT, args.output, args.version, revision))


if __name__ == "__main__":
    main()
