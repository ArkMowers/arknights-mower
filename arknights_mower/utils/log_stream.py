"""Keep WebSocket I/O out of the shared log consumer."""

import json
from copy import deepcopy
from queue import Empty, Full, Queue
from threading import Event, Lock
from uuid import uuid4

from simple_websocket import ConnectionClosed

from arknights_mower.utils.log_history import LogHistory, record_text


class Subscription:
    def __init__(self, capacity):
        self.messages = Queue(maxsize=capacity)
        self.closed = Event()


class LogStream:
    def __init__(
        self,
        history_limit=100,
        pending_limit=100,
        *,
        detail_limit=50,
        source_limit=2000,
        history_bytes=4 * 1024 * 1024,
    ):
        self._history_limits = (
            history_limit,
            detail_limit,
            source_limit,
            history_bytes,
        )
        self._pending_limit = pending_limit
        self._subscriptions = set()
        self._lock = Lock()
        self._reset_history()

    def _reset_history(self):
        self._stream_id = uuid4().hex
        self._next_seq = 1
        envelope_bytes = len(
            json.dumps(self._message([], snapshot=True)).encode("utf-8")
        )
        self._history = LogHistory(*self._history_limits, envelope_bytes)

    def _message(self, records, *, snapshot=False, evicted=None):
        message = {
            "type": "log",
            "stream_id": self._stream_id,
            "snapshot": snapshot,
            "data": "\n".join(record_text(record) for record in records),
            "records": records,
        }
        if not snapshot:
            message["evicted"] = evicted or []
        return message

    def clear(self):
        with self._lock:
            self._reset_history()
            self._broadcast(self._message([], snapshot=True))

    def subscribe(self):
        with self._lock:
            subscription = Subscription(self._pending_limit)
            subscription.messages.put_nowait(
                json.dumps(
                    self._message(list(self._history.records.values()), snapshot=True)
                )
            )
            self._subscriptions.add(subscription)
            return subscription

    def unsubscribe(self, subscription):
        with self._lock:
            self._subscriptions.discard(subscription)
            subscription.closed.set()

    def publish(self, record):
        """Publish one log record (dict) or legacy text string."""
        record = deepcopy(record) if isinstance(record, dict) else {"msg": record}
        with self._lock:
            record["seq"] = self._next_seq
            self._next_seq += 1
            evicted = self._history.append(record)
            self._broadcast(self._message([record], evicted=evicted))

    def broadcast(self, message):
        with self._lock:
            self._broadcast(message)

    def _broadcast(self, message):
        payload = json.dumps(message)
        for subscription in tuple(self._subscriptions):
            try:
                subscription.messages.put_nowait(payload)
            except Full:
                # A slow client reconnects to the latest history. Never let its
                # backlog grow indefinitely or block other clients/logging.
                subscription.closed.set()
                self._subscriptions.discard(subscription)

    def serve(self, ws):
        subscription = self.subscribe()
        try:
            while not subscription.closed.is_set():
                # Check for disconnects even when no new logs are produced.
                ws.receive(timeout=0)
                try:
                    payload = subscription.messages.get(timeout=1)
                except Empty:
                    continue
                ws.send(payload)
        except (ConnectionClosed, OSError):
            # Closing a tab, sleep and network changes are normal disconnects.
            # Only this request owns its socket writes and teardown.
            pass
        finally:
            self.unsubscribe(subscription)
            try:
                ws.close()
            except (ConnectionClosed, OSError):
                pass
