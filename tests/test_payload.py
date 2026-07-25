import unittest
import zlib

from videoseal_cli.payload import (
    MESSAGE_BITS,
    bit_accuracy_percent,
    bytes_to_bits,
    decode_watermark_id,
    encode_watermark_id,
    expected_bits,
    logits_to_payload,
    payload_to_message_bits,
    watermark_id_to_codeword,
)


EXAMPLE_ID = "wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw"


def logits_for_bytes(raw: bytes) -> list[float]:
    return [2.0 if bit else -2.0 for bit in bytes_to_bits(raw)]


class PayloadTests(unittest.TestCase):
    def test_canonical_wm_v1_round_trip(self):
        raw = decode_watermark_id(EXAMPLE_ID)
        self.assertEqual(len(raw), 16)
        self.assertEqual(encode_watermark_id(raw), EXAMPLE_ID)

    def test_rs_codeword_fills_pixel_seal_capacity(self):
        codeword = watermark_id_to_codeword(EXAMPLE_ID)
        bits = payload_to_message_bits(EXAMPLE_ID, MESSAGE_BITS)
        self.assertEqual(len(codeword), 32)
        self.assertEqual(len(bits), MESSAGE_BITS)
        self.assertEqual([int(bit) for bit in bits], bytes_to_bits(codeword))

    def test_rs_payload_round_trip(self):
        logits = logits_for_bytes(watermark_id_to_codeword(EXAMPLE_ID))
        decoded, decoded_bits, valid, encoding = logits_to_payload(logits)
        self.assertTrue(valid)
        self.assertEqual(decoded, EXAMPLE_ID)
        self.assertEqual(encoding, "wm_v1_rs16")
        self.assertEqual(bit_accuracy_percent(decoded_bits, expected_bits(EXAMPLE_ID)), 100.0)

    def test_rs_recovers_eight_corrupted_bytes(self):
        damaged = bytearray(watermark_id_to_codeword(EXAMPLE_ID))
        for index in range(8):
            damaged[index] ^= 0xA5

        decoded, corrected_bits, valid, encoding = logits_to_payload(logits_for_bytes(bytes(damaged)))
        self.assertTrue(valid)
        self.assertEqual(decoded, EXAMPLE_ID)
        self.assertEqual(encoding, "wm_v1_rs16")
        self.assertEqual(bit_accuracy_percent(corrected_bits, expected_bits(EXAMPLE_ID)), 100.0)

    def test_rs_rejects_nine_corrupted_bytes(self):
        damaged = bytearray(watermark_id_to_codeword(EXAMPLE_ID))
        for index in range(9):
            damaged[index] ^= 0xA5

        decoded, _decoded_bits, valid, encoding = logits_to_payload(logits_for_bytes(bytes(damaged)))
        self.assertFalse(valid)
        self.assertEqual(decoded, "")
        self.assertEqual(encoding, "invalid")

    def test_rejects_removed_and_malformed_payload_formats(self):
        invalid_ids = [
            "",
            "watermark-id-001",
            "wm_v1_short",
            "wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw=",
            "wm_v1_k3qV9x7nB4mLp2ZaQ8fTd!",
        ]
        for watermark_id in invalid_ids:
            with self.subTest(watermark_id=watermark_id):
                with self.assertRaises(ValueError):
                    payload_to_message_bits(watermark_id, MESSAGE_BITS)

    def test_rejects_retired_repeated_bit_payload(self):
        raw_id = decode_watermark_id(EXAMPLE_ID)
        decoded, _bits, valid, encoding = logits_to_payload(logits_for_bytes(raw_id + raw_id))
        self.assertFalse(valid)
        self.assertEqual(decoded, "")
        self.assertEqual(encoding, "invalid")

    def test_rejects_retired_crc_text_payload(self):
        text = b"watermark-id-001"
        checksum = zlib.crc32(text).to_bytes(4, "big")
        retired_payload = (bytes([0x80 | len(text)]) + text + checksum).ljust(32, b"\0")
        decoded, _bits, valid, encoding = logits_to_payload(logits_for_bytes(retired_payload))
        self.assertFalse(valid)
        self.assertEqual(decoded, "")
        self.assertEqual(encoding, "invalid")

    def test_requires_exact_256_bit_model_capacity(self):
        with self.assertRaises(ValueError):
            payload_to_message_bits(EXAMPLE_ID, 128)
        with self.assertRaises(ValueError):
            logits_to_payload([1.0] * 128)


if __name__ == "__main__":
    unittest.main()
