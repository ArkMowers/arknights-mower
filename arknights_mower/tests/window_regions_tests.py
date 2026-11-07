"""HTML hit regions preserve controls and reject outdated viewport snapshots."""

from copy import deepcopy

import pytest

from arknights_mower.utils.window_regions import WindowHitRegions
from arknights_mower.utils.window_shell import WindowShellBridge


def viewport():
    return {
        "width": 800,
        "height": 600,
        "regions": [
            {"kind": "move", "x": 0, "y": 0, "width": 662, "height": 36},
            {
                "kind": "resize",
                "edge": "top",
                "x": 0,
                "y": 0,
                "width": 800,
                "height": 5,
            },
            {
                "kind": "resize",
                "edge": "top-left",
                "x": 0,
                "y": 0,
                "width": 8,
                "height": 8,
            },
        ],
    }


def test_bridge_regions_leave_controls_and_content_to_the_webview():
    bridge = WindowShellBridge(None, system="Linux", backend="gtk")
    assert bridge.set_hit_regions(viewport()) is True
    regions = bridge._regions
    assert regions.hit_test(30, 20, 800, 600) == "move"
    assert regions.hit_test(700, 20, 800, 600) is None
    assert regions.hit_test(30, 80, 800, 600) is None
    assert regions.hit_test(0, 0, 800, 600) == "top-left"
    assert regions.hit_test(40, 2, 800, 600) == "top"
    bridge.dispose()
    assert regions.hit_test(30, 20, 800, 600) is None
    assert bridge.set_hit_regions(viewport()) is False


def test_old_regions_do_not_capture_controls_after_a_resize():
    regions = WindowHitRegions()
    assert regions.update(viewport())
    assert regions.hit_test(500, 20, 640, 600) is None
    resized = {
        "width": 640,
        "height": 600,
        "regions": [
            {"kind": "move", "x": 0, "y": 0, "width": 502, "height": 36},
        ],
    }
    assert regions.update(resized)
    assert regions.hit_test(500, 20, 640, 600) == "move"
    assert regions.hit_test(520, 20, 640, 600) is None


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"width": float("inf"), "height": 600, "regions": []},
        {"width": True, "height": 600, "regions": []},
        {"width": 800, "height": 600, "regions": [{}] * 129},
        {
            "width": 800,
            "height": 600,
            "regions": [
                {"kind": "move", "x": 780, "y": 0, "width": 100, "height": 36},
            ],
        },
        {
            "width": 800,
            "height": 600,
            "regions": [
                {
                    "kind": "resize",
                    "edge": "unknown",
                    "x": 0,
                    "y": 0,
                    "width": 8,
                    "height": 8,
                },
            ],
        },
    ],
)
def test_invalid_update_releases_previously_draggable_regions(bad):
    regions = WindowHitRegions()
    assert regions.update(viewport())
    assert regions.update(bad) is False
    assert regions.hit_test(30, 20, 800, 600) is None


def test_snapshot_does_not_follow_mutation_of_the_bridge_argument():
    payload = deepcopy(viewport())
    regions = WindowHitRegions()
    assert regions.update(payload)
    payload["regions"][0]["width"] = 800
    assert regions.hit_test(700, 20, 800, 600) is None
