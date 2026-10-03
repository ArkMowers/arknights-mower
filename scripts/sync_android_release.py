"""Link to the independently published Android host; never mirror its binaries."""

import argparse
from pathlib import Path

REPO = "ALEXsun0/arknights-mower-android"
MARKER = "<!-- android-downloads -->"


def append_download_link(body: Path) -> None:
    text = body.read_text(encoding="utf-8")
    if MARKER in text:
        return
    text += (
        f"\n\n{MARKER}\n"
        "Android：本次附件中的 `android_arm64.zip` 是 Mower 热更新包，"
        "供已安装的 Android 宿主导入或在线更新。\n\n"
        f"APK 与 MAA Python 兼容接口请前往 [Mower Android 下载页面]"
        f"(https://github.com/{REPO}/releases)。"
        "Android 仓库定期检测新的 Mower / MAA 发行，独立构建并发布 APK；"
        "构建完成时间与本次 Mower 发版不同步。"
        "已有兼容宿主可直接更新 Mower，无需等待新 APK。\n"
    )
    body.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body", type=Path, required=True)
    args = parser.parse_args()
    append_download_link(args.body)


if __name__ == "__main__":
    main()
