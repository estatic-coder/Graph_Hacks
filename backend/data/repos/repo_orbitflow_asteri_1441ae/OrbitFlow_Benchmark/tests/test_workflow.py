import unittest
from orbitflow.api import create_order
from orbitflow.storage import SHIPMENTS, EVENTS
from orbitflow.stock import STOCK, RESERVATIONS
from orbitflow.carrier import FAILURES, LABELS
from orbitflow.notify import MESSAGES

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        SHIPMENTS.clear(); EVENTS.clear(); RESERVATIONS.clear(); FAILURES.clear(); LABELS.clear(); MESSAGES.clear()
        STOCK.clear(); STOCK.update({"book": 5, "laptop": 2})

    def test_successful_shipping(self):
        s = create_order({"order_id":"o1","customer_id":"regular","amount":40,"sku":"book"})
        self.assertEqual(s.status, "shipped")
        self.assertEqual(STOCK["book"], 4)
        self.assertIn(("o1", "shipped"), MESSAGES)

    def test_vip_review_does_not_reserve(self):
        s = create_order({"order_id":"o2","customer_id":"vip-1","amount":40,"sku":"book"})
        self.assertEqual(s.status, "review")
        self.assertEqual(STOCK["book"], 5)
        self.assertEqual(MESSAGES, [])

    def test_carrier_failure_releases_stock(self):
        FAILURES.add("o3")
        s = create_order({"order_id":"o3","customer_id":"regular","amount":40,"sku":"book"})
        self.assertEqual(s.status, "failed")
        self.assertEqual(s.attempts, 3)
        self.assertEqual(STOCK["book"], 5)
        self.assertEqual([e for _,e in EVENTS].count("carrier_retry"), 3)
        self.assertIn(("o3", "failed"), MESSAGES)

    def test_out_of_stock(self):
        STOCK["book"] = 0
        s = create_order({"order_id":"o4","customer_id":"regular","amount":40,"sku":"book"})
        self.assertEqual(s.status, "out_of_stock")
        self.assertNotIn("o4", SHIPMENTS)
