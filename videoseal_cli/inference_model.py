from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any
import warnings

import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml

warnings.filterwarnings("ignore", category=FutureWarning, module=r"timm\.models\.layers")

from ._vendor.videoseal.models.blender import Blender
from ._vendor.videoseal.models.embedder import build_embedder
from ._vendor.videoseal.models.extractor import build_extractor
from ._vendor.videoseal.modules.jnd import JND


class AttrDict(dict):
    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def to_attr_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return AttrDict({key: to_attr_dict(item) for key, item in value.items()})
    if isinstance(value, list):
        return [to_attr_dict(item) for item in value]
    return value


def load_yaml_config(name: str) -> AttrDict:
    resource = resources.files("videoseal_cli.videoseal_configs").joinpath(name)
    with resource.open("r", encoding="utf-8") as handle:
        return to_attr_dict(yaml.safe_load(handle))


class RGB2YUV(nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer(
            "M",
            torch.tensor(
                [
                    [0.299, 0.587, 0.114],
                    [-0.14713, -0.28886, 0.436],
                    [0.615, -0.51499, -0.10001],
                ],
                dtype=torch.float32,
            ),
        )

    def forward(self, x):
        x = x.permute(0, 2, 3, 1).contiguous()
        yuv = torch.matmul(x, self.M.T)
        return yuv.permute(0, 3, 1, 2).contiguous()


class VideoSealInferenceModel(nn.Module):
    def __init__(
        self,
        embedder,
        detector,
        attenuation,
        scaling_w: float,
        scaling_i: float,
        img_size: int,
        chunk_size: int,
        step_size: int,
        blending_method: str,
        video_mode: str = "repeat",
        clamp: bool = True,
    ):
        super().__init__()
        self.embedder = embedder
        self.detector = detector
        self.attenuation = attenuation
        self.img_size = int(img_size)
        self.chunk_size = int(chunk_size)
        self.step_size = int(step_size)
        self.video_mode = video_mode
        self.clamp = clamp
        self.rgb2yuv = RGB2YUV()
        self.blender = Blender(scaling_i, scaling_w, blending_method)

    @property
    def device(self):
        return next(self.parameters()).device

    @staticmethod
    def _apply_video_mode(preds_w: torch.Tensor, total_frames: int, step_size: int, video_mode: str) -> torch.Tensor:
        if video_mode == "repeat":
            preds_w = torch.repeat_interleave(preds_w, step_size, dim=0)
        elif video_mode == "alternate":
            full_preds = torch.zeros((total_frames,) + preds_w.shape[1:], device=preds_w.device)
            full_preds[::step_size] = preds_w
            preds_w = full_preds
        elif video_mode == "interpolate":
            full_preds = torch.zeros((total_frames,) + preds_w.shape[1:], device=preds_w.device)
            alpha = 1 - torch.linspace(0, 1, steps=step_size, device=preds_w.device)
            alpha = alpha.repeat((total_frames - 1) // step_size).view(-1, 1, 1, 1)
            start_frames = torch.repeat_interleave(preds_w[:-1], step_size, dim=0)
            end_frames = torch.repeat_interleave(preds_w[1:], step_size, dim=0)
            interpolated_preds = alpha * start_frames + (1 - alpha) * end_frames
            full_preds[: len(interpolated_preds)] = interpolated_preds
            full_preds[len(interpolated_preds):] = preds_w[-1]
            preds_w = full_preds
        else:
            raise ValueError(f"unknown video_mode: {video_mode}")
        return preds_w[:total_frames]

    @torch.no_grad()
    def embed(
        self,
        imgs: torch.Tensor,
        msgs: torch.Tensor,
        is_video: bool = True,
        interpolation: dict | None = None,
        lowres_attenuation: bool = True,
    ) -> dict:
        if not is_video:
            raise ValueError("standalone CLI only supports video embedding")
        if msgs.shape[0] != 1:
            raise ValueError("message should be unique per video")
        interpolation = interpolation or {"mode": "bilinear", "align_corners": False, "antialias": True}
        repeated_msgs = msgs.repeat(self.chunk_size, 1)
        imgs_w = torch.zeros_like(imgs)

        for ii in range(0, len(imgs[:: self.step_size]), self.chunk_size):
            nimgs_in_chunk = min(self.chunk_size, len(imgs[:: self.step_size]) - ii)
            start = ii * self.step_size
            end = start + nimgs_in_chunk * self.step_size
            chunk = imgs[start:end]
            chunk_msgs = repeated_msgs[:nimgs_in_chunk]

            resized = chunk
            if resized.shape[-2:] != (self.img_size, self.img_size):
                resized = F.interpolate(resized, size=(self.img_size, self.img_size), **interpolation)
            resized = resized.to(self.device)
            key_frames = resized[:: self.step_size]
            if self.embedder.yuv:
                key_frames = self.rgb2yuv(key_frames)[:, 0:1]
            preds_w = self.embedder(key_frames, chunk_msgs.to(self.device))
            preds_w = self._apply_video_mode(preds_w, len(chunk), self.step_size, self.video_mode)

            if self.attenuation is not None and lowres_attenuation:
                self.attenuation.to(resized.device)
                preds_w = self.attenuation.heatmaps(resized) * preds_w

            preds_w = preds_w.to(imgs.device)
            if chunk.shape[-2:] != (self.img_size, self.img_size):
                preds_w = F.interpolate(preds_w, size=chunk.shape[-2:], **interpolation)

            if self.attenuation is not None and not lowres_attenuation:
                self.attenuation.to(chunk.device)
                preds_w = self.attenuation.heatmaps(chunk) * preds_w

            imgs_w[start:end] = self.blender(chunk, preds_w)

        if self.clamp:
            imgs_w = torch.clamp(imgs_w, 0, 1)
        return {"imgs_w": imgs_w, "msgs": msgs.repeat(len(imgs), 1)}

    @torch.no_grad()
    def detect(
        self,
        imgs: torch.Tensor,
        is_video: bool = True,
        interpolation: dict | None = None,
    ) -> dict:
        if not is_video:
            raise ValueError("standalone CLI only supports video detection")
        interpolation = interpolation or {"mode": "bilinear", "align_corners": False, "antialias": True}
        all_preds = []
        for ii in range(0, len(imgs), self.chunk_size):
            chunk = imgs[ii: ii + self.chunk_size]
            resized = chunk
            if resized.shape[-2:] != (self.img_size, self.img_size):
                resized = F.interpolate(resized, size=(self.img_size, self.img_size), **interpolation)
            preds = self.detector(resized)
            all_preds.append(preds)
        return {"preds": torch.cat(all_preds, dim=0)}


def build_videoseal_from_checkpoint(checkpoint_path: Path) -> VideoSealInferenceModel:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    args = to_attr_dict(checkpoint["args"])
    args.img_size = args.get("img_size_proc") or args.get("img_size_extractor")
    args.hidden_size_multiplier = args.get("hidden_size_multiplier", 2)
    if "videowam_chunk_size" in args and "videoseal_chunk_size" not in args:
        args.videoseal_chunk_size = args.videowam_chunk_size
    if "videowam_step_size" in args and "videoseal_step_size" not in args:
        args.videoseal_step_size = args.videowam_step_size

    embedder_cfg = load_yaml_config("embedder.yaml")
    extractor_cfg = load_yaml_config("extractor.yaml")
    attenuation_cfg = load_yaml_config("attenuation.yaml")

    embedder_model_name = args.get("embedder_model") or embedder_cfg.model
    extractor_model_name = args.get("extractor_model") or extractor_cfg.model
    embedder = build_embedder(
        embedder_model_name,
        embedder_cfg[embedder_model_name],
        int(args.nbits),
        args.hidden_size_multiplier,
    )
    extractor = build_extractor(
        extractor_model_name,
        extractor_cfg[extractor_model_name],
        int(args.img_size),
        int(args.nbits),
    )
    attenuation = None
    if str(args.get("attenuation", "")).lower().startswith("jnd"):
        attenuation = JND(**attenuation_cfg[args.attenuation])

    model = VideoSealInferenceModel(
        embedder=embedder,
        detector=extractor,
        attenuation=attenuation,
        scaling_w=float(args.get("scaling_w", 1.0)),
        scaling_i=float(args.get("scaling_i", 1.0)),
        img_size=int(args.img_size),
        chunk_size=int(args.get("videoseal_chunk_size", 32)),
        step_size=int(args.get("videoseal_step_size", 4)),
        blending_method=str(args.get("blending_method", "additive")),
    )
    message = model.load_state_dict(checkpoint["model"], strict=False)
    unexpected = list(message.unexpected_keys)
    missing = list(message.missing_keys)
    if unexpected or missing:
        raise RuntimeError(f"checkpoint state did not match model; missing={missing}, unexpected={unexpected}")
    return model
