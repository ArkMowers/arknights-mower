"""Check CI selection against changed inputs and complete test inventories."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts import ci_test_scope as scope

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "files",
    [
        ["ui/src/App.vue"],
        ["ui/src/stores/gui.js", "ui/src/styles/log.css"],
        ["ui/src/components/DeviceSettings.test.js"],
    ],
)
def test_frontend_source_keeps_python_contracts_without_full_backend(files):
    assert scope.scope_outputs(json.dumps(files)) == {
        "backend": "false",
        "python_shards": "[0]",
    }


@pytest.mark.parametrize(
    "files",
    [
        [],
        {},
        [None],
        ["ui/src/App.vue", "arknights_mower/utils/config/conf.py"],
        ["ui/src/riic/vendor/domain/mood.ts"],
        ["ui/src/pages/basement_skill/skill.json"],
        ["ui/src/pages/basement_skill/roster.js"],
        ["ui/src/unknown.wasm"],
        ["ui/public/frontend-routes.json"],
        ["ui/package-lock.json"],
        ["ui/vite.config.js"],
        ["scripts/build_mood_runtime.mjs"],
        ["arknights_mower/data/mood/mood_runtime.js"],
        [".github/workflows/format-check-and-test.yml"],
        ["ui/src/../../server.py"],
    ],
)
def test_shared_and_unknown_inputs_keep_full_backend(files):
    assert scope.scope_outputs(json.dumps(files)) == {
        "backend": "true",
        "python_shards": "[0, 1, 2]",
    }


@pytest.mark.parametrize("raw", ["", "null", "truncated[", '"ui/src/App.vue"'])
def test_missing_or_invalid_filter_output_runs_all_checks(raw):
    assert scope.scope_outputs(raw)["backend"] == "true"


def test_three_shards_cover_every_discovered_file_exactly_once():
    groups = [scope.select_tests(ROOT, shard=shard, count=3) for shard in range(3)]
    flattened = [path for group in groups for path in group]
    assert sorted(flattened) == scope.test_files(ROOT)
    assert len(flattened) == len(set(flattened))


def test_frontend_scope_retains_source_readers_shared_runtime_and_web_routing():
    files = scope.select_tests(ROOT, frontend=True)
    assert "arknights_mower/tests/ai_prompt_contract_tests.py" in files
    assert "arknights_mower/tests/mastery_task_contract_tests.py" in files
    assert "arknights_mower/tests/calculated_mood_tests.py" in files
    assert "arknights_mower/tests/web_routing_tests.py" in files
    assert "arknights_mower/tests/ui_state_tests.py" in files


def test_native_deduplication_only_applies_when_compatibility_job_runs():
    regular = set(scope.select_tests(ROOT))
    delegated = set(scope.select_tests(ROOT, native_update=True))
    assert regular - delegated == {
        "arknights_mower/tests/shared_ocr_tests.py",
        "arknights_mower/tests/software_update_transaction_tests.py",
    }
    assert delegated <= regular


def test_delegated_modules_run_completely_on_linux_with_failure_fallback():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/format-check-and-test.yml").read_text("utf-8")
    )
    job = workflow["jobs"]["update-compatibility"]
    assert "ubuntu-latest" in job["strategy"]["matrix"]["os"]
    assert "outputs.update != 'false'" in job["if"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    arguments = shlex.split(commands.replace("\\\n", ""))
    for path in scope.NATIVE_UPDATE_TESTS:
        module = path.removesuffix(".py").replace("/", ".")
        assert module in arguments or path in arguments


def test_test_discovery_matches_pytest_patterns_including_nested_files(tmp_path):
    for path in (
        "arknights_mower/tests/a_tests.py",
        "arknights_mower/tests/test_b.py",
        "scripts/tests/nested/test_c.py",
        "scripts/tests/nested/support.py",
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    assert scope.test_files(tmp_path) == [
        "arknights_mower/tests/a_tests.py",
        "arknights_mower/tests/test_b.py",
        "scripts/tests/nested/test_c.py",
    ]


@pytest.mark.parametrize("shard,count", [(3, 3), (-1, 3), (0, 0), (0, -1)])
def test_invalid_shard_fails_instead_of_silently_omitting_tests(shard, count):
    with pytest.raises(ValueError):
        scope.select_tests(ROOT, shard=shard, count=count)


def test_scope_cli_reads_json_as_data_and_appends_action_outputs(tmp_path):
    output = tmp_path / "outputs"
    output.write_text("existing=value\n", encoding="utf-8")
    env = dict(
        os.environ,
        CHANGED_CODE_FILES=json.dumps(["ui/src/App.vue"]),
        GITHUB_OUTPUT=str(output),
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci_test_scope.py"), "scope"],
        env=env,
        check=True,
        timeout=10,
    )
    assert output.read_text(encoding="utf-8") == (
        "existing=value\nbackend=false\npython_shards=[0]\n"
    )
