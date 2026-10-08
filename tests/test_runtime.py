"""Check portable defaults and containment of local runtime configuration."""
import json
from pathlib import Path
import tempfile
import unittest

from runtime_config import active_environment, contained_path, read_config


class RuntimeTests(unittest.TestCase):
    def test_fresh_checkout_uses_local_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.assertIsNone(read_config(root))
            self.assertEqual(active_environment(root), root / ".venv")

    def test_existing_custom_runtime_is_respected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = {"version": 1, "environment": ".runtimes/example",
                      "speaker_models": ".runtimes/example/models/speakers"}
            (root / "runtime.json").write_text(json.dumps(config), encoding="utf-8")
            self.assertEqual(read_config(root), (root / ".runtimes/example",
                                                 root / ".runtimes/example/models/speakers"))

    def test_paths_cannot_escape_application_root(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in ("../outside", ".", directory, ""):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    contained_path(value, directory)

    def test_speaker_cache_must_belong_to_selected_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {"version": 1, "environment": ".runtimes/example",
                      "speaker_models": "models/speakers"}
            (Path(directory) / "runtime.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_config(directory)


if __name__ == "__main__":
    unittest.main()
