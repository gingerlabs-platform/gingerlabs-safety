import contextlib
import io
import unittest

from videoseal_cli.cli import build_parser


class CliTests(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_embed_uses_pixel_seal_low_impact_defaults(self):
        args = self.parser.parse_args(
            [
                "embed",
                "--input",
                "input.mp4",
                "--output",
                "output.mp4",
                "--id",
                "wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw",
            ]
        )
        self.assertEqual(args.model, "pixelseal")
        self.assertEqual(args.device, "auto")
        self.assertEqual(args.scaling_w, 0.15)
        self.assertEqual(args.chunk_size, 8)
        self.assertTrue(args.full_resolution_jnd)
        self.assertFalse(args.temporal_pooling)
        self.assertEqual(args.temporal_pool_size, 4)
        self.assertEqual(args.temporal_pool_depth, 2)
        self.assertFalse(hasattr(args, "step_size"))
        self.assertFalse(hasattr(args, "video_mode"))
        self.assertFalse(hasattr(args, "lowres_attenuation"))

    def test_detect_defaults_to_pixelseal_avg_and_eight_frames(self):
        args = self.parser.parse_args(["detect", "--input", "input.mp4"])
        self.assertEqual(args.model, "pixelseal")
        self.assertEqual(args.chunk_size, 8)
        self.assertEqual(args.aggregation, "avg")

    def test_rejects_retired_model_and_flags(self):
        cases = [
            ["detect", "--input", "input.mp4", "--model", "videoseal"],
            [
                "embed",
                "--input",
                "input.mp4",
                "--output",
                "output.mp4",
                "--id",
                "wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw",
                "--step-size",
                "4",
            ],
            [
                "embed",
                "--input",
                "input.mp4",
                "--output",
                "output.mp4",
                "--id",
                "wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw",
                "--video-mode",
                "repeat",
            ],
            [
                "embed",
                "--input",
                "input.mp4",
                "--output",
                "output.mp4",
                "--id",
                "wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw",
                "--lowres-attenuation",
            ],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.parser.parse_args(arguments)


if __name__ == "__main__":
    unittest.main()
