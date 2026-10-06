import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from catalog_io import load_catalog_file, find_product_image, memory_path, source_link_label
from core import make_search_text, parse_query, search
from room_engine import candidate_sets, algorithm_layout, validate_layout

BASE = Path(__file__).parent

class FakeModel:
    def encode(self,texts,**kwargs):
        return np.zeros((len(texts),384))

class CatalogTests(unittest.TestCase):
    def test_current_catalog_normalization(self):
        df = load_catalog_file(BASE)
        self.assertGreaterEqual(len(df),100)
        self.assertEqual(set(df.category),{"bed","wardrobe","kitchen_cabinets","dining_table","tv","sofa","dresser"})
        self.assertAlmostEqual(float(df.loc[df.product_id=="P122","width_cm"].iloc[0]),138.1)
        self.assertAlmostEqual(float(df.loc[df.product_id=="P124","width_cm"].iloc[0]),67.6)
        self.assertFalse(df[["price_kzt","width_cm","depth_cm"]].isna().any().any())
        self.assertTrue(all(make_search_text(row) for _,row in df.iterrows()))

    def test_all_catalog_categories_search_without_budget(self):
        df = load_catalog_file(BASE)
        examples = {"bed":"Ақ төсек керек","wardrobe":"Ақ шкаф керек","sofa":"Жасыл диван керек",
                    "dresser":"Ақ комод керек","kitchen_cabinets":"Ақ кухонный шкаф керек",
                    "dining_table":"Ақ обеденный стол керек","tv":"Қара теледидар керек"}
        for category,query in examples.items():
            with self.subTest(category=category):
                self.assertEqual(parse_query(query)["category"],category)
                results,_,filters = search(df,np.zeros((len(df),384)),FakeModel(),query,set())
                self.assertNotIn("max_price_kzt",filters)
                self.assertFalse(results.empty)
                self.assertTrue(results.category.eq(category).all())

    def test_current_catalog_room(self):
        df = load_catalog_file(BASE)
        room = {"room_type":"bedroom","width_cm":400,"depth_cm":400,"budget_kzt":None}
        sets = candidate_sets(df,room,missing_policy="available")
        plan = None
        for selected in sets:
            plan = algorithm_layout(selected,room)
            if plan is not None:
                self.assertEqual(validate_layout(selected,plan,room),[])
                break
        self.assertIsNotNone(plan)

    def test_image_replacement_and_absent_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            row = {"product_id":"P001","image_file":"images/P001.jpg"}
            self.assertIsNone(find_product_image(base,row))
            (base/"images").mkdir()
            image = base/"images/P001.jpg"
            old = b"old catalog image"
            image.write_bytes(old)
            sha = hashlib.sha1(b"blob "+str(len(old)).encode()+b"\0"+old).hexdigest()
            (base/"legacy_image_hashes.json").write_text(json.dumps({"images/P001.jpg":sha}))
            self.assertIsNone(find_product_image(base,row))
            image.write_bytes(b"new catalog image")
            self.assertEqual(find_product_image(base,row),image)
            other = {"product_id":"missing","image_file":"../outside.jpg"}
            self.assertIsNone(find_product_image(base,other))

    def test_catalog_scoped_memory_and_link_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base/"catalog.xlsx").write_bytes(b"old")
            first = memory_path(base)
            (base/"catalog.xlsx").write_bytes(b"new")
            self.assertNotEqual(first,memory_path(base))
        self.assertIn("категория",source_link_label("https://kaspi.kz/shop/c/beds/"))
        self.assertNotIn("категория",source_link_label("https://kaspi.kz/shop/p/bed-123/"))

if __name__ == "__main__":
    unittest.main()
