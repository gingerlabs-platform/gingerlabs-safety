import io
import unittest

try:
    from fastapi.testclient import TestClient
    from PIL import Image

    from gingerlabs_moderation.policy import Detection
    from gingerlabs_moderation.web import create_app

    WEB_DEPENDENCIES_AVAILABLE = True
except ImportError:
    WEB_DEPENDENCIES_AVAILABLE = False


class FakeDetectorSuite:
    def detect(self, rgb_image, minimum_score):
        return [
            Detection(
                detector="nudenet",
                label="FEMALE_BREAST_EXPOSED",
                score=0.88,
                box=(2, 3, 12, 13),
            )
        ]


@unittest.skipUnless(WEB_DEPENDENCIES_AVAILABLE, "moderation web dependencies are optional")
class ModerationWebTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(FakeDetectorSuite))

    @staticmethod
    def image_bytes():
        output = io.BytesIO()
        Image.new("RGB", (20, 16), (240, 230, 220)).save(output, format="PNG")
        return output.getvalue()

    def test_local_tester_page_is_available(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Image moderation tester", response.text)
        self.assertIn("Local only", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_upload_returns_candidate_without_blocking(self):
        response = self.client.post(
            "/api/analyze",
            files={"files": ("cleavage-test.png", self.image_bytes(), "image/png")},
            data={
                "exact_parts_threshold": "0.45",
                "buttocks_threshold": "0.65",
                "candidate_threshold": "0.35",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["filename"], "cleavage-test.png")
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["detections"][0]["role"], "candidate")

    def test_non_image_upload_is_rejected_without_detector_call(self):
        response = self.client.post(
            "/api/analyze",
            files={"files": ("notes.txt", b"not an image", "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("JPEG", response.json()["results"][0]["error"])


if __name__ == "__main__":
    unittest.main()
