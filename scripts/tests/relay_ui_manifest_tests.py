import hashlib
import json
import zlib
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from scripts.relay_ui_manifest import manifest


def test_release_manifest_ranges_match_published_bytes(tmp_path):
    archive = tmp_path / "ui.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("relay-ui.json", json.dumps({"build": "a" * 64}))
        bundle.mkdir("assets/")
        bundle.writestr("assets/名字.js", b"content" * 64, ZIP_DEFLATED)
        bundle.writestr("empty.txt", b"", ZIP_STORED)
    raw = archive.read_bytes()
    result = manifest(archive)
    assert result["archive"] == hashlib.sha256(raw).hexdigest()
    assert result["build"] == "a" * 64
    with ZipFile(archive) as bundle:
        for item in result["files"]:
            pos = item["offset"]
            data = raw[pos : pos + item["length"]]
            if item["method"] == ZIP_DEFLATED:
                data = zlib.decompress(data, -15)
            assert data == bundle.read(item["path"])
            assert item["sha256"] == hashlib.sha256(data).hexdigest()
