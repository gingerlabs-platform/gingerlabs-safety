import unittest

from videoseal_cli.payload import (
    bit_accuracy_percent,
    decode_watermark_id,
    encode_watermark_id,
    expected_bits,
    legacy_wm_v1_to_message_bits,
    logits_to_payload,
    payload_to_message_bits,
)


EXAMPLE_LEGACY_ID = "wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw"


class PayloadTests(unittest.TestCase):
    def test_legacy_wm_v1_round_trip(self):
        raw = decode_watermark_id(EXAMPLE_LEGACY_ID)
        self.assertEqual(len(raw), 16)
        self.assertEqual(encode_watermark_id(raw), EXAMPLE_LEGACY_ID)

    def test_text_payload_uses_crc32_when_it_fits(self):
        bits = payload_to_message_bits("watermark-id-001", 256)
        logits = [2.0 if bit else -2.0 for bit in bits]
        decoded, decoded_bits, valid, encoding = logits_to_payload(logits)
        self.assertTrue(valid)
        self.assertEqual(decoded, "watermark-id-001")
        self.assertEqual(encoding, "text_crc32")
        self.assertEqual(bit_accuracy_percent(decoded_bits, expected_bits("watermark-id-001", 256)), 100.0)

    def test_long_text_payload_uses_text_without_crc(self):
        payload = EXAMPLE_LEGACY_ID
        bits = payload_to_message_bits(payload, 256)
        logits = [2.0 if bit else -2.0 for bit in bits]
        decoded, _decoded_bits, valid, encoding = logits_to_payload(logits)
        self.assertTrue(valid)
        self.assertEqual(decoded, payload)
        self.assertEqual(encoding, "text")

    def test_legacy_repeated_wm_v1_decode_fallback(self):
        bits = legacy_wm_v1_to_message_bits(EXAMPLE_LEGACY_ID, 256)
        self.assertEqual(bits[:128], bits[128:])
        logits = [2.0 if bit else -2.0 for bit in bits]
        decoded, _decoded_bits, valid, encoding = logits_to_payload(logits)
        self.assertTrue(valid)
        self.assertEqual(decoded, EXAMPLE_LEGACY_ID)
        self.assertEqual(encoding, "wm_v1_legacy")

    def test_rejects_text_payload_that_exceeds_capacity(self):
        with self.assertRaises(ValueError):
            payload_to_message_bits("x" * 32, 256)


if __name__ == "__main__":
    unittest.main()
