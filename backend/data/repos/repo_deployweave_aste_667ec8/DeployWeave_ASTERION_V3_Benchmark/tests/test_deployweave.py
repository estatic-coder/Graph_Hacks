import unittest
from deployweave.api import create_rollout,approve_rollout,deny_rollout,run_worker_once,retry_rollout,get_rollout,blast_radius
from deployweave.store import ROLLOUTS,EVENTS,READY,AUDIT
from deployweave.capacity import SLOTS,LOCKED
from deployweave.registry import VERSIONS,CHANGES
from deployweave.health import ALWAYS_BAD,BAD_FIRST,CHECKS
from deployweave.notifications import NOTICES
from deployweave.retry import ROLLBACK_COUNTS
from deployweave.maintenance import sweep_locks
class DeployWeaveTests(unittest.TestCase):
    def setUp(self):
        for c in (ROLLOUTS,EVENTS,READY,AUDIT,LOCKED,CHANGES,ALWAYS_BAD,BAD_FIRST,CHECKS,NOTICES,ROLLBACK_COUNTS):c.clear()
        SLOTS.update(auth=2,ledger=2,gateway=1)
        VERSIONS.clear();VERSIONS.update(auth='1.0',ledger='1.0',gateway='1.0')
    def create(self,k='r1',service='auth',env='staging',version='2.0'):
        return create_rollout(dict(rollout_id=k,service=service,environment=env,version=version))
    def test_staging_queues_without_probe(self):
        r=self.create();self.assertEqual((r.status,SLOTS['auth'],READY,CHECKS),('ready',1,['r1'],{}));self.assertIn('r1',LOCKED)
    def test_success_installs_and_commits(self):
        self.create();self.assertEqual(run_worker_once().status,'deployed');self.assertEqual(VERSIONS['auth'],'2.0');self.assertEqual(SLOTS['auth'],1);self.assertNotIn('r1',LOCKED)
    def test_bad_once_recovers(self):
        BAD_FIRST.add('r1');self.create();r=run_worker_once();self.assertEqual((r.status,CHECKS['r1'],EVENTS.count(('r1','health_failed'))),('deployed',2,1))
    def test_permanent_bad_rolls_back(self):
        ALWAYS_BAD.add('r1');self.create();self.assertEqual(run_worker_once().status,'rolled_back');self.assertEqual(CHECKS['r1'],3);self.assertEqual(VERSIONS['auth'],'1.0');self.assertEqual(SLOTS['auth'],2);self.assertNotIn('r1',LOCKED)
    def test_production_review(self):
        r=self.create(env='production');self.assertEqual(r.status,'review');self.assertEqual(READY,[]);self.assertEqual(SLOTS['auth'],2)
    def test_gateway_review(self):
        r=self.create(service='gateway');self.assertEqual(r.status,'review');self.assertEqual(READY,[])
    def test_approve_then_worker(self):
        self.create(env='production');self.assertEqual(approve_rollout('r1').status,'ready');self.assertEqual(run_worker_once().status,'deployed')
    def test_denial_does_not_refund(self):
        self.create(env='production');self.assertEqual(deny_rollout('r1').status,'denied');self.assertEqual(SLOTS['auth'],2)
    def test_muted_not_saved(self):
        self.assertEqual(self.create(env='sandbox').status,'muted')
        with self.assertRaises(KeyError):get_rollout('r1')
    def test_missing_dependency_blocks_persisted(self):
        VERSIONS.pop('ledger');self.assertEqual(self.create().status,'blocked');self.assertEqual(get_rollout('r1').status,'blocked');self.assertEqual(READY,[])
    def test_no_slot_not_saved(self):
        SLOTS['auth']=0;self.assertEqual(self.create().status,'no_slot')
        with self.assertRaises(KeyError):get_rollout('r1')
    def test_approval_no_slot_saved(self):
        self.create(env='production');SLOTS['auth']=0;self.assertEqual(approve_rollout('r1').status,'no_slot');self.assertEqual(get_rollout('r1').status,'no_slot')
    def test_invalid_approval(self):
        self.create()
        with self.assertRaises(ValueError):approve_rollout('r1')
    def test_retry_after_rollback_success(self):
        ALWAYS_BAD.add('r1');self.create();run_worker_once();ALWAYS_BAD.clear();self.assertEqual(retry_rollout('r1').status,'ready');self.assertEqual(run_worker_once().status,'deployed');self.assertEqual(CHECKS['r1'],4);self.assertEqual(SLOTS['auth'],1)
    def test_retry_limit(self):
        ALWAYS_BAD.add('r1');self.create();run_worker_once();retry_rollout('r1');run_worker_once()
        with self.assertRaises(ValueError):retry_rollout('r1')
    def test_retry_budget_consumed_on_no_slot(self):
        ALWAYS_BAD.add('r1');self.create();run_worker_once();SLOTS['auth']=0;retry_rollout('r1');self.assertEqual(ROLLBACK_COUNTS['r1'],1);self.assertEqual(READY,[])
        with self.assertRaises(ValueError):retry_rollout('r1')
    def test_sweep_not_needed_after_rollback(self):
        ALWAYS_BAD.add('r1');self.create();run_worker_once();self.assertEqual(sweep_locks(),[])
    def test_empty_queue(self):self.assertIsNone(run_worker_once())
    def test_no_double_execute(self):
        self.create();run_worker_once();self.assertIsNone(run_worker_once());self.assertEqual(CHECKS['r1'],1)
    def test_dependency_blast_radius(self):
        self.assertEqual(blast_radius('ledger'),['auth','gateway']);self.assertEqual(blast_radius('auth'),['gateway']);self.assertEqual(blast_radius('gateway'),[])
