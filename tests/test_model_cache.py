import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from videoseal_cli import model_cache


class ModelCacheTests(unittest.TestCase):
    def test_downloads_and_verifies_to_cache(self):
        payload = b"checkpoint-bytes"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            source = tmpdir / "source.pth"
            cache = tmpdir / "cache"
            source.write_bytes(payload)

            with mock.patch.object(model_cache, "MODEL_URL", source.as_uri()), \
                 mock.patch.object(model_cache, "MODEL_SHA256", digest), \
                 mock.patch.object(model_cache, "MODEL_FILENAME", "model.pth"), \
                 mock.patch.object(model_cache, "MODEL_SIZE_BYTES", len(payload)):
                resolved = model_cache.resolve_model_path(str(cache), offline=False, force_download=False)

            self.assertEqual(resolved.resolve(), (cache / "model.pth").resolve())
            self.assertEqual(resolved.read_bytes(), payload)

    def test_offline_requires_cached_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                model_cache.resolve_model_path(tmp, offline=True, force_download=False)

    def test_rejects_corrupt_cached_model_when_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / model_cache.MODEL_FILENAME).write_bytes(b"bad")
            with self.assertRaises(RuntimeError):
                model_cache.resolve_model_path(str(cache), offline=True, force_download=False)


if __name__ == "__main__":
    unittest.main()
