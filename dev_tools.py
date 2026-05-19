import filecmp
import os
import shutil
import subprocess
import sys
from urllib.parse import urljoin, urlparse

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(PROJECT_ROOT, "ui")
NPX_COMMAND = "npx.cmd" if os.name == "nt" else "npx"
BASE_URL = "https://arkmowers.github.io/arknights-mower/"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "ui", "dist", "docs")
VISITED = set()
LATEST_RUFF_READY = False
BLACKLIST_DIRS = [
    "venv",
    "ArknightsGameResource",
    "__pycache__",
    "dist",
    "dist2",
    "build",
    ".idea",
    ".git",
    ".github",
    "screenshots",
    "screenshot",
    "temp",
    "temp2",
    "log",
    "log2",
    "tmp",
    "ui\\node_modules",
    "ui\\dist",
]


def detect_project_python():
    candidates = [
        os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe"),
        os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe"),
        os.path.join(PROJECT_ROOT, "venv", "bin", "python"),
        os.path.join(PROJECT_ROOT, ".venv", "bin", "python"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return sys.executable


PYTHON_COMMAND = detect_project_python()


def save_file(url, content):
    parsed = urlparse(url)
    path = parsed.path.lstrip("/")
    if not path or path.endswith("/"):
        path += "index.html"
    if path.startswith("ui/dist/docs/"):
        path = path[len("ui/dist/docs/") :]
    local_path = os.path.join(OUTPUT_DIR, path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as file:
        file.write(content)
    print(f"Saved: {local_path}")


def download(url):
    import requests
    from bs4 import BeautifulSoup

    if url in VISITED or not url.startswith(BASE_URL):
        return
    VISITED.add(url)
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
    except Exception as error:
        print(f"Failed to download {url}: {error}")
        return

    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        soup = BeautifulSoup(response.text, "html.parser")
        for image in soup.find_all("img"):
            source = image.get("src")
            if not source:
                continue
            absolute_url = urljoin(url, source)
            if not absolute_url.startswith(BASE_URL):
                continue
            download(absolute_url)
            local_path = urlparse(absolute_url).path.lstrip("/") or "index.html"
            image["src"] = os.path.relpath(
                local_path, os.path.dirname(urlparse(url).path.lstrip("/")) or "."
            )

        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            absolute_url = urljoin(url, href)
            if not absolute_url.startswith(BASE_URL):
                continue
            download(absolute_url)
            local_path = urlparse(absolute_url).path.lstrip("/") or "index.html"
            node_path = os.path.dirname(urlparse(url).path.lstrip("/")) or "."
            anchor["href"] = os.path.relpath(local_path, node_path)

        save_file(url, soup.prettify("utf-8"))
    else:
        save_file(url, response.content)


def compare_and_update(new_dir, old_dir, update_dir):
    for root, _, files in os.walk(new_dir):
        for file_name in files:
            new_file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(new_file_path, new_dir)
            old_file_path = os.path.join(old_dir, relative_path)
            update_file_path = os.path.join(update_dir, relative_path)

            if not os.path.exists(old_file_path) or not filecmp.cmp(
                new_file_path, old_file_path, shallow=False
            ):
                os.makedirs(os.path.dirname(update_file_path), exist_ok=True)
                shutil.copy2(new_file_path, update_file_path)
                print(f"Updated: {relative_path}")


def remove_empty_folders(directory):
    for root, dirs, _ in os.walk(directory, topdown=False):
        for directory_name in dirs:
            directory_path = os.path.join(root, directory_name)
            if not os.listdir(directory_path):
                os.rmdir(directory_path)
                print(f"Removed empty folder: {directory_path}")


def compare_all_subfolders(base_new_dir, base_old_dir, base_update_dir):
    for subfolder in os.listdir(base_new_dir):
        new_dir = os.path.join(base_new_dir, subfolder)
        old_dir = os.path.join(base_old_dir, subfolder)
        update_dir = os.path.join(base_update_dir, subfolder)
        if os.path.isdir(new_dir):
            print(f"Processing subfolder: {subfolder}")
            os.makedirs(update_dir, exist_ok=True)
            compare_and_update(new_dir, old_dir, update_dir)


def is_blacklisted(path):
    rel_path = os.path.relpath(path, PROJECT_ROOT)
    return any(blacklisted_dir in rel_path for blacklisted_dir in BLACKLIST_DIRS)


def ensure_latest_ruff():
    global LATEST_RUFF_READY

    if LATEST_RUFF_READY:
        return

    print("Installing latest Ruff...")
    run_command([PYTHON_COMMAND, "-m", "pip", "install", "--upgrade", "ruff"])
    LATEST_RUFF_READY = True


def run_latest_ruff(args):
    ensure_latest_ruff()
    run_command([PYTHON_COMMAND, "-m", "ruff", *args], cwd=PROJECT_ROOT)


def run_latest_prettier(args):
    run_command(
        [NPX_COMMAND, "--yes", "prettier@latest", *args],
        cwd=PROJECT_ROOT,
    )


def format_ui_files():
    print("Formatting UI files with latest Prettier...")
    run_latest_prettier(["--write", "ui/**/*.js", "ui/**/*.vue"])


def verify_ui_prettier():
    print("Running UI Prettier verification with latest Prettier...")
    run_latest_prettier(["--check", "ui/**/*.js", "ui/**/*.vue"])


def verify_python_ruff_check():
    print("Running Python Ruff lint check...")
    run_latest_ruff(["check", "."])


def verify_python_ruff_format():
    print("Running Python Ruff format check...")
    run_latest_ruff(["format", "--check", "."])


def process_files(base_dir):
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [
            directory_name
            for directory_name in dirs
            if not is_blacklisted(os.path.join(root, directory_name))
        ]

        for file_name in files:
            file_path = os.path.join(root, file_name)
            if file_name.endswith(".py"):
                print(f"Checking and fixing Python file: {file_path}")
                run_latest_ruff(["format", file_path])
                run_latest_ruff(["check", file_path, "--fix"])


def run_command(command, cwd=None):
    printable_command = command if isinstance(command, str) else " ".join(command)
    try:
        result = subprocess.run(
            command,
            shell=isinstance(command, str),
            check=True,
            text=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print(f"Command: {printable_command}")
        print(result.stdout)
        print(result.stderr)
    except subprocess.CalledProcessError as error:
        print(f"Error while running command: {printable_command}")
        print(error.stdout)
        print(error.stderr)


if __name__ == "__main__":
    new_dir = os.path.join(PROJECT_ROOT, "dist", "mower")
    old_dir = "D:\\mower4.1.5.4"
    update_dir = os.path.join(PROJECT_ROOT, "dist", "update")

    # compare_all_subfolders(new_dir, old_dir, update_dir)
    remove_empty_folders(update_dir)
    compare_and_update(new_dir, old_dir, update_dir)
    process_files(PROJECT_ROOT)
    verify_python_ruff_check()
    verify_python_ruff_format()
    format_ui_files()
    verify_ui_prettier()
    # download(BASE_URL)
