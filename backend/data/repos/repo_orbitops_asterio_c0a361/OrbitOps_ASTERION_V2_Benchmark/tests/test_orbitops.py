import unittest
from orbitops.api import create_alert, approve_alert, reject_alert, run_agent_once, retry_failed_alert, get_alert
from orbitops.store import ALERTS, EVENTS, PENDING
from orbitops.credits import BALANCE, HELD
from orbitops.pager import ALWAYS_FAIL, FAIL_FIRST, CALLS, INCIDENTS, NOTICES
from orbitops.reopen import REOPENED
from orbitops.maintenance import sweep_holds

class OrbitOpsTests(unittest.TestCase):
    def setUp(self):
        for obj in (ALERTS, EVENTS, PENDING, HELD, ALWAYS_FAIL, FAIL_FIRST, CALLS, INCIDENTS, NOTICES, REOPENED):
            obj.clear()
        BALANCE.update(core=4, security=2)

    def make(self, alert_id="a1", team="core", severity=3, source="production"):
        return create_alert(dict(alert_id=alert_id, service="billing", team=team, severity=severity, source=source))

    def test_initial_enqueue_no_send(self):
        a = self.make()
        self.assertEqual((a.status, BALANCE["core"], PENDING, CALLS), ("pending", 3, ["a1"], {}))

    def test_send_success(self):
        self.make()
        self.assertEqual(run_agent_once().status, "sent")
        self.assertEqual(CALLS["a1"], 1)
        self.assertNotIn("a1", HELD)
        self.assertEqual(BALANCE["core"], 3)

    def test_timeout_once(self):
        FAIL_FIRST.add("a1")
        self.make()
        self.assertEqual(run_agent_once().incident_key, "INC-a1-2")
        self.assertEqual(EVENTS.count(("a1", "page_timeout")), 1)

    def test_exhausted_releases(self):
        ALWAYS_FAIL.add("a1")
        self.make()
        self.assertEqual(run_agent_once().status, "failed")
        self.assertEqual(CALLS["a1"], 3)
        self.assertEqual(BALANCE["core"], 4)
        self.assertNotIn("a1", HELD)

    def test_security_review(self):
        self.assertEqual(self.make(team="security").status, "review")
        self.assertEqual(PENDING, [])
        approve_alert("a1")
        self.assertEqual(BALANCE["security"], 1)
        self.assertEqual(run_agent_once().status, "sent")

    def test_high_severity_review(self):
        self.assertEqual(self.make(severity=9).status, "review")
        self.assertEqual(BALANCE["core"], 4)

    def test_muted_not_saved(self):
        self.assertEqual(self.make(source="synthetic").status, "muted")
        with self.assertRaises(KeyError):
            get_alert("a1")

    def test_initial_credit_failure_not_saved(self):
        BALANCE["core"] = 0
        self.assertEqual(self.make().status, "no_credit")
        with self.assertRaises(KeyError):
            get_alert("a1")

    def test_decline_has_no_hold(self):
        self.make(team="security")
        self.assertEqual(reject_alert("a1").status, "declined")
        self.assertEqual(BALANCE["security"], 2)

    def test_reopen_after_recovery(self):
        ALWAYS_FAIL.add("a1")
        self.make()
        run_agent_once()
        ALWAYS_FAIL.clear()
        retry_failed_alert("a1")
        self.assertEqual(run_agent_once().status, "sent")
        self.assertEqual(CALLS["a1"], 4)
        self.assertEqual(BALANCE["core"], 3)

    def test_reopen_once_only(self):
        ALWAYS_FAIL.add("a1")
        self.make()
        run_agent_once()
        retry_failed_alert("a1")
        run_agent_once()
        with self.assertRaises(ValueError):
            retry_failed_alert("a1")

    def test_no_double_dispatch(self):
        self.make()
        run_agent_once()
        self.assertIsNone(run_agent_once())
        self.assertEqual(CALLS["a1"], 1)

    def test_no_auto_sweep_needed_on_failure(self):
        ALWAYS_FAIL.add("a1")
        self.make()
        run_agent_once()
        self.assertEqual(sweep_holds(), [])

    def test_empty_queue(self):
        self.assertIsNone(run_agent_once())

if __name__ == "__main__":
    unittest.main()
