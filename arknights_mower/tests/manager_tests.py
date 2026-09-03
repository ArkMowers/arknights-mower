import tempfile
import unittest
from pathlib import Path

from manager import Api


class ManagerApiTests(unittest.TestCase):
    def test_instances_are_stored_at_explicit_writable_path(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            storage_path = Path(temporary_dir) / "nested" / "instances.json"
            api = Api(storage_path)

            api.add("default", "/tmp/mower-data")

            reloaded = Api(storage_path)
            self.assertEqual(
                reloaded.get_instances(),
                [{"name": "default", "path": "/tmp/mower-data"}],
            )


if __name__ == "__main__":
    unittest.main()
