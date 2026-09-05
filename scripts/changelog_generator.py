#!/usr/bin/env python3
"""从 git 提交自动生成 release changelog。

- 分类：conventional commit 前缀 + 中文关键词兜底，deps/依赖升级类提交
  进 Dependencies 分组，跳过 build/ci/style/debug 以及正文含 [skip changelog]
  的提交
- 版本头：tag 去 v 前缀并补发布日期（tag 创建日；手动触发未打 tag 时回退 HEAD 提交日）
- 条目：提交标题原文 + PR 链接 + 裸 @署名 `[(#N)](url) @user`，无 PR 时仅
  `@user`
- 贡献者：通过 GitHub API 把 git 提交解析成裸 @登录名，逐条署名；GitHub Release
  根据 mention 生成原生 Contributors 头像区
- 对比基准：正式版 tag 只取上一个正式版 tag；测试版 tag 优先取上一个测试版
  tag，没有则取上一个正式版 tag；都无可达 tag 时回退到仓库最新对应类型 tag
"""

import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

CATEGORY_ORDER = [
    ("feat", "New"),
    ("fix", "Bug Fixes"),
    ("perf", "Improvements"),
    ("deps", "Dependencies"),
    ("chore", "Maintenance"),
    ("docs", "Documentation"),
    ("other", "Other"),
]

PREFIX_CATEGORY = {
    "feat": "feat",
    "fix": "fix",
    "perf": "perf",
    "refactor": "perf",
    "rft": "perf",
    "docs": "docs",
    "doc": "docs",
    "chore": "chore",
}

KEYWORD_CATEGORY = {
    "修复": "fix",
    "新增": "feat",
    "更新": "perf",
    "改进": "perf",
    "优化": "perf",
    "重构": "perf",
    "文档": "docs",
}

IGNORE_PREFIXES = ("build", "ci", "style", "debug")

STABLE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
ALPHA_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+-alpha\.[0-9]+$")
VERSION_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:-alpha\.[0-9]+)?$")

DEPENDENCY_SCOPE_RE = re.compile(r"^\w+\(deps(?:-dev)?\): *")
DEPENDENCY_PATTERNS = (
    re.compile(r"依赖.*(?:升级|更新)"),
    re.compile(r"(?:升级|更新).*依赖"),
)

SEP = "\x1f"
REC = "\x1e"

_login_cache: dict[str, str] = {}

GITHUB_NOREPLY_DOMAIN = "users.noreply.github.com"
GITHUB_LOGIN_RE = re.compile(r"(?=.{1,39}\Z)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
COAUTHOR_RE = re.compile(
    r"^Co-authored-by:\s*(?P<name>.+?)\s*<(?P<email>[^<>\r\n]+)>\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def release_date(tag: str) -> str:
    """发布日期：tag 创建日；tag 未创建（手动触发）时回退到 HEAD 提交日。"""
    try:
        date = git("for-each-ref", "--format=%(creatordate:short)", f"refs/tags/{tag}")
        if date.strip():
            return date.strip()
    except subprocess.CalledProcessError:
        pass
    return git("log", "-1", "--format=%cs", "HEAD").strip()


def mention_login(login: str) -> str:
    return f"@{login}"


def parse_category(message: str) -> str | None:
    """返回分类名；build/ci/style/debug 前缀返回 None（跳过）。

    依赖升级类提交（deps 前缀/scope 或中文"依赖…升级/更新"句式）优先归入
    deps，不因 build 前缀被跳过。
    """
    if DEPENDENCY_SCOPE_RE.match(message) or any(
        pattern.search(message) for pattern in DEPENDENCY_PATTERNS
    ):
        return "deps"
    if re.match(rf"^(?:{'|'.join(IGNORE_PREFIXES)}) *(?:\([^)]*\))?: *", message):
        return None
    match = re.match(r"^(?P<prefix>\w+)(?:\([\w\-]+\))?:\s*", message)
    if match:
        return PREFIX_CATEGORY.get(match.group("prefix").lower(), "other")
    for keyword, category in KEYWORD_CATEGORY.items():
        if keyword in message:
            return category
    return "other"


def strip_prefix(message: str) -> str:
    return re.sub(r"^(\w+)(?:\([^)]*\))?:\s*", "", message)


def extract_pr(message: str) -> tuple[str, int | None]:
    """分离条目末尾的 (#N)，返回（描述, PR 号或 None）。"""
    match = re.search(r"\(#(\d+)\)\s*$", message)
    if match:
        return message[: match.start()].rstrip(), int(match.group(1))
    return message, None


def github_api_get(url: str):
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None


def email_cache_key(email: str) -> str | None:
    """返回可安全作为身份缓存键的规范化邮箱。"""
    normalized = email.strip().casefold()
    local, separator, domain = normalized.rpartition("@")
    if not separator or not local or not domain:
        return None
    return normalized


def noreply_login(email: str) -> str | None:
    """从 GitHub noreply 邮箱严格解析登录名，其他邮箱不做猜测。"""
    normalized = email.strip()
    local, separator, domain = normalized.rpartition("@")
    if not separator or domain.casefold() != GITHUB_NOREPLY_DOMAIN:
        return None
    if "+" in local:
        user_id, login = local.split("+", 1)
        if not user_id.isdecimal():
            return None
    else:
        login = local
    if not GITHUB_LOGIN_RE.fullmatch(login):
        return None
    return login


def commit_login(repo: str, commit_hash: str, email: str) -> str | None:
    cache_key = email_cache_key(email)
    if cache_key and cache_key in _login_cache:
        return _login_cache[cache_key]

    data = github_api_get(f"https://api.github.com/repos/{repo}/commits/{commit_hash}")
    login = None
    if data:
        candidate = (data.get("author") or {}).get("login")
        if isinstance(candidate, str) and candidate:
            login = candidate
    if login is None:
        login = noreply_login(email)
    if login is not None and cache_key:
        _login_cache[cache_key] = login
    return login


def _reachable_commit_count(name: str) -> int | None:
    """HEAD 到 name 祖先的提交数；name 不是 HEAD 的祖先时返回 None。"""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", name, "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    count = git("rev-list", "--count", f"{name}..HEAD").strip()
    return int(count) if count.isdigit() else None


def _tag_matches_kind(name: str, kinds: tuple[str, ...]) -> bool:
    return ("stable" in kinds and bool(STABLE_TAG_RE.match(name))) or (
        "alpha" in kinds and bool(ALPHA_TAG_RE.match(name))
    )


def _nearest_tag(name: str, kinds: tuple[str, ...]) -> str:
    """HEAD 的可达版本 tag 里，按提交距离取最近的指定类型 tag。"""
    candidates: list[tuple[int, str]] = []
    for candidate in git("tag", "-l").splitlines():
        candidate = candidate.strip()
        if candidate == name or not VERSION_TAG_RE.match(candidate):
            continue
        if not _tag_matches_kind(candidate, kinds):
            continue
        distance = _reachable_commit_count(candidate)
        if distance is not None:
            candidates.append((distance, candidate))
    if candidates:
        return min(candidates)[1]
    return ""


def _latest_tag(name: str, kinds: tuple[str, ...]) -> str:
    """按创建时间取仓库里最新的指定类型版本 tag（不要求可达）。"""
    for candidate in git("tag", "--sort=-creatordate").splitlines():
        candidate = candidate.strip()
        if candidate == name or not _tag_matches_kind(candidate, kinds):
            continue
        return candidate
    return ""


def find_base_tag(tag: str) -> str:
    """按发布类型选取 changelog 对比基准 tag。

    正式版（vX.Y.Z）只取上一个正式版 tag；测试版（vX.Y.Z-alpha.N）优先取
    上一个测试版 tag，没有则取上一个正式版 tag。都在 HEAD 的可达祖先里按
    提交距离取最近；没有可达 tag 时回退到仓库里最新创建的对应类型 tag。
    """
    if ALPHA_TAG_RE.match(tag):
        base = _nearest_tag(tag, ("alpha",))
        if base:
            return base
        base = _nearest_tag(tag, ("stable",))
        if base:
            return base
        base = _latest_tag(tag, ("alpha",))
        if base:
            return base
        return _latest_tag(tag, ("stable",))
    base = _nearest_tag(tag, ("stable",))
    if base:
        return base
    return _latest_tag(tag, ("stable",))


def collect_commits(base: str) -> list[dict]:
    cmd = [
        "log",
        "--no-merges",
        f"--pretty=format:%H{SEP}%an{SEP}%ae{SEP}%s{SEP}%b{REC}",
    ]
    if base:
        cmd.append(f"{base}..HEAD")
    else:
        cmd += ["-30", "HEAD"]

    commits = []
    for record in git(*cmd).split(REC):
        record = record.strip("\r\n")
        if not record:
            continue
        fields = record.split(SEP, 4)
        if len(fields) < 5:
            continue
        commit_hash, author_name, author_email, subject, body = fields
        if "[skip changelog]" in body:
            continue
        category = parse_category(subject)
        if category is None:
            continue
        authors = [(author_name, author_email)]
        authors.extend(
            (match.group("name"), match.group("email").strip())
            for match in COAUTHOR_RE.finditer(body)
        )
        desc, number = extract_pr(strip_prefix(subject).strip())
        commits.append(
            {
                "hash": commit_hash,
                "category": category,
                "desc": desc,
                "number": number,
                "authors": authors,
            }
        )
    return commits


def resolve_logins(
    repo: str, commit_hash: str, authors: list[tuple[str, str]]
) -> list[str]:
    """主作者走 commit API；共同作者使用邮箱缓存或 GitHub noreply 邮箱。

    解析不出可靠登录名的作者跳过，全部按大小写不敏感去重。
    """
    resolved: list[str] = []
    seen: set[str] = set()
    for index, (_, email) in enumerate(authors):
        if index == 0:
            login = commit_login(repo, commit_hash, email)
        else:
            cache_key = email_cache_key(email)
            login = _login_cache.get(cache_key) if cache_key else None
            if login is None:
                login = noreply_login(email)
                if login is not None and cache_key:
                    _login_cache[cache_key] = login
        if login is None:
            continue
        key = login.casefold()
        if key not in seen:
            seen.add(key)
            resolved.append(login)
    return resolved


def prepend_changelog(path: Path, block: str) -> bool:
    """把版本块插入文件顶部标题之后，旧内容整体下移（平铺倒序）。

    幂等：目标文件已存在相同版本标题时不重复插入，返回是否真的写入了。
    只做插入，绝不改动或删除文件里已有的其他版本内容。
    """
    text = path.read_text(encoding="utf-8")
    version = re.match(r"^## (.+?)(?: - |\s*$)", block.splitlines()[0]).group(1)
    if re.search(rf"^## {re.escape(version)}(?: - |\s*$)", text, re.MULTILINE):
        return False
    if text.startswith("# "):
        heading_end = text.index("\n") + 1
        head, tail = text[:heading_end], text[heading_end:]
        new_text = head + "\n" + block.rstrip() + "\n\n" + tail.lstrip("\n")
    else:
        new_text = block.rstrip() + "\n\n" + text.lstrip("\n")
    path.write_text(new_text, encoding="utf-8")
    return True


def render_release_body(tag: str, repo: str, base: str, commits: list[dict]) -> str:
    version = tag.removeprefix("v")
    lines = [f"## {version} - {release_date(tag)}", ""]
    for category, title in CATEGORY_ORDER:
        items = [c for c in commits if c["category"] == category]
        if not items:
            continue
        lines.append(f"### {title}")
        lines.append("")
        for commit in items:
            logins = resolve_logins(repo, commit["hash"], commit["authors"])
            mentions = " ".join(mention_login(login) for login in logins)
            if commit["number"]:
                pr = f"[(#{commit['number']})](https://github.com/{repo}/pull/{commit['number']})"
                lines.append(f"- {commit['desc']} {pr} {mentions}")
            else:
                lines.append(f"- {commit['desc']} {mentions}")
        lines.append("")
    if base:
        lines.append(
            f"**Full Changelog**: [{base}...{tag}]"
            f"(https://github.com/{repo}/compare/{base}...{tag})"
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="release tag，如 v4.1.6-alpha.2")
    parser.add_argument("--repo", required=True, help="GitHub 仓库，如 owner/repo")
    parser.add_argument("--out", required=True, help="输出文件路径")
    parser.add_argument(
        "--prepend-to", help="把生成的版本块插入该文件顶部（写回仓库 CHANGELOG.md 用）"
    )
    args = parser.parse_args()

    base = find_base_tag(args.tag)
    commits = collect_commits(base)
    body = render_release_body(args.tag, args.repo, base, commits)

    Path(args.out).write_text(body, encoding="utf-8")
    if args.prepend_to:
        inserted = prepend_changelog(Path(args.prepend_to), body)
        if not inserted:
            version = args.tag.removeprefix("v")
            print(f"prepend skipped: {args.prepend_to} already contains {version}")
    print(
        f"changelog written to {args.out}: {len(commits)} commits, base={base or '(none)'}"
    )


if __name__ == "__main__":
    main()
