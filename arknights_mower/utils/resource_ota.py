"""Shared file-level resource OTA codec; standard library only."""

import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

OTA_MARKER = "resource-ota.json"
VERSION_MARKER = "arknights_mower/data/version.json"
MAX_FILES = 50000
MAX_BYTES = 512 * 1024**2
MAX_MANIFEST_BYTES = 16 * 1024**2


def safe_name(name, allowed_file):
    if not isinstance(name, str) or not name or len(name) > 1024:
        raise ValueError("资源 OTA 路径无效")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
        or any(ord(char) < 32 for char in name)
        or any(part.rstrip(" .") != part for part in path.parts)
        or path.as_posix() != name
        or not allowed_file(name)
    ):
        raise ValueError(f"资源 OTA 包含未允许的路径：{name}")
    return name


def _members(archive):
    members = archive.infolist()
    names = [item.filename for item in members]
    if (
        len(names) > MAX_FILES + 1
        or len(names) != len(set(names))
        or len(names) != len({name.casefold() for name in names})
        or sum(item.file_size for item in members) > MAX_BYTES + MAX_MANIFEST_BYTES
        or any(
            item.is_dir()
            or item.flag_bits & 1
            or stat.S_ISLNK(item.external_attr >> 16)
            for item in members
        )
    ):
        raise ValueError("资源 OTA 条目数量、类型或体积无效")
    return {item.filename: item for item in members}


def _digest(stream):
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_BYTES:
            raise ValueError("资源 OTA 文件过大")
        digest.update(chunk)
    return {"size": size, "sha256": digest.hexdigest()}


def _archive_files(archive, allowed_file):
    members = _members(archive)
    result = {}
    for name in sorted(members):
        safe_name(name, allowed_file)
        with archive.open(name) as stream:
            result[name] = _digest(stream)
    if VERSION_MARKER not in result:
        raise ValueError("资源整包缺少版本清单")
    if (
        len(result) > MAX_FILES
        or sum(info["size"] for info in result.values()) > MAX_BYTES
    ):
        raise ValueError("资源整包文件数或体积过大")
    return result


def _version(archive):
    if archive.getinfo(VERSION_MARKER).file_size > MAX_MANIFEST_BYTES:
        raise ValueError("资源版本清单过大")
    value = json.loads(archive.read(VERSION_MARKER))
    version = value.get("res_version") if isinstance(value, dict) else None
    if not isinstance(version, str) or not re.fullmatch(
        r"v?\d{4}\.\d{2}\.\d{2}-[0-9a-fA-F]{6,40}", version
    ):
        raise ValueError("资源版本无效")
    return version


def build_ota(source, target, output, allowed_file):
    """Build a direct OTA; removed files are omitted from the target inventory."""
    with Path(target).open("rb") as stream:
        full = {"name": "resource.zip", **_digest(stream)}
    with ZipFile(source) as before, ZipFile(target) as after:
        old = _archive_files(before, allowed_file)
        files = _archive_files(after, allowed_file)
        changed = [name for name in files if files[name] != old.get(name)]
        manifest = {
            "format": 1,
            "kind": "mower-resource-ota",
            "from": _version(before),
            "to": _version(after),
            "files": files,
            "changed": changed,
            "full": full,
        }
        if manifest["from"] == manifest["to"]:
            raise ValueError("资源 OTA 起点与目标相同")
        encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise ValueError("资源 OTA 清单过大")
        with ZipFile(output, "w", ZIP_DEFLATED) as package:
            package.writestr(OTA_MARKER, encoded)
            for name in changed:
                with (
                    after.open(name) as stream,
                    package.open("payload/" + name, "w") as destination,
                ):
                    while chunk := stream.read(1024 * 1024):
                        destination.write(chunk)
    return manifest


def apply_ota(
    archive, destination, *, from_version, source_file, allowed_file, callback=None
):
    """Reconstruct and verify every target file in an empty staging directory."""
    report = callback or (lambda **values: None)
    members = _members(archive)
    if OTA_MARKER not in members or members[OTA_MARKER].file_size > MAX_MANIFEST_BYTES:
        raise ValueError("资源 OTA 缺少有效清单")
    manifest = json.loads(archive.read(OTA_MARKER))
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("format")) is not int
        or manifest["format"] != 1
        or manifest.get("kind") != "mower-resource-ota"
        or manifest.get("from") != from_version
        or not isinstance(from_version, str)
        or not isinstance(manifest.get("to"), str)
        or manifest.get("to") == from_version
    ):
        raise ValueError("资源 OTA 格式或起点版本不匹配")
    files, changed = manifest.get("files"), manifest.get("changed")
    if (
        not isinstance(files, dict)
        or not 0 < len(files) <= MAX_FILES
        or VERSION_MARKER not in files
        or len(files) != len({name.casefold() for name in files})
        or not isinstance(changed, list)
        or any(not isinstance(name, str) or name not in files for name in changed)
        or len(changed) != len(set(changed))
    ):
        raise ValueError("资源 OTA 文件清单无效")
    total = 0
    for name, info in files.items():
        safe_name(name, allowed_file)
        if (
            not isinstance(info, dict)
            or set(info) != {"size", "sha256"}
            or type(info["size"]) is not int
            or not 0 <= info["size"] <= MAX_BYTES
            or not isinstance(info["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", info["sha256"])
        ):
            raise ValueError("资源 OTA 文件摘要或大小无效")
        total += info["size"]
    if total > MAX_BYTES or set(members) != {
        OTA_MARKER,
        *("payload/" + name for name in changed),
    }:
        raise ValueError("资源 OTA 内容与清单不一致或目标过大")
    changed = set(changed)
    for name in changed:
        if members["payload/" + name].file_size != files[name]["size"]:
            raise ValueError("资源 OTA 文件大小不符")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    completed = 0
    for name, info in sorted(files.items()):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in changed:
            stream = archive.open("payload/" + name)
        else:
            source = Path(source_file(name))
            if (
                source.is_symlink()
                or not source.is_file()
                or source.stat().st_size != info["size"]
            ):
                raise ValueError(f"资源 OTA 起点文件不匹配：{name}")
            stream = source.open("rb")
        digest = hashlib.sha256()
        written = 0
        with stream, target.open("wb") as output:
            while chunk := stream.read(1024 * 1024):
                written += len(chunk)
                if written > info["size"]:
                    raise ValueError("资源 OTA 文件超过声明大小")
                digest.update(chunk)
                output.write(chunk)
        if written != info["size"] or digest.hexdigest() != info["sha256"]:
            raise ValueError(f"资源 OTA 文件 SHA-256 校验失败：{name}")
        completed += written
        report(
            phase="extracting",
            message="正在重建资源 OTA",
            progress=84 + round(completed / max(total, 1) * 10, 1),
        )
    target_version = json.loads((destination / VERSION_MARKER).read_bytes())
    if target_version.get("res_version") != manifest["to"]:
        raise ValueError("资源 OTA 目标版本与资源清单不一致")
    return target_version
