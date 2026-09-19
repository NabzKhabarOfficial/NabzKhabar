import unittest

from car_prices import format_price, is_supported_brand


class CarPricePipelineTests(unittest.TestCase):
    def test_format_price(self):
        self.assertEqual(format_price("1,617,000,000"), "۱٬۶۱۷٬۰۰۰٬۰۰۰")
        self.assertEqual(format_price("—"), "—")

    def test_supported_domestic_and_assembly_brands(self):
        self.assertTrue(is_supported_brand("سایپا"))
        self.assertTrue(is_supported_brand("مدیران خودرو"))
        self.assertTrue(is_supported_brand("کرمان موتور"))

    def test_imported_only_brand_is_excluded(self):
        self.assertFalse(is_supported_brand("بنز"))


if __name__ == "__main__":
    unittest.main()
