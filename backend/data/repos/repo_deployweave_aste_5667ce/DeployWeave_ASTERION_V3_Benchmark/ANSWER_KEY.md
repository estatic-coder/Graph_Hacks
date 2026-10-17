# DeployWeave answer key (DO NOT INDEX)

1. No static CALLS from create/approve/retry to probe. Producers enqueue into READY; separate `run_worker_once -> poll_once -> execute -> probe`. Producer paths: `create_rollout -> submit -> enqueue`; `approve_rollout -> approve -> enqueue`; `retry_rollout -> retry_rollback -> enqueue` (conditional).
2. enqueue called from submit, approve, retry_rollback. READY mutated in store.enqueue and consumer.poll_once pop(0). No scheduler.
3. downstream(ledger)=[auth,gateway]; downstream(auth)=[gateway]; downstream(gateway)=[]; no cycle. ledger -> auth and gateway; auth -> gateway.
4. SLOTS/LOCKED in capacity; VERSIONS/CHANGES in registry; EVENTS/AUDIT/READY/ROLLOUTS in store; NOTICES in notifications. Mutators acquire,refund,commit,install,restore,emit,audit,enqueue,save,notify,consumer pop.
5. auth staging r1 v2: status ready; SLOTS auth1 (ledger2,gateway1); LOCKED {r1}; READY [r1]; EVENTS [(r1,ready)]; VERSIONS auth1.0 unchanged; CHECKS {}; NOTICES []. saved.
6. production review saved, emits review_requested, no acquire/queue; approve acquires auth slot 2->1, status ready, enqueues, emits approved; worker pops, install 2.0, probe once success, commit clears lock, deployed, emits deployed, notice, slot remains1.
7. gateway is CRITICAL_SERVICES; routes review; saved and review_requested; no slot acquisition/queue.
8. dependencies_healthy checks ledger key exists and not None; missing ledger -> blocked saved, missing_dependency event, no hold/queue.
9. three probes, three health_failed events; events ready + three health_failed + rolled_back. AUDIT installed,restored; CHANGES (r1,1.0,2.0),(r1,2.0,1.0); final auth1.0; SLOTS auth2; LOCKED empty; NOTICES rolled_back; attempts3.
10. two probes, one health_failed; events ready,health_failed,deployed; AUDIT installed; CHANGES one install; auth2.0; SLOTS auth1; lock cleared; notice deployed.
11. limit4 means 5 probes /5 failures, immediate success1.
12. initial3 failures rollback -> retry resets attempts0 -> success1; CHECKS cumulative4; final attempts1; EVENTS ready + 3 health_failed + rolled_back + retried + deployed; AUDIT installed,restored,installed; CHANGES install,restore,install; auth2.0; slots auth1; lock cleared; NOTICES rolled_back,deployed.
13. ROLLBACK_COUNTS increments before acquire. No slot -> retry_slot_denied, no enqueue, counts1; second retry raises ValueError retry budget exhausted.
14. sandbox muted unsaved/unqueued event muted; missing dependency blocked saved event missing_dependency; no-slot ready attempt no_slot unsaved event slot_denied. All no lock acquired.
15. deny only review, no slot held so none refunded; refund used on rollback or orphan sweep, restores SLOTS if locked.
16. Remove refund: `test_permanent_bad_rolls_back` catches wrong slots, leftover lock; `test_sweep_not_needed_after_rollback` detects sweep now returns [r1]. `test_retry_after_rollback_success` catches final slots=0 instead of1. `test_retry_limit` still passes. Other success and review tests do not execute rollback branch. Potential indirect effect from `test_retry_budget_consumed_on_no_slot`? It sets SLOTS=0 after rollback, so likely passes.
17. Remove restore: `test_permanent_bad_rolls_back` asserts VERSIONS auth1.0, fails. `test_retry_after_rollback_success` eventually version2.0 either way, so may not detect. CHANGES lacks restore entry; AUDIT still falsely says restored unless also removed.
18. Remove commit: `test_success_installs_and_commits` catches retained lock via notIn; `test_no_double_execute` only tests checks/queue, may pass; stale lock on deployed status may be cleaned by manual sweep, yielding orphan_refunded and restoring slot (undesired). Note `test_retry_after_rollback_success` checks slots not HELD so may pass.
19. approve invalid `test_invalid_approval`, no slot `test_approval_no_slot_saved`, success `test_approve_then_worker`; retry successful `test_retry_after_rollback_success`, limit `test_retry_limit`, insufficient slots `test_retry_budget_consumed_on_no_slot`; wrong status guard not directly tested.
20. Removing ledger from auth deps makes auth stage no longer blocked when ledger absent; `test_missing_dependency_blocks_persisted` fails; changes dependency blast radius? ledger still directly upstream of gateway, auth no longer downstream of ledger, so downstream ledger=[gateway].
21. Destructive READY.pop before load/status guard/execute, no ACK/redelivery; queue item can be lost. In-memory state wiped by full process loss.
22. Version mutated by install before health probe/rollback; crash can leave new version with incomplete rollout status and lock outstanding in memory. No real deployment or durability; process restart loses in-memory variables.
23. No scheduler; sweep terminal statuses rolled_back/deployed/denied only; no automatic queue repair.
24. No live orchestration, brokers, HTTP or durable data layer; all simulation in-memory.
25. Only checks non-None VERSIONS entries, not probe or runtime service health. Blast radius is structural, not proven availability impact.
26. Must actually invoke graph tools, show graph-based ranking and recompute after edge addition; do not accept narrative alone.
27. Must persist and retrieve finding across processes with real FalkorDB query IDs/revision/provenance, then demonstrate stale invalidation after change.
28. Four real role sessions/tasks/handoffs in FalkorDB, retrieve evidence and final verdict from graph.
29. Actual insert/query of synthetic company graph with explicit synthetic provenance; source-only fake claims inadequate.
30. Must execute isolated mutation and report actual result. Expected failure detectors: test_permanent_bad_rolls_back, test_sweep_not_needed_after_rollback, test_retry_after_rollback_success. Full suite original 20 tests. Must distinguish selected subset vs full suite and preserve original repo.
