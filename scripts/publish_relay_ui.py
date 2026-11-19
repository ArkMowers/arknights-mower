"""Publish immutable browser assets first, then the instance build's entry manifest."""

import hashlib
import json
import mimetypes
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path


class Entry(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.styles = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "module":
            self.scripts.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.styles.append(attrs["href"])


def publication(root):
    build = json.loads((root / "relay-ui.json").read_bytes())["build"]
    if not re.fullmatch(r"[0-9a-f]{64}", build):
        raise ValueError("Invalid build identifier")
    entry = Entry()
    entry.feed((root / "index.html").read_text(encoding="utf-8"))
    objects = {}
    public = {}
    for file in sorted(root.rglob("*")):
        if not file.is_file() or file.suffix in {".gz", ".map"}:
            continue
        name = file.relative_to(root).as_posix()
        if name.startswith("manager/") or name in {"index.html", "relay-ui.json"}:
            continue
        if name.startswith("assets/"):
            key = name
        else:
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            key = f"files/{digest}{file.suffix.lower()}"
            public["/" + name] = "/" + key
        objects[key] = file
    if len(entry.scripts) != 1 or not entry.styles:
        raise ValueError("Missing frontend entry")
    for url in entry.scripts + entry.styles:
        if not url.startswith("/assets/") or url[1:] not in objects:
            raise ValueError(f"Missing frontend asset {url}")
    manifest = dict(
        schema=1,
        build=build,
        entry=entry.scripts[0],
        styles=entry.styles,
        public=public,
    )
    return objects, manifest


def publish(root, bucket, s3):
    from botocore.exceptions import ClientError

    objects, manifest = publication(root)
    key = f"builds/{manifest['build']}/manifest.json"
    try:
        s3.head_object(Bucket=bucket, Key=key)
        print("Build already published", manifest["build"])
        return
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
            raise
    existing = set()
    for prefix in ("assets/", "files/"):
        for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=prefix
        ):
            existing.update(obj["Key"] for obj in page.get("Contents", []))

    def put(key, data, mime):
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=mime,
                CacheControl="public, max-age=31536000, immutable",
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
                raise

    def upload(key):
        file = objects[key]
        mime = {
            ".js": "text/javascript",
            ".css": "text/css",
            ".webp": "image/webp",
        }.get(file.suffix)
        put(
            key,
            file.read_bytes(),
            mime or mimetypes.guess_type(file.name)[0] or "application/octet-stream",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(upload, sorted(objects.keys() - existing)))
    put(
        key,
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode(),
        "application/json",
    )
    print("Published build", manifest["build"])


if __name__ == "__main__":
    import boto3

    account = os.environ["R2_ACCOUNT_ID"]
    if not re.fullmatch(r"[0-9a-f]{32}", account):
        raise SystemExit("Set the R2_ACCOUNT_ID repository variable")
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        region_name="auto",
    )
    publish(Path(sys.argv[1]), os.environ["R2_BUCKET"], client)
