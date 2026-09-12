"""Inspect local release contents without importing code or contacting a server."""

import ast
import gzip
import re
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path

VERSION_RE = re.compile(r"v?\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?(?:\+[^\s]+)?")


def package_format(path):
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


def package_version(path):
    with Path(path).open("rb") as stream:
        content = stream.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError("安装包版本文件过大")
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError) as error:
        raise ValueError("安装包 __init__.py 内容无效") from error
    values = []
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else ([node.target] if isinstance(node, ast.AnnAssign) else [])
        )
        if any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in targets
        ):
            value = node.value
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                raise ValueError("安装包 __version__ 必须为明确的版本字符串")
            values.append(value.value)
    if len(values) != 1 or not VERSION_RE.fullmatch(values[0]):
        raise ValueError("安装包 __init__.py 缺少唯一有效的 __version__")
    return values[0].removeprefix("v")


def executable_platform(path):
    with Path(path).open("rb") as stream:
        header = stream.read(4096)
    if header[:2] == b"MZ" and len(header) >= 64:
        offset = struct.unpack_from("<I", header, 60)[0]
        if offset + 6 <= len(header) and header[offset : offset + 4] == b"PE\0\0":
            machine = struct.unpack_from("<H", header, offset + 4)[0]
            arch = {0x8664: "x64", 0xAA64: "arm64"}.get(machine)
            if arch:
                return "windows", {arch}
    if (
        header[:4] == b"\x7fELF"
        and len(header) >= 64
        and header[4] == 2
        and header[5] in (1, 2)
    ):
        endian = "<" if header[5] == 1 else ">"
        machine = struct.unpack_from(endian + "H", header, 18)[0]
        arch = {62: "x64", 183: "arm64"}.get(machine)
        if arch:
            return "linux", {arch}
    macho = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}
    cpus = {0x1000007: "x64", 0x100000C: "arm64"}
    if header[:4] in macho and len(header) >= 32:
        arch = cpus.get(struct.unpack_from(macho[header[:4]] + "I", header, 4)[0])
        if arch:
            return "macos", {arch}
    if header[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf") and len(header) >= 8:
        count = struct.unpack_from(">I", header, 4)[0]
        size = 20 if header[:4] == b"\xca\xfe\xba\xbe" else 32
        if 0 < count <= 16 and 8 + count * size <= len(header):
            arches = {
                cpus.get(struct.unpack_from(">I", header, 8 + i * size)[0])
                for i in range(count)
            } - {None}
            if arches:
                return "macos", arches
    raise ValueError("安装包主程序格式或架构不受支持")


def validate_payload(payload, system, arch):
    payload = Path(payload).resolve()
    runtime = payload / ("Contents/Resources" if system == "macos" else "_internal")

    def require(path):
        if (
            not path.is_file()
            or not path.resolve().is_relative_to(payload)
            or path.stat().st_size == 0
        ):
            raise ValueError(
                f"安装包不完整或路径无效：缺少 {path.relative_to(payload)}"
            )
        return path

    executable = require(
        payload
        / {"windows": "mower.exe", "linux": "mower", "macos": "Contents/MacOS/mower"}[
            system
        ]
    )
    actual_system, arches = executable_platform(executable)
    if actual_system != system or arch not in arches:
        raise ValueError("安装包主程序的系统或架构与当前运行程序不匹配")
    manager = require(
        payload
        / {
            "windows": "manager.exe",
            "linux": "manager",
            "macos": "Contents/MacOS/manager",
        }[system]
    )
    manager_system, manager_arches = executable_platform(manager)
    if manager_system != system or arch not in manager_arches:
        raise ValueError("安装包 manager 的系统或架构与当前运行程序不匹配")
    version = package_version(require(runtime / "arknights_mower/__init__.py"))
    for name in (
        "arknights_mower/utils/update_runtime.py",
        "arknights_mower/utils/software_update_worker.py",
        "ui/dist/index.html",
        "ui/dist/manager/index.html",
        "base_library.zip",
    ):
        require(runtime / name)
    try:
        with zipfile.ZipFile(runtime / "base_library.zip") as library:
            if (
                not library.namelist()
                or sum(item.file_size for item in library.infolist()) > 256 * 1024**2
                or library.testzip() is not None
            ):
                raise ValueError("安装包 Python 标准库损坏")
    except zipfile.BadZipFile as error:
        raise ValueError("安装包 Python 标准库损坏") from error
    if system == "windows":
        libraries = runtime.glob("python3*.dll")
    elif system == "linux":
        libraries = runtime.glob("libpython3*.so*")
    else:
        libraries = (
            path
            for pattern in ("Python", "Python3", "libpython3*.dylib")
            for path in (payload / "Contents/Frameworks").rglob(pattern)
        )
    if not any(
        path.is_file()
        and path.resolve().is_relative_to(payload)
        and path.stat().st_size > 0
        for path in libraries
    ):
        raise ValueError("安装包不完整：缺少 Python 运行库")
    return version


def inspect_package(path, system, arch):
    # Reuse the installer's bounded extraction and path/link checks.
    from .software_update_worker import MAX_EXTRACTED_BYTES, extract_archive

    kind = package_format(path)
    with tempfile.TemporaryDirectory(
        prefix="inspect-", dir=Path(path).parent
    ) as temporary:
        destination = Path(temporary)
        if kind == "dmg":
            if system != "macos":
                raise ValueError("DMG 安装包仅适用于 macOS")

            def run(*arguments):
                subprocess.run(
                    arguments,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=120,
                )

            run("/usr/bin/hdiutil", "verify", str(path))
            mount = destination / "mount"
            mount.mkdir()
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
                payload = mount / "mower.app"
                version = validate_payload(payload, system, arch)
                run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(payload))
            finally:
                run("/usr/bin/hdiutil", "detach", str(mount))
        else:
            if system == "macos":
                raise ValueError("macOS 请使用完整的 DMG 安装包")
            if kind == "tar.gz":
                # tarfile can stop at the tar end marker before the gzip CRC/footer.
                total = 0
                with gzip.open(path, "rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_EXTRACTED_BYTES:
                            raise ValueError("安装包解压后过大")
            extract_archive(path, destination)
            version = validate_payload(destination / "mower", system, arch)
    return {"version": version, "format": kind}
