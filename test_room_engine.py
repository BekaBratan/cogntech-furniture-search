import unittest
from unittest.mock import patch
import json
import io
import pandas as pd
from room_engine import *

class RoomTests(unittest.TestCase):
    def setUp(self):
        self.room = {"room_type":"bedroom","width_cm":400,"depth_cm":400,"budget_kzt":500000,"color":"белый","style":"minimalist"}
        self.items = [dict(product_id="B",name="Bed",category="bed",width_cm=160,depth_cm=210,price_kzt=180000,available=True,color="белый",style="минимализм"),
                      dict(product_id="W",name="Wardrobe",category="wardrobe",width_cm=80,depth_cm=45,price_kzt=41000,available=True,color="белый",style="minimalist")]
    def test_parser(self):
        p = parse_room_request("Мне нужен дизайн спальни 4 на 4 метра, в белом стиле, бюджет примерно 500К")
        self.assertEqual(p["budget_kzt"],500000)
        self.assertEqual(p["width_cm"],400)
        self.assertEqual(p["room_type"],"bedroom")
        self.assertNotIn("style",p)
    def test_examples(self):
        for kind in ROOMS:
            for example in layout_examples(kind):
                self.assertEqual(validate_layout(example["input"]["furniture"],example["output"]["placements"],example["input"]["room"]),[])
    def test_selection(self):
        sets = candidate_sets(pd.DataFrame(self.items),self.room)
        self.assertEqual({i["product_id"] for i in sets[0]},{"B","W"})
    def test_hidden_required(self):
        with self.assertRaises(ValueError):
            candidate_sets(pd.DataFrame(self.items),self.room,{"B"})
    def test_budget(self):
        with self.assertRaises(ValueError):
            candidate_sets(pd.DataFrame(self.items),{**self.room,"budget_kzt":100000})
    def test_solver(self):
        p = algorithm_layout(self.items,self.room,[(0,0,100,100)])
        self.assertIsNotNone(p)
        self.assertEqual(validate_layout(self.items,p,self.room,[(0,0,100,100)]),[])
    def test_unknown_duplicate_and_nan(self):
        p = [{"product_id":"B","x_cm":float("nan"),"y_cm":0,"rotation_deg":0},
             {"product_id":"B","x_cm":0,"y_cm":0,"rotation_deg":0}]
        self.assertTrue(validate_layout(self.items,p,self.room))
    def test_overlap(self):
        p = [dict(product_id=i["product_id"],x_cm=0,y_cm=0,rotation_deg=0) for i in self.items]
        self.assertTrue(any("overlap" in e for e in validate_layout(self.items,p,self.room)))
    def test_clearance(self):
        p = [dict(product_id="B",x_cm=0,y_cm=190,rotation_deg=0)]
        self.assertTrue(validate_layout(self.items[:1],p,self.room))
    def test_rotation(self):
        self.assertEqual(rectangle(self.items[0],dict(x_cm=0,y_cm=0,rotation_deg=90)),(0,0,210,160))
    def test_qwen_retry(self):
        good = algorithm_layout(self.items,self.room)
        responses = [io.BytesIO(json.dumps({"message":{"content":'{"placements":[]}'}}).encode()),
                     io.BytesIO(json.dumps({"message":{"content":json.dumps({"placements":good})}}).encode())]
        with patch("urllib.request.urlopen",side_effect=responses) as call:
            self.assertEqual(qwen_layout(self.items,self.room),good)
            self.assertEqual(call.call_count,2)
    def test_cloud_transport(self):
        good = algorithm_layout(self.items,self.room)
        response = io.BytesIO(json.dumps({"choices":[{"message":{"content":json.dumps({"placements":good})}}]}).encode())
        with patch("urllib.request.urlopen",return_value=response) as call:
            self.assertEqual(cloud_layout(self.items,self.room,"test-not-a-real-key"),good)
            self.assertEqual(call.call_args.args[0].full_url,"https://api.groq.com/openai/v1/chat/completions")
    def test_missing_cloud_key(self):
        with self.assertRaises(ValueError):
            cloud_layout(self.items,self.room,"")

if __name__ == "__main__":
    unittest.main()
