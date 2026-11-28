"""Select conservative Python CI scope and disjoint file groups."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath

# These suites cover the Python readers of frontend source and shared WebUI state.
# Resources, shared RIIC logic, dependencies and unknown inputs retain full coverage.
FRONTEND_CONTRACT_TESTS = (
    "arknights_mower/tests/ai_prompt_contract_tests.py",
    "arknights_mower/tests/calculated_mood_tests.py",
    "arknights_mower/tests/conf_cache_header_tests.py",
    "arknights_mower/tests/gui_storage_tests.py",
    "arknights_mower/tests/mastery_task_contract_tests.py",
    "arknights_mower/tests/ui_state_tests.py",
    "arknights_mower/tests/web_routing_tests.py",
)

# Both complete modules also run on Linux in the native compatibility matrix.
NATIVE_UPDATE_TESTS = {
    "arknights_mower/tests/shared_ocr_tests.py",
    "arknights_mower/tests/software_update_transaction_tests.py",
}


def frontend_source_only(files):
    if not isinstance(files, list) or not files:
        return False
    for name in files:
        if not isinstance(name, str):
            return False
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not name.startswith("ui/src/")
            or name.startswith("ui/src/riic/")
            or name.startswith("ui/src/pages/basement_skill/")
            or path.suffix not in {".vue", ".js", ".ts", ".css", ".scss"}
        ):
            return False
    return True


def scope_outputs(raw_files):
    try:
        files = json.loads(raw_files)
    except (ValueError, TypeError):
        files = None
    frontend = frontend_source_only(files)
    return {
        "backend": "false" if frontend else "true",
        "python_shards": json.dumps([0] if frontend else [0, 1, 2]),
    }


def test_files(root):
    return sorted(
        path.relative_to(root).as_posix()
        for directory in ("arknights_mower/tests", "scripts/tests")
        for path in (root / directory).rglob("*.py")
        if path.name.endswith("_tests.py") or path.name.startswith("test_")
    )


def select_tests(root, *, shard=0, count=1, frontend=False, native_update=False):
    if count < 1 or not 0 <= shard < count:
        raise ValueError("invalid Python test shard")
    files = test_files(root)
    if frontend:
        missing = set(FRONTEND_CONTRACT_TESTS) - set(files)
        if missing:
            raise ValueError(f"missing frontend contract suites: {sorted(missing)}")
        files = [path for path in files if path in FRONTEND_CONTRACT_TESTS]
    elif native_update:
        files = [path for path in files if path not in NATIVE_UPDATE_TESTS]
    selected = files[shard::count]
    if not selected:
        raise ValueError("empty Python test shard")
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("scope")
    tests = commands.add_parser("tests")
    tests.add_argument("--shard", type=int, default=0)
    tests.add_argument("--count", type=int, default=1)
    tests.add_argument("--frontend", action="store_true")
    tests.add_argument("--native-update", action="store_true")
    args = parser.parse_args()
    if args.command == "scope":
        outputs = scope_outputs(os.environ.get("CHANGED_CODE_FILES", ""))
        text = "".join(f"{name}={value}\n" for name, value in outputs.items())
        if path := os.environ.get("GITHUB_OUTPUT"):
            with open(path, "a", encoding="utf-8") as output:
                output.write(text)
        else:
            print(text, end="")
    else:
        root = Path(__file__).resolve().parents[1]
        for path in select_tests(
            root,
            shard=args.shard,
            count=args.count,
            frontend=args.frontend,
            native_update=args.native_update,
        ):
            print(path)


if __name__ == "__main__":
    main()
