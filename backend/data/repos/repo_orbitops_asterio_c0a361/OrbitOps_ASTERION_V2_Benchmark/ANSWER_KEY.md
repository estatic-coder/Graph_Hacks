# PRIVATE EVALUATOR ANSWER KEY — DO NOT INDEX

1. No synchronous CALLS path from producer API entrypoints to send_page; create->submit->enqueue, approve->authorize->enqueue, retry_failed->reopen_failed->enqueue; separate run_agent_once->drain_one->deliver->send_page via PENDING.
2. run_agent_once->drain_one->deliver->send_page; guard if PENDING empty and if loaded status != pending.
3. submit, authorize, reopen_failed call enqueue; enqueue appends PENDING; drain_one pops; no scheduler.
4. submit->hold ready path; authorize->hold review success attempt; reopen_failed->hold after reopening budget increment.
5. pending, core BALANCE 3, HELD {a1}, PENDING [a1], EVENTS [(a1,pending)], CALLS {}, NOTICES [].
6. security creation review saved, no balance change or enqueue. approve reserves security balance 2->1 and queues; worker separately dequeues, pages once, commits reservation, status sent, notice sent.
7. severity>=8 routes review saved, no hold or enqueue, balance core 4.
8. synthetic muted event, not saved; get_alert raises KeyError.
9. 3 send_page calls; 3 page_timeout events; status failed; balance core restored 4; HELD empty; events pending, 3x page_timeout, failed; notice failed.
10. 2 calls; incident key INC-a1-2; events pending,page_timeout,sent; balance core 3; HELD empty; notice sent.
11. 5 calls and 5 page_timeout events on persistent timeout; first-call success 1 call, 0 timeouts.
12. initial fail 3 calls, reopened resets attempts to 0, recovered one call => 4 cumulative; final attempts 1, balance 3, HELD cleared, sent; events pending,3x page_timeout,failed,reopened,sent; notices failed,sent.
13. REOPENED counter increments before hold. Failed hold emits reopen_credit_denied leaving failed and no enqueue; next reopen attempts raises reopen budget exceeded.
14. initial no_credit unsaved credit_denied; approval no_credit saved approval_credit_denied no enqueue; delivery failed after 3 page_timeout, saved failed, failed notice, balance restored.
15. Entry removed, load occurs; if status not pending return alert without deliver. No automatic requeue.
16. exhaustion cleanup deletion detected by test_exhausted_releases and test_reopen_after_recovery (final balance expectation); test_reopen_once_only likely still passes, success-only tests do not execute exhaustion.
17. HELD and alert.reserved remain true after sent; test_send_success fails assertNotIn. Credits remain spent, not additionally charged.
18. Invalid status raises ValueError no mutations, and failed hold changes status no_credit, approval_credit_denied, save, no queue; both untested directly.
19. deliver->send_page each attempt, three catches emit page_timeout, then release, status failed, emit failed, notify failed, save; run_agent_once->drain_one reaches it.
20. test_initial_enqueue_no_send checks CALLS == {} via tuple assertion, while pending and balance are checked.
21. PENDING.pop(0) is destructive before deliver; interruption loses the queue item, no ack/requeue; in-process state also vanishes on process crash. Distinguish simulated interruption from observed test.
22. sweep_holds not scheduled; normal failed delivery already releases hold, sweep empty.
23. No evidence of durable broker/Celery/Kafka/Redis/HTTP transport in indexed OrbitOps code. Pager simulated in memory. Avoid claims about system outside scope.
24. worker owned by Reliability Engineering lead Maya Rao in metadata/ownership.json; ADR-011 manual review for security and severity>=8.
25. consumer owned by Core Infrastructure lead Noah Iyer; ADR-012 documents destructive queue pop risk and explicitly accepts for prototype.
26. Pick test_exhausted_releases, test_reopen_after_recovery as detectors; possibly test_reopen_once_only as behavior execution but non-detecting. Justify from assertions.
27. Must demonstrate persistent FalkorDB-backed memory across independent sessions and provenance/revision invalidation; repo has no implemented agent memory, this is a system evaluation task.
28. Must demonstrate four actual agent roles, persisted handoffs and evidence. Correct diagnosis: review route blocks enqueue until approve_alert called.
29. Must run two controlled graph scenarios and show causally different tool/test selection, no arbitrary assumptions.
30. Must produce real diff, graph impact, sandbox execution logs and verdict, distinguish heuristic predictions from test failures. Repo fixtures do not themselves implement this agent behavior.
