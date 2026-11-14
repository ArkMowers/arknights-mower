import unittest
from threading import Event, Thread
from unittest.mock import patch

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, cancellation_scope, csleep


class CancellationScopeTests(unittest.TestCase):
    def setUp(self):
        self.stop = Event()
        self.stop.set()
        self.enterContext(patch.object(config, "stop_mower", self.stop))

    def test_settings_scope_preserves_task_signal_and_restores_policy(self):
        with cancellation_scope(lambda: False):
            csleep(0)
        self.assertTrue(self.stop.is_set())
        with self.assertRaises(MowerExit):
            csleep(0)

    def test_nested_scope_restores_parent_after_cancellation(self):
        with cancellation_scope(lambda: False):
            with self.assertRaises(MowerExit):
                with cancellation_scope(lambda: True):
                    csleep(0)
            csleep(0)
        with self.assertRaises(MowerExit):
            csleep(0)

    def test_scoped_wait_observes_shutdown_after_sleep(self):
        closing = Event()
        with (
            cancellation_scope(closing.is_set),
            patch(
                "arknights_mower.utils.csleep.time.sleep",
                side_effect=lambda seconds: closing.set(),
            ) as sleep,
            self.assertRaises(MowerExit),
        ):
            csleep(1)
        sleep.assert_called_once()

    def test_settings_scope_does_not_change_another_threads_task_cancellation(self):
        outcomes = []

        def task_wait():
            try:
                csleep(0)
            except MowerExit:
                outcomes.append("cancelled")

        with cancellation_scope(lambda: False):
            worker = Thread(target=task_wait)
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            csleep(0)
        self.assertEqual(outcomes, ["cancelled"])
