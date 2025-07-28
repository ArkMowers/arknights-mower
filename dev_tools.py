import filecmp
import os
import shutil
import subprocess
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://arkmowers.github.io/arknights-mower/"
OUTPUT_DIR = "ui/dist/docs"
VISITED = set()


def save_file(url, content):
    parsed = urlparse(url)
    # 只保留 URL 的 path 部分，不要包含域名和 offline_docs
    path = parsed.path.lstrip("/")
    if not path or path.endswith("/"):
        path += "index.html"
    # 防止 path 以 offline_docs/ 开头
    if path.startswith(OUTPUT_DIR + "/"):
        path = path[len(OUTPUT_DIR) + 1 :]
    local_path = os.path.join(OUTPUT_DIR, path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(content)
    print(f"Saved: {local_path}")


def download(url):
    if url in VISITED or not url.startswith(BASE_URL):
        return
    VISITED.add(url)
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type:
        soup = BeautifulSoup(resp.text, "html.parser")
        # 只本地化图片资源
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                abs_url = urljoin(url, src)
                if abs_url.startswith(BASE_URL):
                    download(abs_url)
                    parsed = urlparse(abs_url)
                    local_path = parsed.path.lstrip("/") or "index.html"
                    img["src"] = os.path.relpath(
                        local_path,
                        os.path.dirname(urlparse(url).path.lstrip("/")) or ".",
                    )
        # 页面内链接递归下载并本地化
        for a in soup.find_all("a"):
            href = a.get("href")
            if href and not href.startswith("#") and not href.startswith("mailto:"):
                abs_url = urljoin(url, href)
                if abs_url.startswith(BASE_URL):
                    download(abs_url)
                    parsed = urlparse(abs_url)
                    local_path = parsed.path.lstrip("/") or "index.html"
                    node_path = os.path.dirname(urlparse(url).path.lstrip("/")) or "."
                    a["href"] = os.path.relpath(local_path, node_path)
        save_file(url, soup.prettify("utf-8"))
    else:
        save_file(url, resp.content)


def compare_and_update(new_dir, old_dir, update_dir):
    """
    比较两个文件夹，将 new_dir 中新增或修改的文件复制到 update_dir 中，保持文件夹结构。
    """
    for root, _, files in os.walk(new_dir):
        for file in files:
            new_file_path = os.path.join(root, file)
            relative_path = os.path.relpath(new_file_path, new_dir)
            old_file_path = os.path.join(old_dir, relative_path)
            update_file_path = os.path.join(update_dir, relative_path)

            # 如果文件在 old_dir 中不存在，或者文件内容不同
            if not os.path.exists(old_file_path) or not filecmp.cmp(
                new_file_path, old_file_path, shallow=False
            ):
                # 创建目标文件夹
                os.makedirs(os.path.dirname(update_file_path), exist_ok=True)
                # 复制文件到 update_dir
                shutil.copy2(new_file_path, update_file_path)
                print(f"Updated: {relative_path}")


def remove_empty_folders(directory):
    """
    递归删除空文件夹。
    """
    for root, dirs, _ in os.walk(directory, topdown=False):
        for dir in dirs:
            dir_path = os.path.join(root, dir)
            if not os.listdir(dir_path):  # 如果文件夹为空
                os.rmdir(dir_path)
                print(f"Removed empty folder: {dir_path}")


def compare_all_subfolders(base_new_dir, base_old_dir, base_update_dir):
    """
    遍历主文件夹下的所有子文件夹，对每个子文件夹执行比较和更新。
    """
    for subfolder in os.listdir(base_new_dir):
        new_dir = os.path.join(base_new_dir, subfolder)
        old_dir = os.path.join(base_old_dir, subfolder)
        update_dir = os.path.join(base_update_dir, subfolder)

        # 确保是文件夹
        if os.path.isdir(new_dir):
            print(f"Processing subfolder: {subfolder}")
            os.makedirs(update_dir, exist_ok=True)
            compare_and_update(new_dir, old_dir, update_dir)


def is_blacklisted(path):
    """
    检查路径是否在黑名单中
    """
    for blacklisted_dir in BLACKLIST_DIRS:
        if blacklisted_dir in path:
            return True
    return False


def process_files(base_dir):
    """
    遍历目录，检查并格式化 .py、.vue 和 .js 文件
    """
    for root, dirs, files in os.walk(base_dir):
        # 跳过黑名单中的目录
        dirs[:] = [d for d in dirs if not is_blacklisted(os.path.join(root, d))]

        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith(".py"):
                # 使用 ruff 检查和修复 Python 文件
                print(f"Checking and fixing Python file: {file_path}")
                run_command(f"ruff check {file_path} --fix")
            elif file.endswith(".vue") or file.endswith(".js"):
                # 使用 prettier 检查和格式化 Vue 和 JavaScript 文件
                print(f"Checking and formatting Vue/JS file: {file_path}")
                run_command(f"prettier --check {file_path}")
                run_command(f"prettier --write {file_path}")


def run_command(command):
    """
    运行命令并打印输出
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print(result.stdout)
        print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error while running command: {command}")
        print(e.stdout)
        print(e.stderr)


if __name__ == "__main__":
    # 定义文件夹路径
    new_dir = (
        "F:\\Git\\arknights-mower\\dist\\mower\\_internal"  # 替换为 new 文件夹的路径
    )
    old_dir = "I:\\Mower2025.7.1_full\\_internal"  # 替换为 old 文件夹的路径
    update_dir = "F:\\Git\\arknights-mower\\dist\\update"  # 替换为 update 文件夹的路径
    BLACKLIST_DIRS = [
        "venv",
        "ArknightsGameResource",
        "__pycache__",
        "dist",
        "build",
        ".idea",
        ".git",
        ".github",
        "screenshots",
        "temp",
        "log",
        "ui\\node_modules",
        "ui\\dist",
    ]
    # 执行比较和更新
    compare_all_subfolders(new_dir, old_dir, update_dir)

    remove_empty_folders(update_dir)
    # process_files("F:\\Git\\arknights-mower")

    # 下载在线文档至本地
    download(BASE_URL)
