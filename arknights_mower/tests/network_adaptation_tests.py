"""Only completed CONNECTING facts supply bounded, purpose-specific protection."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from arknights_mower.utils.network_adaptation import (
    NetworkAdaptation,
    get_network_adaptation,
)

NOW = datetime(2026, 10, 29, 0, 10)
WAIT_RECIPIENTS = ("CONNECTING", "LOADING")


def record(adaptation, seconds=30, scene="CONNECTING", at=NOW, **kwargs):
    return adaptation.record(
        scene,
        elapsed_seconds=seconds,
        base_seconds=kwargs.pop("base_seconds", 10),
        observed_at=at,
        **kwargs,
    )


def test_nine_seconds_qualifies_run_order_but_not_thirty_second_wait():
    adaptation = NetworkAdaptation()
    event = record(adaptation, 9, base_seconds=30)

    assert adaptation.peek_run_order(NOW, base_seconds=15) == event
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=30) is None
    assert adaptation.take_run_order(NOW, event.event_id, base_seconds=15) == event
    assert 15 + event.compensation_seconds == 24
    assert adaptation.take_wait("LOADING", NOW, base_seconds=30) is None
    assert adaptation.take_run_order(NOW, base_seconds=15) == event


def test_waiting_consumption_and_shared_run_order_reads_are_independent():
    adaptation = NetworkAdaptation()
    event = record(adaptation)

    for _ in range(3):
        assert adaptation.take_run_order(NOW, base_seconds=15) == event
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=30) == event
    assert adaptation.take_wait("LOADING", NOW, base_seconds=30) is None
    assert adaptation.peek_run_order(NOW, base_seconds=15) == event
    assert adaptation.take_run_order(NOW, base_seconds=15) == event


@pytest.mark.parametrize("duration", [0.1, 3, 9, 10, 30])
def test_all_positive_connecting_durations_are_recorded_before_qualification(duration):
    adaptation = NetworkAdaptation()
    event = record(adaptation, duration, base_seconds=30)

    assert event.scene == "CONNECTING"
    assert event.duration_seconds == duration
    assert event.base_seconds == 30
    assert adaptation.observations == (event,)


@pytest.mark.parametrize(
    "source",
    ["LOADING", "LOGIN_LOADING", "LOGIN_CONNECTING", "UNKNOWN", "OPERATOR_ONGOING"],
)
def test_other_scenes_never_create_or_renew_network_facts(source):
    adaptation = NetworkAdaptation()
    callback = Mock()
    adaptation.set_observation_callback(callback)

    assert record(adaptation, 120, source, timed_out=True) is None
    assert adaptation.observations == ()
    assert adaptation.peek_run_order(NOW, base_seconds=15) is None
    callback.assert_not_called()


@pytest.mark.parametrize("recipient", WAIT_RECIPIENTS)
def test_connecting_and_loading_share_one_wait_consumption(recipient):
    adaptation = NetworkAdaptation()
    event = record(adaptation)

    assert adaptation.take_wait(recipient, NOW, base_seconds=30) == event
    for following in WAIT_RECIPIENTS:
        assert adaptation.take_wait(following, NOW, base_seconds=30) is None
    assert adaptation.take_run_order(NOW, base_seconds=15) == event


@pytest.mark.parametrize(
    "recipient", ["LOGIN_LOADING", "LOGIN_CONNECTING", "UNKNOWN", "OPERATOR_ONGOING"]
)
def test_unrelated_wait_recipient_cannot_consume_network_fact(recipient):
    adaptation = NetworkAdaptation()
    event = record(adaptation)

    assert adaptation.take_wait(recipient, NOW, base_seconds=30) is None
    assert adaptation.take_wait("LOADING", NOW, base_seconds=30) == event


def test_later_ten_second_record_does_not_replace_larger_thirty_second_record():
    adaptation = NetworkAdaptation()
    largest = record(adaptation, 30)
    smaller = record(adaptation, 10, at=NOW + timedelta(seconds=1))
    now = NOW + timedelta(seconds=2)

    assert adaptation.observations == (largest, smaller)
    assert adaptation.peek_run_order(now, base_seconds=15) == largest
    assert adaptation.take_wait("LOADING", now, base_seconds=30) == largest
    assert adaptation.take_wait("CONNECTING", now, base_seconds=15) == smaller
    assert adaptation.take_wait("LOADING", now, base_seconds=15) is None
    assert adaptation.peek_run_order(now, base_seconds=15) == largest


def test_waiting_selects_largest_unconsumed_record_even_when_it_is_older():
    adaptation = NetworkAdaptation()
    older = record(adaptation, 20)
    newer = record(adaptation, 30, at=NOW + timedelta(seconds=1))
    now = NOW + timedelta(seconds=2)

    assert adaptation.take_wait("CONNECTING", now, base_seconds=30) == newer
    assert adaptation.take_wait("LOADING", now, base_seconds=30) == older
    assert adaptation.take_wait("CONNECTING", now, base_seconds=30) is None


def test_equal_largest_durations_prefer_newer_fact():
    adaptation = NetworkAdaptation()
    older = record(adaptation, 30)
    newer = record(adaptation, 30, at=NOW + timedelta(seconds=1))
    now = NOW + timedelta(seconds=2)

    assert adaptation.peek_run_order(now, base_seconds=15) == newer
    assert adaptation.take_run_order(now, older.event_id, base_seconds=15) is None
    assert adaptation.take_wait("LOADING", now, base_seconds=30) == newer
    assert adaptation.take_wait("CONNECTING", now, base_seconds=30) == older


def test_expired_fact_is_unavailable_at_the_fifteen_minute_boundary():
    adaptation = NetworkAdaptation()
    event = record(adaptation)
    before_expiry = NOW + timedelta(minutes=15, microseconds=-1)

    assert adaptation.peek_run_order(before_expiry, base_seconds=15) == event
    expiry = NOW + timedelta(minutes=15)
    assert adaptation.take_run_order(expiry, event.event_id, base_seconds=15) is None
    for recipient in WAIT_RECIPIENTS:
        assert adaptation.take_wait(recipient, expiry, base_seconds=30) is None
    assert adaptation.observations == ()


def test_each_fact_expires_independently_without_later_short_fact_renewing_maximum():
    adaptation = NetworkAdaptation()
    older = record(adaptation, 30)
    newer = record(adaptation, 10, at=NOW + timedelta(minutes=14))
    before = NOW + timedelta(minutes=14, seconds=59)

    for _ in range(3):
        assert adaptation.peek_run_order(before, base_seconds=15) == older
    assert (
        adaptation.peek_run_order(NOW + timedelta(minutes=15), base_seconds=15) == newer
    )
    assert (
        adaptation.peek_run_order(NOW + timedelta(minutes=29), base_seconds=15) is None
    )


@pytest.mark.parametrize(
    "duration,base,qualified",
    [
        (7.49, 15, False),
        (7.5, 15, False),
        (7.51, 15, True),
        (9, 15, True),
        (14.99, 30, False),
        (15, 30, False),
        (15.01, 30, True),
        (1.5, 3, False),
        (1.51, 3, True),
        (60, 120, False),
        (60.01, 120, True),
    ],
)
def test_consumers_require_strictly_more_than_half_their_own_base(
    duration, base, qualified
):
    adaptation = NetworkAdaptation()
    event = record(adaptation, duration, base_seconds=30)
    expected = event if qualified else None

    assert adaptation.peek_run_order(NOW, base_seconds=base) == expected
    assert adaptation.take_run_order(NOW, base_seconds=base) == expected
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=base) == expected


def test_timeout_flag_does_not_override_strict_purpose_threshold():
    adaptation = NetworkAdaptation()
    event = record(adaptation, 3, base_seconds=3, timed_out=True)

    assert event.timed_out
    assert adaptation.take_run_order(NOW, base_seconds=15) is None
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=6) is None
    assert adaptation.take_wait("LOADING", NOW, base_seconds=5) == event


def test_wait_qualification_uses_target_timeout_not_source_base():
    adaptation = NetworkAdaptation()
    event = record(adaptation, 9, base_seconds=120)

    assert adaptation.take_wait("LOADING", NOW, base_seconds=30) is None
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=10) == event


def test_raw_duration_qualifies_before_ninety_second_compensation_cap():
    adaptation = NetworkAdaptation()
    event = record(adaptation, 180, timed_out=True)

    assert event.duration_seconds == 180
    assert event.compensation_seconds == 90
    assert adaptation.take_run_order(NOW, base_seconds=300) == event
    assert adaptation.take_wait("LOADING", NOW, base_seconds=300) == event
    assert adaptation.peek_run_order(NOW, base_seconds=360) is None


@pytest.mark.parametrize(
    "duration,expected", [(89.9, 89.9), (90, 90), (90.1, 90), (120, 90)]
)
def test_compensation_is_capped_at_ninety_seconds(duration, expected):
    event = record(NetworkAdaptation(), duration)

    assert event.duration_seconds == duration
    assert event.compensation_seconds == expected


def test_record_notifies_current_callback_once_after_storing_fact():
    adaptation = NetworkAdaptation()
    seen = []
    adaptation.set_observation_callback(
        lambda event: seen.append((event, adaptation.observations))
    )

    event = record(adaptation)

    assert seen == [(event, (event,))]
    for _ in range(3):
        adaptation.peek_run_order(NOW, base_seconds=15)
        adaptation.take_run_order(NOW, base_seconds=15)
    assert seen == [(event, (event,))]
    adaptation.set_observation_callback(None)
    record(adaptation, 20)
    assert len(seen) == 1


def test_replacing_callback_does_not_keep_previous_instance_listener():
    adaptation = NetworkAdaptation()
    old, current = Mock(), Mock()
    adaptation.set_observation_callback(old)
    adaptation.set_observation_callback(current)

    event = record(adaptation)

    old.assert_not_called()
    current.assert_called_once_with(event)


def test_observations_and_wait_consumption_remain_bounded():
    adaptation = NetworkAdaptation()
    for index in range(1100):
        now = NOW + timedelta(milliseconds=500 * index)
        event = record(adaptation, at=now)
        assert adaptation.take_wait("CONNECTING", now, base_seconds=30) == event
    assert len(adaptation.observations) == 1024
    assert adaptation.observations[0].event_id == 77
    assert adaptation.observations[-1].event_id == 1100
    assert len(adaptation._waiting_used) == 1024


@pytest.mark.parametrize(
    "elapsed,baseline",
    [
        (0, 10),
        (-1, 10),
        (float("nan"), 10),
        (float("inf"), 10),
        (30, 0),
        (30, -1),
        (30, float("inf")),
    ],
)
def test_invalid_timing_values_never_create_facts(elapsed, baseline):
    adaptation = NetworkAdaptation()
    callback = Mock()
    adaptation.set_observation_callback(callback)

    assert record(adaptation, elapsed, base_seconds=baseline) is None
    assert adaptation.observations == ()
    callback.assert_not_called()


def test_wall_clock_rollback_does_not_make_future_fact_recent():
    adaptation = NetworkAdaptation()
    record(adaptation)

    assert (
        adaptation.peek_run_order(NOW - timedelta(seconds=1), base_seconds=15) is None
    )


@pytest.mark.parametrize("owner", [SimpleNamespace(), MagicMock()])
def test_owner_keeps_one_adapter_despite_dynamic_missing_attributes(owner):
    adaptation = get_network_adaptation(owner)

    assert isinstance(adaptation, NetworkAdaptation)
    assert get_network_adaptation(owner) is adaptation


def test_instances_do_not_share_facts_or_callbacks():
    first = get_network_adaptation(SimpleNamespace())
    second = get_network_adaptation(SimpleNamespace())
    listener = Mock()
    second.set_observation_callback(listener)
    record(first)

    assert second.peek_run_order(NOW, base_seconds=15) is None
    listener.assert_not_called()
