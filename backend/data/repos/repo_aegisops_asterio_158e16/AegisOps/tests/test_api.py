import unittest
from aegisops.api import ingest_alert, list_host_incidents, release_host
from aegisops.firewall import BLOCKED_HOSTS
from aegisops.store import INCIDENTS

class ApiTests(unittest.TestCase):
    def setUp(self):
        BLOCKED_HOSTS.clear(); INCIDENTS.clear()
    def test_ingest_and_list(self):
        ingest_alert({"host":"edge-1","kind":"malware","severity":9})
        self.assertEqual(len(list_host_incidents("edge-1")), 1)
    def test_release(self):
        BLOCKED_HOSTS.add("edge-1")
        self.assertTrue(release_host("edge-1"))
        self.assertNotIn("edge-1", BLOCKED_HOSTS)
