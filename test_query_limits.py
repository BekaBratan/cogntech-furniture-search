import unittest
import pandas as pd
from core import parse_limits,evaluate_rules

class PriceTests(unittest.TestCase):
    def test_kazakh_price_without_thousands_is_literal(self):
        filters = parse_limits('Ақ шкаф, бағасы 100 ден төмен')
        self.assertEqual(filters['max_price_kzt'],100)
        row = dict(product_id='P001',price_kzt=48000,available=True)
        self.assertFalse(evaluate_rules(row,filters,set())['R3: бюджеттен аспайды'])

    def test_explicit_thousands(self):
        for query in ('Ақ шкаф, бағасы 100 мыңнан төмен','цена до 100 тыс','бюджет 100К','бағасы 100 000 теңгеден төмен'):
            with self.subTest(query=query):
                self.assertEqual(parse_limits(query)['max_price_kzt'],100000)

    def test_no_budget_remains_optional(self):
        self.assertNotIn('max_price_kzt',parse_limits('Ақ шкаф керек'))

if __name__=='__main__':
    unittest.main()
