"""Calculator source verification accepts checkout line endings and rejects drift."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def test_calculator_source_verification_uses_portable_paths_and_lf_hashes(tmp_path):
    script = (
        Path(__file__).parents[2]
        / ".agents/skills/mower-riic/scripts/verify_calculator.py"
    )
    spec = importlib.util.spec_from_file_location("calculator_source_check", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    vendor = tmp_path / "ui/src/riic/vendor"
    target = vendor / "domain/operators.ts"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"export const operators = []\r\n")
    manifest = {
        "files": {
            "domain/operators.ts": hashlib.sha256(
                b"export const operators = []\n"
            ).hexdigest()
        }
    }
    (vendor / "source.json").write_text(json.dumps(manifest), encoding="utf-8")
    module.verify(tmp_path)
    target.write_bytes(b"export const operators = [1]\r\n")
    with pytest.raises(SystemExit, match="domain/operators.ts"):
        module.verify(tmp_path)
