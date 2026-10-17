import unittest
from aegisops.pipeline import process_event
from aegisops.firewall import BLOCKED_HOSTS
from aegisops.notifications import MESSAGES
from aegisops.audit import AUDIT_LOG
from aegisops.store import INCIDENTS

class PipelineTests(unittest.TestCase):
    def setUp(self):
        BLOCKED_HOSTS.clear(); MESSAGES.clear(); AUDIT_LOG.clear(); INCIDENTS.clear()
    def test_critical_isolation(self):
        incident = process_event({"host":"edge-1","kind":"malware","severity":9})
        self.assertEqual(incident.status, "isolated")
        self.assertIn("edge-1", BLOCKED_HOSTS)
    def test_trusted_host_not_isolated(self):
        incident = process_event({"host":"core-db","kind":"malware","severity":10})
        self.assertEqual(incident.status, "manual_review")
        self.assertNotIn("core-db", BLOCKED_HOSTS)
    def test_ignored_no_incident(self):
        self.assertIsNone(process_event({"host":"edge-1","kind":"cpu_spike","severity":9}))
        self.assertEqual(len(INCIDENTS), 0)
    def test_critical_notifies_both(self):
        process_event({"host":"edge-1","kind":"malware","severity":9})
        self.assertEqual(len(MESSAGES), 2)
    def test_warning_only_security(self):
        process_event({"host":"edge-1","kind":"malware","severity":3})
        self.assertEqual(len(MESSAGES), 1)
