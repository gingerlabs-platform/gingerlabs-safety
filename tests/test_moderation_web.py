import io
from pathlib import Path
from unittest import mock
import unittest

try:
    from fastapi.testclient import TestClient
    from PIL import Image

    from gingerlabs_moderation.policy import Detection
    from gingerlabs_moderation.web import MAX_SAMPLED_VIDEO_FRAMES, _sample_frame_indices, create_app

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
        self.assertIn("Image and video moderation tester", response.text)
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
        self.assertEqual(result["mediaType"], "image")
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["detections"][0]["role"], "candidate")

    def test_unsupported_upload_is_rejected_without_detector_call(self):
        response = self.client.post(
            "/api/analyze",
            files={"files": ("notes.txt", b"not an image", "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("JPEG", response.json()["results"][0]["error"])

    def test_video_upload_is_staged_analyzed_and_removed(self):
        staged_path: Path | None = None

        def fake_video_analysis(path, service, config, interval_seconds):
            nonlocal staged_path
            staged_path = path
            self.assertEqual(path.read_bytes(), b"synthetic-video")
            self.assertEqual(interval_seconds, 0.75)
            return {
                "mediaType": "video",
                "width": 720,
                "height": 1280,
                "durationSeconds": 2.0,
                "sampleIntervalSeconds": interval_seconds,
                "sampledFrameCount": 4,
                "blockedFrameCount": 0,
                "decision": "allow",
                "reasons": ["No configured blocking category was confirmed in 4 sampled frames."],
                "frames": [],
            }

        with mock.patch("gingerlabs_moderation.web._analyze_video", side_effect=fake_video_analysis):
            response = self.client.post(
                "/api/analyze",
                files={"files": ("clip.mp4", b"synthetic-video", "video/mp4")},
                data={"video_sample_interval_seconds": "0.75"},
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["mediaType"], "video")
        self.assertEqual(result["sampledFrameCount"], 4)
        self.assertIsNotNone(staged_path)
        self.assertFalse(staged_path.exists())

    def test_invalid_video_sampling_interval_is_rejected(self):
        response = self.client.post(
            "/api/analyze",
            files={"files": ("clip.mp4", b"synthetic-video", "video/mp4")},
            data={"video_sample_interval_seconds": "0.1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("between 0.25 and 5 seconds", response.json()["error"])

    def test_video_frame_sampling_includes_start_and_end(self):
        indices = _sample_frame_indices(frame_count=151, fps=30.0, interval_seconds=0.5)

        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 150)
        self.assertEqual(len(indices), 11)

    def test_video_frame_sampling_is_evenly_capped(self):
        indices = _sample_frame_indices(frame_count=36_000, fps=30.0, interval_seconds=0.25)

        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 35_999)
        self.assertLessEqual(len(indices), MAX_SAMPLED_VIDEO_FRAMES)
        self.assertEqual(indices, sorted(set(indices)))


if __name__ == "__main__":
    unittest.main()
