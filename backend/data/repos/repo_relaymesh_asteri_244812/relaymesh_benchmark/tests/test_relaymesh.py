import unittest
from relaymesh.api import create_job, approve_job, reject_job, run_worker_once, replay_job, get_job
from relaymesh.store import JOBS, EVENTS, OUTBOX
from relaymesh.quota import CREDITS, RESERVED
from relaymesh.transport import FAIL_ALWAYS, FAIL_ONCE, CALLS, RECEIPTS
from relaymesh.notify import NOTICES
from relaymesh.replay import REPLAY_COUNTS

class RelayTests(unittest.TestCase):
    def setUp(self):
        JOBS.clear(); EVENTS.clear(); OUTBOX.clear(); RESERVED.clear()
        FAIL_ALWAYS.clear(); FAIL_ONCE.clear(); CALLS.clear(); RECEIPTS.clear()
        NOTICES.clear(); REPLAY_COUNTS.clear()
        CREDITS.update(normal=5, vip=5, banned=5)

    def create(self, job_id='j1', tenant='normal', payload='hello'):
        return create_job(dict(job_id=job_id, tenant=tenant, payload=payload))

    def test_submission_only_queues(self):
        job = self.create()
        self.assertEqual(job.status, 'queued')
        self.assertEqual(CALLS, {})
        self.assertEqual(OUTBOX, ['j1'])
        self.assertEqual(CREDITS['normal'], 4)

    def test_worker_success(self):
        self.create(); job = run_worker_once()
        self.assertEqual(job.status, 'delivered')
        self.assertEqual(CALLS['j1'], 1)
        self.assertNotIn('j1', RESERVED)
        self.assertEqual(CREDITS['normal'], 4)

    def test_transient_timeout(self):
        FAIL_ONCE.add('j1'); self.create(); job = run_worker_once()
        self.assertEqual(job.status, 'delivered')
        self.assertEqual(CALLS['j1'], 2)
        self.assertEqual(EVENTS.count(('j1', 'delivery_timeout')), 1)

    def test_persistent_timeout_restores_quota(self):
        FAIL_ALWAYS.add('j1'); self.create(); job = run_worker_once()
        self.assertEqual(job.status, 'dead_letter')
        self.assertEqual(CALLS['j1'], 3)
        self.assertEqual(CREDITS['normal'], 5)
        self.assertNotIn('j1', RESERVED)

    def test_vip_review_handoff(self):
        job = self.create(tenant='vip')
        self.assertEqual(job.status, 'review')
        self.assertEqual(OUTBOX, [])
        approve_job('j1')
        self.assertEqual(get_job('j1').status, 'queued')
        self.assertEqual(run_worker_once().status, 'delivered')

    def test_blocked_not_saved(self):
        self.assertEqual(self.create(tenant='banned').status, 'blocked')
        with self.assertRaises(KeyError): get_job('j1')

    def test_review_rejection(self):
        self.create(tenant='vip'); reject_job('j1')
        self.assertEqual(get_job('j1').status, 'rejected')
        self.assertEqual(CALLS, {})

    def test_no_quota_not_saved(self):
        CREDITS['normal'] = 0
        self.assertEqual(self.create().status, 'no_quota')
        with self.assertRaises(KeyError): get_job('j1')

    def test_replay_after_dead_letter(self):
        FAIL_ALWAYS.add('j1'); self.create(); run_worker_once()
        FAIL_ALWAYS.clear(); replay_job('j1')
        self.assertEqual(run_worker_once().status, 'delivered')
        self.assertEqual(CALLS['j1'], 4)
        self.assertEqual(CREDITS['normal'], 4)

    def test_replay_limit(self):
        FAIL_ALWAYS.add('j1'); self.create(); run_worker_once()
        replay_job('j1'); run_worker_once()
        with self.assertRaises(ValueError): replay_job('j1')

    def test_queued_job_is_not_dispatched_twice(self):
        self.create(); self.assertEqual(run_worker_once().status, 'delivered')
        self.assertIsNone(run_worker_once())
        self.assertEqual(CALLS['j1'], 1)

if __name__ == '__main__': unittest.main()
