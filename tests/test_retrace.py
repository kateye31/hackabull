"""Run with:  python -m unittest -v"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from app import priority
from detection import detect, evaluate, make_demo_scene


class PriorityRules(unittest.TestCase):
    def test_road_is_always_highest(self):
        self.assertEqual(priority.compute({"category": "flooded_road"})["priority"], 1)

    def test_anything_blocking_a_road_goes_to_the_top(self):
        self.assertEqual(priority.compute({"category": "debris", "blocks_road": True})["priority"], 1)

    def test_deep_or_moving_water_bumps_priority(self):
        self.assertEqual(priority.compute({"category": "flooded_building"})["priority"], 2)
        self.assertEqual(priority.compute({"category": "flooded_building", "depth": "waist"})["priority"], 1)
        self.assertEqual(priority.compute({"category": "standing_water", "moving": True})["priority"], 2)

    def test_building_cost_needs_sqft_then_scales(self):
        c = priority.compute({"category": "flooded_building"})["cost"]
        self.assertTrue(c["needs_sqft"])
        self.assertIsNone(c["low"])
        c = priority.compute({"category": "flooded_building", "affected_sqft": 100})["cost"]
        lo = 100 * (priority.CLEANUP_PER_SQFT[0] + priority.DRYWALL_PER_SQFT[0])
        self.assertEqual(c["low"], round(lo))

    def test_sort_open_first_then_priority(self):
        items = [priority.compute(x) | x for x in (
            {"id": "a", "category": "debris", "status": "New"},
            {"id": "b", "category": "flooded_road", "status": "Cleared"},
            {"id": "c", "category": "flooded_road", "status": "New"},
        )]
        self.assertEqual([i["id"] for i in sorted(items, key=priority.sort_key)], ["c", "a", "b"])


class DetectionOnSyntheticScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.scene = cls.tmp / "scenes" / "t"
        make_demo_scene.main(["--out", str(cls.scene)])
        cls.out = detect.detect(cls.scene)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_finds_flooded_roads_and_buildings(self):
        cats = {i["category"] for i in self.out["issues"]}
        self.assertIn("flooded_road", cats)
        self.assertIn("flooded_building", cats)

    def test_pond_and_pools_not_flagged(self):
        rows = dict(evaluate.eval_scene(self.scene))
        self.assertTrue(rows["Pools/ponds wrongly flagged, with before/after"].startswith("0 of"))

    def test_new_water_iou(self):
        rows = dict(evaluate.eval_scene(self.scene))
        self.assertGreater(float(rows["New-water (flood) IoU"].rstrip("%")), 80)

    def test_pins_inside_scene_bounds(self):
        (s, w), (n, e) = self.out["bounds"]
        for i in self.out["issues"]:
            self.assertTrue(s <= i["lat"] <= n and w <= i["lon"] <= e, i["id"])


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import server
        cls.tmp = Path(tempfile.mkdtemp())
        scene = cls.tmp / "scenes" / "t"
        make_demo_scene.main(["--out", str(scene)])
        detect.detect(scene)
        cls.app = server.create(cls.tmp / "t.db", reset=True, scenes_dir=cls.tmp / "scenes")
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_issues_loaded_and_sorted(self):
        items = self.client.get("/api/issues").get_json()
        self.assertGreater(len(items), 5)
        self.assertEqual([i["priority"] for i in items], sorted(i["priority"] for i in items))

    def test_resident_report_then_status_flow(self):
        r = self.client.post("/api/reports", data={
            "lat": "27.961", "lon": "-82.458", "category": "flooded_road", "depth": "knee", "flow": "moving"})
        self.assertEqual(r.status_code, 201)
        iid = r.get_json()["id"]
        self.assertEqual(r.get_json()["priority"], 1)
        for status in ("Verified", "Cleared"):
            r = self.client.patch(f"/api/issues/{iid}", json={"status": status})
            self.assertEqual(r.get_json()["status"], status)
        self.assertFalse(r.get_json()["open"])
        self.assertEqual([h["status"] for h in r.get_json()["history"]], ["New", "Verified", "Cleared"])

    def test_report_requires_pin(self):
        r = self.client.post("/api/reports", data={"category": "debris"})
        self.assertEqual(r.status_code, 400)

    def test_bad_status_rejected(self):
        iid = self.client.get("/api/issues").get_json()[0]["id"]
        self.assertEqual(self.client.patch(f"/api/issues/{iid}", json={"status": "Nope"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
