import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gingerlabs_moderation.detectors as detectors


class ModerationDetectorTests(unittest.TestCase):
    def test_xywh_box_is_converted_to_xyxy(self):
        self.assertEqual(detectors._xywh_to_xyxy([10, 20, 30, 40]), (10, 20, 40, 60))

    def test_cached_exact_parts_model_must_match_pinned_hash(self):
        payload = b"pinned-model-fixture"
        expected_hash = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_root = Path(temporary_directory)
            target = cache_root / detectors.ERAX_REVISION / detectors.ERAX_FILENAME
            target.parent.mkdir(parents=True)
            target.write_bytes(payload)

            with mock.patch.object(detectors, "ERAX_SHA256", expected_hash):
                resolved = detectors.exact_parts_model_path(cache_root)

            self.assertEqual(resolved, target)

    def test_model_download_is_hash_verified(self):
        payload = b"downloaded-model-fixture"
        expected_hash = hashlib.sha256(payload).hexdigest()
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = [payload, b""]
        response.__exit__.return_value = False

        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                mock.patch.object(detectors, "ERAX_SHA256", expected_hash),
                mock.patch.object(detectors.urllib.request, "urlopen", return_value=response),
            ):
                resolved = detectors.exact_parts_model_path(Path(temporary_directory))

            self.assertEqual(resolved.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
