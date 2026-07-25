from typing import Any

from .payload import logits_to_payload, payload_to_message_bits
from .inference_model import build_pixelseal_from_checkpoint
from .model_cache import resolve_model_path


def require_runtime_imports():
    missing = []
    modules = {}
    for name in ("torch", "numpy"):
        try:
            modules[name] = __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise RuntimeError(
            "Missing Python dependencies: "
            + ", ".join(missing)
            + ". Install the Python package dependencies or use a standalone binary release."
        )
    return modules["torch"], modules["numpy"]


def select_device(device: str):
    torch, _ = require_runtime_imports()
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    return torch.device(device)


def load_model(
    model_card: str,
    device_name: str,
    model_cache_dir: str | None,
    offline: bool,
    force_model_download: bool,
):
    if model_card != "pixelseal":
        raise ValueError("standalone CLI only supports --model pixelseal")
    torch, _ = require_runtime_imports()

    device = select_device(device_name)
    checkpoint_path = resolve_model_path(model_cache_dir, offline, force_model_download)
    model = build_pixelseal_from_checkpoint(checkpoint_path)

    model.eval()
    model.to(device)
    return model, device, torch


def model_nbits(model: Any) -> int:
    msg_processor = getattr(getattr(model, "embedder", None), "msg_processor", None)
    nbits = getattr(msg_processor, "nbits", None)
    if not nbits:
        nbits = getattr(model, "nbits", None)
    if not nbits:
        raise ValueError("Could not determine VideoSeal message capacity")
    return int(nbits)


def configure_detection(model: Any, chunk_size: int) -> None:
    model.chunk_size = int(chunk_size)


def configure_low_impact_embedding(
    model: Any,
    scaling_w: float,
    chunk_size: int,
    temporal_pooling: bool,
    temporal_pool_size: int,
    temporal_pool_depth: int,
) -> None:
    model.blender.scaling_w = float(scaling_w)
    model.chunk_size = int(chunk_size)
    model.step_size = 1
    model.video_mode = "repeat"

    unet = getattr(getattr(model, "embedder", None), "unet", None)
    if unet is None or not hasattr(unet, "time_pooling"):
        raise ValueError("PixelSeal embedder does not support temporal pooling configuration")

    unet.time_pooling = bool(temporal_pooling)
    if temporal_pooling:
        unet.time_pooling_depth = int(temporal_pool_depth)
        unet.temporal_pool.kernel_size = int(temporal_pool_size)
        unet.temporal_pool.stride = int(temporal_pool_size)
    else:
        unet.temporal_pool.kernel_size = 1
        unet.temporal_pool.stride = 1


def frames_to_video_tensor(frames, device):
    torch, numpy = require_runtime_imports()
    if frames.ndim != 4 or frames.shape[-1] < 3:
        raise ValueError(f"expected frames in [F,H,W,C] RGB format, got shape {tuple(frames.shape)}")
    frames = frames[..., :3]
    video = torch.from_numpy(numpy.ascontiguousarray(frames)).to(device=device, dtype=torch.float32)
    return (video / 255.0).permute(0, 3, 1, 2).contiguous()


def video_tensor_to_uint8(video):
    torch, _ = require_runtime_imports()
    video = video.detach().clamp(0, 1).mul(255.0).add(0.5).to(torch.uint8)
    return video.cpu().permute(0, 2, 3, 1).contiguous().numpy()


def message_tensor(watermark_id: str, nbits: int, device):
    torch, _ = require_runtime_imports()
    bits = payload_to_message_bits(watermark_id, nbits)
    return torch.tensor(bits, dtype=torch.float32, device=device).unsqueeze(0)


def aggregate_logits(logits, aggregation: str):
    if logits.ndim == 4:
        logits = logits.mean(dim=(-2, -1))

    if aggregation == "avg":
        return logits.mean(dim=0, keepdim=True)
    if aggregation == "squared_avg":
        return (logits * logits.abs()).mean(dim=0, keepdim=True)
    if aggregation == "l1norm_avg":
        weights = logits.norm(p=1, dim=1, keepdim=True)
        return (logits * weights).mean(dim=0, keepdim=True)
    if aggregation == "l2norm_avg":
        weights = logits.norm(p=2, dim=1, keepdim=True)
        return (logits * weights).mean(dim=0, keepdim=True)
    raise ValueError(f"unknown aggregation: {aggregation}")


def decode_soft_bits(soft_bits) -> tuple[str, list[bool], bool, str]:
    flat = soft_bits.detach().float().cpu().reshape(-1).tolist()
    return logits_to_payload([float(value) for value in flat])
