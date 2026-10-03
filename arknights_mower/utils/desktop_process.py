"""macOS GUI helpers without multiprocessing's persistent resource tracker.

Cocoa needs a fresh process. An inherited pipe provides the small command
channel without shared semaphores or a separate resource-tracking process.
"""

import os
import subprocess
import sys
from multiprocessing import Pipe, parent_process
from multiprocessing.connection import Connection
from pathlib import Path
from queue import Empty
from threading import Lock, Thread
from time import sleep


class Channel:
    def __init__(self, connection, writer=None):
        self.connection = connection
        self.writer = writer if writer is not None else connection
        self.write_lock = Lock()
        self.owner_pid = os.getpid()
        self.closed = False

    def send(self, message):
        with self.write_lock:
            self.writer.send(message)

    put = send
    put_nowait = send

    def recv(self):
        return self.connection.recv()

    def get(self, block=True, timeout=None):
        if not self.connection.poll(timeout if block else 0):
            raise Empty
        return self.recv()

    def close(self):
        if self.closed or self.owner_pid != os.getpid():
            return
        self.closed = True
        errors = []
        ends = (
            (self.connection,)
            if self.writer is self.connection
            else (
                self.connection,
                self.writer,
            )
        )
        for end in ends:
            try:
                end.close()
            except Exception as exc:
                errors.append(exc)
        if errors:
            for error in errors[1:]:
                errors[0].add_note(str(error))
            raise errors[0]


def log_channel():
    """Reusable single-reader log queue; children inherit only its write end."""
    return Channel(*Pipe(duplex=False))


class DesktopProcess:
    """The process operations used by the shared desktop cleanup routine."""

    def __init__(self, process, channel):
        self.process = process
        self.channel = channel
        self.pid = process.pid
        self.owner_pid = os.getpid()

    def is_alive(self):
        return self.process.poll() is None

    def join(self, timeout=None):
        try:
            self.process.wait(timeout)
        except subprocess.TimeoutExpired:
            return
        self.channel.close()

    def terminate(self):
        self.process.terminate()

    def kill(self):
        self.process.kill()

    def close(self):
        self.channel.close()


def start_worker(kind, *args, log_queue=None):
    parent, child = Pipe()
    channel = Channel(parent)
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(__file__).resolve().parents[2] / "webview_ui.py"))
    command.extend(["--desktop-worker", kind, str(child.fileno())])
    descriptors = [child.fileno()]
    if log_queue is not None:
        descriptors.append(log_queue.writer.fileno())
        command.append(str(log_queue.writer.fileno()))
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    try:
        process = subprocess.Popen(command, pass_fds=tuple(descriptors), env=env)
    except BaseException:
        channel.close()
        raise
    finally:
        child.close()
    worker = DesktopProcess(process, channel)
    try:
        # Keep instance paths and browser tokens off the process command line.
        channel.send(args)
    except BaseException as error:
        from arknights_mower.utils.device.owned import close_process

        for cleanup in (
            channel.close,
            lambda: close_process(worker, worker.owner_pid),
        ):
            try:
                cleanup()
            except Exception as cleanup_error:
                error.add_note(f"关闭部分初始化的桌面资源失败：{cleanup_error}")
        raise
    return worker, channel


def watch_parent():
    """Exit a GUI helper when its controller disappears, including SIGKILL."""
    parent = parent_process()
    parent_pid = os.getppid()

    def alive():
        if parent is not None:
            return parent.is_alive()
        return parent_pid != 1 and os.getppid() == parent_pid

    def monitor():
        while alive():
            sleep(0.5)
        os._exit(0)

    Thread(target=monitor, daemon=True).start()


def run_worker(target, descriptor, log_descriptor=None):
    channel = Channel(Connection(int(descriptor)))
    log_queue = (
        Channel(Connection(int(log_descriptor), readable=False))
        if log_descriptor is not None
        else None
    )
    watch_parent()
    try:
        args = channel.recv()
        if log_queue is None:
            target(channel, *args)
        else:
            target(channel, *args, log_queue=log_queue)
    finally:
        channel.close()
        if log_queue is not None:
            log_queue.close()
