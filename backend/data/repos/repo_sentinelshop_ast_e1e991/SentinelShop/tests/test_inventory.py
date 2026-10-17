import unittest
from sentinelshop.inventory import STOCK, check_stock, reserve_stock

class InventoryTests(unittest.TestCase):
    def setUp(self):
        STOCK["LAMP-2"] = 4

    def test_reservation_reduces_stock(self):
        self.assertTrue(check_stock("LAMP-2", 2))
        self.assertTrue(reserve_stock("LAMP-2", 2))
        self.assertEqual(STOCK["LAMP-2"], 2)
