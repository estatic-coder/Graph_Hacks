import unittest
from orbitflow.risk import evaluate_risk

class RiskTests(unittest.TestCase):
    def test_vip_review(self):
        self.assertEqual(evaluate_risk("vip-1", 10), "manual_review")

    def test_high_value_review(self):
        self.assertEqual(evaluate_risk("regular", 500), "manual_review")

    def test_regular_approved(self):
        self.assertEqual(evaluate_risk("regular", 499), "approved")
