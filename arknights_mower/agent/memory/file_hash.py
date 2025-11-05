from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Iterable, Tuple


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def sha256_file(path: Path | str) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_for_paths(paths: Iterable[Path | str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in paths:
        pp = Path(p).resolve()
        if not pp.exists() or not pp.is_file():
            out[str(pp)] = sha256_bytes(f"MISSING:{pp}".encode("utf-8"))
            continue
        out[str(pp)] = sha256_file(pp)
    return out


def fileset_fingerprint(file_hashes: Dict[str, str]) -> str:
    items = sorted(file_hashes.items(), key=lambda kv: kv[0])
    h = hashlib.sha256()
    for path, digest in items:
        h.update(path.encode("utf-8"))
        h.update(b"\0")
        h.update(digest.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def diff_file_hashes(old: Dict[str, str], new: Dict[str, str]) -> Tuple[set, set, set]:
    old_keys = set(old.keys())
    new_keys = set(new.keys())
    added = new_keys - old_keys
    removed = old_keys - new_keys
    changed = {p for p in old_keys & new_keys if old[p] != new[p]}
    return added, removed, changed
