"""Actual desktop launch and parent ownership, with no GUI imports or windows."""

import json
import os
import sys
import time
from multiprocessing import parent_process
from pathlib import Path


def wait_without_gui(channel, marker, *unused):
    ready = Path(marker).with_suffix(".tmp")
    ready.write_text(
        json.dumps({"parent": parent_process().pid, "helper": os.getpid()}),
        encoding="utf-8",
    )
    ready.replace(marker)
    time.sleep(60)


def main():
    import webview_ui

    webview_ui.splash_screen = wait_without_gui
    webview_ui.start_tray = wait_without_gui
    webview_ui.webview_window = wait_without_gui
    process, _ = webview_ui.start_desktop_child(sys.argv[1], sys.argv[2])
    process.join(60)


if __name__ == "__main__":
    main()
