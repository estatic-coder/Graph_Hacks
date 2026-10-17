import unittest
from orbitflow.api import create_order
from orbitflow.manual_review import approve_review
from orbitflow.storage import SHIPMENTS, EVENTS
from orbitflow.stock import STOCK, RESERVATIONS
from orbitflow.carrier import FAILURES, LABELS
from orbitflow.notify import MESSAGES

class ReviewTests(unittest.TestCase):
    def setUp(self):
        SHIPMENTS.clear(); EVENTS.clear(); RESERVATIONS.clear(); FAILURES.clear(); LABELS.clear(); MESSAGES.clear()
        STOCK.clear(); STOCK.update({"book": 5, "laptop": 2})

    def test_review_approval_ships(self):
        create_order({"order_id":"r1","customer_id":"vip-1","amount":40,"sku":"book"})
        s = approve_review("r1", "book")
        self.assertEqual(s.status, "shipped")
        self.assertIn(("r1", "review_approved"), EVENTS)

    def test_review_requires_review_status(self):
        create_order({"order_id":"r2","customer_id":"regular","amount":40,"sku":"book"})
        with self.assertRaises(ValueError):
            approve_review("r2", "book")
