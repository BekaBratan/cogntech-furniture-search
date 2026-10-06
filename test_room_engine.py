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
    def test_available_partial(self):
        items = candidate_sets(pd.DataFrame(self.items[1:]),self.room,missing_policy="available")[0]
        self.assertEqual([i["product_id"] for i in items],["W"])
    def test_placeholder_missing_bed(self):
        items = candidate_sets(pd.DataFrame(self.items[1:]),self.room,missing_policy="placeholder")[0]
        virtual = [i for i in items if i.get("placeholder")]
        self.assertEqual(virtual[0]["category"],"bed")
        self.assertIsNone(virtual[0]["price_kzt"])
        self.assertEqual(catalog_cost(items),41000)
        p = algorithm_layout(items,self.room)
        self.assertIsNotNone(p)
        self.assertEqual(validate_layout(items,p,self.room),[])
    def test_placeholder_does_not_replace_present_bed(self):
        items = candidate_sets(pd.DataFrame(self.items),self.room,missing_policy="placeholder")[0]
        self.assertFalse(any(i.get("placeholder") for i in items))
    def test_placeholders_all_missing(self):
        df = pd.DataFrame(self.items).iloc[:0]
        items = candidate_sets(df,self.room,missing_policy="placeholder")[0]
        self.assertEqual(len(items),2)
        self.assertEqual(catalog_cost(items),0)
        self.assertTrue(all(i.get("placeholder") and i["price_kzt"] is None for i in items))
    def test_hidden_required(self):
        with self.assertRaises(ValueError):
            candidate_sets(pd.DataFrame(self.items),self.room,{"B"})
    def test_budget(self):
        with self.assertRaises(ValueError):
            candidate_sets(pd.DataFrame(self.items),{**self.room,"budget_kzt":100000})
    def test_optional_budget(self):
        for request in ({**self.room,"budget_kzt":None},{k:v for k,v in self.room.items() if k != "budget_kzt"}):
            items = candidate_sets(pd.DataFrame(self.items),request)[0]
            self.assertEqual({i['product_id'] for i in items},{'B','W'})
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

    def test_cloud_403_details_redacted(self):
        from urllib.error import HTTPError
        key = "gsk_testsecret"
        body = io.BytesIO(json.dumps({"error":{"message":"Model permission denied "+key}}).encode())
        error = HTTPError("https://api.groq.com",403,"Forbidden",{},body)
        with patch("urllib.request.urlopen",side_effect=error) as call:
            with self.assertRaises(CloudServiceError) as caught:
                cloud_layout(self.items,self.room,key)
        self.assertIn("Model permission denied",str(caught.exception))
        self.assertNotIn(key,str(caught.exception))
        self.assertEqual(call.call_count,1)
        self.assertEqual(call.call_args.args[0].get_header("User-agent"),"cogntech-furniture-search/1.0")

    def test_cloud_non_json_403(self):
        from urllib.error import HTTPError
        error = HTTPError("https://api.groq.com",403,"Forbidden",{},io.BytesIO(b"error code: 1010"))
        with patch("urllib.request.urlopen",side_effect=error):
            with self.assertRaisesRegex(CloudServiceError,"Cloudflare 1010"):
                cloud_layout(self.items,self.room,"test-key")

if __name__ == "__main__":
    unittest.main()
