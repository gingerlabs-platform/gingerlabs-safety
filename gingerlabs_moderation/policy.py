from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


DetectorName = Literal["nudenet", "exact_parts"]
Decision = Literal["allow", "block"]
DetectionRole = Literal["blocking", "candidate", "ignored"]


@dataclass(frozen=True)
class Detection:
    detector: DetectorName
    label: str
    score: float
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class PolicyConfig:
    exact_parts_threshold: float = 0.45
    buttocks_threshold: float = 0.65
    candidate_threshold: float = 0.35

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class ClassifiedDetection:
    detector: DetectorName
    label: str
    score: float
    box: tuple[int, int, int, int]
    role: DetectionRole
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "detector": self.detector,
            "label": self.label,
            "score": round(self.score, 4),
            "box": list(self.box),
            "role": self.role,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reasons: tuple[str, ...]
    detections: tuple[ClassifiedDetection, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "detections": [detection.to_dict() for detection in self.detections],
        }


EXACT_BLOCK_LABELS = {
    "nipple": "Visible nipple detected",
    "penis": "Visible penis detected",
    "vagina": "Visible vagina detected",
}
NUDENET_BUTTOCKS_LABEL = "BUTTOCKS_EXPOSED"
NUDENET_BREAST_CANDIDATE = "FEMALE_BREAST_EXPOSED"


def _normalize_label(label: str) -> str:
    return label.strip().replace(" ", "_").upper()


def evaluate_policy(
    detections: list[Detection] | tuple[Detection, ...],
    config: PolicyConfig | None = None,
) -> PolicyResult:
    active_config = config or PolicyConfig()
    active_config.validate()

    classified: list[ClassifiedDetection] = []
    blocking_reasons: list[str] = []

    for detection in detections:
        if not 0.0 <= detection.score <= 1.0:
            raise ValueError("detection score must be between 0 and 1")

        normalized = _normalize_label(detection.label)
        role: DetectionRole = "ignored"
        reason = "Not part of the GingerLabs blocking policy"

        if detection.detector == "exact_parts":
            exact_label = detection.label.strip().lower()
            if exact_label in EXACT_BLOCK_LABELS and detection.score >= active_config.exact_parts_threshold:
                role = "blocking"
                reason = EXACT_BLOCK_LABELS[exact_label]
        elif detection.detector == "nudenet":
            if normalized == NUDENET_BUTTOCKS_LABEL and detection.score >= active_config.buttocks_threshold:
                role = "blocking"
                reason = "Bare buttocks detected"
            elif normalized == NUDENET_BREAST_CANDIDATE and detection.score >= active_config.candidate_threshold:
                role = "candidate"
                reason = "Broad exposed-breast candidate; does not block without an exact nipple detection"

        if role == "blocking" and reason not in blocking_reasons:
            blocking_reasons.append(reason)

        classified.append(
            ClassifiedDetection(
                detector=detection.detector,
                label=detection.label,
                score=detection.score,
                box=detection.box,
                role=role,
                reason=reason,
            )
        )

    classified.sort(key=lambda detection: detection.score, reverse=True)
    return PolicyResult(
        decision="block" if blocking_reasons else "allow",
        reasons=tuple(blocking_reasons),
        detections=tuple(classified),
    )
