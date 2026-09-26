"""Read release metadata from the package's existing version file."""

import ast
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from tarfile import open as open_tar

VERSION_FILE_NAME = "__init__.py"
VERSION_FILE_PATH = PurePosixPath("mower/_internal/arknights_mower") / VERSION_FILE_NAME
MAX_VERSION_FILE_BYTES = 1024 * 1024
ARCHIVE_FORMATS = {"windows": "zip", "linux": "tar.gz", "macos": "dmg"}
PLATFORMS = frozenset(ARCHIVE_FORMATS)
ARCHITECTURES = frozenset(("x64", "arm64"))


def package_format(path: Path) -> str:
    if zipfile.is_zipfile(path):
        return "zip"
    with Path(path).open("rb") as stream:
        if stream.read(2) == b"\x1f\x8b":
            return "tar.gz"
        if stream.seek(0, 2) >= 512:
            stream.seek(-512, 2)
            if stream.read(4) == b"koly":
                return "dmg"
    raise ValueError("无法识别安装包内容，请选择完整的 Release ZIP、tar.gz 或 DMG")


def _read_limited(stream, size: int) -> bytes:
    if size < 1 or size > MAX_VERSION_FILE_BYTES:
        raise ValueError("安装包版本文件为空或过大")
    content = stream.read(MAX_VERSION_FILE_BYTES + 1)
    if len(content) != size or len(content) > MAX_VERSION_FILE_BYTES:
        raise ValueError("安装包版本文件读取不完整或过大")
    return content


def _parse_version_file(content: bytes) -> dict:
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError) as error:
        raise ValueError("安装包版本文件内容无效") from error
    names = {
        "__version__": "版本号",
        "__release_system__": "系统信息",
        "__release_arch__": "架构信息",
        "__release_archive__": "归档格式",
    }
    values = {name: [] for name in names}
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else ([node.target] if isinstance(node, ast.AnnAssign) else [])
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id in values:
                value = node.value
                if not isinstance(value, ast.Constant) or not isinstance(
                    value.value, str
                ):
                    raise ValueError(
                        f"安装包版本文件中的 {names[target.id]} 必须是明确字符串"
                    )
                values[target.id].append(value.value)
    for name, label in names.items():
        if len(values[name]) != 1:
            raise ValueError(f"安装包版本文件缺少唯一的{label}")

    version = values["__version__"][0]
    from .software_update import VERSION_RE

    system = values["__release_system__"][0]
    arch = values["__release_arch__"][0]
    archive = values["__release_archive__"][0]
    if not VERSION_RE.fullmatch(version):
        raise ValueError("安装包版本文件缺少有效版本号")
    if system not in PLATFORMS:
        raise ValueError("安装包版本文件缺少有效系统信息")
    if arch not in ARCHITECTURES:
        raise ValueError("安装包版本文件缺少有效架构信息")
    if archive != ARCHIVE_FORMATS[system]:
        raise ValueError("安装包版本文件中的归档格式与系统不匹配")
    return {"version": version, "system": system, "arch": arch, "archive": archive}


def _zip_version(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            matches = [
                info
                for info in archive.infolist()
                if info.filename == str(VERSION_FILE_PATH)
            ]
            if len(matches) != 1 or matches[0].is_dir():
                raise ValueError("安装包缺少唯一的版本文件")
            info = matches[0]
            with archive.open(info) as stream:
                return _parse_version_file(_read_limited(stream, info.file_size))
    except zipfile.BadZipFile as error:
        raise ValueError("安装包 ZIP 内容损坏") from error


def _tar_version(path: Path) -> dict:
    try:
        with open_tar(path, "r:gz") as archive:
            matches = [
                member
                for member in archive.getmembers()
                if PurePosixPath(member.name.removeprefix("./")) == VERSION_FILE_PATH
            ]
            if len(matches) != 1 or not matches[0].isfile():
                raise ValueError("安装包缺少唯一的版本文件")
            member = matches[0]
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("无法读取安装包版本文件")
            with stream:
                return _parse_version_file(_read_limited(stream, member.size))
    except (OSError, ValueError):
        raise
    except Exception as error:
        raise ValueError("安装包 tar.gz 内容损坏") from error


def _dmg_version(path: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="mower-release-") as temporary:
        mount = Path(temporary) / "mount"
        mount.mkdir()

        def run(*arguments: str) -> None:
            try:
                subprocess.run(
                    arguments,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=120,
                )
            except (OSError, subprocess.SubprocessError) as error:
                raise ValueError("无法只读挂载 DMG 安装包") from error

        run(
            "/usr/bin/hdiutil",
            "attach",
            "-readonly",
            "-nobrowse",
            "-mountpoint",
            str(mount),
            str(path),
        )
        try:
            version_file = (
                mount
                / "mower.app/Contents/Resources/arknights_mower"
                / VERSION_FILE_NAME
            )
            if (
                not version_file.is_file()
                or version_file.is_symlink()
                or not version_file.resolve().is_relative_to(mount.resolve())
            ):
                raise ValueError("安装包缺少唯一的版本文件")
            size = version_file.stat().st_size
            with version_file.open("rb") as stream:
                return _parse_version_file(_read_limited(stream, size))
        finally:
            run("/usr/bin/hdiutil", "detach", str(mount))


def inspect_package(path: Path, system: str, arch: str) -> dict:
    """Return package metadata after validating only its version file."""
    path = Path(path)
    kind = package_format(path)
    expected = ARCHIVE_FORMATS.get(system)
    if expected is None or arch not in ARCHITECTURES:
        raise ValueError("当前系统或架构没有受支持的 Release 安装包")
    if kind != expected:
        raise ValueError("安装包格式与当前系统不匹配")
    if kind == "zip":
        metadata = _zip_version(path)
    elif kind == "tar.gz":
        metadata = _tar_version(path)
    else:
        metadata = _dmg_version(path)
    if (metadata["system"], metadata["arch"]) != (system, arch):
        raise ValueError("安装包的系统或架构与当前运行程序不匹配")
    if metadata["archive"] != kind:
        raise ValueError("安装包归档格式与版本文件不匹配")
    return {"version": metadata["version"], "format": kind}


def inspect_ota_package(path: Path, current_version: str, system: str, arch: str):
    """Recognize a local OTA ZIP and check its origin before starting a worker.

    The worker validates every manifest entry and reconstructed file before
    stopping any running instance. Return None for a regular Release archive.
    """
    if not zipfile.is_zipfile(path):
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > 50001:
                raise ValueError("OTA 差异包文件数量过多")
            entries = [
                item for item in archive.infolist() if item.filename == "ota.json"
            ]
            if not entries:
                return None
            if len(entries) != 1 or entries[0].is_dir():
                raise ValueError("OTA 差异包缺少唯一的清单")
            if entries[0].file_size > 16 * 1024**2:
                raise ValueError("OTA 差异包清单过大")
            with archive.open(entries[0]) as stream:
                manifest = json.load(stream)
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("OTA 差异包清单损坏") from error
    if system != "windows" or arch != "x64":
        raise ValueError("手动 OTA 差异包目前仅支持 Windows x64")
    from .software_update import VERSION_RE

    if (
        not isinstance(manifest, dict)
        or manifest.get("kind") != "mower-ota"
        or type(manifest.get("format")) is not int
        or manifest["format"] not in (1, 2)
        or manifest.get("platform") != system
        or manifest.get("arch") != arch
        or not isinstance(manifest.get("from"), str)
        or not VERSION_RE.fullmatch(manifest["from"])
        or manifest["from"].startswith("v")
        or not isinstance(manifest.get("to"), str)
        or not VERSION_RE.fullmatch(manifest["to"])
        or manifest["to"].startswith("v")
    ):
        raise ValueError("OTA 差异包格式或平台不匹配")
    installed = current_version.split("+", 1)[0].removeprefix("v")
    if manifest["from"] != installed:
        raise ValueError(
            f"OTA 差异包需要从 {manifest['from']} 更新，当前版本为 {installed}"
        )
    return {"version": manifest["to"], "format": "zip"}
