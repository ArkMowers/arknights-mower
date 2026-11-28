"""Bounded cleanup for a child process created by this mower process."""

import os


def close_process(
    process, owner_pid: int, *, timeout: float = 1, error_type=RuntimeError
) -> None:
    """Join before escalating, and never act on another process's children."""
    if process is None or owner_pid != os.getpid():
        return
    failures = []
    if process.pid is not None:
        for action in (None, process.terminate, process.kill):
            if action is not None:
                if not process.is_alive():
                    break
                try:
                    action()
                except Exception as exc:
                    failures.append(exc)
            try:
                process.join(timeout=timeout)
            except Exception as exc:
                failures.append(exc)
        if process.is_alive():
            failures.append(error_type("自有工作进程未能在限定时间退出"))
    if process.pid is None or not process.is_alive():
        try:
            process.close()
        except Exception as exc:
            failures.append(exc)
    if failures:
        for error in failures[1:]:
            failures[0].add_note(str(error))
        raise failures[0]
