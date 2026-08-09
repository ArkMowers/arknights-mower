import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _require_path(relative_path: str) -> str:
    path = PROJECT_ROOT / relative_path
    if not path.exists():
        raise FileNotFoundError(f"required build asset is missing: {path}")
    return str(path)


def _find_npm_executable() -> str:
    for candidate in ("npm.cmd", "npm"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("npm executable not found in PATH")


def ensure_frontend_built():
    ui_dir = PROJECT_ROOT / "ui"
    package_json = ui_dir / "package.json"
    if not package_json.exists():
        raise FileNotFoundError(f"frontend package.json is missing: {package_json}")

    if sys.platform.startswith("win"):
        subprocess.run(
            ["cmd", "/c", "npm", "run", "build"],
            cwd=ui_dir,
            check=True,
        )
        return

    npm_executable = _find_npm_executable()
    subprocess.run([npm_executable, "run", "build"], cwd=ui_dir, check=True)


def _is_ignored_build_dir(name: str) -> bool:
    return name in ("tests", "__pycache__")


def _collect_arknights_mower_datas():
    # 打包整个 arknights_mower 包，但跳过 tests/ 与 __pycache__ 等与运行无关的目录。
    # datas 以 (源文件, 目标目录) 逐文件给出，目标目录必须保留包内相对结构，
    # 否则 PyInstaller 只取文件名、把所有文件扁平化到包根目录。
    src_root = PROJECT_ROOT / "arknights_mower"
    result = []
    for path in sorted(src_root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(src_root).as_posix()
        if any(_is_ignored_build_dir(part) for part in rel.split("/")):
            continue
        parent = Path(rel).parent.as_posix()
        dest = "arknights_mower" if parent == "." else f"arknights_mower/{parent}"
        result.append((str(path), dest))
    return result


def _collect_ui_dist_datas():
    # ui/dist 逐文件收集，跳过预压缩的 .gz 副本——它们在运行时由
    # server.py 按 Accept-Encoding 提供，放进发布包只会白白增大体积。
    src_root = PROJECT_ROOT / "ui" / "dist"
    result = []
    for path in sorted(src_root.rglob("*")):
        if path.is_dir() or path.suffix == ".gz":
            continue
        rel = path.relative_to(src_root).as_posix()
        parent = Path(rel).parent.as_posix()
        dest = "./ui/dist" if parent == "." else f"./ui/dist/{parent}"
        result.append((str(path), dest))
    return result


def get_pyinstaller_common_datas():
    ensure_frontend_built()
    return [
        *[(src, dst) for src, dst in _collect_arknights_mower_datas()],
        (_require_path("logo.png"), "."),
        (_require_path("CHANGELOG.md"), "."),
        *[(src, dst) for src, dst in _collect_ui_dist_datas()],
    ]
