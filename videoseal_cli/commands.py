import json
import tempfile
from pathlib import Path

from .model_cache import default_model_cache_dir, resolve_model_path, verify_model_file
from .payload import bit_accuracy_percent, expected_bits, legacy_wm_v1_to_message_bits
from .runtime_tools import resolve_tool
from .video_io import move_video, mux_audio_from_source, read_video_rgb, write_video_rgb_h264


def embed_command(args) -> dict:
    from .model import configure_model, frames_to_video_tensor, load_model, message_tensor, model_nbits, video_tensor_to_uint8

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if input_path == output_path:
        raise ValueError("--output must be different from --input")

    frames, fps = read_video_rgb(input_path)

    model, device, torch = load_model(
        args.model,
        args.device,
        args.model_cache_dir,
        args.offline,
        args.force_model_download,
    )
    configure_model(
        model,
        scaling_w=args.scaling_w,
        chunk_size=args.chunk_size,
        step_size=args.step_size,
        video_mode=args.video_mode,
    )

    nbits = model_nbits(model)
    msg = message_tensor(args.id, nbits, device)
    video = frames_to_video_tensor(frames, device)

    with torch.inference_mode():
        outputs = model.embed(
            video,
            msgs=msg,
            is_video=True,
            lowres_attenuation=bool(args.lowres_attenuation),
        )
        watermarked = video_tensor_to_uint8(outputs["imgs_w"])

    with tempfile.TemporaryDirectory(prefix="videoseal_cli_") as tmpdir:
        temp_video = Path(tmpdir) / "watermarked_silent.mp4"
        write_video_rgb_h264(
            watermarked,
            temp_video,
            fps=fps,
            crf=args.crf,
            pix_fmt=args.pix_fmt,
            codec=args.codec,
            preset=args.preset,
        )
        if args.copy_audio:
            mux_audio_from_source(temp_video, input_path, output_path)
        else:
            move_video(temp_video, output_path)

    return {
        "input": str(input_path),
        "output": str(output_path),
        "watermark_id": args.id,
        "frames_processed": int(frames.shape[0]),
        "fps": fps,
        "message_bits": nbits,
        "model": args.model,
        "device": str(device),
        "scaling_w": args.scaling_w,
        "chunk_size": args.chunk_size,
        "step_size": args.step_size,
        "video_mode": args.video_mode,
        "lowres_attenuation": bool(args.lowres_attenuation),
        "codec": args.codec,
        "crf": args.crf,
        "pix_fmt": args.pix_fmt,
        "copy_audio": bool(args.copy_audio),
    }


def detect_command(args) -> dict:
    from .model import aggregate_logits, configure_model, decode_soft_bits, frames_to_video_tensor, load_model, model_nbits

    input_path = Path(args.input).expanduser().resolve()
    frames, _fps = read_video_rgb(input_path)

    model, device, torch = load_model(
        args.model,
        args.device,
        args.model_cache_dir,
        args.offline,
        args.force_model_download,
    )
    configure_model(model, chunk_size=args.chunk_size)

    nbits = model_nbits(model)
    video = frames_to_video_tensor(frames, device)

    with torch.inference_mode():
        outputs = model.detect(video, is_video=True)
        logits = outputs["preds"][:, 1:]
        soft_bits = aggregate_logits(logits, args.aggregation)
        decoded_watermark_id, decoded_bits, format_valid, payload_encoding = decode_soft_bits(soft_bits)

    expected_id = (args.expected_id or "").strip() or None
    accuracy = None
    match = None
    if expected_id is not None:
        expected = expected_bits(expected_id, nbits)
        accuracy = bit_accuracy_percent(decoded_bits, expected)
        match = decoded_watermark_id == expected_id
        try:
            legacy_expected = [bool(bit) for bit in legacy_wm_v1_to_message_bits(expected_id, nbits)]
            accuracy = max(accuracy, bit_accuracy_percent(decoded_bits, legacy_expected))
        except ValueError:
            pass

    confidence = float(torch.sigmoid(torch.abs(soft_bits)).mean().item() * 100.0)
    return {
        "decoded_watermark_id": decoded_watermark_id,
        "expected_watermark_id": expected_id,
        "match": match,
        "bit_accuracy_percent": accuracy,
        "confidence_percent": confidence,
        "frames_checked": int(frames.shape[0]),
        "message_bits": nbits,
        "aggregation": args.aggregation,
        "payload_encoding": payload_encoding,
        "model": args.model,
        "device": str(device),
        "input": str(input_path),
        "format_valid": bool(format_valid),
    }


def doctor_command(args) -> dict:
    checks = {}
    for tool in ("ffmpeg", "ffprobe"):
        try:
            checks[tool] = {"ok": True, "path": resolve_tool(tool)}
        except Exception as exc:
            checks[tool] = {"ok": False, "error": str(exc)}

    cache_dir = Path(args.model_cache_dir).expanduser().resolve() if args.model_cache_dir else default_model_cache_dir()
    model_path = cache_dir / "videoseal_y_256b_img.pth"
    if args.download_model:
        try:
            model_path = resolve_model_path(args.model_cache_dir, offline=False, force_download=args.force_model_download)
        except Exception as exc:
            checks["model"] = {"ok": False, "path": str(model_path), "error": str(exc)}
        else:
            checks["model"] = {"ok": True, "path": str(model_path), "cached": True}
    else:
        model_exists = model_path.exists()
        model_verified = verify_model_file(model_path) if model_exists else False
        checks["model"] = {
            "ok": True,
            "path": str(model_path),
            "cached": model_exists,
            "verified": model_verified,
            "status": "cached" if model_verified else "will download on first embed/detect",
        }

    try:
        import numpy
        import torch

        checks["python_runtime"] = {
            "ok": True,
            "torch": torch.__version__,
            "numpy": numpy.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
        }
    except Exception as exc:
        checks["python_runtime"] = {"ok": False, "error": str(exc)}

    return {"ok": all(item.get("ok") for item in checks.values()), "checks": checks}


def print_embed_result(result: dict) -> None:
    print(json.dumps(result, indent=2))


def print_detect_result(result: dict, output_format: str) -> None:
    if output_format in {"json", "both"}:
        print(json.dumps(result, indent=2))
    if output_format == "both":
        print()
    if output_format in {"text", "both"}:
        match = result["match"]
        match_text = "not checked" if match is None else str(bool(match)).lower()
        accuracy = result["bit_accuracy_percent"]
        accuracy_text = "not checked" if accuracy is None else f"{accuracy:.2f}%"
        print(f"decoded_watermark_id: {result['decoded_watermark_id']}")
        print(f"expected_watermark_id: {result['expected_watermark_id'] or 'not provided'}")
        print(f"match: {match_text}")
        print(f"bit_accuracy_percent: {accuracy_text}")
        print(f"confidence_percent: {result['confidence_percent']:.2f}%")
        print(f"frames_checked: {result['frames_checked']}")
        print(f"message_bits: {result['message_bits']}")
        print(f"aggregation: {result['aggregation']}")
        print(f"payload_encoding: {result['payload_encoding']}")


def print_doctor_result(result: dict, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, indent=2))
        return
    print(f"ok: {str(bool(result['ok'])).lower()}")
    for name, check in result["checks"].items():
        status = "ok" if check.get("ok") else "failed"
        detail = check.get("path") or check.get("error") or ""
        print(f"{name}: {status} {detail}".rstrip())
