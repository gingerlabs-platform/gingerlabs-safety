import base64
import zlib
from collections.abc import Sequence


PREFIX = "wm_v1_"
RAW_ID_BYTES = 16
RAW_ID_BITS = RAW_ID_BYTES * 8


def decode_legacy_wm_v1_id(watermark_id: str) -> bytes:
    watermark_id = watermark_id.strip()
    if not watermark_id.startswith(PREFIX):
        raise ValueError(f"watermark ID must start with {PREFIX!r}")

    suffix = watermark_id[len(PREFIX):]
    padded = suffix + "=" * (-len(suffix) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise ValueError("watermark ID suffix must be valid unpadded Base64URL") from exc

    if len(raw) != RAW_ID_BYTES:
        raise ValueError(
            f"watermark ID suffix must decode to {RAW_ID_BYTES} bytes / {RAW_ID_BITS} bits; "
            f"got {len(raw)} bytes"
        )
    return raw


def encode_legacy_wm_v1_id(raw: bytes) -> str:
    if len(raw) != RAW_ID_BYTES:
        raise ValueError(f"expected {RAW_ID_BYTES} bytes, got {len(raw)}")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{PREFIX}{encoded}"


# Backwards-compatible aliases used by older tests/callers.
decode_watermark_id = decode_legacy_wm_v1_id
encode_watermark_id = encode_legacy_wm_v1_id


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


def bytes_to_message_bits(raw: bytes, nbits: int) -> list[float]:
    bits = bytes_to_bits(raw)
    if nbits < len(bits):
        raise ValueError(f"VideoSeal model has {nbits} bits, but payload needs {len(bits)} bits")
    bits.extend([0] * (nbits - len(bits)))
    return [float(bit) for bit in bits[:nbits]]


def payload_to_message_bits(payload: str, nbits: int) -> list[float]:
    payload = (payload or "").strip()
    if not payload:
        raise ValueError("watermark_id cannot be empty")

    encoded_text = payload.encode("utf-8")
    capacity_bytes = nbits // 8
    if capacity_bytes < 2:
        raise ValueError(f"VideoSeal model has {nbits} bits, not enough for a text watermark ID")

    max_text_bytes = capacity_bytes - 1
    if len(encoded_text) > max_text_bytes:
        raise ValueError(
            f"watermark_id is {len(encoded_text)} UTF-8 bytes, but this {nbits}-bit model can store "
            f"at most {max_text_bytes} bytes. Use a shorter ID or a higher-capacity model."
        )

    max_crc_text_bytes = max(0, capacity_bytes - 5)
    if len(encoded_text) <= max_crc_text_bytes:
        checksum = zlib.crc32(encoded_text) & 0xFFFFFFFF
        raw = bytes([0x80 | len(encoded_text)]) + encoded_text + checksum.to_bytes(4, "big")
    else:
        raw = bytes([len(encoded_text)]) + encoded_text

    raw = raw.ljust(capacity_bytes, b"\0")
    return bytes_to_message_bits(raw, nbits)


def message_bits_to_payload(bits: Sequence[bool | int]) -> tuple[str, bool, str]:
    raw = bits_to_bytes(bits)
    if not raw:
        return "", False, "invalid"

    header = raw[0]
    has_crc = bool(header & 0x80)
    text_len = header & 0x7F
    payload_start = 1
    payload_end = payload_start + text_len

    if text_len == 0 or payload_end > len(raw):
        return "", False, "invalid"

    payload_bytes = raw[payload_start:payload_end]
    try:
        payload = payload_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return "", False, "invalid"

    if has_crc:
        checksum_end = payload_end + 4
        if checksum_end > len(raw):
            return "", False, "invalid"
        expected_checksum = int.from_bytes(raw[payload_end:checksum_end], "big")
        actual_checksum = zlib.crc32(payload_bytes) & 0xFFFFFFFF
        if expected_checksum != actual_checksum:
            return "", False, "invalid"
        if any(raw[checksum_end:]):
            return "", False, "invalid"
        return payload, True, "text_crc32"

    if any(raw[payload_end:]):
        return "", False, "invalid"
    return payload, True, "text"


def legacy_wm_v1_to_message_bits(watermark_id: str, nbits: int) -> list[float]:
    if nbits < RAW_ID_BITS:
        raise ValueError(f"VideoSeal model has {nbits} bits, but wm_v1 IDs require at least {RAW_ID_BITS} bits")

    payload_bits = bytes_to_bits(decode_legacy_wm_v1_id(watermark_id))
    repeats = max(1, nbits // len(payload_bits))
    encoded = (payload_bits * repeats)[:nbits]
    if len(encoded) < nbits:
        encoded.extend([0] * (nbits - len(encoded)))
    return [float(bit) for bit in encoded]


def legacy_logits_to_wm_v1(logits: Sequence[float]) -> tuple[str, bool]:
    if len(logits) < RAW_ID_BITS:
        return "", False

    usable = (len(logits) // RAW_ID_BITS) * RAW_ID_BITS
    chunks = [logits[offset:offset + RAW_ID_BITS] for offset in range(0, usable, RAW_ID_BITS)]
    decoded_bits = []
    for bit_index in range(RAW_ID_BITS):
        mean_logit = sum(chunk[bit_index] for chunk in chunks) / len(chunks)
        decoded_bits.append(mean_logit > 0)

    return encode_legacy_wm_v1_id(bits_to_bytes(decoded_bits)), True


def logits_to_payload(logits: Sequence[float]) -> tuple[str, list[bool], bool, str]:
    decoded_bits = [float(value) > 0 for value in logits]
    decoded_payload, format_valid, encoding = message_bits_to_payload(decoded_bits)
    if format_valid:
        return decoded_payload, decoded_bits, True, encoding

    legacy_payload, legacy_valid = legacy_logits_to_wm_v1(logits)
    if legacy_valid:
        return legacy_payload, decoded_bits, True, "wm_v1_legacy"

    return "", decoded_bits, False, "invalid"


def watermark_id_to_repeated_bits(watermark_id: str, nbits: int) -> list[float]:
    return legacy_wm_v1_to_message_bits(watermark_id, nbits)


def repeated_logits_to_watermark_id(logits: Sequence[float]) -> tuple[str, list[bool], bool]:
    payload, bits, valid, _encoding = logits_to_payload(logits)
    return payload, bits, valid


def expected_bits(payload: str, nbits: int | None = None) -> list[bool]:
    if nbits is None:
        return [bool(bit) for bit in bytes_to_bits(decode_legacy_wm_v1_id(payload))]
    return [bool(bit) for bit in payload_to_message_bits(payload, nbits)]


def bit_accuracy_percent(decoded_bits: Sequence[bool], expected: Sequence[bool]) -> float:
    if len(decoded_bits) != len(expected):
        raise ValueError(f"bit sequences must have the same length; got {len(decoded_bits)} and {len(expected)}")
    correct = sum(bool(left) == bool(right) for left, right in zip(decoded_bits, expected, strict=True))
    return correct / len(expected) * 100.0
