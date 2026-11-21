"""python -m unittest -v"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="clearpath-test-"))
os.environ["CLEARPATH_DATA"] = str(_TMP)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from clearpath import config, vision  # noqa: E402
from clearpath.contracts import ReviewedDetails, SavedCapture  # noqa: E402
from clearpath.reporting import channels, gemini, report  # noqa: E402
from clearpath.store import Store, now  # noqa: E402
from evaluation.make_synthetic import scene  # noqa: E402


def setUpModule():
    config.ensure_dirs()


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


def _pair(blocked: bool):
    rng = np.random.default_rng(5)
    img, path = scene(rng)
    ref = np.clip(img, 0, 255).astype(np.uint8)
    cap = ref.copy()
    if blocked:  # a big dark object in the middle of the walkway
        cv2.rectangle(cap, (250, 300), (390, 440), (25, 25, 30), -1)
    d = Path(tempfile.mkdtemp(dir=_TMP))
    cv2.imwrite(str(d / "ref.jpg"), cv2.cvtColor(ref, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(d / "cap.jpg"), cv2.cvtColor(cap, cv2.COLOR_RGB2BGR))
    return d / "ref.jpg", d / "cap.jpg", d


class Contracts(unittest.TestCase):
    def test_phase_is_checked(self):
        with self.assertRaises(ValueError):
            SavedCapture("INS-0001", "later", Path("x.jpg"), now())


class Vision(unittest.TestCase):
    def _check(self, method):
        ref, cap, d = _pair(blocked=True)
        r = vision.compare(ref, cap, d / "overlay.png", method=method)
        self.assertEqual(r.method, method)
        self.assertEqual(r.verdict, "obstructed")
        self.assertTrue(r.overlay_path.exists())
        ref, cap, d = _pair(blocked=False)
        self.assertEqual(vision.compare(ref, cap, d / "overlay.png", method=method).verdict, "clear")

    def test_opencv_baseline(self):
        self._check("opencv")

    def test_dinov2(self):
        if not vision.dino.available():
            self.skipTest("DINOv2 not available offline")
        self._check("dinov2")


class StoreLinksCaptures(unittest.TestCase):
    def test_initial_and_follow_up_share_reference(self):
        s = Store(_TMP / "t.db")
        ref, cap, _ = _pair(blocked=True)
        loc = s.add_location("Ramp", ref)
        iid = s.new_inspection(loc)
        s.add_capture(SavedCapture(iid, "initial", cap, now()))
        s.add_capture(SavedCapture(iid, "follow_up", ref, now()))
        b = s.bundle(iid)
        self.assertEqual(b["reference_path"], str(ref))
        self.assertEqual(b["initial"]["phase"], "initial")
        self.assertEqual(b["follow_up"]["phase"], "follow_up")
        s.set_status(iid, "reviewed")
        self.assertEqual([e["status"] for e in s.bundle(iid)["events"]], ["captured", "reviewed"])


class Reporting(unittest.TestCase):
    def _bundle(self, confirmed=True, desc="Cone on the ramp"):
        s = Store(_TMP / "r.db")
        ref, cap, d = _pair(blocked=True)
        iid = s.new_inspection(s.add_location("Ramp", ref))
        c = s.add_capture(SavedCapture(iid, "initial", cap, now()))
        s.save_comparison(c.capture_id, vision.compare(ref, cap, d / "o.png", method="opencv"))
        s.save_review(iid, ReviewedDetails("Trash or debris", "Minor: narrows the path", desc, "", "Sam", confirmed, now()))
        return s.bundle(iid)

    def test_needs_confirmed_review(self):
        with self.assertRaises(ValueError):
            report.draft_text(self._bundle(confirmed=False))

    def test_html_escapes_user_text(self):
        b = self._bundle(desc="<script>alert(1)</script>")
        out = report.build(b)
        self.assertNotIn("<script>alert", out.html)
        self.assertIn("&lt;script&gt;", out.html)
        self.assertIn("data:image/jpeg;base64,", out.html)

    def test_unverified_channels_hidden(self):
        f = _TMP / "ch.json"
        f.write_text('{"channels": [{"name": "A", "url": "https://x", "verified": true, "verified_by": "", "verified_on": ""},'
                     '{"name": "B", "url": "https://y", "verified": true, "verified_by": "Kim", "verified_on": "2026-11-21"}]}')
        self.assertEqual([c["name"] for c in channels.verified(f)], ["B"])

    def test_gemini_without_key(self):
        config.GEMINI_API_KEY = None
        self.assertFalse(gemini.observe("a.jpg", "b.jpg")["available"])


class AppFlow(unittest.TestCase):
    def test_demo_inspection_end_to_end(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=180).run()
        at.sidebar.radio[0].set_value("Locations").run()
        next(b for b in at.button if "demo" in b.label).click().run()
        at.sidebar.radio[0].set_value("Inspect").run()
        next(b for b in at.button if b.label == "Start inspection").click().run()
        next(b for b in at.button if b.label == "Check this photo").click().run()
        self.assertFalse(at.exception)
        at.text_area[0].set_value("Scooter lying across the walkway.")
        next(t for t in at.text_input if t.label == "Your name").set_value("Tester")
        at.checkbox[0].check()
        next(b for b in at.button if b.label == "Confirm details").click().run()
        next(b for b in at.button if b.label.startswith("Mark as sent")).click().run()
        next(b for b in at.button if b.label == "Check follow-up photo").click().run()
        next(b for b in at.button if b.label == "Confirm resolved").click().run()
        self.assertFalse(at.exception)
        self.assertIn("Resolved.", [s.value for s in at.success])


if __name__ == "__main__":
    unittest.main()
