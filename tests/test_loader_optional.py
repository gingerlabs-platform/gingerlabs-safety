import os
import unittest
from pathlib import Path


class LoaderOptionalTests(unittest.TestCase):
    def test_preseeded_pixelseal_checkpoint_loads_strictly(self):
        checkpoint = os.environ.get("PIXELSEAL_TEST_CHECKPOINT")
        if not checkpoint:
            self.skipTest("set PIXELSEAL_TEST_CHECKPOINT to run loader integration test")

        from videoseal_cli.inference_model import build_pixelseal_from_checkpoint
        from videoseal_cli.model import model_nbits

        model = build_pixelseal_from_checkpoint(Path(checkpoint))
        self.assertEqual(model_nbits(model), 256)
        self.assertEqual(type(model.embedder).__name__, "UnetEmbedder")
        self.assertEqual(type(model.detector).__name__, "ConvnextExtractor")
        self.assertEqual(model.img_size, 256)


if __name__ == "__main__":
    unittest.main()
