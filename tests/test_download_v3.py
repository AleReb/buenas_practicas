import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import download_v3
from download_v3 import atomic_json


class AtomicJsonTests(unittest.TestCase):
    def test_retries_a_transient_windows_file_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "checkpoint.json"
            destination.write_text('{"rows": 0}', encoding="utf-8")
            real_replace = download_v3.os.replace
            attempts = 0

            def replace_after_transient_lock(source, target):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("archivo temporalmente bloqueado")
                real_replace(source, target)

            with (
                patch("download_v3.os.replace", side_effect=replace_after_transient_lock),
                patch("download_v3.time.sleep") as sleep,
            ):
                atomic_json(destination, {"rows": 500, "complete": False})

            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                {"rows": 500, "complete": False},
            )
            self.assertEqual(attempts, 2)
            sleep.assert_called_once_with(0.05)
            self.assertFalse(destination.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
