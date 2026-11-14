"""Retain bounded operation history without losing lifecycle evidence."""

import json

import pytest

from arknights_mower.utils.log_stream import LogStream


def snapshot(stream):
    subscription = stream.subscribe()
    result = json.loads(subscription.messages.get_nowait())
    stream.unsubscribe(subscription)
    return result


def facility(identifier, phase="started", room="recycle", **extra):
    return {
        "msg": phase,
        "event": {
            "type": "facility-arrangement",
            "id": identifier,
            "phase": phase,
            "anchor": phase == "started",
            "room": room,
            "label": room,
            "agents": ["行铃"],
        },
        **extra,
    }


def parent(identifier, room="recycle"):
    return {"type": "facility-arrangement", "id": identifier, "room": room}


@pytest.mark.parametrize(
    "kind", ["facility-arrangement", "recruitment-slot", "rescue-staffing"]
)
def test_details_before_the_anchor_reserve_one_operation_entry(kind):
    stream = LogStream(history_limit=3)
    stream.publish("older-1")
    stream.publish("older-2")
    scope = parent("current")
    anchor = facility("current")
    if kind == "recruitment-slot":
        scope = {"type": kind, "id": "current", "slot": 1}
        anchor = {"msg": "started", "event": {**scope, "phase": "started"}}
    elif kind == "rescue-staffing":
        scope = {"type": kind, "id": "current", "room": "recycle", "attempt": "attempt"}
        anchor = {
            "msg": "queued",
            "event": {
                "type": kind,
                "id": "current",
                "phase": "queued",
                "anchor": True,
                "rooms": [
                    {
                        "room": "recycle",
                        "label": "recycle",
                        "agents": ["行铃"],
                        "status": "pending",
                    }
                ],
            },
        }
    for message in ("entering facility", "opening facility details"):
        stream.publish({"msg": message, "parent": scope})
        assert snapshot(stream)["records"][:2] == [
            {"msg": "older-1", "seq": 1},
            {"msg": "older-2", "seq": 2},
        ]
    stream.publish({**anchor, "parent": scope})
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "older-1",
        "older-2",
        "entering facility",
        "opening facility details",
        anchor["msg"],
    ]


@pytest.mark.parametrize(
    "kind,metadata,terminal",
    [
        ("depot-scan", {}, "stopped"),
        (
            "facility-observation",
            {"room": "room_1_2", "label": "制造站 B102"},
            "failed",
        ),
        ("mood-calculation", {"label": "基建调度"}, "completed"),
        (
            "production-switch",
            {
                "room": "room_1_2",
                "label": "制造站 B102",
                "facility": "manufacture",
                "product": "赤金",
            },
            "completed",
        ),
        (
            "order-read",
            {
                "rooms": [{"room": "room_2_1", "label": "贸易站 B201"}],
                "after_switch": False,
            },
            "completed",
        ),
    ],
)
def test_id_only_parent_groups_details_and_keeps_anchor_and_terminal(
    kind, metadata, terminal
):
    stream = LogStream(history_limit=2, detail_limit=1)
    scope = {"type": kind, "id": "one"}
    event = {**scope, **metadata, "phase": "started", "anchor": True}
    stream.publish("other")
    stream.publish({"msg": "early", "parent": scope})
    stream.publish({"msg": "started", "event": event, "parent": scope})
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "other",
        "early",
        "started",
    ]

    stream.publish({"msg": "newest", "parent": scope})
    stream.publish(
        {"msg": terminal, "event": {**event, "phase": terminal, "anchor": False}}
    )
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "other",
        "started",
        "newest",
        terminal,
    ]

    stream.publish({"msg": "separate", "parent": {**scope, "id": "two"}})
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "started",
        "newest",
        terminal,
        "separate",
    ]


def test_pending_first_detail_is_disposable_after_the_real_anchor():
    stream = LogStream(history_limit=2, detail_limit=2)
    stream.publish("older")
    for index in range(4):
        stream.publish({"msg": f"before-{index}", "parent": parent("current")})
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "older",
        "before-2",
        "before-3",
    ]
    stream.publish(facility("current"))
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "older",
        "before-2",
        "before-3",
        "started",
    ]
    stream.publish({"msg": "after", "parent": parent("current")})
    stream.publish(facility("current", "completed"))
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "older",
        "before-3",
        "started",
        "after",
        "completed",
    ]


def test_evicted_pending_references_do_not_accumulate_or_capture_later_anchors():
    stream = LogStream(history_limit=2)
    for index in range(20):
        stream.publish({"msg": f"pending-{index}", "parent": parent(str(index))})
        assert len(stream._history.pending) <= 2
    stream.publish(facility("0"))
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "pending-19",
        "started",
    ]
    assert len(stream._history.pending) == 1


@pytest.mark.parametrize(
    "evidence",
    [
        {"msg": "Scene 9: waiting"},
        {"msg": "读取设施失败", "level": "WARNING"},
        {"msg": "重设行铃至空闲", "event": {"type": "operator-reset-idle"}},
    ],
)
def test_late_anchor_keeps_semantic_evidence_from_the_first_pending_record(evidence):
    stream = LogStream(detail_limit=0)
    stream.publish({**evidence, "parent": parent("current")})
    stream.publish(facility("current"))
    stream.publish({"msg": "ordinary detail", "parent": parent("current")})
    stream.publish(facility("current", "completed"))
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        evidence["msg"],
        "started",
        "completed",
    ]
    assert not stream._history.pending


def test_byte_budget_clears_pending_ownership_before_a_later_anchor():
    stream = LogStream(history_bytes=800)
    stream.publish({"msg": "x" * 2000, "parent": parent("current")})
    assert snapshot(stream)["records"] == []
    assert not stream._history.pending
    stream.publish(facility("current"))
    assert [row["msg"] for row in snapshot(stream)["records"]] == ["started"]


def test_conflicting_late_anchor_does_not_adopt_pending_details():
    stream = LogStream(history_limit=2)
    for index in range(2):
        stream.publish({"msg": f"pending-{index}", "parent": parent("same")})
    stream.publish(facility("same", room="meeting"))
    stream.publish("other")
    assert [row["msg"] for row in snapshot(stream)["records"]] == ["started", "other"]


def test_details_do_not_displace_one_hundred_top_level_entries():
    stream = LogStream()
    for index in range(99):
        stream.publish(f"ordinary-{index}")
    stream.publish(facility("last"))
    for index in range(150):
        stream.publish({"msg": f"detail-{index}", "parent": parent("last")})
    stream.publish(facility("last", "completed"))

    history = snapshot(stream)
    records = history["records"]
    assert [record["msg"] for record in records[:99]] == [
        f"ordinary-{index}" for index in range(99)
    ]
    assert [record["msg"] for record in records if "parent" in record] == [
        f"detail-{index}" for index in range(100, 150)
    ]
    assert [record["event"]["phase"] for record in records if "event" in record] == [
        "started",
        "completed",
    ]
    assert history["data"].splitlines() == [record["msg"] for record in records]


def test_live_evictions_and_reconnect_have_identical_sources():
    stream = LogStream(history_limit=2, detail_limit=2)
    subscription = stream.subscribe()
    initial = json.loads(subscription.messages.get_nowait())
    assert initial["snapshot"] is True and initial["records"] == []
    retained = {}
    for record in [
        facility("first"),
        *[{"msg": str(index), "parent": parent("first")} for index in range(5)],
        facility("first", "completed"),
        "second",
        "third",
    ]:
        stream.publish(record)
        message = json.loads(subscription.messages.get_nowait())
        assert message["snapshot"] is False
        assert message["stream_id"] == initial["stream_id"]
        retained.update((row["seq"], row) for row in message["records"])
        for seq in message["evicted"]:
            retained.pop(seq, None)
        assert list(retained.values()) == snapshot(stream)["records"]
    assert [row["msg"] for row in retained.values()] == ["second", "third"]


def test_nested_rescue_attempts_share_the_top_level_budget():
    stream = LogStream(history_limit=2, detail_limit=1)
    rescue = {
        "type": "rescue-staffing",
        "id": "rescue",
        "phase": "queued",
        "anchor": True,
        "rooms": [
            {
                "room": "recycle",
                "label": "recycle",
                "agents": ["行铃"],
                "status": "pending",
            }
        ],
    }
    stream.publish({"msg": "queued", "event": rescue})
    scope = {
        "type": "rescue-staffing",
        "id": "rescue",
        "room": "recycle",
        "attempt": "attempt",
    }
    stream.publish(facility("attempt", parent=scope))
    for index in range(5):
        stream.publish({"msg": f"detail-{index}", "parent": scope})
    stream.publish(facility("attempt", "completed", parent=scope))
    stream.publish("other")
    records = snapshot(stream)["records"]
    assert [row["msg"] for row in records] == [
        "queued",
        "started",
        "detail-4",
        "completed",
        "other",
    ]


def test_unknown_or_conflicting_parent_uses_an_independent_source_entry():
    stream = LogStream(history_limit=2)
    stream.publish(facility("first"))
    stream.publish({"msg": "unknown", "parent": parent("missing")})
    stream.publish(
        facility("first", "completed", room="meeting", parent=parent("first"))
    )
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "unknown",
        "completed",
    ]


@pytest.mark.parametrize("value", [[], {}, ["facility-arrangement"]])
@pytest.mark.parametrize("field", ["event", "parent"])
def test_malformed_identity_is_forwarded_as_an_independent_source(field, value):
    stream = LogStream(history_limit=1)
    stream.publish(facility("first"))
    record = {"msg": "malformed", field: {"type": value, "id": "first"}}
    stream.publish(record)
    assert snapshot(stream)["records"] == [{**record, "seq": 2}]


@pytest.mark.parametrize("room", [[], {}, None, 17, True])
def test_malformed_rescue_room_uses_an_independent_source(room):
    stream = LogStream(history_limit=1)
    stream.publish(
        {
            "msg": "queued",
            "event": {
                "type": "rescue-staffing",
                "id": "rescue",
                "phase": "queued",
                "anchor": True,
                "rooms": [
                    {
                        "room": "recycle",
                        "label": "recycle",
                        "agents": ["行铃"],
                        "status": "pending",
                    }
                ],
            },
        }
    )
    record = {
        "msg": "invalid room",
        "parent": {
            "type": "rescue-staffing",
            "id": "rescue",
            "room": room,
            "attempt": "attempt",
        },
    }
    stream.publish(record)
    assert snapshot(stream)["records"] == [{**record, "seq": 2}]


@pytest.mark.parametrize("number", [9, 9998, -1])
def test_wait_scene_end_survives_detail_trimming(number):
    stream = LogStream(detail_limit=1)
    stream.publish(facility("first"))
    stream.publish({"msg": f"Scene {number}: waiting", "parent": parent("first")})
    stream.publish({"msg": "Scene 201: ended", "parent": parent("first")})
    for index in range(3):
        stream.publish({"msg": str(index), "parent": parent("first")})
    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "started",
        f"Scene {number}: waiting",
        "Scene 201: ended",
        "2",
    ]


def test_hard_record_limit_keeps_evidence_or_evicts_the_whole_operation():
    stream = LogStream(source_limit=4, detail_limit=50)
    stream.publish(facility("first"))
    for index in range(10):
        stream.publish({"msg": str(index), "parent": parent("first")})
    stream.publish(facility("first", "completed"))
    stream.publish(facility("first", "updated"))
    records = snapshot(stream)["records"]
    assert len(records) == 4
    assert [row["event"]["phase"] for row in records if "event" in row] == [
        "started",
        "completed",
        "updated",
    ]
    stream.publish(facility("first", "failed"))
    stream.publish(facility("first", "completed"))
    assert snapshot(stream)["records"] == []


def test_history_budget_counts_both_wire_representations_and_escaped_unicode():
    budget = 1600
    stream = LogStream(history_bytes=budget)
    for _ in range(20):
        stream.publish({"msg": "回收站\n" * 20, "event": {"type": "unknown"}})
        history = snapshot(stream)
        assert len(json.dumps(history).encode("utf-8")) <= budget
        assert history["data"] == "\n".join(row["msg"] for row in history["records"])
    assert len(history["records"]) < 20


def test_evicted_scene_end_cannot_revive_an_older_wait():
    stream = LogStream(history_limit=2)
    stream.publish(facility("old"))
    stream.publish({"msg": "Scene 9: 连接中"})
    stream.publish({"msg": "Scene 201: 基建", "parent": parent("old")})
    stream.publish("new")
    records = snapshot(stream)["records"]
    assert all("Scene 9:" not in row["msg"] for row in records)


def test_evicted_scene_end_does_not_remove_an_unrelated_operation():
    stream = LogStream(history_limit=2)
    stream.publish(facility("old"))
    stream.publish({"msg": "Scene 9: 连接中", "parent": parent("current")})
    stream.publish(facility("current"))
    stream.publish({"msg": "Scene 201: 基建", "parent": parent("old")})
    stream.publish(facility("current", "completed"))
    stream.publish("new")

    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "started",
        "completed",
        "new",
    ]


def test_large_scene_number_does_not_interrupt_log_delivery():
    stream = LogStream()
    scene = f"Scene {'1' * 5000}: unknown"
    stream.publish("Scene 9: 连接中")
    stream.publish(scene)
    stream.publish("next")

    assert [row["msg"] for row in snapshot(stream)["records"]] == [
        "Scene 9: 连接中",
        scene,
        "next",
    ]


def test_snapshot_isolation_includes_every_mutable_record_field():
    stream = LogStream()
    record = facility("a", agents=["行铃"])
    stream.publish(record)
    expected = snapshot(stream)["records"]
    record["agents"].append("旅骨")
    record["event"]["agents"].append("旅骨")
    assert snapshot(stream)["records"] == expected


def test_clear_notifies_existing_subscribers_and_starts_a_new_stream():
    stream = LogStream()
    subscription = stream.subscribe()
    previous = json.loads(subscription.messages.get_nowait())
    stream.publish("old")
    subscription.messages.get_nowait()
    stream.clear()
    cleared = json.loads(subscription.messages.get_nowait())
    assert cleared["snapshot"] is True and cleared["records"] == []
    assert cleared["stream_id"] != previous["stream_id"]
    stream.publish("new")
    live = json.loads(subscription.messages.get_nowait())
    assert live["stream_id"] == cleared["stream_id"]
    assert live["records"] == [{"msg": "new", "seq": 1}]
