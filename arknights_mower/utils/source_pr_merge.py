"""Build an ordered PR combination in an isolated Git checkout."""

import subprocess
from pathlib import Path


def merge_source_pulls(git, repository, plan, directory, env, run=None):
    """Return a reproducible merge commit; never touch the running checkout.

    The caller owns the temporary directory. A worker can supply its cancellable
    command runner, so fetching and merging remain cancellable before shutdown.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    environment = {
        **env,
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "Mower",
        "GIT_AUTHOR_EMAIL": "update@localhost",
        "GIT_COMMITTER_NAME": "Mower",
        "GIT_COMMITTER_EMAIL": "update@localhost",
        "GIT_AUTHOR_DATE": plan["merge_date"],
        "GIT_COMMITTER_DATE": plan["merge_date"],
        "GIT_MERGE_AUTOEDIT": "no",
    }
    hooks = directory / ".git" / "mower-no-hooks"
    prefix = [
        git,
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "core.autocrlf=false",
        "-c",
        "core.safecrlf=false",
    ]

    def command(*args):
        if run:
            return run(prefix + list(args), cwd=directory, env=environment, timeout=300)
        return subprocess.run(
            prefix + list(args),
            cwd=directory,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=True,
        )

    def output(*args):
        return subprocess.check_output(
            prefix + list(args),
            cwd=directory,
            env=environment,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
            text=True,
            encoding="utf-8",
        ).strip()

    command("init", "--template=")
    refs = [(f"refs/heads/{plan['source_branch']}", plan["base_commit"])] + [
        (f"refs/pull/{pull['number']}/head", pull["sha"]) for pull in plan["source_prs"]
    ]
    command("fetch", "--no-tags", repository, *[ref for ref, _ in refs])
    fetched = (directory / ".git/FETCH_HEAD").read_text(encoding="utf-8").splitlines()
    if [line.split("\t")[0] for line in fetched] != [sha for _, sha in refs]:
        raise ValueError("PR 提交或目标分支已改变，请重新检查并确认更新")
    command("checkout", "--detach", plan["base_commit"])
    for pull in plan["source_prs"]:
        try:
            command(
                "merge",
                "--no-ff",
                "--no-edit",
                "-m",
                f"Merge PR #{pull['number']}",
                pull["sha"],
            )
        except subprocess.CalledProcessError as exc:
            if output("diff", "--name-only", "--diff-filter=U"):
                raise ValueError(
                    f"PR #{pull['number']} 与前面所选 PR 存在合并冲突，请调整选择"
                ) from exc
            raise ValueError(
                f"PR #{pull['number']} 试合并失败，请检查 Git 日志后重试"
            ) from exc
    try:
        output("cat-file", "-e", "HEAD:arknights_mower/utils/update_runtime.py")
    except subprocess.CalledProcessError as exc:
        raise ValueError("合并结果缺少实例恢复模块，无法自动安装") from exc
    return output("rev-parse", "HEAD")
