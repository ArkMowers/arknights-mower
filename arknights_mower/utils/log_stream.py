"""Keep WebSocket I/O out of the shared log consumer."""

import json
from collections import deque
from queue import Empty, Full, Queue
from threading import Event, Lock

from simple_websocket import ConnectionClosed


class Subscription:
    def __init__(self, capacity):
        self.messages = Queue(maxsize=capacity)
        self.closed = Event()


class LogStream:
    def __init__(self, history_limit=100, pending_limit=100):
        self._history = deque(maxlen=history_limit)
        self._pending_limit = pending_limit
        self._subscriptions = set()
        self._lock = Lock()

    def clear(self):
        with self._lock:
            self._history.clear()

    def subscribe(self):
        with self._lock:
            subscription = Subscription(self._pending_limit)
            subscription.messages.put_nowait(
                json.dumps({"type": "log", "data": "\n".join(self._history)})
            )
            self._subscriptions.add(subscription)
            return subscription

    def unsubscribe(self, subscription):
        with self._lock:
            self._subscriptions.discard(subscription)
            subscription.closed.set()

    def publish(self, message):
        with self._lock:
            self._history.append(message)
            self._broadcast({"type": "log", "data": message})

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
