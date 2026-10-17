import unittest
from nexuspay.api import create_payment, get_payment, approve_payment, reject_payment, refund_payment
from nexuspay.config import MAX_GATEWAY_RETRIES
from nexuspay.gateway import FAIL_ALWAYS, FAIL_ONCE, CALL_COUNTS, AUTHORIZATIONS
from nexuspay.ledger import BALANCES, HOLDS
from nexuspay.store import PAYMENTS, EVENTS
from nexuspay.notify import MESSAGES
from nexuspay.refunds import REFUNDS

class PaymentTests(unittest.TestCase):
    def setUp(self):
        PAYMENTS.clear(); EVENTS.clear(); HOLDS.clear(); FAIL_ALWAYS.clear(); FAIL_ONCE.clear()
        CALL_COUNTS.clear(); AUTHORIZATIONS.clear(); MESSAGES.clear(); REFUNDS.clear()
        BALANCES.clear(); BALANCES.update({"regular-1": 2000, "vip-1": 5000, "blocked-1": 1000})

    def make(self, pid, account="regular-1", amount=100):
        return create_payment({"payment_id": pid, "account_id": account, "amount": amount})

    def test_successful_payment(self):
        p = self.make("p1")
        self.assertEqual(p.status, "paid")
        self.assertEqual(BALANCES["regular-1"], 1900)
        self.assertNotIn("p1", HOLDS)

    def test_persistent_timeout_restores_balance(self):
        FAIL_ALWAYS.add("p2")
        p = self.make("p2")
        self.assertEqual(p.status, "failed")
        self.assertEqual(CALL_COUNTS["p2"], MAX_GATEWAY_RETRIES + 1)
        self.assertEqual(BALANCES["regular-1"], 2000)
        self.assertEqual(EVENTS.count(("p2", "gateway_timeout")), 3)
        self.assertIn(("p2", "failed"), MESSAGES)

    def test_transient_timeout_then_success(self):
        FAIL_ONCE.add("p3")
        p = self.make("p3")
        self.assertEqual(p.status, "paid")
        self.assertEqual(CALL_COUNTS["p3"], 2)
        self.assertEqual(EVENTS.count(("p3", "gateway_timeout")), 1)

    def test_vip_review_no_hold(self):
        p = self.make("p4", "vip-1", 20)
        self.assertEqual(p.status, "review")
        self.assertNotIn("p4", HOLDS)
        self.assertEqual(MESSAGES, [])

    def test_blocked_not_saved(self):
        p = self.make("p5", "blocked-1", 20)
        self.assertEqual(p.status, "blocked")
        self.assertNotIn("p5", PAYMENTS)

    def test_review_approval_paid(self):
        self.make("p6", "vip-1", 20)
        p = approve_payment("p6")
        self.assertEqual(p.status, "paid")
        self.assertIn(("p6", "review_approved"), EVENTS)

    def test_review_rejection(self):
        self.make("p7", "vip-1", 20)
        p = reject_payment("p7")
        self.assertEqual(p.status, "rejected")
        self.assertNotIn("p7", HOLDS)

    def test_refund_after_paid(self):
        self.make("p8")
        p = refund_payment("p8")
        self.assertEqual(p.status, "refunded")
        self.assertIn("p8", REFUNDS)

    def test_refund_requires_paid(self):
        self.make("p9", "vip-1", 20)
        with self.assertRaises(ValueError):
            refund_payment("p9")

    def test_get_review_payment(self):
        self.make("p10", "vip-1", 20)
        self.assertEqual(get_payment("p10").status, "review")
