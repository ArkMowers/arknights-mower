#!/usr/bin/env python3
"""从 git 提交自动生成 release changelog。

- 分类：conventional commit 前缀 + 中文关键词兜底，deps/依赖升级类提交
  进 Dependencies 分组，跳过 build/ci/style/debug 以及正文含 [skip changelog]
  的提交
- 版本头：tag 去 v 前缀并补发布日期（tag 创建日；手动触发未打 tag 时回退 HEAD 提交日）
- 条目：更新说明 + PR 链接 + 裸 @署名 `[(#N)](url) @user`，无 PR 时仅
  `@user`
- 描述优先读取已合并 PR 的 Changelog 段，再读提交说明段，旧提交回退标题
- 普通合并归并为一个发布条目；没有发布说明的旧合并继续读取分支提交
- 本次发布内经差异确认的完整回退相互抵消，跨版本回退保留说明
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
import sys
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
CHANGELOG_ENTRY_RE = re.compile(r"^Changelog:[ \t]*(.*)$")
TRAILER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:[ \t]")
REVERT_TARGET_RE = re.compile(
    r"^This reverts commit ([0-9a-f]{7,64})(?:[.,]|$)", re.MULTILINE
)
MERGE_PR_RE = re.compile(r"^Merge pull request #([0-9]+)\b")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=30,
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
    if message.startswith('Revert "'):
        return "other"
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


def extract_changelog_entry(body: str) -> str | None:
    """读取第一个 Changelog 说明段，遇到空行或其他元数据字段结束。

    标记所在行必须有说明文字；缺少标记或说明为空时返回 None，兼容旧标题。
    """
    lines = body.splitlines()
    for index, line in enumerate(lines):
        match = CHANGELOG_ENTRY_RE.fullmatch(line)
        if match is None:
            continue
        description = match.group(1).strip()
        if not description:
            return None
        parts = [description]
        for continuation in lines[index + 1 :]:
            if (
                not continuation.strip()
                or TRAILER_LINE_RE.match(continuation)
                or re.match(r"^#{1,6}\s", continuation.lstrip())
            ):
                break
            parts.append(continuation.strip())
        return " ".join(parts)
    return None


def extract_pr_changelog(body: str) -> str | None:
    """读取唯一的 PR 发布说明，不读取代码块、注释或后续审阅栏目。"""
    visible = []
    fence = None
    in_comment = False
    for line in body.splitlines():
        stripped = line.lstrip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            visible.append("")
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in line
            visible.append("")
            continue
        marker = re.match(r"^(`{3,}|~{3,})", stripped)
        if marker:
            if fence is None:
                fence = marker.group(1)
            elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            visible.append("")
            continue
        if fence is not None:
            visible.append("")
            continue
        visible.append(line)
    markers = [
        i for i, line in enumerate(visible) if CHANGELOG_ENTRY_RE.fullmatch(line)
    ]
    if len(markers) != 1:
        return None
    index = markers[0]
    first = CHANGELOG_ENTRY_RE.fullmatch(visible[index]).group(1).strip()
    if not first:
        return None
    parts = [first]
    for line in visible[index + 1 :]:
        if (
            not line.strip()
            or TRAILER_LINE_RE.match(line)
            or re.match(r"^#{1,6}\s", line.lstrip())
        ):
            break
        parts.append(line.strip())
    return " ".join(parts)


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


def read_commits(revision: str, *, first_parent=False, limit=None) -> list[dict]:
    cmd = [
        "log",
        "--topo-order",
        f"--pretty=format:%H{SEP}%an{SEP}%ae{SEP}%s{SEP}%b{SEP}%P{REC}",
    ]
    if first_parent:
        cmd.append("--first-parent")
    if limit is not None:
        cmd.append(f"-{limit}")
    cmd.append(revision)
    records = []
    for record in git(*cmd).split(REC):
        record = record.strip("\r\n")
        if not record:
            continue
        fields = record.split(SEP, 5)
        if len(fields) != 6:
            continue
        commit_hash, author_name, author_email, subject, body, parents = fields
        authors = [(author_name, author_email)]
        authors.extend(
            (match.group("name"), match.group("email").strip())
            for match in COAUTHOR_RE.finditer(body)
        )
        records.append(
            {
                "hash": commit_hash,
                "subject": subject,
                "body": body,
                "parents": parents.split(),
                "authors": authors,
            }
        )
    return records


def inverse_changes_match(original: dict, reversal: dict) -> bool:
    """保守比较两个主线变化的完整逆向差异，保留位置、空白和二进制内容。"""
    if not original["parents"] or not reversal["parents"]:
        return False

    def diff(before, after):
        patch = subprocess.run(
            [
                "git",
                "diff",
                "--no-ext-diff",
                "--no-renames",
                "--binary",
                "--unified=0",
                before,
                after,
            ],
            capture_output=True,
            check=True,
            timeout=30,
        ).stdout
        return b"".join(
            line
            for line in patch.splitlines(keepends=True)
            if not line.startswith(b"index ")
        )

    return bool(expected := diff(original["hash"], original["parents"][0])) and (
        expected == diff(reversal["parents"][0], reversal["hash"])
    )


def effective_changes(changes: list[dict]) -> list[dict]:
    """从新到旧抵消完整回退；分支内的目标归属于引入它的主线合并。"""
    owners = {}
    positions = {change["hash"]: i for i, change in enumerate(changes)}
    for change in changes:
        for member in [change, *change["members"]]:
            owners[member["hash"]] = change["hash"]
    by_hash = {change["hash"]: change for change in changes}
    active = set(by_hash)
    for change in changes:
        if change["hash"] not in active:
            continue
        targets = {
            target
            for member in [change, *change["members"]]
            for target in REVERT_TARGET_RE.findall(member["body"])
        }
        for target in targets:
            matches = {owner for sha, owner in owners.items() if sha.startswith(target)}
            if len(matches) != 1:
                continue
            original_hash = matches.pop()
            if (
                original_hash not in active
                or positions[original_hash] <= positions[change["hash"]]
            ):
                continue
            try:
                matched = inverse_changes_match(by_hash[original_hash], change)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                matched = False
            if matched:
                active.difference_update((original_hash, change["hash"]))
                break
            print(
                f"changelog: unconfirmed full revert {change['hash'][:12]}; keeping entries",
                file=sys.stderr,
            )
    return [change for change in changes if change["hash"] in active]


class PullRequests:
    """按实际合并 SHA 确认 PR 归属，复用本次发布内的读取结果。"""

    def __init__(self, repo: str):
        self.repo = repo
        self.by_number = {}
        self.failures = 0

    def for_change(self, change: dict) -> dict | None:
        if not self.repo:
            return None
        _, number = extract_pr(change["subject"])
        if match := MERGE_PR_RE.match(change["subject"]):
            number = int(match.group(1))
        if number:
            if number not in self.by_number:
                self.by_number[number] = github_api_get(
                    f"https://api.github.com/repos/{self.repo}/pulls/{number}"
                )
            candidates = [self.by_number[number]]
        else:
            candidates = github_api_get(
                f"https://api.github.com/repos/{self.repo}/commits/{change['hash']}/pulls"
                "?per_page=100"
            )
            if candidates is None:
                self.failures += 1
                return None
            if not isinstance(candidates, list):
                candidates = []
        valid = []
        for pull in candidates:
            if pull is None:
                self.failures += 1
                continue
            if not isinstance(pull, dict):
                continue
            base = pull.get("base") or {}
            if not isinstance(base, dict):
                continue
            base_repo = base.get("repo") or {}
            if not isinstance(base_repo, dict):
                continue
            if (
                (pull.get("merged") or pull.get("merged_at"))
                and pull.get("merge_commit_sha") == change["hash"]
                and str(base_repo.get("full_name", "")).casefold()
                == self.repo.casefold()
                and isinstance(pull.get("title"), str)
                and isinstance(pull.get("body"), (str, type(None)))
                and type(pull.get("number")) is int
                and pull["number"] > 0
            ):
                valid.append(pull)
        if len(valid) == 1:
            return valid[0]
        if len(valid) > 1:
            print(
                f"changelog: ambiguous PR for {change['hash'][:12]}; using Git",
                file=sys.stderr,
            )
        return None


def commit_entry(record: dict) -> dict | None:
    category = parse_category(record["subject"])
    if "[skip changelog]" in record["body"] or category is None:
        return None
    desc, number = extract_pr(strip_prefix(record["subject"]).strip())
    return {
        "hash": record["hash"],
        "category": category,
        "desc": extract_changelog_entry(record["body"]) or desc,
        "number": number,
        "authors": record["authors"],
    }


def collect_commits(base: str, repo: str = "") -> list[dict]:
    changes = read_commits(
        f"{base}..HEAD" if base else "HEAD",
        first_parent=True,
        limit=None if base else 30,
    )
    for change in changes:
        change["members"] = (
            [
                record
                for record in read_commits(f"{change['hash']}^1..{change['hash']}")
                if record["hash"] != change["hash"]
            ]
            if len(change["parents"]) > 1
            else []
        )
    pulls = PullRequests(repo)
    entries = []
    for change in effective_changes(changes):
        if "[skip changelog]" in change["body"]:
            continue
        is_merge = len(change["parents"]) > 1
        if not is_merge and parse_category(change["subject"]) is None:
            continue
        pull = pulls.for_change(change)
        description = extract_pr_changelog(pull.get("body") or "") if pull else None
        if description is None and is_merge:
            description = extract_pr_changelog(change["body"])
        if description is not None:
            category = parse_category(pull["title"] if pull else change["subject"])
            number = pull["number"] if pull else extract_pr(change["subject"])[1]
            if number is None and (match := MERGE_PR_RE.match(change["subject"])):
                number = int(match.group(1))
            if category is not None and (
                not pull or "[skip changelog]" not in (pull.get("body") or "")
            ):
                entries.append(
                    {
                        "hash": change["hash"],
                        "category": category,
                        "desc": description,
                        "number": number,
                        "authors": change["authors"],
                        "contributor_commits": [
                            record
                            for record in (change["members"] or [change])
                            if len(record["parents"]) < 2
                        ],
                    }
                )
            continue
        if pull and "Changelog:" in (pull.get("body") or ""):
            print(
                f"changelog: invalid PR description for {change['hash'][:12]}; using Git",
                file=sys.stderr,
            )
        # 旧合并的分支提交也先抵消内部的完整回退，再沿用原有标题与分类。
        fallback = change["members"] if is_merge else [change]
        ordinary = [record for record in fallback if len(record["parents"]) < 2]
        for record in ordinary:
            record.setdefault("members", [])
        for record in effective_changes(ordinary):
            if entry := commit_entry(record):
                entries.append(entry)
    if pulls.failures:
        print(
            f"changelog: {pulls.failures} PR read(s) unavailable; using Git fallback",
            file=sys.stderr,
        )
    return entries


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


def existing_release_block(path: Path, tag: str) -> str | None:
    """已有版本块作为本次发布的固定正文，后续构建不重新读取 PR。"""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    heading = re.search(
        rf"^## {re.escape(tag.removeprefix('v'))}(?: - [^\n]+)?[ \t]*$",
        text,
        re.MULTILINE,
    )
    if heading is None:
        return None
    following = re.search(r"^## ", text[heading.end() :], re.MULTILINE)
    end = heading.end() + following.start() if following else len(text)
    return text[heading.start() : end].rstrip() + "\n"


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
            logins = []
            seen = set()
            for contributor in commit.get("contributor_commits") or [commit]:
                for login in resolve_logins(
                    repo, contributor["hash"], contributor["authors"]
                ):
                    if login.casefold() not in seen:
                        seen.add(login.casefold())
                        logins.append(login)
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

    existing = (
        existing_release_block(Path(args.prepend_to), args.tag)
        if args.prepend_to
        else None
    )
    if existing is not None:
        Path(args.out).write_text(existing, encoding="utf-8")
        print(f"changelog reused from {args.prepend_to}: {args.tag}")
        return
    base = find_base_tag(args.tag)
    commits = collect_commits(base, args.repo)
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
