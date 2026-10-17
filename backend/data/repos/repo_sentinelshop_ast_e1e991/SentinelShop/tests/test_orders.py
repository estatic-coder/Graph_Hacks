import unittest
from sentinelshop.inventory import STOCK
from sentinelshop.notifications import SENT_MESSAGES
from sentinelshop.repository import ORDERS
from sentinelshop.orders import place_order

class OrderTests(unittest.TestCase):
    def setUp(self):
        STOCK["BOOK-1"] = 12
        SENT_MESSAGES.clear()
        ORDERS.clear()

    def test_successful_order(self):
        order = place_order("trusted-alice", "BOOK-1", 1, 100)
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(STOCK["BOOK-1"], 11)
        self.assertEqual(len(SENT_MESSAGES), 1)
        self.assertEqual(len(ORDERS), 1)

    def test_declined_payment_has_no_side_effects(self):
        order = place_order("new-bob", "BOOK-1", 1, 800)
        self.assertEqual(order.status, "payment_declined")
        self.assertEqual(STOCK["BOOK-1"], 12)
        self.assertEqual(SENT_MESSAGES, [])
        self.assertEqual(ORDERS, [])
