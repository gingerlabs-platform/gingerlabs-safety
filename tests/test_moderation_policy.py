import unittest

from gingerlabs_moderation.policy import Detection, PolicyConfig, evaluate_policy


def detection(detector, label, score=0.9):
    return Detection(detector=detector, label=label, score=score, box=(1, 2, 30, 40))


class ModerationPolicyTests(unittest.TestCase):
    def test_broad_breast_candidate_does_not_block_without_exact_nipple(self):
        result = evaluate_policy([detection("nudenet", "FEMALE_BREAST_EXPOSED")])

        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.detections[0].role, "candidate")
        self.assertIn("does not block", result.detections[0].reason)

    def test_exact_nipple_blocks(self):
        result = evaluate_policy([detection("exact_parts", "nipple")])

        self.assertEqual(result.decision, "block")
        self.assertEqual(result.reasons, ("Visible nipple detected",))

    def test_exact_genital_categories_block(self):
        for label in ("penis", "vagina"):
            with self.subTest(label=label):
                result = evaluate_policy([detection("exact_parts", label)])
                self.assertEqual(result.decision, "block")

    def test_nudenet_bare_buttocks_blocks(self):
        result = evaluate_policy([detection("nudenet", "BUTTOCKS_EXPOSED", 0.7)])

        self.assertEqual(result.decision, "block")
        self.assertEqual(result.reasons, ("Bare buttocks detected",))

    def test_unrequested_categories_are_ignored(self):
        detections = [
            detection("nudenet", "MALE_BREAST_EXPOSED"),
            detection("nudenet", "ANUS_EXPOSED"),
            detection("exact_parts", "anus"),
            detection("exact_parts", "make_love"),
        ]

        result = evaluate_policy(detections)

        self.assertEqual(result.decision, "allow")
        self.assertTrue(all(item.role == "ignored" for item in result.detections))

    def test_each_threshold_is_enforced(self):
        config = PolicyConfig(
            exact_parts_threshold=0.8,
            buttocks_threshold=0.8,
            candidate_threshold=0.8,
        )
        result = evaluate_policy(
            [
                detection("exact_parts", "nipple", 0.79),
                detection("nudenet", "BUTTOCKS_EXPOSED", 0.79),
                detection("nudenet", "FEMALE_BREAST_EXPOSED", 0.79),
            ],
            config,
        )

        self.assertEqual(result.decision, "allow")
        self.assertTrue(all(item.role == "ignored" for item in result.detections))

    def test_invalid_threshold_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            evaluate_policy([], PolicyConfig(exact_parts_threshold=1.1))


if __name__ == "__main__":
    unittest.main()
