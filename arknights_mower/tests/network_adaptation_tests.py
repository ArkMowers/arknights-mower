"""Network facts qualify independently against half of each saved base budget."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils.network_adaptation import (
    NetworkAdaptation,
    get_network_adaptation,
)

NOW = datetime(2026, 10, 29, 0, 10)
WAIT_RECIPIENTS = ("CONNECTING", "LOADING", "LOGIN_LOADING")


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
    assert event is not None
    assert adaptation.peek_run_order(NOW, base_seconds=15) == event
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=30) is None
    taken = adaptation.take_run_order(NOW, event.event_id, base_seconds=15)
    assert taken == event
    assert 15 + taken.compensation_seconds == 24
    assert adaptation.take_wait("LOADING", NOW, base_seconds=30) is None
    assert adaptation.take_run_order(NOW, base_seconds=15) is None


def test_nine_seconds_qualifies_short_wait_but_not_fifty_second_run_buffer():
    adaptation = NetworkAdaptation()
    event = record(adaptation, 9)
    assert adaptation.peek_run_order(NOW, base_seconds=50) is None
    assert adaptation.take_run_order(NOW, base_seconds=50) is None
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=10) == event
    assert adaptation.peek_run_order(NOW, base_seconds=50) is None
    assert adaptation.take_run_order(NOW, base_seconds=15) == event


def test_run_order_peek_preserves_independent_one_time_wait_consumption():
    adaptation = NetworkAdaptation()
    event = record(adaptation)
    for _ in range(3):
        assert adaptation.peek_run_order(NOW, base_seconds=15) == event
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=30) == event
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=30) is None
    assert adaptation.peek_run_order(NOW, base_seconds=15) == event
    assert adaptation.take_run_order(NOW, event.event_id, base_seconds=15) == event
    assert adaptation.take_run_order(NOW, base_seconds=15) is None
    assert adaptation.peek_run_order(NOW, base_seconds=15) is None


def test_run_order_consumption_does_not_consume_wait_evidence():
    adaptation = NetworkAdaptation()
    event = record(adaptation, scene="LOGIN_CONNECTING")
    assert adaptation.take_run_order(NOW, base_seconds=15) == event
    assert adaptation.take_wait("LOADING", NOW, base_seconds=30) == event
    assert adaptation.take_wait("LOGIN_LOADING", NOW, base_seconds=30) is None


@pytest.mark.parametrize("source", ["CONNECTING", "LOGIN_CONNECTING"])
@pytest.mark.parametrize("duration", [0.1, 3, 9, 10, 30])
def test_all_positive_network_durations_are_facts_before_consumer_filtering(
    source, duration
):
    adaptation = NetworkAdaptation()
    event = record(adaptation, duration, source, base_seconds=30)
    assert event is not None
    assert event.scene == source
    assert event.duration_seconds == duration
    assert event.base_seconds == 30
    assert adaptation.observations == (event,)


@pytest.mark.parametrize(
    "source", ["LOADING", "LOGIN_LOADING", "UNKNOWN", "OPERATOR_ONGOING"]
)
def test_loading_publisher_logo_and_unrelated_scenes_never_produce_facts(source):
    adaptation = NetworkAdaptation()
    assert record(adaptation, 120, source, timed_out=True) is None
    assert adaptation.observations == ()
    assert adaptation.peek_run_order(NOW, base_seconds=15) is None
    for recipient in WAIT_RECIPIENTS:
        assert adaptation.take_wait(recipient, NOW, base_seconds=30) is None


@pytest.mark.parametrize("source", ["CONNECTING", "LOGIN_CONNECTING"])
@pytest.mark.parametrize("recipient", WAIT_RECIPIENTS)
def test_network_and_loading_recipients_share_one_wait_consumption(source, recipient):
    adaptation = NetworkAdaptation()
    event = record(adaptation, scene=source)
    assert adaptation.take_wait(recipient, NOW, base_seconds=30) == event
    for following in WAIT_RECIPIENTS:
        assert adaptation.take_wait(following, NOW, base_seconds=30) is None
    assert adaptation.take_run_order(NOW, base_seconds=15) == event


@pytest.mark.parametrize(
    "recipient", ["LOGIN_CONNECTING", "UNKNOWN", "OPERATOR_ONGOING"]
)
def test_unrelated_wait_recipient_cannot_consume_network_fact(recipient):
    adaptation = NetworkAdaptation()
    event = record(adaptation)
    assert adaptation.take_wait(recipient, NOW, base_seconds=30) is None
    assert adaptation.take_wait("LOADING", NOW, base_seconds=30) == event


def test_new_short_fact_does_not_hide_an_older_qualified_fact():
    adaptation = NetworkAdaptation()
    qualified = record(adaptation, 20)
    short = record(adaptation, 1, "LOGIN_CONNECTING", NOW + timedelta(seconds=1))
    now = NOW + timedelta(seconds=2)
    assert adaptation.observations == (qualified, short)
    assert adaptation.peek_run_order(now, base_seconds=30) == qualified
    assert adaptation.take_wait("LOADING", now, base_seconds=30) == qualified
    assert adaptation.take_run_order(now, base_seconds=30) == qualified


def test_each_consumer_selects_its_latest_qualifying_fact():
    adaptation = NetworkAdaptation()
    old = record(adaptation, 30)
    latest = record(adaptation, 9, "LOGIN_CONNECTING", NOW + timedelta(seconds=1))
    now = NOW + timedelta(seconds=2)
    assert adaptation.peek_run_order(now, base_seconds=15) == latest
    assert adaptation.take_wait("CONNECTING", now, base_seconds=30) == old
    assert adaptation.take_run_order(now, base_seconds=15) == latest
    assert adaptation.take_wait("LOGIN_LOADING", now, base_seconds=30) is None


def test_consumed_latest_qualified_fact_does_not_fall_back_to_older_qualified_fact():
    adaptation = NetworkAdaptation()
    old = record(adaptation, 30)
    latest = record(adaptation, 9, "LOGIN_CONNECTING", NOW + timedelta(seconds=1))
    record(adaptation, 1, at=NOW + timedelta(seconds=2))
    now = NOW + timedelta(seconds=3)
    assert adaptation.take_run_order(now, old.event_id, base_seconds=15) is None
    assert adaptation.take_run_order(now, latest.event_id, base_seconds=15) == latest
    assert adaptation.take_run_order(now, base_seconds=15) is None
    assert adaptation.take_wait("LOADING", now, base_seconds=10) == latest
    for recipient in WAIT_RECIPIENTS:
        assert adaptation.take_wait(recipient, now, base_seconds=10) is None


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


def test_new_short_facts_and_repeated_lookup_do_not_extend_old_qualified_fact_ttl():
    adaptation = NetworkAdaptation()
    event = record(adaptation)
    for minute in range(15):
        now = NOW + timedelta(minutes=minute)
        record(adaptation, 1, at=now)
        assert adaptation.peek_run_order(now, base_seconds=15) == event
    assert (
        adaptation.peek_run_order(NOW + timedelta(minutes=15), base_seconds=15) is None
    )


@pytest.mark.parametrize(
    "duration,base,qualified",
    [
        (7.49, 15, False),
        (7.5, 15, True),
        (9, 15, True),
        (14.99, 30, False),
        (15, 30, True),
        (1.49, 3, False),
        (1.5, 3, True),
        (59.99, 120, False),
        (60, 120, True),
    ],
)
def test_consumers_use_exactly_half_their_own_base_budget(duration, base, qualified):
    adaptation = NetworkAdaptation()
    event = record(adaptation, duration, base_seconds=30)
    assert event is not None
    expected = event if qualified else None
    assert adaptation.peek_run_order(NOW, base_seconds=base) == expected
    assert adaptation.take_run_order(NOW, base_seconds=base) == expected
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=base) == expected


def test_observed_timeout_does_not_override_consumer_half_budget_threshold():
    adaptation = NetworkAdaptation()
    event = record(adaptation, 3, base_seconds=3, timed_out=True)
    assert event.timed_out
    assert event.duration_seconds == event.compensation_seconds == 3
    assert event.base_seconds == 3
    assert adaptation.take_run_order(NOW, base_seconds=15) is None
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=30) is None
    assert adaptation.take_wait("LOADING", NOW, base_seconds=6) == event
    assert adaptation.take_run_order(NOW, base_seconds=6) == event


def test_wait_qualification_uses_target_timeout_instead_of_observation_source_base():
    adaptation = NetworkAdaptation()
    event = record(adaptation, 9, "LOGIN_CONNECTING", base_seconds=120)
    assert adaptation.take_wait("LOGIN_LOADING", NOW, base_seconds=30) is None
    assert adaptation.take_wait("CONNECTING", NOW, base_seconds=10) == event


def test_qualification_uses_raw_duration_before_compensation_is_capped():
    adaptation = NetworkAdaptation()
    event = record(adaptation, 180, timed_out=True)
    assert event.duration_seconds == 180
    assert event.compensation_seconds == 120
    assert adaptation.take_run_order(NOW, base_seconds=300) == event
    assert adaptation.take_wait("LOADING", NOW, base_seconds=300) == event


def test_new_qualified_fact_can_be_used_after_previous_consumption():
    adaptation = NetworkAdaptation()
    first = record(adaptation)
    adaptation.take_run_order(NOW, base_seconds=15)
    adaptation.take_wait("CONNECTING", NOW, base_seconds=30)
    second = record(adaptation, 25, "LOGIN_CONNECTING", NOW + timedelta(seconds=30))
    now = NOW + timedelta(seconds=31)
    assert second.event_id != first.event_id
    assert adaptation.take_run_order(now, base_seconds=15) == second
    assert adaptation.take_wait("LOGIN_LOADING", now, base_seconds=30) == second


def test_loading_after_consumption_cannot_renew_network_evidence():
    adaptation = NetworkAdaptation()
    record(adaptation)
    adaptation.take_run_order(NOW, base_seconds=15)
    adaptation.take_wait("CONNECTING", NOW, base_seconds=30)
    now = NOW + timedelta(seconds=30)
    assert record(adaptation, 30, "LOADING", now, timed_out=True) is None
    assert record(adaptation, 30, "LOGIN_LOADING", now, timed_out=True) is None
    assert adaptation.peek_run_order(now, base_seconds=15) is None
    for recipient in WAIT_RECIPIENTS:
        assert adaptation.take_wait(recipient, now, base_seconds=30) is None


def test_raw_observations_and_consumption_state_stay_bounded_at_1024():
    adaptation = NetworkAdaptation()
    for index in range(1100):
        now = NOW + timedelta(milliseconds=500 * index)
        event = record(adaptation, at=now)
        assert adaptation.take_run_order(now, base_seconds=15) == event
        assert adaptation.take_wait("CONNECTING", now, base_seconds=30) == event
    assert len(adaptation.observations) == 1024
    assert adaptation.observations[0].event_id == 77
    assert adaptation.observations[-1].event_id == 1100
    assert len(adaptation._run_order_used) == len(adaptation._waiting_used) == 1024


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
    assert record(adaptation, elapsed, base_seconds=baseline) is None
    assert adaptation.observations == ()


def test_wall_clock_rollback_does_not_treat_future_fact_as_recent():
    adaptation = NetworkAdaptation()
    record(adaptation)
    assert (
        adaptation.peek_run_order(NOW - timedelta(seconds=1), base_seconds=15) is None
    )


@pytest.mark.parametrize("owner", [SimpleNamespace(), MagicMock()])
def test_owner_keeps_one_adapter_even_if_missing_attributes_are_dynamic(owner):
    adaptation = get_network_adaptation(owner)
    assert isinstance(adaptation, NetworkAdaptation)
    assert get_network_adaptation(owner) is adaptation


def test_separate_instances_do_not_share_network_observations():
    first = get_network_adaptation(SimpleNamespace())
    second = get_network_adaptation(SimpleNamespace())
    record(first)
    assert second.peek_run_order(NOW, base_seconds=15) is None
