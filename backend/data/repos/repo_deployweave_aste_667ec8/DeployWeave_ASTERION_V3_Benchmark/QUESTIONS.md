# DeployWeave: 30 ASTERION V2 benchmark questions

## A. Graph topology and dataflow
1. Enumerate static CALLS paths from `create_rollout`, `approve_rollout`, and `retry_rollout` to `probe`. Distinguish queue/state handoffs.
2. Which functions write to `READY`, which remove entries, and is there an automatic scheduler?
3. What is the downstream blast radius of `ledger`, `auth`, and `gateway`? Explain the dependency direction and any cycles.
4. Identify the state stores and mutation functions for `SLOTS`, `LOCKED`, `VERSIONS`, `CHANGES`, `EVENTS`, `AUDIT`, and `NOTICES`.

## B. Scenario and control-flow reasoning
5. After a normal staging `create_rollout` of auth v2.0 returns, give status, slots, lock, queue, events, registry, probe calls, notices.
6. Trace a production auth rollout through submission, approval, and one worker iteration. Separate persistence, queue handoff, and CALLS.
7. Trace a gateway staging rollout. Why is it in review without an acquired slot?
8. If the ledger version is absent, what happens when staging auth v2.0 is submitted? Is it saved, queued, or charged a slot?
9. With `MAX_HEALTH_RETRIES=2` and an always-failing health probe, give checks, ordered events, audit, `CHANGES`, version, slots, lock, and notices.
10. If the first probe fails and the second passes, give probe calls, ordered events, audit, `CHANGES`, version, slots, lock, and notices.
11. If `MAX_HEALTH_RETRIES` changes from 2 to 4, give persistent-failure probe calls and immediate-success calls.
12. After a rollback is retried and health recovers, give attempts reset/final, cumulative probe checks, event history, audit, `CHANGES`, slots, and version.
13. Can a retry failure due to no available slot burn the only rollback retry allowance? Explain order and subsequent call.
14. Compare a sandbox rollout, a missing-dependency rollout, and a no-slot staging rollout: persistence, events, reservations, and queue.
15. Compare `deny_rollout` with `refund`: when is a slot returned, and why does normal denial not return one?

## C. Mutations and tests
16. Remove `refund(r)` from `execute` rollback exhaustion. Identify regression-detecting tests, tests executing the branch without detection, and tests executing other branches. Explain assertion chains.
17. Remove `restore(r,old)` from `execute`. Which tests detect the incorrect live version? Which other observables change?
18. Remove `commit(r)` from the success branch. Which tests detect the leaked lock, and what does `sweep_locks()` do afterward?
19. Which `approve` branches have direct tests (invalid status, no slots, success)? Which `retry_rollback` branches are exercised?
20. For changing `DEPENDENCIES['auth']` to remove `ledger`, identify impacted routing decisions and tests without claiming all downstream services are definitely broken.

## D. Reliability and architecture
21. If the consumer crashes after `READY.pop(0)` and before `execute`, is the rollout lost from the queue? Is there an ack/redelivery mechanism?
22. If the process crashes after `install(r)` but before `restore` or `commit`, which state could be inconsistent? Distinguish in-memory simulation from real deployment durability.
23. Is `sweep_locks()` scheduled? Can it repair a missing READY queue item or only stale terminal-state reservations?
24. Are there live Kubernetes, Docker, HTTP, Kafka, Redis, or durable database integrations? Bound conclusions to the indexed repository.
25. Does `dependencies_healthy()` actually health-check dependent services, or only check whether a version entry exists? How does that affect blast-radius conclusions?

## E. Graph-native agent capabilities (requires active execution, not prose-only)
26. Run an agent graph algorithm to rank critical services using dependency centrality, and show why the output changes after adding a new downstream dependency edge.
27. Persist a verified finding about the destructive READY queue-loss window. Retrieve it in an independent process/session with provenance and revision; then change the source and demonstrate invalidation.
28. Have four independent agent roles investigate a staging deployment rolled back due to failing health checks. Persist task claims, shared evidence, graph handoffs, and reviewer verdict in FalkorDB.
29. Connect a mock team, engineer, issue, and architecture decision record to `deployweave/worker.py`. Answer who owns retry policy and why, with graph provenance. Explicitly label synthetic organizational data.
30. In an isolated workspace, remove `refund(r)` from `execute`. Use graph impact to choose tests, run the full test suite, capture real subprocess results and show the changed dependency/evidence graph. Separate predictions from empirical results.
