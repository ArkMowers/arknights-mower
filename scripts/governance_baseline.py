"""Keep policy history distinct from the requested change comparison."""

import json
import re
import subprocess
from pathlib import Path


def policy_comparison_base(
    repository: Path, comparison_base: str | None, policy: str
) -> str | None:
    """Use a fixed pre-policy commit when the shared comparison ancestor is older."""
    configuration = repository / "scripts/governance_baselines.json"
    if not configuration.exists():
        return comparison_base
    baselines = json.loads(configuration.read_text(encoding="utf-8"))
    if (
        not isinstance(baselines, dict)
        or set(baselines) != {"legacy_format", "development_prose"}
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value)
            for value in baselines.values()
        )
    ):
        raise ValueError("Invalid policy baseline configuration")

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )

    revisions = list(baselines.items())
    if comparison_base is not None:
        revisions.insert(0, ("comparison", comparison_base))
    for label, revision in revisions:
        result = git(
            "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"
        )
        if result.returncode:
            raise ValueError(
                f"Unavailable {label} policy comparison commit: {revision}"
            )
        if label == "comparison":
            comparison_base = result.stdout.strip()
        elif git("merge-base", "--is-ancestor", revision, "HEAD").returncode:
            raise ValueError(f"Policy baseline {label} is outside the reviewed history")
    if comparison_base is None:
        return None
    floor = baselines[policy]
    ancestor = git("merge-base", comparison_base, "HEAD")
    if ancestor.returncode:
        raise ValueError("Cannot determine shared policy comparison history")
    shared = ancestor.stdout.strip()
    older = git("merge-base", "--is-ancestor", shared, floor)
    if older.returncode == 0:
        return floor
    newer = git("merge-base", "--is-ancestor", floor, shared)
    if older.returncode != 1 or newer.returncode != 0:
        raise ValueError(
            f"Policy baseline {policy} and comparison history are unrelated"
        )
    return shared
