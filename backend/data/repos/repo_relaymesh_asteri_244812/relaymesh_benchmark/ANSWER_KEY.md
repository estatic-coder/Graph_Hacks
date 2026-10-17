# Evaluator-only answer key. DO NOT INDEX INTO ASTERION

## 1
Two static delivery paths: run_worker_once→poll_once→dispatch→deliver; create_job→submit and approve_job→approve only enqueue and do not statically call dispatch. Cross-invocation workflow via OUTBOX.

## 2
Queued, credit 4, reserved j1, outbox [j1], queued event, no delivery or notice.

## 3
3 calls; 3 delivery_timeout, 1 dead_letter; quota restored to 5; reservation cleared; dead_letter notice.

## 4
2 calls; receipt receipt:j1:2; queued, delivery_timeout, delivered events; credit 4.

## 5
Review persisted with no hold/queue; approve reserves/enqueues; separate worker polls and delivers.

## 6
Blocked event; not saved or queued; get_job raises KeyError.

## 7
no_quota event, status no_quota; no persistence, outbox, transport, notice, or reservation.

## 8
Normal and approved review worker flows can leak quota; test_persistent_timeout_restores_quota detects; VIP review success does not detect failure cleanup.

## 9
6 maximum calls if retries=4; 1 on immediate success.

## 10
Invalid status ValueError and insufficient quota review_quota_failed not directly tested.

## 11
Review rejection has no reservation, so no quota to restore; release restores only reserved credit.

## 12
attempts resets to 0, prior CALLS remains 3, next successful call number 4, credit 4, replayed then delivered.

## 13
ValueError replay limit reached; count increments on accepted replay requests, not transport attempts.

## 14
REPLAY_COUNTS increments before reserve; failed reservation consumes replay budget even though nothing enqueued.

## 15
enqueue in submit, approve, replay; poll_once pops; no scheduler/worker runner shown.

## 16
No callers/scheduler in repo; normal dead letter already releases quota; sweep only releases stale reserved entries with terminal statuses.

## 17
poll_once pops and returns job unchanged without dispatch.

## 18
Blocked, no-quota, review, and submission-only tests do not deliver; inspect actual inputs and worker calls, not just graph paths.

## 19
Reserved entry and job.reservation remain set; credit stays decremented (same as successful debit) but reservation leak; test_worker_success asserts RESERVED absence.

## 20
All implementations in-memory; no evidence for listed external services in repository; cannot prove ecosystem-wide absence.

## 21
no_quota not saved, no notice; dead_letter saved and notified, reservation returned.

## 22
Yes, pop occurs before dispatch; no crash recovery or durable ack in source; risk is inference.

## 23
6 delivery_timeout and 2 dead_letter events; 6 total calls.

## 24
Not via provided API without approval; unless external mutation/queue injection; static negative evidence scoped to repository.