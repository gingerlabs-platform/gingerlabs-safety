import base64
import binascii
import re
from collections.abc import Sequence
from functools import lru_cache

from ._vendor.reedsolo import RSCodec, ReedSolomonError


PREFIX = "wm_v1_"
RAW_ID_BYTES = 16
RAW_ID_BITS = RAW_ID_BYTES * 8
RS_PARITY_BYTES = 16
CODEWORD_BYTES = RAW_ID_BYTES + RS_PARITY_BYTES
MESSAGE_BITS = CODEWORD_BYTES * 8
PAYLOAD_ENCODING = "wm_v1_rs16"
_CANONICAL_ID_PATTERN = re.compile(r"^wm_v1_[A-Za-z0-9_-]{22}$")


@lru_cache(maxsize=1)
def _rs_codec() -> RSCodec:
    return RSCodec(RS_PARITY_BYTES)


def decode_watermark_id(watermark_id: str) -> bytes:
    watermark_id = (watermark_id or "").strip()
    if not _CANONICAL_ID_PATTERN.fullmatch(watermark_id):
        raise ValueError(
            "watermark ID must use the canonical format "
            "'wm_v1_' followed by 22 unpadded Base64URL characters"
        )

    suffix = watermark_id[len(PREFIX):]
    try:
        raw = base64.b64decode(suffix + "==", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("watermark ID suffix must be valid unpadded Base64URL") from exc

    if len(raw) != RAW_ID_BYTES or encode_watermark_id(raw) != watermark_id:
        raise ValueError(
            f"watermark ID suffix must canonically encode {RAW_ID_BYTES} bytes / {RAW_ID_BITS} bits"
        )
    return raw


def encode_watermark_id(raw: bytes) -> str:
    if len(raw) != RAW_ID_BYTES:
        raise ValueError(f"expected {RAW_ID_BYTES} ID bytes, got {len(raw)}")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{PREFIX}{encoded}"


def bytes_to_bits(raw: bytes) -> list[int]:
    bits: list[int] = []
    for byte in raw:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    return bits


def bits_to_bytes(bits: Sequence[bool | int]) -> bytes:
    usable = (len(bits) // 8) * 8
    if usable <= 0:
        return b""

    output = bytearray()
    for offset in range(0, usable, 8):
        value = 0
        for bit in bits[offset:offset + 8]:
            value = (value << 1) | int(bool(bit))
        output.append(value)
    return bytes(output)


def watermark_id_to_codeword(watermark_id: str) -> bytes:
    codeword = bytes(_rs_codec().encode(decode_watermark_id(watermark_id)))
    if len(codeword) != CODEWORD_BYTES:
        raise RuntimeError(f"expected a {CODEWORD_BYTES}-byte Reed-Solomon codeword, got {len(codeword)}")
    return codeword


def payload_to_message_bits(payload: str, nbits: int) -> list[float]:
    if nbits != MESSAGE_BITS:
        raise ValueError(
            f"PixelSeal RS-protected wm_v1 IDs require exactly {MESSAGE_BITS} message bits; "
            f"model reports {nbits}"
        )
    return [float(bit) for bit in bytes_to_bits(watermark_id_to_codeword(payload))]


def logits_to_payload(logits: Sequence[float]) -> tuple[str, list[bool], bool, str]:
    if len(logits) != MESSAGE_BITS:
        raise ValueError(f"expected {MESSAGE_BITS} PixelSeal message logits, got {len(logits)}")

    decoded_bits = [float(value) > 0 for value in logits]
    codeword = bits_to_bytes(decoded_bits)
    try:
        decoded, corrected, _errata = _rs_codec().decode(codeword)
    except (ReedSolomonError, ValueError, IndexError):
        return "", decoded_bits, False, "invalid"

    decoded = bytes(decoded)
    corrected = bytes(corrected)
    if len(decoded) != RAW_ID_BYTES or len(corrected) < CODEWORD_BYTES:
        return "", decoded_bits, False, "invalid"

    corrected_bits = [bool(bit) for bit in bytes_to_bits(corrected[:CODEWORD_BYTES])]
    return encode_watermark_id(decoded), corrected_bits, True, PAYLOAD_ENCODING


def expected_bits(payload: str, nbits: int = MESSAGE_BITS) -> list[bool]:
    return [bool(bit) for bit in payload_to_message_bits(payload, nbits)]


def bit_accuracy_percent(decoded_bits: Sequence[bool], expected: Sequence[bool]) -> float:
    if len(decoded_bits) != len(expected):
        raise ValueError(f"bit sequences must have the same length; got {len(decoded_bits)} and {len(expected)}")
    correct = sum(bool(left) == bool(right) for left, right in zip(decoded_bits, expected, strict=True))
    return correct / len(expected) * 100.0
