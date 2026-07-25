import argparse
import sys


def bounded_number(value_type, minimum, maximum):
    def parse(value):
        parsed = value_type(value)
        if parsed < minimum or parsed > maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return parsed

    return parse


def add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", choices=["pixelseal"], default="pixelseal")
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument("--model-cache-dir", default=None, help="Directory for the downloaded PixelSeal checkpoint.")
    parser.add_argument("--offline", action="store_true", help="Use only an already cached checkpoint.")
    parser.add_argument("--force-model-download", action="store_true", help="Redownload and reverify the checkpoint.")
    parser.add_argument("--chunk-size", type=bounded_number(int, 1, 128), default=8)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="videoseal-cli",
        description="Embed and detect RS-protected PixelSeal watermark IDs directly in video pixels.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    embed = subparsers.add_parser("embed", help="Embed a canonical wm_v1 watermark ID into video pixels.")
    embed.add_argument("--input", required=True, help="Input video path.")
    embed.add_argument("--output", required=True, help="Output watermarked video path.")
    embed.add_argument("--id", required=True, help="Canonical wm_v1 ID containing a 16-byte Base64URL payload.")
    add_runtime_args(embed)
    embed.add_argument("--scaling-w", type=bounded_number(float, 0.01, 1.0), default=0.15)
    embed.add_argument(
        "--full-resolution-jnd",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply JND attenuation at the original frame resolution.",
    )
    embed.add_argument(
        "--temporal-pooling",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable PixelSeal temporal pooling.",
    )
    embed.add_argument("--temporal-pool-size", type=bounded_number(int, 2, 16), default=4)
    embed.add_argument("--temporal-pool-depth", type=bounded_number(int, 1, 7), default=2)
    embed.add_argument("--codec", default="h264", help="ffmpeg video codec. h264 maps to libx264.")
    embed.add_argument("--crf", type=int, default=12)
    embed.add_argument("--pix-fmt", default="yuv420p")
    embed.add_argument("--preset", default="medium")
    embed.add_argument("--copy-audio", action="store_true", help="Mux the original input audio into the output.")

    detect = subparsers.add_parser("detect", help="Detect a text watermark ID from video pixels.")
    detect.add_argument("--input", required=True, help="Input video path.")
    detect.add_argument("--expected-id", default=None, help="Optional expected watermark ID for match/accuracy reporting.")
    add_runtime_args(detect)
    detect.add_argument(
        "--aggregation",
        choices=["avg", "squared_avg", "l1norm_avg", "l2norm_avg"],
        default="avg",
    )
    detect.add_argument("--format", choices=["json", "text", "both"], default="both")

    doctor = subparsers.add_parser("doctor", help="Check bundled runtime tools and model cache status.")
    doctor.add_argument("--model-cache-dir", default=None, help="Directory for downloaded VideoSeal checkpoints.")
    doctor.add_argument("--download-model", action="store_true", help="Download and verify the model during the check.")
    doctor.add_argument("--force-model-download", action="store_true", help="Redownload and reverify the checkpoint.")
    doctor.add_argument("--format", choices=["json", "text"], default="text")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "embed":
            from .commands import embed_command, print_embed_result

            result = embed_command(args)
            print_embed_result(result)
            return 0
        if args.command == "detect":
            from .commands import detect_command, print_detect_result

            result = detect_command(args)
            print_detect_result(result, args.format)
            return 0
        if args.command == "doctor":
            from .commands import doctor_command, print_doctor_result

            result = doctor_command(args)
            print_doctor_result(result, args.format)
            return 0 if result["ok"] else 1
    except Exception as exc:
        print(f"videoseal-cli: error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2
