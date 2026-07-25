import hashlib
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from videoseal_cli import model_cache


class ModelCacheTests(unittest.TestCase):
    def model_constants(self, source: Path, payload: bytes, filename: str = "pixelseal.pth"):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(model_cache, "MODEL_URL", source.as_uri()))
        stack.enter_context(mock.patch.object(model_cache, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()))
        stack.enter_context(mock.patch.object(model_cache, "MODEL_FILENAME", filename))
        stack.enter_context(mock.patch.object(model_cache, "MODEL_SIZE_BYTES", len(payload)))
        return stack

    def test_downloads_and_verifies_to_cache(self):
        payload = b"pixel-seal-checkpoint"
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            source = tmpdir / "source.pth"
            cache = tmpdir / "cache"
            source.write_bytes(payload)

            with self.model_constants(source, payload):
                resolved = model_cache.resolve_model_path(str(cache), offline=False, force_download=False)

            self.assertEqual(resolved.resolve(), (cache / "pixelseal.pth").resolve())
            self.assertEqual(resolved.read_bytes(), payload)

    def test_corrupt_cache_is_replaced_when_online(self):
        payload = b"valid-checkpoint"
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            source = tmpdir / "source.pth"
            cache = tmpdir / "cache"
            cache.mkdir()
            source.write_bytes(payload)
            (cache / "pixelseal.pth").write_bytes(b"corrupt")

            with self.model_constants(source, payload):
                resolved = model_cache.resolve_model_path(str(cache), offline=False, force_download=False)

            self.assertEqual(resolved.read_bytes(), payload)

    def test_force_download_replaces_valid_cache(self):
        old_payload = b"old"
        new_payload = b"new"
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            source = tmpdir / "source.pth"
            cache = tmpdir / "cache"
            cache.mkdir()
            source.write_bytes(new_payload)
            (cache / "pixelseal.pth").write_bytes(old_payload)

            with self.model_constants(source, new_payload):
                resolved = model_cache.resolve_model_path(str(cache), offline=False, force_download=True)

            self.assertEqual(resolved.read_bytes(), new_payload)

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

    def test_old_videoseal_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "videoseal_y_256b_img.pth").write_bytes(b"retired-model")
            with self.assertRaises(RuntimeError):
                model_cache.resolve_model_path(str(cache), offline=True, force_download=False)
            self.assertTrue((cache / "videoseal_y_256b_img.pth").is_file())


if __name__ == "__main__":
    unittest.main()
