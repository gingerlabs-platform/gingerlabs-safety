import argparse
import sys


def add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default="videoseal", help="Only 'videoseal' is supported in standalone v1.")
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="cpu")
    parser.add_argument("--model-cache-dir", default=None, help="Directory for downloaded VideoSeal checkpoints.")
    parser.add_argument("--offline", action="store_true", help="Use only an already cached checkpoint.")
    parser.add_argument("--force-model-download", action="store_true", help="Redownload and reverify the checkpoint.")
    parser.add_argument("--chunk-size", type=int, default=16)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="videoseal-cli",
        description="Embed and detect VideoSeal text watermarks directly in video pixels.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    embed = subparsers.add_parser("embed", help="Embed a text watermark ID into video pixels.")
    embed.add_argument("--input", required=True, help="Input video path.")
    embed.add_argument("--output", required=True, help="Output watermarked video path.")
    embed.add_argument("--id", required=True, help="Text watermark ID to embed.")
    add_runtime_args(embed)
    embed.add_argument("--scaling-w", type=float, default=0.2)
    embed.add_argument("--step-size", type=int, default=4)
    embed.add_argument("--video-mode", choices=["repeat", "interpolate", "alternate"], default="repeat")
    embed.add_argument("--lowres-attenuation", dest="lowres_attenuation", action="store_true", default=True)
    embed.add_argument("--no-lowres-attenuation", dest="lowres_attenuation", action="store_false")
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
