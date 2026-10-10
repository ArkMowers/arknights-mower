"""Shared JSON codec and unavailable-BOX detection."""

import json
from unittest.mock import patch

import pytest

from arknights_mower.utils import mastery_support_data as data
from arknights_mower.utils.mastery_support_types import (
    RosterUnavailableError,
    SupportPlanError,
    decode_json,
    decode_supports,
    encode_supports,
)


def test_support_codec_roundtrip_and_corrupt_input():
    value = {"stages": [{"operator": "艾丽妮", "level": 1}]}
    assert decode_supports({"support_plan": encode_supports(value)}) == value
    assert decode_json(value) is value
    assert decode_json(encode_supports(None)) is None
    with pytest.raises(SupportPlanError, match="数据损坏"):
        decode_supports({"support_plan": "{broken"})


@pytest.mark.parametrize(
    "payload", [None, {}, [], {"data": {}}, {"data": {"characters": []}}]
)
def test_absent_or_empty_box_is_distinct_from_planning_failure(tmp_path, payload):
    box = tmp_path / "cultivate.json"
    if payload is not None:
        box.write_text(json.dumps(payload))
    with patch("arknights_mower.utils.path.get_path", return_value=box):
        with pytest.raises(RosterUnavailableError):
            data.owned_roster()
