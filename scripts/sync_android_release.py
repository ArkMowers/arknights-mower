"""Reuse a compatible APK and MAA Python adapter from the Android release repo."""

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

if __package__:
    from .package_android import RUNTIME_API
else:
    from package_android import RUNTIME_API

REPO = "ALEXsun0/arknights-mower-android"
RELEASE_TAG = re.compile(r"v?\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$")


def api_json(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "mower-release"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/repos/{REPO}/{path}", headers=headers)
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def releases():
    for page in range(1, 101):
        batch = api_json(f"releases?per_page=100&page={page}")
        yield from batch
        if len(batch) < 100:
            return
    raise ValueError("release pagination limit exceeded")


def candidates(items, channel):
    return sorted(
        (
            r
            for r in items
            if not r.get("draft")
            and RELEASE_TAG.fullmatch(r.get("tag_name", ""))
            and (
                channel == "beta"
                or (not r.get("prerelease") and "-" not in r["tag_name"])
            )
        ),
        key=lambda r: r.get("published_at") or "",
        reverse=True,
    )


def download(asset, destination, limit):
    name = asset["name"]
    digest = asset.get("digest") or ""
    url = asset["browser_download_url"]
    parsed = urlparse(url)
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
        or parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or not parsed.path.startswith(f"/{REPO}/releases/download/")
        or not 0 < asset["size"] <= limit
    ):
        raise ValueError("invalid Android release asset metadata")
    target = destination / name
    size = 0
    sha = hashlib.sha256()
    try:
        # No API credential is sent to the public asset download endpoint.
        with urlopen(url, timeout=60) as response, target.open("wb") as out:
            while chunk := response.read(256 * 1024):
                size += len(chunk)
                if size > asset["size"]:
                    raise ValueError("Android asset exceeds declared size")
                sha.update(chunk)
                out.write(chunk)
        if size != asset["size"] or sha.hexdigest() != digest[7:]:
            raise ValueError("Android asset digest or size mismatch")
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


def companion_assets(meta, assets):
    if meta.get("format") != 1 or meta.get("runtime_api") != RUNTIME_API:
        return None
    selected = []
    for key, pattern in (
        ("apk", r"mower-android-[A-Za-z0-9_.-]+\.apk"),
        ("maa_python", r"mower-maa-python-[A-Za-z0-9_.-]+\.zip"),
    ):
        name = meta.get(key, {}).get("name", "")
        if not re.fullmatch(pattern, name) or name not in assets:
            raise ValueError(f"Android release missing declared {key} asset")
        selected.append(assets[name])
    return selected


def sync(items, channel, output, body, fetch=download):
    output.mkdir(parents=True, exist_ok=True)
    for release in candidates(items, channel):
        assets = {a["name"]: a for a in release.get("assets", [])}
        if "android-release.json" not in assets:
            continue
        with tempfile.TemporaryDirectory(dir=output) as temp:
            staging = Path(temp)
            metadata = fetch(assets["android-release.json"], staging, 64 * 1024)
            meta = json.loads(metadata.read_text())
            selected = companion_assets(meta, assets)
            if selected is None:
                continue
            # Fetch both before exposing either to the release upload glob.
            files = [
                fetch(
                    a, staging, 1024**3 if a["name"].endswith(".apk") else 16 * 1024**2
                )
                for a in selected
            ]
            for path in files:
                path.replace(output / path.name)
        tag = release["tag_name"]
        url = f"https://github.com/{REPO}/releases/tag/{tag}"
        with body.open("a") as stream:
            stream.write(
                f"\n\nAndroid APK 与 MAA Python 兼容接口复用自 [{REPO} {tag}]({url})，"
                "保留原始文件和各自版本，不随本次 Mower 发布重新构建。"
                "已有兼容 APK 的用户只需更新 Android Mower 包；MAA 核心与资源从官方更新。\n"
            )
        return [a["name"] for a in selected]
    # Bootstrapping a new platform must not prevent desktop releases.
    message = "没有同渠道且兼容的 Android 宿主 Release，本次仅发布 Mower 热更新包。"
    print(f"::warning::{message}")
    with body.open("a") as stream:
        stream.write(
            f"\n\n{message} APK 与 Python 接口见 https://github.com/{REPO}/releases 。\n"
        )
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=("stable", "beta"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--body", type=Path, required=True)
    args = parser.parse_args()
    print(sync(releases(), args.channel, args.output, args.body))


if __name__ == "__main__":
    main()
