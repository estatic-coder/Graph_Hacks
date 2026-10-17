# RelayMesh ASTERION Blind Benchmark

1. Enumerate all static call paths from create_job() and approve_job() to deliver(). Which path crosses an outbox/state handoff instead of a direct CALLS edge?
2. After create_job() returns for a normal tenant, has deliver() run? List status, quota, reservation, outbox, events and notices.
3. For a job that always times out, how many transport calls occur with MAX_DELIVERY_RETRIES=2? Give all events, status, quota, reservation and notice effects.
4. If transport times out once and then succeeds, how many calls occur? What is the receipt, event order and final quota?
5. Trace a VIP job from create_job() to approve_job() to run_worker_once(). Distinguish persistence and queue edges from static CALLS edges.
6. A banned tenant submits a job. Is it saved or queued? What does get_job() do afterward?
7. If quota is zero for a normal tenant, which actions happen and which do not? Is the job persisted?
8. If dispatch() no longer calls release() after retry exhaustion, which workflows and tests are affected? Separate regression-detecting tests from static-only reachability.
9. If MAX_DELIVERY_RETRIES changes from 2 to 4, what is the maximum transport-call count? What if the first attempt succeeds?
10. Which failure branches in approve() lack direct test coverage? Include invalid status and insufficient quota.
11. Does reject_job() restore quota? Explain why it normally does not need to, and distinguish it from release().
12. When a dead-letter job is replayed after the transport recovers, what happens to attempts, total transport calls, quota and events?
13. If replay_dead_letter() is invoked twice after two dead-letter outcomes, which exception is raised? Does the limit count successful replay requests or delivery attempts?
14. Identify a subtle bug in replay_dead_letter(): what happens when reserve() fails, and can the replay budget be consumed without enqueueing?
15. Which functions write to OUTBOX, which reads it, and is there any automatic background worker or scheduler in the repository?
16. Does sweep_orphans() run automatically? Does it restore quota after a normal dead-letter path? Distinguish intended cleanup from actual reachable calls.
17. What happens if OUTBOX contains a job whose status is no longer queued? Is dispatch() called?
18. Which tests call create_job() but do not cause deliver() to run? Separate static reachability from actual test execution.
19. If consume() is removed from the success path, what state leaks remain and which existing assertions detect them?
20. Find evidence of Kafka, Redis, Celery, an HTTP transport, or a durable database. Can the repository establish their absence beyond its own source tree?
21. Compare the two failure states no_quota and dead_letter. Which is saved, which sends a notice, and which changes quota?
22. If the worker crashes after OUTBOX.pop(0) but before dispatch(), can the job be lost from the queue? What source supports the risk and what is not modeled?
23. If a replayed job fails permanently, how many total delivery_timeout events and dead_letter events exist across the original run and replay?
24. Can a VIP job reach deliver() without an explicit approve_job() call through the public API? State assumptions and negative evidence.
