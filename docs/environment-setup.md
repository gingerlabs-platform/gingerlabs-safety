# Environment setup

The public VideoSeal CLI has no production service credentials. Normal release
users do not set environment variables.

Development and packaging support these optional local paths:

| Variable | Source |
| --- | --- |
| `FFMPEG_BIN`, `FFPROBE_BIN` | Absolute paths to trusted FFmpeg/FFprobe binaries used by PyInstaller. `scripts/build_release.py` sets them from its required command-line arguments. |
| `VIDEOSEAL_CLI_FFMPEG_DIR` | Optional directory containing both tools for an unpackaged developer run. Release archives bundle them. |
| `PIXELSEAL_TEST_CHECKPOINT` | Optional local path to the verified PixelSeal checkpoint for the loader integration test. It must match the SHA-256 documented in `README.md`. |

Do not add backend `WATERMARK_SECRET`, MongoDB, Telegram, AWS, or RunPod values
to this repository. The CLI receives only public `wm_v1_...` IDs and downloads
the public checksum-verified model.
