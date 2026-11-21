"""python -m unittest -v"""
import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TMP = Path(tempfile.mkdtemp(prefix="clearpath-test-"))
os.environ["CLEARPATH_DATA"] = str(_TMP)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ["CLEARPATH_ML"] = "off"       # no model downloads in the default suite
os.environ["CLEARPATH_OFFLINE"] = "1"    # no satellite / OpenStreetMap calls

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from clearpath import config, demo, vision  # noqa: E402

# `python -m unittest` discovery imports the clearpath package before this file runs,
# so config already holds the REAL data folder. Reload so tests never touch it.
importlib.reload(config)
importlib.reload(demo)
assert config.DATA == _TMP and demo.DEMO.parent == _TMP, "tests must not write to the real data folder"
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

    def test_auto_falls_back_without_torch(self):
        ref, cap, d = _pair(blocked=True)
        with patch.dict(sys.modules, {"torch": None}):
            result = vision.compare(ref, cap, d / "overlay.png", method="auto")
        self.assertEqual(result.method, "opencv")
        self.assertIn("fallback", result.details)

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
        s.save_review(iid, ReviewedDetails("Storm debris pile", "Minor: hazard beside the road or sidewalk", desc, "", "Sam", confirmed, now()))
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


class RealDemoPhotos(unittest.TestCase):
    def test_import_real_photos_and_eval_pairs(self):

        ref, cap, d = _pair(blocked=True)
        shoot = Path(tempfile.mkdtemp(dir=_TMP))
        shutil.copy(ref, shoot / "reference.JPG")
        shutil.copy(cap, shoot / "blocked.jpeg")
        shutil.copy(ref, shoot / "cleared.jpg")
        s = Store(_TMP / "real.db")
        eval_root = _TMP / "eval-real"
        demo.EVAL_REAL, old = eval_root, demo.EVAL_REAL
        try:
            loc_id = demo.add_real("Palm St & 3rd / NE", shoot, "Curb ramp, facing north", s, to_eval=True)
        finally:
            demo.EVAL_REAL = old
        loc = s.location(loc_id)
        self.assertIn("Curb ramp", loc["description"])
        self.assertTrue(demo.demo_photo(loc["reference_path"], "initial"))
        self.assertTrue(demo.demo_photo(loc["reference_path"], "follow_up"))
        labels = (eval_root / "labels.csv").read_text().splitlines()
        self.assertIn("palm-st---3rd---ne-blocked,obstructed,,", labels)
        self.assertIn("palm-st---3rd---ne-cleared,clear,,", labels)
        self.assertTrue((eval_root / "palm-st---3rd---ne-blocked" / "capture.jpg").exists())
        with self.assertRaises(ValueError):
            demo.add_real("Palm St & 3rd / NE", shoot, store=s)

    def test_missing_blocked_photo(self):

        ref, _, _ = _pair(blocked=False)
        shoot = Path(tempfile.mkdtemp(dir=_TMP))
        shutil.copy(ref, shoot / "reference.jpg")
        with self.assertRaises(FileNotFoundError):
            demo.add_real("Nowhere", shoot, store=Store(_TMP / "real2.db"))


class Satellite(unittest.TestCase):
    """Offline checks for clearpath.satellite and its use in prompts and reports."""

    def _site(self):
        import json
        from clearpath import satellite
        ref, cap, d = _pair(blocked=True)
        ref = ref.rename(d / "reference.jpg")
        cap = cap.rename(d / "initial.jpg")
        info = {"spec": "x", "source": "esri", "layer": "1", "label": "Esri Wayback 2024-09-19",
                "captured": "2023-02-26", "detail": "", "attribution": "", "lat": 27.9, "lon": -82.4, "zoom": 19}
        meta = {"name": "Street", "lat": 27.92650, "lon": -82.45550, "zoom": 19,
                "images": {ref.name: info, "initial.jpg": {**info, "source": "noaa", "label": "NOAA NGS 20241014a-rgb",
                                                           "captured": "2024-10-14"}}}
        meta["images"]["reference.jpg"] = meta["images"].pop(ref.name)
        (d / "site.json").write_text(json.dumps(meta))
        return ref, cap, satellite

    def test_tile_math(self):
        from clearpath import satellite
        x, y = satellite._world_px(0, 0, 1)
        self.assertEqual((x, y), (256, 256))

    def test_prompt_switches_to_aerial(self):
        ref, cap, _ = self._site()
        mode, prompt = gemini.build_prompt(ref, capture_path=cap)
        self.assertEqual(mode, "aerial")
        self.assertIn("NOAA NGS 20241014a-rgb", prompt)
        self.assertIn("captured 2023-02-26", prompt)
        mode, _ = gemini.build_prompt(_pair(blocked=False)[0])
        self.assertEqual(mode, "ground")

    def test_report_has_coordinates_and_credits(self):
        ref, cap, satellite = self._site()
        s = Store(_TMP / "sat.db")
        iid = s.new_inspection(s.add_location("Street", ref))
        c = s.add_capture(SavedCapture(iid, "initial", cap, now()))
        comparison = vision.compare(ref, cap, cap.with_name("o.png"), method="opencv")
        comparison.details["imagery"] = satellite.imagery_for(ref, cap)
        s.save_comparison(c.capture_id, comparison)
        s.save_review(iid, ReviewedDetails("Storm debris pile", "Partly blocked: passable with difficulty",
                                           "Debris at the curb.", "", "Sam", True, now()))
        out = report.build(s.bundle(iid))
        self.assertIn("27.92650, -82.45550", out.text)
        self.assertIn("After imagery: NOAA NGS 20241014a-rgb, captured 2024-10-14", out.text)
        self.assertIn("NOAA National Geodetic Survey", out.html)
        self.assertIn("Esri World Imagery Wayback", out.html)


class AppFlow(unittest.TestCase):
    def _demo_app(self, url_page=None):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=180)
        if url_page:
            at.query_params["page"] = url_page
        at.run()
        return at

    def test_resident_reports_then_reviewer_clears(self):
        at = self._demo_app()
        at.sidebar.radio[0].set_value("Locations").run()
        next(b for b in at.button if "demo" in b.label).click().run()
        # resident: one photo and a note
        at.sidebar.radio[0].set_value("Report damage").run()
        at.text_area[0].set_value("Big branch across the sidewalk, no way past with a wheelchair.")
        next(b for b in at.button if b.label == "Send report").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("is with the reviewer" in s.value for s in at.success))
        # reviewer: queue -> open -> confirm -> send -> after cleanup -> cleared
        at.sidebar.radio[0].set_value("Review").run()
        self.assertIn("Needs review (1)", [h.value for h in at.subheader])
        next(b for b in at.button if b.label == "Open").click().run()
        self.assertTrue(any("Big branch across the sidewalk" in i.value for i in at.info))
        self.assertIn("Big branch across the sidewalk", at.text_area[0].value)  # pre-filled from the resident note
        next(t for t in at.text_input if t.label == "Your name").set_value("Tester")
        at.checkbox[0].check()
        next(b for b in at.button if b.label == "Confirm details").click().run()
        next(b for b in at.button if b.label.startswith("Mark as sent")).click().run()
        next(b for b in at.button if b.label == "Check after-cleanup photo").click().run()
        next(b for b in at.button if b.label == "Confirm cleared").click().run()
        self.assertFalse(at.exception)
        self.assertIn("Cleared.", [s.value for s in at.success])
        next(b for b in at.button if b.label == "Back to queue").click().run()
        self.assertIn("Closed (1)", [h.value for h in at.subheader])

    def test_resident_link_hides_reviewer_pages(self):
        at = self._demo_app(url_page="report")
        self.assertFalse(at.exception)
        self.assertEqual(len(at.sidebar.radio), 0)
        self.assertIn("Report storm damage", [h.value for h in at.header])
        self.assertTrue(any("35 feet" in w.value for w in at.warning))



def _jpeg_with_gps(lat, lon, rgb=None) -> bytes:
    import io
    from PIL import Image
    img = Image.fromarray(rgb if rgb is not None else np.full((60, 80, 3), 120, np.uint8))
    ex = Image.Exif()

    def dms(v):
        v = abs(v)
        return (float(int(v)), float(int(v * 60 % 60)), round(v * 3600 % 60, 4))
    ex[0x8825] = {1: "N" if lat >= 0 else "S", 2: dms(lat), 3: "E" if lon >= 0 else "W", 4: dms(lon)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=ex)
    return buf.getvalue()


class Geo(unittest.TestCase):
    def test_haversine_and_offset(self):
        from clearpath import geo
        lat, lon = geo.offset(28.0, -82.46, 300, 400)
        self.assertAlmostEqual(geo.haversine_m(28.0, -82.46, lat, lon), 500, delta=2)

    def test_exif_gps_roundtrip_and_strip(self):
        from clearpath import capture, geo
        data = _jpeg_with_gps(28.00123, -82.45987)
        lat, lon = geo.exif_gps(data)
        self.assertAlmostEqual(lat, 28.00123, places=4)
        self.assertAlmostEqual(lon, -82.45987, places=4)
        saved = capture.save_capture(data, "INS-9999", "initial").image_path
        self.assertIsNone(geo.exif_gps(saved.read_bytes()))  # GPS is gone once saved

    def test_canopy_index(self):
        from PIL import Image
        from clearpath import geo
        rng = np.random.default_rng(0)
        img = np.full((100, 100, 3), (150, 150, 150), np.uint8)
        leaves = rng.integers(-30, 30, (100, 50, 1))
        img[:, :50] = np.clip(np.array([40, 90, 35]) + leaves, 0, 255)   # textured dark green canopy, left half
        f = _TMP / "canopy.png"
        Image.fromarray(img).save(f)
        self.assertAlmostEqual(geo.canopy_fraction(f, radius_frac=0.5), 0.5, delta=0.05)
        self.assertEqual(geo.tree_risk(0.5), "high")
        water = np.full((100, 100, 3), (40, 95, 80), np.uint8)   # smooth green water is not canopy
        f2 = _TMP / "water.png"
        Image.fromarray(water).save(f2)
        self.assertLess(geo.canopy_fraction(f2), 0.02)


class DamageEquations(unittest.TestCase):
    def test_half_blocked_walkway(self):
        from clearpath.vision import ml
        walk = np.zeros((100, 100), bool)
        walk[50:, 20:80] = True
        changed = np.zeros_like(walk)
        changed[50:, 20:50] = True
        m = ml.damage_metrics(walk, changed, "Storm debris pile")
        self.assertAlmostEqual(m["blocked_share"], 0.5, places=2)
        self.assertAlmostEqual(m["narrowest_clear_width"], 0.5, places=2)
        self.assertAlmostEqual(m["damage_index"], 35.0)          # 100 * 0.5 * 0.7
        self.assertTrue(m["suggested_severity"].startswith("Partly"))

    def test_fully_blocked_and_power_line(self):
        from clearpath.vision import ml
        walk = np.zeros((100, 100), bool)
        walk[50:] = True
        m = ml.damage_metrics(walk, walk.copy(), "Fallen tree or limbs")
        self.assertTrue(m["suggested_severity"].startswith("Fully blocked"))
        m = ml.damage_metrics(walk, np.zeros_like(walk), "Downed power line")
        self.assertTrue(m["suggested_severity"].startswith("Fully blocked"))  # always critical

    def test_no_walkway_found_uses_lower_half(self):
        from clearpath.vision import ml
        m = ml.damage_metrics(np.zeros((40, 40), bool), np.ones((40, 40), bool))
        self.assertIn("lower half", m["note"])


OSM = [  # a tiny stand-in for an Overpass response
    {"type": "node", "id": 1, "lat": 28.001, "lon": -82.459,
     "tags": {"craft": "gardener", "name": "Oak Tree Care", "phone": "+1 813 555 0100"}},
    {"type": "node", "id": 2, "lat": 28.010, "lon": -82.459, "tags": {"shop": "hardware", "name": "Corner Hardware"}},
    {"type": "way", "id": 3, "center": {"lat": 28.02, "lon": -82.45}, "tags": {"amenity": "hospital", "name": "General Hospital"}},
    {"type": "node", "id": 4, "lat": 28.0005, "lon": -82.4590, "tags": {"amenity": "shelter", "shelter_type": "public_transport"}},
    {"type": "node", "id": 5, "lat": 28.003, "lon": -82.462, "tags": {"amenity": "community_centre", "name": "Rec Center"}},
]


class NearbyHelpAndPlan(unittest.TestCase):
    def test_resources_by_need(self):
        from clearpath.reporting import resources
        near = resources.nearby(28.0006, -82.4594, resources.needed_categories("Fallen tree or limbs"), elements=OSM)
        self.assertEqual(near["by_category"]["tree_service"][0]["name"], "Oak Tree Care")
        self.assertEqual(near["by_category"]["hospital"][0]["name"], "General Hospital")
        self.assertEqual([p["name"] for p in near["by_category"]["shelter"]], ["Rec Center"])  # bus shelter excluded
        self.assertLess(near["by_category"]["tree_service"][0]["distance_m"], 100)

    def test_offline_without_cache(self):
        from clearpath.reporting import resources
        self.assertFalse(resources.for_damage(1.0, 2.0, "Storm debris pile")["available"])
        self.assertFalse(resources.for_damage(None, None, None)["available"])

    def test_rule_plan(self):
        from clearpath.reporting import plan, resources
        near = resources.nearby(28.0006, -82.4594, resources.needed_categories("Downed power line"), elements=OSM)
        p = plan.rule_plan("Downed power line", None, 5, near, "Palm St")
        self.assertEqual(p["priority"], "Critical")
        self.assertTrue(any("911" in x for x in p["safety"]))
        near = resources.nearby(28.0006, -82.4594, resources.needed_categories("Fallen tree or limbs"), elements=OSM)
        p = plan.rule_plan("Fallen tree or limbs", "Fully blocked: road or sidewalk impassable", 60, near)
        self.assertEqual(p["priority"], "High")
        self.assertEqual(p["call_first"][0]["name"], "Oak Tree Care")


class StoreMigration(unittest.TestCase):
    def test_old_database_gets_map_columns(self):
        import sqlite3
        db = _TMP / "old.db"
        with sqlite3.connect(db) as c:
            c.execute("CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, "
                      "reference_path TEXT NOT NULL, created_at TEXT NOT NULL)")
            c.execute("INSERT INTO locations VALUES (1, 'Old spot', '', 'x.jpg', '2026-01-01')")
        s = Store(db)
        s.set_location_geo(1, 28.0, -82.0, None, 0.3)
        s.set_aerial(1, "after.jpg", {"verdict": "clear"})
        loc = s.location(1)
        self.assertEqual((loc["lat"], loc["canopy"], loc["aerial_result"]["verdict"]), (28.0, 0.3, "clear"))


class LocateReports(unittest.TestCase):
    def test_gps_photo_finds_nearest_spot(self):
        from clearpath import pipeline
        s = Store(_TMP / "loc.db")
        ref, _, _ = _pair(blocked=False)
        a = s.add_location("A", ref)
        s.set_location_geo(a, 28.0000, -82.4600)
        b = s.add_location("B", ref)
        s.set_location_geo(b, 28.0100, -82.4600)
        got = pipeline.locate(s, _jpeg_with_gps(28.0101, -82.4601))
        self.assertEqual((got["location"]["name"], got["matched_by"]), ("B", "photo GPS"))
        got = pipeline.locate(s, _jpeg_with_gps(10.0, 10.0), location_id=a)  # far away: falls back to the pick
        self.assertEqual(got["matched_by"], "resident's choice")
        with self.assertRaises(LookupError):
            pipeline.locate(s, _jpeg_with_gps(10.0, 10.0))


class ResidentsAPI(unittest.TestCase):
    def test_report_round_trip(self):
        from fastapi.testclient import TestClient
        from api import main
        main._store = None
        client = TestClient(main.app)
        demo.seed(main.store())
        spots = client.get("/api/locations").json()
        self.assertGreaterEqual(len(spots), 4)
        self.assertEqual(client.get(spots[0]["before_url"]).status_code, 200)
        photo = demo.demo_photo(main.store().location(spots[0]["id"])["reference_path"], "initial").read_bytes()
        with patch.object(gemini, "check_resident_photo", return_value="relevant"):
            r = client.post("/api/reports", files={"photo": ("p.jpg", photo, "image/jpeg")},
                            data={"location_id": spots[0]["id"], "note": "Tree down across the sidewalk"})
        self.assertEqual(r.status_code, 201, r.text)
        rid = r.json()["id"]
        st = client.get(f"/api/reports/{rid}").json()   # background analysis has run by now
        self.assertFalse(st["processing"])
        self.assertNotIn("note", st)                      # residents never see notes or photos
        events = main.store().bundle(rid)["events"]
        self.assertTrue(any((e["note"] or "").startswith("Resident: Tree down") for e in events))
        self.assertIsNotNone(main.store().bundle(rid)["plan"])

    def test_ground_upload_uses_satellite_before_and_finishes_processing(self):
        from fastapi.testclient import TestClient
        from api import main

        ref, photo, _ = Satellite()._site()
        s = Store(_TMP / "mixed-api.db")
        loc_id = s.add_location("Aerial test location", ref)
        draft = {"available": True, "path_blocked": True, "obstruction_type": "Fallen tree or limbs",
                 "model": "test", "observations": ["Tree across the road."], "regions": [[0.2, 0.2, 0.7, 0.7]]}
        with patch.object(main, "_store", s), patch.object(gemini, "observe", return_value=draft) as observe, \
             patch.object(gemini, "check_resident_photo", return_value="relevant"), \
             patch.object(vision, "compare", side_effect=AssertionError("Mixed photos cannot be aligned")):
            client = TestClient(main.app)
            before = client.get(f"/api/locations/{loc_id}/before.jpg")
            self.assertEqual(before.content, ref.read_bytes())
            response = client.post("/api/reports", files={"photo": ("initial.jpg", photo.read_bytes(), "image/jpeg")},
                                   data={"location_id": loc_id})
            self.assertEqual(response.status_code, 201, response.text)
            iid = response.json()["id"]
            self.assertFalse(client.get(f"/api/reports/{iid}").json()["processing"])
        self.assertEqual(observe.call_args.args[0], str(ref))
        self.assertEqual(observe.call_args.kwargs["imagery"]["mode"], "mixed")
        self.assertEqual(observe.call_args.kwargs["imagery"]["before"]["captured"], "2023-02-26")
        bundle = s.bundle(iid)
        self.assertIsNone(bundle["initial"]["comparison"])
        self.assertTrue(Path(bundle["initial"]["observation"]["overlay_path"]).is_file())
        s.save_review(iid, ReviewedDetails("Fallen tree or limbs", "Partly blocked: passable with difficulty",
                                           "Tree across the road.", "", "Sam", True, now()))
        out = report.build(s.bundle(iid))
        self.assertIn("Initial ground photo", out.html)
        self.assertNotIn("NOAA", out.html)

    def test_photo_screening_rejects_before_creating_a_report(self):
        from fastapi.testclient import TestClient
        from api import main

        ref, photo, _ = _pair(blocked=True)
        s = Store(_TMP / "photo-screening.db")
        loc = s.add_location("Street photo test", ref)
        with patch.object(main, "_store", s):
            client = TestClient(main.app)
            for decision, status, message in (
                ("unrelated", 422, "Upload a ground-level photo"),
                ("unclear", 422, "couldn't see the issue clearly"),
                (None, 503, "couldn't check your photo right now"),
            ):
                with self.subTest(decision=decision), patch.object(gemini, "check_resident_photo", return_value=decision):
                    response = client.post("/api/reports", files={"photo": ("upload.jpg", photo.read_bytes(), "image/jpeg")},
                                           data={"location_id": loc})
                    self.assertEqual(response.status_code, status)
                    self.assertIn(message, response.json()["detail"])
                    self.assertEqual(s.inspections(), [])

    def test_rejects_bad_input(self):
        from fastapi.testclient import TestClient
        from api import main
        client = TestClient(main.app)
        r = client.post("/api/reports", files={"photo": ("x.txt", b"not a photo", "text/plain")})
        self.assertEqual(r.status_code, 415)
        r = client.post("/api/reports", files={"photo": ("p.jpg", _jpeg_with_gps(1.0, 1.0), "image/jpeg")})
        self.assertEqual(r.status_code, 422)              # no spot near that GPS and none picked
        self.assertEqual(client.get("/api/reports/INS-9999").status_code, 404)


class NeighborhoodMap(unittest.TestCase):
    def test_pins_take_the_most_urgent_status_and_names_cannot_break_out(self):
        from clearpath import mapview
        locs = [{"id": 1, "name": "A</script><script>alert(1)</script>", "lat": 28.0, "lon": -82.4, "canopy": 0.4},
                {"id": 2, "name": "B", "lat": 28.01, "lon": -82.41, "canopy": None},
                {"id": 3, "name": "No coords", "lat": None, "lon": None}]
        ins = [{"id": "INS-1", "location_id": 1, "status": "resolved"},
               {"id": "INS-2", "location_id": 1, "status": "captured"}]
        d = mapview.map_data(locs, ins)
        self.assertEqual([x["color"] for x in d["spots"]], [mapview.COLOR["captured"], mapview.COLOR[None]])
        self.assertIn("high", d["spots"][0]["canopy"])
        html = mapview.leaflet_html(d)
        self.assertNotIn("</script><script>alert", html)


if __name__ == "__main__":
    unittest.main()
