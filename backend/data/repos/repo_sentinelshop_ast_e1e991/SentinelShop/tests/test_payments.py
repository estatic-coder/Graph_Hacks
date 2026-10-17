import unittest
from sentinelshop.payments import authorize_payment

class PaymentTests(unittest.TestCase):
    def test_trusted_user_approved(self):
        self.assertEqual(authorize_payment("trusted-alice", 100), "charge:trusted-alice:100")

    def test_high_risk_declined(self):
        self.assertIsNone(authorize_payment("new-bob", 800))

    def test_invalid_amount_declined(self):
        self.assertIsNone(authorize_payment("trusted-alice", 0))
