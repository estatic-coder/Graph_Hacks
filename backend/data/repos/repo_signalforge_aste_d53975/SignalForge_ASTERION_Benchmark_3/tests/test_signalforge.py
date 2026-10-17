import unittest
from signalforge.api import create_incident,approve_incident,reject_incident,run_worker_once,reopen_incident,get_incident
from signalforge.store import INCIDENTS,EVENTS,QUEUE
from signalforge.budget import TOKENS,RESERVED
from signalforge.notifier import FAIL_ALWAYS,FAIL_ONCE,CALLS,TICKETS,NOTICES
from signalforge.reopen import REOPEN_COUNTS
class TestSignalForge(unittest.TestCase):
 def setUp(self):
  for x in (INCIDENTS,EVENTS,QUEUE,RESERVED,FAIL_ALWAYS,FAIL_ONCE,CALLS,TICKETS,NOTICES,REOPEN_COUNTS): x.clear()
  TOKENS.update(normal=3,critical=2)
 def create(self,team="normal",severity=3,service="billing"):
  return create_incident(dict(incident_id="i1",service=service,team=team,severity=severity))
 def test_submission_queues_only(self):
  self.assertEqual(self.create().status,"queued");self.assertEqual(QUEUE,["i1"]);self.assertEqual(CALLS,{});self.assertEqual(TOKENS["normal"],2)
 def test_worker_success(self):
  self.create();self.assertEqual(run_worker_once().status,"sent");self.assertNotIn("i1",RESERVED);self.assertEqual(TOKENS["normal"],2)
 def test_fail_once(self):
  FAIL_ONCE.add("i1");self.create();self.assertEqual(run_worker_once().status,"sent");self.assertEqual(CALLS["i1"],2);self.assertEqual(EVENTS.count(("i1","send_timeout")),1)
 def test_persistent_failure_releases_budget(self):
  FAIL_ALWAYS.add("i1");self.create();self.assertEqual(run_worker_once().status,"failed");self.assertEqual(CALLS["i1"],3);self.assertEqual(TOKENS["normal"],3);self.assertNotIn("i1",RESERVED)
 def test_critical_review_handoff(self):
  self.assertEqual(self.create(team="critical").status,"review");self.assertEqual(QUEUE,[]);approve_incident("i1");self.assertEqual(get_incident("i1").status,"queued");self.assertEqual(run_worker_once().status,"sent")
 def test_high_severity_review(self): self.assertEqual(self.create(severity=9).status,"review")
 def test_muted_not_saved(self):
  self.assertEqual(self.create(service="sandbox").status,"muted")
  with self.assertRaises(KeyError): get_incident("i1")
 def test_no_budget_not_saved(self):
  TOKENS["normal"]=0;self.assertEqual(self.create().status,"no_budget")
  with self.assertRaises(KeyError): get_incident("i1")
 def test_review_rejection(self):
  self.create(team="critical");reject_incident("i1");self.assertEqual(get_incident("i1").status,"rejected");self.assertEqual(TOKENS["critical"],2)
 def test_reopen_after_failure(self):
  FAIL_ALWAYS.add("i1");self.create();run_worker_once();FAIL_ALWAYS.clear();reopen_incident("i1");self.assertEqual(run_worker_once().status,"sent");self.assertEqual(CALLS["i1"],4);self.assertEqual(TOKENS["normal"],2)
 def test_reopen_limit(self):
  FAIL_ALWAYS.add("i1");self.create();run_worker_once();reopen_incident("i1");run_worker_once()
  with self.assertRaises(ValueError): reopen_incident("i1")
 def test_empty_queue(self): self.assertIsNone(run_worker_once())
 def test_no_double_dispatch(self):
  self.create();run_worker_once();self.assertIsNone(run_worker_once());self.assertEqual(CALLS["i1"],1)
if __name__=="__main__": unittest.main()
