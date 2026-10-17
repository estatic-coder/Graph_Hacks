import unittest
from sentinelshop.api import checkout, order_history
from sentinelshop.inventory import STOCK
from sentinelshop.repository import ORDERS

class APITests(unittest.TestCase):
    def setUp(self):
        STOCK["BOOK-1"] = 12
        ORDERS.clear()

    def test_checkout(self):
        order = checkout("user:trusted-alice", "BOOK-1", 1, 100)
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(len(order_history("user:trusted-alice")), 1)

    def test_rejects_invalid_session(self):
        with self.assertRaises(PermissionError):
            checkout("bad-token", "BOOK-1", 1, 100)
