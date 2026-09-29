"""One process-owned, ordered shutdown for desktop and server entry points."""

import logging
import os
from enum import IntEnum
from threading import Event, Lock, Thread, get_ident


class Phase(IntEnum):
    GATE = 0
    SIGNAL = 10
    INTERRUPT = 20
    WORKER = 30
    DEVICE = 40
    SCREENSHOTS = 50
    SERVER = 60
    UI = 70
    LOG_RELAY = 75
    CHANNEL = 80
    REGISTRATION = 90
    LOG = 100


class OwnedResource:
    def __init__(self, name, close, phase):
        self.name = name
        self.phase = phase
        self.owner_pid = os.getpid()
        self._close = close
        self._closed = False
        self._lock = Lock()

    def close(self):
        with self._lock:
            if self._closed or self.owner_pid != os.getpid():
                return
            self._closed = True
        self._close()


class Shutdown:
    def __init__(self):
        self.requested = Event()
        self.reason = None
        self.errors = []
        self._resources = []
        self._owned = {}
        self._lock = Lock()
        self._closed = False
        self._done = Event()
        self._closer = None
        self._watcher = None

    def watch(self):
        """Serve fatal worker requests also under a headless Flask launcher."""
        if self._watcher is None:
            self._watcher = Thread(target=self._watch, daemon=True)
            self._watcher.start()

    def _watch(self):
        self.requested.wait()
        self.close()

    @property
    def closing(self):
        return self.requested.is_set()

    def request(self, reason="exit"):
        # Safe from a failing worker or a signal handler: no joins or device I/O.
        if self.reason is None:
            self.reason = reason
        self.requested.set()

    def own(self, name, close, phase):
        with self._lock:
            if name in self._owned:
                return self._owned[name]
            resource = OwnedResource(name, close, phase)
            self._owned[name] = resource
            if not self._closed:
                self._resources.append(resource)
                return resource
        # A creator already in flight must not leak a late resource.
        self.release(resource)
        return resource

    def release(self, resource):
        try:
            resource.close()
        except Exception as exc:
            self.errors.append((resource.name, exc))
            logging.getLogger("arknights_mower.utils.log").exception(
                "关闭自有资源失败：%s", resource.name
            )

    def close(self, reason="exit"):
        self.request(reason)
        with self._lock:
            if self._closed:
                resources = None
            else:
                self._closed = True
                self._closer = get_ident()
                resources, self._resources = self._resources, []
        if resources is None:
            if self._closer != get_ident():
                self._done.wait(60)
            return
        try:
            for resource in sorted(resources, key=lambda item: item.phase):
                self.release(resource)
        finally:
            self._done.set()


shutdown = Shutdown()
