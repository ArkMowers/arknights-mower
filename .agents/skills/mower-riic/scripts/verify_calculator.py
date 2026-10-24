"""Verify the bundled calculator against its recorded source and local patches."""

import hashlib
import json
from pathlib import Path


def verify(root):
    vendor = root / "ui" / "src" / "riic" / "vendor"
    manifest = json.loads((vendor / "source.json").read_text("utf-8"))
    patches = manifest.get("localPatches", {})
    errors = []
    for name, source_hash in manifest["files"].items():
        path = vendor / name
        expected = patches.get(name, {}).get("sha256", source_hash)
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            errors.append(name)
    recorded = set(manifest["files"]) | {"source.json", "THIRD_PARTY_MOWER_LICENSE"}
    errors.extend(
        str(p.relative_to(vendor))
        for p in vendor.rglob("*")
        if p.is_file() and str(p.relative_to(vendor)) not in recorded
    )
    if errors:
        raise SystemExit("Calculator source mismatch: " + ", ".join(errors))
    print(
        f"Verified {len(manifest['files'])} calculator files and {len(patches)} local patches"
    )


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[4])
