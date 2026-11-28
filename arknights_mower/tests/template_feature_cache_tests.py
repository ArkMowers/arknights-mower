"""资源模板复用特征，截图和公共 Matcher 输入保留逐次计算。"""

import gc
import weakref
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Event
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import matcher, recognize, resource_pkg


@pytest.fixture(autouse=True)
def isolated_cache():
    matcher.clear_template_feature_cache()
    yield
    matcher.clear_template_feature_cache()


@pytest.fixture
def visual_path(monkeypatch):
    random = np.random.default_rng(18)
    template = random.integers(0, 256, (80, 90), dtype=np.uint8)
    frame = random.integers(0, 256, (192, 192), dtype=np.uint8)
    reader = recognize.Recognizer(Mock())
    reader.set_frame((None, cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB), frame))
    monkeypatch.setattr(recognize, "loadres", lambda *args: template)
    calls = []
    original = matcher.keypoints
    scaled = matcher.keypoints_scale_invariant

    def extract(image):
        calls.append(("fixed", image.shape, image.tobytes()))
        return original(image)

    def extract_scaled(image):
        calls.append(("scaled", image.shape, image.tobytes()))
        return scaled(image)

    monkeypatch.setattr(matcher, "keypoints", extract)
    monkeypatch.setattr(matcher, "keypoints_scale_invariant", extract_scaled)
    monkeypatch.setattr(matcher, "flann", Mock(knnMatch=Mock(return_value=[])))
    return reader, template, frame, calls


def test_find_and_score_reuse_resource_features_across_fresh_frames(visual_path):
    reader, template, frame, calls = visual_path
    for _ in range(3):
        reader.set_frame((None, cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB), frame))
        reader.find("audit_template")
        reader.score("audit_template")
    assert sum(shape == template.shape for _, shape, _ in calls) == 1
    assert sum(shape == frame.shape for _, shape, _ in calls) == 3


def test_threshold_and_scale_modes_do_not_reuse_other_features(visual_path):
    reader, template, _, calls = visual_path
    for _ in range(2):
        reader.find("audit_template")
        reader.find("audit_template", thres=100)
        reader.find("audit_template", thres=200)
        reader.find("control_central")
        reader.score("control_central")
    template_calls = [
        (mode, pixels) for mode, shape, pixels in calls if shape == template.shape
    ]
    assert len(template_calls) == 5
    assert sorted(mode for mode, _ in template_calls) == ["fixed"] * 4 + ["scaled"]
    assert len({pixels for mode, pixels in template_calls if mode == "fixed"}) == 3


def test_resource_reload_and_changed_pixels_each_recompute_features(visual_path):
    reader, template, _, calls = visual_path
    reader.find("audit_template")
    resource_pkg.reload_resource_caches()
    reader.find("audit_template")
    template[0, 0] ^= 255
    reader.find("audit_template")
    assert sum(shape == template.shape for _, shape, _ in calls) == 3


def test_public_dynamic_queries_are_never_reused(visual_path):
    reader, template, _, calls = visual_path
    reader.find("audit_template")
    reader.matcher.score(template)
    template[0, 0] ^= 255
    reader.matcher.match(template, judge=False)
    assert sum(shape == template.shape for _, shape, _ in calls) == 3


def test_entry_capacity_evicts_least_recent_resource(visual_path, monkeypatch):
    reader, template, _, calls = visual_path
    monkeypatch.setattr(matcher, "TEMPLATE_FEATURE_CAPACITY", 2)
    for resource in ("audit_a", "audit_b", "audit_a", "audit_c", "audit_b"):
        reader.find(resource)
    assert sum(shape == template.shape for _, shape, _ in calls) == 4


def test_oversized_feature_payload_is_not_cached(visual_path, monkeypatch):
    reader, template, _, calls = visual_path
    monkeypatch.setattr(matcher, "TEMPLATE_FEATURE_BYTES", 1)
    reader.find("audit_template")
    reader.find("audit_template")
    assert sum(shape == template.shape for _, shape, _ in calls) == 2


def test_byte_budget_evicts_old_payloads_even_below_entry_capacity(
    visual_path, monkeypatch
):
    reader, template, _, _ = visual_path
    original = matcher.keypoints
    visits = []

    def controlled_features(image):
        if image.shape == template.shape:
            visits.append(1)
            return (
                [cv2.KeyPoint(float(index), 10.0, 1.0) for index in range(10)],
                np.zeros((10, 32), dtype=np.uint8),
            )
        return original(image)

    monkeypatch.setattr(matcher, "keypoints", controlled_features)
    monkeypatch.setattr(matcher, "TEMPLATE_FEATURE_BYTES", 700)
    for resource in ("audit_a", "audit_a", "audit_b", "audit_b", "audit_a"):
        reader.find(resource)
    assert len(visits) == 3


def test_extraction_failure_keeps_existing_matcher_failure_and_can_retry(
    visual_path, monkeypatch
):
    reader, template, _, _ = visual_path
    original = matcher.keypoints
    attempts = []

    def fail_first(image):
        if image.shape == template.shape:
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("template extraction failed")
        return original(image)

    monkeypatch.setattr(matcher, "keypoints", fail_first)
    for _ in range(3):
        assert reader.find("audit_template") is None
    assert len(attempts) == 2


def test_empty_origin_does_not_compile_template(visual_path):
    reader, template, _, calls = visual_path
    blank = np.zeros((192, 192), dtype=np.uint8)
    reader.set_frame((None, cv2.cvtColor(blank, cv2.COLOR_GRAY2RGB), blank))
    assert reader.find("audit_template") is None
    assert not any(shape == template.shape for _, shape, _ in calls)


def test_feature_snapshots_preserve_values_without_sharing_mutable_objects():
    image = np.random.default_rng(8).integers(0, 256, (80, 90), dtype=np.uint8)
    original_points, original_descriptors = matcher.keypoints(image)
    points, descriptors = matcher.resource_template_features("audit_template", image)
    assert [point.pt for point in points] == [point.pt for point in original_points]
    for actual, original in zip(points, original_points):
        assert (
            actual.size,
            actual.angle,
            actual.response,
            actual.octave,
            actual.class_id,
        ) == (
            original.size,
            original.angle,
            original.response,
            original.octave,
            original.class_id,
        )
    np.testing.assert_array_equal(descriptors, original_descriptors)
    expected = points[0].pt
    points[0].pt = (-1, -1)
    with pytest.raises(ValueError):
        descriptors[0, 0] ^= 255
    next_points, next_descriptors = matcher.resource_template_features(
        "audit_template", image
    )
    assert next_points[0].pt == expected
    np.testing.assert_array_equal(next_descriptors, original_descriptors)
    reference = weakref.ref(image)
    del image
    gc.collect()
    assert reference() is None


def test_cached_callbacks_do_not_keep_recognizer_alive(visual_path):
    frame = visual_path[2]
    reader = recognize.Recognizer(Mock())
    reader.set_frame((None, cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB), frame))
    reader.find("audit_template")
    reference = weakref.ref(reader)
    del reader
    gc.collect()
    assert reference() is None


@pytest.mark.parametrize("dpi_aware", [False, True])
def test_prepared_features_keep_real_matching_rectangle_and_scores(dpi_aware):
    template = np.random.default_rng(40).integers(0, 256, (80, 90), dtype=np.uint8)
    origin = np.zeros((192, 192), dtype=np.uint8)
    origin[50:130, 60:150] = template
    subject = matcher.Matcher(origin)
    cv2.setRNGSeed(18)
    expected = subject.score(template, dpi_aware=dpi_aware)
    cv2.setRNGSeed(18)
    actual = subject.score(
        template,
        dpi_aware=dpi_aware,
        query_features=partial(
            matcher.resource_template_features,
            "audit_template",
            template,
            dpi_aware=dpi_aware,
        ),
    )
    assert expected is not None
    assert actual[0] == expected[0] == [[60, 50], [150, 130]]
    np.testing.assert_allclose(actual[1], expected[1])


def test_concurrent_resource_requests_compile_once(visual_path):
    reader, template, _, calls = visual_path
    reader.matcher
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: reader.find("audit_template"), range(8)))
    assert sum(shape == template.shape for _, shape, _ in calls) == 1


def test_reload_waits_for_inflight_build_and_clears_it(visual_path, monkeypatch):
    reader, template, _, calls = visual_path
    reader.matcher
    entered, release, clearing = Event(), Event(), Event()
    original = matcher.keypoints

    def blocked(image):
        if image.shape == template.shape and not entered.is_set():
            entered.set()
            assert release.wait(2)
        return original(image)

    def clear():
        clearing.set()
        matcher.clear_template_feature_cache()

    monkeypatch.setattr(matcher, "keypoints", blocked)
    with ThreadPoolExecutor(max_workers=2) as executor:
        finding = executor.submit(reader.find, "audit_template")
        try:
            assert entered.wait(2)
            reloading = executor.submit(clear)
            assert clearing.wait(2)
        finally:
            release.set()
        finding.result(timeout=2)
        reloading.result(timeout=2)
    reader.find("audit_template")
    assert sum(shape == template.shape for _, shape, _ in calls) == 2
