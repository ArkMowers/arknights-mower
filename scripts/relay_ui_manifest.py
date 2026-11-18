"""Describe the independently compressed files in one published frontend ZIP."""

import hashlib
import json
import struct
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


def manifest(archive):
    files = []
    with ZipFile(archive) as bundle, archive.open("rb") as stream:
        build = json.loads(bundle.read("relay-ui.json"))["build"]
        for entry in bundle.infolist():
            if entry.is_dir():
                continue
            if entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                raise ValueError("Unsupported frontend compression")
            stream.seek(entry.header_offset)
            header = stream.read(30)
            if header[:4] != b"PK\x03\x04":
                raise ValueError("Invalid ZIP member header")
            name_size, extra_size = struct.unpack_from("<HH", header, 26)
            with bundle.open(entry) as member:
                digest = hashlib.file_digest(member, "sha256").hexdigest()
            files.append(
                {
                    "path": entry.filename,
                    "sha256": digest,
                    "size": entry.file_size,
                    "offset": entry.header_offset + 30 + name_size + extra_size,
                    "length": entry.compress_size,
                    "method": entry.compress_type,
                }
            )
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"schema": 1, "build": build, "archive": digest, "files": files}


if __name__ == "__main__":
    print(json.dumps(manifest(Path(sys.argv[1])), separators=(",", ":")))
