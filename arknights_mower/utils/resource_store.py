"""Persistent, immutable resource generations shared by desktop instances."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from arknights_mower.utils.res_version import (
    RES_PACKAGE_DATA,
    RES_PACKAGE_DIRS,
    RES_PACKAGE_MODELS,
    parse_version,
)

MARKER = "arknights_mower/data/version.json"
SCHEMA_VERSION = 1


def read_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or parse_version(value.get("res_version")) is None:
        raise ValueError("资源版本清单无效")
    return value


def compatibility_error(manifest: dict, mower_version: str) -> str | None:
    schema = manifest.get("schema_version", 1)
    if type(schema) is not int or schema != SCHEMA_VERSION:
        return f"不支持资源格式版本：{schema}"
    requirement = manifest.get("mower_version")
    if requirement is not None:
        try:
            if not isinstance(requirement, str):
                raise ValueError("mower_version 必须是版本范围字符串")
            if not SpecifierSet(requirement).contains(
                Version(mower_version), prereleases=True
            ):
                return f"资源要求 Mower {requirement}，当前为 {mower_version}"
        except (InvalidSpecifier, InvalidVersion, ValueError):
            return "资源的 Mower 版本兼容范围无效"
    return None


def _updated_at(manifest: dict) -> datetime | None:
    try:
        # Resource generators historically emit a local wall-clock timestamp.
        # Only compare like-for-like timestamps; do not guess a missing timezone.
        value = datetime.fromisoformat(
            manifest.get("last_updated", "").replace("Z", "+00:00")
        )
        return value
    except (TypeError, ValueError, AttributeError):
        return None


def resource_newer(candidate: dict, current: dict) -> bool:
    """Hashes identify content, not chronological order; ambiguous ties stay put."""
    candidate_version = parse_version(candidate.get("res_version"))
    current_version = parse_version(current.get("res_version"))
    if candidate_version is None:
        return False
    if current_version is None:
        return True
    if candidate_version[:3] != current_version[:3]:
        return candidate_version[:3] > current_version[:3]
    if candidate_version[3].lower() == current_version[3].lower():
        return False
    newer, older = _updated_at(candidate), _updated_at(current)
    if (
        newer is None
        or older is None
        or (newer.tzinfo is None) != (older.tzinfo is None)
    ):
        return False
    return newer > older


def validate_package(root: Path, mower_version: str) -> dict:
    manifest = read_manifest(root / MARKER)
    if error := compatibility_error(manifest, mower_version):
        raise ValueError(error)
    missing = [
        rel
        for rel in (*RES_PACKAGE_DATA, *RES_PACKAGE_MODELS)
        if not (root / rel).is_file()
    ]
    missing += [rel for rel in RES_PACKAGE_DIRS if not any((root / rel).glob("*.webp"))]
    if missing:
        raise ValueError(f"资源包不完整：缺少 {', '.join(missing)}")
    return manifest


@dataclass(frozen=True)
class ResourceSelection:
    # None selects the complete bundled resource set.
    root: Path | None
    manifest: dict


def read_index(root: Path) -> list[str]:
    try:
        data = json.loads((root / "index.json").read_text(encoding="utf-8"))
        names = data["packages"]
        if not isinstance(names, list) or any(
            not isinstance(name, str)
            or len(name) != 64
            or any(c not in "0123456789abcdef" for c in name)
            for name in names
        ):
            return []
        return names
    except (OSError, ValueError, KeyError, TypeError):
        return []


def select_resource(root: Path, builtin: Path, mower_version: str) -> ResourceSelection:
    try:
        manifest = read_manifest(builtin / "data/version.json")
    except (OSError, ValueError, TypeError):
        manifest = {}
    selected = ResourceSelection(None, manifest)
    for name in read_index(root):
        package = root / "packages" / name
        try:
            candidate = validate_package(package, mower_version)
        except (OSError, ValueError, TypeError):
            continue
        if resource_newer(candidate, selected.manifest):
            selected = ResourceSelection(package, candidate)
    return selected
