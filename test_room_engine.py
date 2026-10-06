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
            candidate_sets(pd.DataFrame(self.items),self.room,{"B"},missing_policy="strict")
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

    def test_invalid_model_layout_is_geometry_error(self):
        calls = []
        def generator(messages):
            calls.append(list(messages))
            return '{"placements":[]}'
        with self.assertRaises(LayoutValidationError):
            qwen_layout(self.items,self.room,generator=generator)
        self.assertEqual(len(calls),3)
        self.assertIn('validated_starting_layout',calls[0][-1]['content'])

    def test_model_receives_valid_seed(self):
        def generator(messages):
            brief = json.loads(messages[-1]['content'].split('Request: ',1)[1])
            seed = brief['validated_starting_layout']
            self.assertEqual(validate_layout(self.items,seed['placements'],self.room),[])
            return json.dumps(seed)
        plan = qwen_layout(self.items,self.room,generator=generator)
        self.assertEqual(validate_layout(self.items,plan,self.room),[])

    def test_living_room_uses_catalog_categories(self):
        items = [dict(product_id=cat,name=cat,category=cat,width_cm=w,depth_cm=d,price_kzt=10000,available=True,color='белый',style='minimalist')
                 for cat,w,d in [('sofa',200,90),('wardrobe',80,45),('dresser',75,33),('dining_table',120,80)]]
        room = {**self.room,'room_type':'living_room'}
        selected = candidate_sets(pd.DataFrame(items),room)[0]
        self.assertEqual({i['category'] for i in selected},{'sofa','wardrobe','dresser','dining_table'})
        alternatives = candidate_sets(pd.DataFrame(items),room)
        self.assertTrue(any(len(group)==1 and group[0]['category']=='sofa' for group in alternatives))
        plan = algorithm_layout(selected,room)
        self.assertIsNotNone(plan)
        self.assertEqual(validate_layout(selected,plan,room),[])

    def test_new_room_types(self):
        self.assertEqual(parse_room_request('Асүй 4 на 4 метра')['room_type'],'kitchen')
        self.assertEqual(parse_room_request('Дизайн столовой 4 на 4 метра')['room_type'],'dining_room')

    def test_missing_office_defaults_to_templates(self):
        room = {**self.room,'room_type':'office'}
        items = candidate_sets(pd.DataFrame(self.items),room)[0]
        self.assertEqual({i['category'] for i in items},{'desk','chair'})
        self.assertTrue(all(i.get('placeholder') for i in items))
        self.assertTrue(all(i['price_kzt'] is None for i in items))

    def test_two_placeholder_chairs_have_separate_placements(self):
        room = {**self.room,'room_type':'office','quantities':{'desk':1,'chair':2,'dresser':0,'bookcase':0}}
        items = candidate_sets(pd.DataFrame(self.items),room)[0]
        chairs = [i for i in items if i['category']=='chair']
        self.assertEqual(len(chairs),2)
        self.assertEqual({i['product_id'] for i in chairs},{'PLACEHOLDER_CHAIR__1','PLACEHOLDER_CHAIR__2'})
        self.assertTrue(all(i['base_product_id']=='PLACEHOLDER_CHAIR' for i in chairs))
        plan = algorithm_layout(items,room)
        self.assertIsNotNone(plan)
        self.assertEqual(validate_layout(items,plan,room),[])
        self.assertEqual(len(plan),3)

    def test_multiple_catalog_prices_and_budget(self):
        room = {**self.room,'quantities':{'bed':1,'wardrobe':2}}
        items = candidate_sets(pd.DataFrame(self.items),room)[0]
        self.assertEqual(catalog_cost(items),262000)
        self.assertEqual(len({i['product_id'] for i in items}),3)
        with self.assertRaises(ValueError):
            candidate_sets(pd.DataFrame(self.items),{**room,'budget_kzt':250000})

    def test_invalid_and_zero_quantities(self):
        for quantities in ({'chair':2},{'bed':0},{'bed':-1},{'bed':True},{'bed':7},{'bed':1.5}):
            with self.subTest(quantities=quantities):
                with self.assertRaises(ValueError):
                    candidate_sets(pd.DataFrame(self.items),{**self.room,'quantities':quantities})

    def test_quantity_query(self):
        parsed = parse_room_request('Кабинет 4 на 4 метра, 1 письменный стол и 2 стула')
        self.assertEqual(parsed['quantities'],{'desk':1,'chair':2})
        self.assertEqual(parse_room_request('2 орындық керек')['quantities'],{'chair':2})

    def test_room_design_presets(self):
        self.assertEqual(design_quantities('bedroom')['nightstand'],2)
        self.assertEqual(design_quantities('dining_room')['chair'],4)
        self.assertEqual(design_quantities('office')['bookcase'],1)
        self.assertEqual(design_quantities('dining_room',300,300)['chair'],2)
        for kind in ROOMS:
            counts = design_quantities(kind)
            self.assertEqual(set(counts),set(ROOMS[kind][0]+ROOMS[kind][1]))
            self.assertLessEqual(sum(counts.values()),20)

    def test_word_quantities_and_generic_stands(self):
        self.assertEqual(parse_room_request('Спальня, две тумбы и один комод')['quantities'],{'nightstand':2,'dresser':1})
        self.assertEqual(parse_room_request('Жатын бөлме, екі тумба және бір төсек')['quantities'],{'nightstand':2,'bed':1})
        self.assertEqual(parse_room_request('Office with two chairs')['quantities'],{'chair':2})
        self.assertEqual(parse_room_request('Кабинет, стол: 2, без комода')['quantities'],{'desk':2,'dresser':0})
        self.assertEqual(parse_room_request('екі тумба','bedroom')['quantities'],{'nightstand':2})
        self.assertEqual(parse_room_request('два стола','office')['quantities'],{'desk':2})

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
