"""Bound source history by explicit operation ownership, independently of rendering."""

import json
import re
from collections import OrderedDict

ID_ONLY_LOG_PARENT_TYPES = (
    "depot-scan",
    "facility-observation",
    "mood-calculation",
    "production-switch",
    "order-read",
)
_LIFECYCLES = {
    *ID_ONLY_LOG_PARENT_TYPES,
    "facility-arrangement",
    "rescue-staffing",
    "recruitment-slot",
}
_SCENE = re.compile(r"Scene:?\s+(-?)([0-9]+):\s*.*$")
_WAIT_SCENES = {"9", "9998", "-1"}


def record_text(record):
    """Render the unchanged source line for the legacy text representation."""
    msg, stamp, level = (
        record.get("msg", ""),
        record.get("t", ""),
        record.get("level", ""),
    )
    if stamp and level:
        return f"{stamp} {level} {msg}"
    return f"{stamp} {msg}" if stamp else msg


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 128


def _parent_reference(record):
    parent = record.get("parent")
    if not isinstance(parent, dict) or not _text(parent.get("id")):
        return None
    kind, identifier = parent.get("type"), parent["id"]
    if kind in ID_ONLY_LOG_PARENT_TYPES:
        return kind, identifier
    if kind == "facility-arrangement":
        room = parent.get("room")
        if _text(room) and record.get("room", room) == room:
            return kind, identifier, room
    elif kind == "recruitment-slot":
        slot = parent.get("slot")
        if type(slot) is int and 1 <= slot <= 4:
            return kind, identifier, slot
    elif kind == "rescue-staffing":
        room, attempt = parent.get("room"), parent.get("attempt")
        if "room" not in parent and "attempt" not in parent:
            return kind, identifier, None, None
        if _text(room) and _text(attempt):
            return kind, identifier, room, attempt
    return None


def _semantic_evidence(record):
    return (
        any(
            key in record
            for key in ("event", "task", "recruitment", "backups", "inventory")
        )
        or record.get("level") not in (None, "INFO")
        or isinstance(record.get("parent"), dict)
        and record["parent"].get("type") == "recruitment-slot"
        or _SCENE.search(record_text(record)) is not None
    )


def _event_spec(record):
    event = record.get("event")
    if (
        not isinstance(event, dict)
        or not isinstance(event.get("type"), str)
        or event["type"] not in _LIFECYCLES
    ):
        return None
    kind, identifier = event["type"], event.get("id")
    if not _text(identifier):
        return None
    phase, parent = event.get("phase"), record.get("parent")
    context = None
    if kind == "recruitment-slot":
        slot = event.get("slot")
        if (
            type(slot) is not int
            or not 1 <= slot <= 4
            or phase not in (None, "started", "completed", "failed", "stopped")
            or not isinstance(parent, dict)
            or any(parent.get(key) != event.get(key) for key in ("type", "id", "slot"))
        ):
            return None
        return (kind, identifier), (slot,), phase in (None, "started")
    start = "queued" if kind == "rescue-staffing" else "started"
    if kind in ID_ONLY_LOG_PARENT_TYPES and (
        isinstance(parent, dict)
        and parent.get("type") == kind
        and parent.get("id") != identifier
    ):
        return None
    if kind == "depot-scan":
        if (
            phase not in ("started", "updated", "completed", "failed", "stopped")
            or type(event.get("anchor")) is not bool
            or event["anchor"] != (phase == start)
        ):
            return None
        return (kind, identifier), (), event["anchor"]
    if (
        phase not in (start, "started", "updated", "waiting", "completed", "failed")
        or type(event.get("anchor")) is not bool
        or event["anchor"] != (phase == start)
    ):
        return None
    if kind == "mood-calculation":
        if not _text(event.get("label")) or phase == "waiting":
            return None
        return (kind, identifier), (event["label"],), event["anchor"]
    if kind == "facility-observation" and phase not in (
        "started",
        "completed",
        "failed",
    ):
        return None
    if kind in ("facility-arrangement", "facility-observation", "production-switch"):
        if not all(_text(event.get(key)) for key in ("room", "label")):
            return None
        signature = (event["room"], event["label"])
        if kind == "production-switch":
            signature += (event.get("facility"), event.get("product"))
        elif isinstance(parent, dict):
            if parent.get("type") == "rescue-staffing":
                context = tuple(parent.get(key) for key in ("id", "room", "attempt"))
            elif (
                kind == "facility-arrangement"
                and parent.get("type") == kind
                and (
                    parent.get("id") != identifier
                    or parent.get("room") != event["room"]
                )
            ):
                return None
        signature += (context,)
    else:
        rooms = event.get("rooms")
        if not isinstance(rooms, list) or not rooms:
            return None
        if not all(
            isinstance(room, dict)
            and all(_text(room.get(key)) for key in ("room", "label"))
            for room in rooms
        ):
            return None
        signature = tuple(
            (room["room"], room["label"], room.get("agents"))
            if kind == "rescue-staffing"
            else (room["room"], room["label"])
            for room in rooms
        )
        if kind == "order-read":
            signature += (event.get("after_switch"),)
    return (kind, identifier), signature, event["anchor"]


class LogHistory:
    def __init__(self, limit, detail_limit, source_limit, byte_limit, envelope_bytes):
        self.limit = max(0, limit)
        self.detail_limit = max(0, detail_limit)
        self.source_limit = max(0, source_limit)
        self.byte_limit = max(envelope_bytes, byte_limit)
        self.envelope_bytes = envelope_bytes
        self.records = OrderedDict()
        self.groups = OrderedDict()
        self.operations = {}
        self.pending = {}
        self.owners = {}
        self.protected = set()
        self.weights = {}
        self.weight = 0
        self.closed_waits = {}
        self.open_waits = []
        self.wait_scene = None

    def _parent_owner(self, record):
        parent = record.get("parent")
        reference = _parent_reference(record)
        if reference is None:
            return None
        operation = self.operations.get(reference[:2])
        if operation is None:
            return self.pending.get(reference)
        group, _, event = operation
        kind = parent.get("type")
        if kind in ID_ONLY_LOG_PARENT_TYPES:
            return group
        if kind == "facility-arrangement":
            if (
                parent.get("room") != event["room"]
                or record.get("room", parent["room"]) != parent["room"]
            ):
                return None
        elif kind == "recruitment-slot":
            if type(parent.get("slot")) is not int or parent["slot"] != event["slot"]:
                return None
        elif kind == "rescue-staffing":
            if "room" in parent or "attempt" in parent:
                if (
                    not _text(parent.get("attempt"))
                    or not _text(parent.get("room"))
                    or parent["room"] not in {room["room"] for room in event["rooms"]}
                ):
                    return None
        else:
            return None
        return group

    def _pending_anchor_owner(self, spec, event):
        key, signature, anchor = spec
        if not anchor or (
            key[0] == "facility-arrangement" and signature[-1] is not None
        ):
            return None
        if key[0] in ID_ONLY_LOG_PARENT_TYPES:
            return self.pending.get(key)
        for reference, group in self.pending.items():
            if reference[:2] != key:
                continue
            if key[0] == "facility-arrangement" and reference[2] == event["room"]:
                return group
            if key[0] == "recruitment-slot" and reference[2] == event["slot"]:
                return group
            if key[0] == "rescue-staffing" and (
                reference[2] is None
                or reference[2] in {room["room"] for room in event["rooms"]}
            ):
                return group
        return None

    def append(self, record):
        seq = record["seq"]
        spec = _event_spec(record)
        reference = _parent_reference(record)
        group = self._parent_owner(record)
        event = record.get("event")
        if (
            isinstance(event, dict)
            and isinstance(event.get("type"), str)
            and event.get("type") in _LIFECYCLES
            and spec is None
        ):
            group, reference = None, None
        if spec is not None:
            key, signature, anchor = spec
            operation = self.operations.get(key)
            if operation is not None:
                if operation[1] == signature and not (
                    key[0] == "recruitment-slot" and anchor
                ):
                    group = operation[0]
                else:
                    # Conflicting identities remain literal source entries.
                    group, spec, reference = None, None, None
            elif group is None:
                group = self._pending_anchor_owner(spec, event)
        if group is None:
            group = seq
            self.groups[group] = []
        self.groups[group].append(seq)
        self.owners[seq] = group
        self.records[seq] = record
        if spec is not None and spec[2] and spec[0] not in self.operations:
            self.operations[spec[0]] = (group, spec[1], event)
            self.pending = {
                ref: owner
                for ref, owner in self.pending.items()
                if owner != group or ref[:2] != spec[0]
            }
            if group in self.records and not _semantic_evidence(self.records[group]):
                self.protected.discard(group)
        if reference is not None and reference[:2] not in self.operations:
            # Context is bound before actual entry. Reserve its quota without
            # inventing an anchor or changing how these sources are displayed.
            self.pending[reference] = group
        scene = _SCENE.search(record_text(record))
        # Keep semantic evidence verbatim. Only ordinary diagnostics are disposable.
        if (seq == group and reference is None) or _semantic_evidence(record):
            self.protected.add(seq)
        if scene:
            number = scene[1] + scene[2].lstrip("0")
            wait_scene = number if number in _WAIT_SCENES else None
            if wait_scene != self.wait_scene:
                self.closed_waits.update((start, seq) for start in self.open_waits)
                self.open_waits = []
                self.wait_scene = wait_scene
            if wait_scene is not None:
                self.open_waits.append(seq)
        # Count the exact default JSON encoding of records and legacy data together.
        weight = (
            len(json.dumps(record).encode("utf-8"))
            + len(json.dumps(record_text(record)).encode("utf-8"))
            - 2
        )
        self.weights[seq] = weight
        self.weight += weight
        before = set(self.records)
        self._trim()
        return sorted(before - self.records.keys())

    def _drop(self, seq):
        group = self.owners.pop(seq)
        self.groups[group].remove(seq)
        del self.records[seq]
        self.weight -= self.weights.pop(seq)
        self.protected.discard(seq)
        if not self.groups[group]:
            del self.groups[group]
            self.operations = {
                key: value
                for key, value in self.operations.items()
                if value[0] != group
            }
            self.pending = {
                key: owner for key, owner in self.pending.items() if owner != group
            }

    def _drop_group(self, group):
        for seq in list(self.groups[group]):
            self._drop(seq)

    def _over_budget(self):
        # Each extra record adds ', ' in records and escaped '\n' in data.
        size = self.envelope_bytes + self.weight + 4 * max(0, len(self.records) - 1)
        return len(self.records) > self.source_limit or size > self.byte_limit

    def _trim(self):
        while len(self.groups) > self.limit:
            self._drop_group(next(iter(self.groups)))
        for members in list(self.groups.values()):
            details = [seq for seq in members if seq not in self.protected]
            for seq in details[: max(0, len(details) - self.detail_limit)]:
                self._drop(seq)
        for seq in list(self.records):
            if not self._over_budget():
                break
            if seq not in self.protected:
                self._drop(seq)
        while self.groups and self._over_budget():
            self._drop_group(next(iter(self.groups)))
        # A removed closing scene must not turn a retained historical wait active.
        changed = True
        while changed:
            changed = False
            for start, end in list(self.closed_waits.items()):
                if start in self.records and end not in self.records:
                    spec = _event_spec(self.records[start])
                    if spec is not None and spec[2]:
                        self._drop_group(self.owners[start])
                    else:
                        self._drop(start)
                    changed = True
                if start not in self.records:
                    del self.closed_waits[start]
        self.open_waits = [seq for seq in self.open_waits if seq in self.records]
