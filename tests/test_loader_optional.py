import os
import unittest
from pathlib import Path


class LoaderOptionalTests(unittest.TestCase):
    def test_preseeded_checkpoint_reports_256_bits(self):
        checkpoint = os.environ.get("VIDEOSEAL_TEST_CHECKPOINT")
        if not checkpoint:
            self.skipTest("set VIDEOSEAL_TEST_CHECKPOINT to run loader integration test")

        from videoseal_cli.inference_model import build_videoseal_from_checkpoint
        from videoseal_cli.model import model_nbits

        model = build_videoseal_from_checkpoint(Path(checkpoint))
        self.assertEqual(model_nbits(model), 256)


if __name__ == "__main__":
    unittest.main()
