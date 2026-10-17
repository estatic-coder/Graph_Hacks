import unittest
from aegisops.rules import classify_event

class RuleTests(unittest.TestCase):
    def test_critical_malware(self):
        self.assertEqual(classify_event("edge-1", "malware", 9), "critical")
    def test_trusted_host_review(self):
        self.assertEqual(classify_event("core-db", "malware", 10), "review")
    def test_low_severity_warning(self):
        self.assertEqual(classify_event("edge-1", "malware", 3), "warning")
    def test_benign_ignored(self):
        self.assertEqual(classify_event("edge-1", "cpu_spike", 9), "ignore")
