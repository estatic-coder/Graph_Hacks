# Evaluator-only answer key (DO NOT INDEX for blind evaluation)

1. `create_payment -> submit -> process -> authorize`; `approve_payment -> approve -> process -> authorize`. Shared `process`, `authorize`. Normal path requires policy approved + hold success; approval requires persisted review + hold success.
2. 3 calls; 3 `gateway_timeout`, 1 `failed` event; hold released and balance restored; failed status and one failed notice. No paid event or notice.
3. 2 calls; 1 `gateway_timeout`, 1 `paid`; hold captured (removed), balance stays debited; one paid notice.
4. VIP policy review returns before hold, gateway, and notice; persisted review and `review_requested` event.
5. State-mediated handoff through PAYMENTS: submit saves review then returns; separate `approve_payment -> approve` loads review, places hold, calls process -> authorize. No static submit -> approve CALLS edge.
6. Blocked result not saved; `get_payment -> load -> PAYMENTS[id]` raises KeyError (assuming ID was not previously stored).
7. Automatic and approved-review failures retain HOLDS and debited balance. `test_persistent_timeout_restores_balance` detects balance regression; no direct reviewed-timeout test. Other tests may assert hold state only on success.
8. Maximum 4 calls with limit 3 and initial attempts 0. If first succeeds, only 1 call.
9. Invalid status is tested indirectly by refund test? No: no direct `approve` invalid-status test. Insufficient-funds review approval untested; persistent gateway timeout after review approval untested. Existing approval test only succeeds.
10. None. `store.record` appends to in-memory EVENTS list. No Kafka producer.
11. No balance restoration. Refund changes status, records refund and notice, adds REFUNDS entry; ledger capture removes hold but retains debit.
12. Reject changes review to rejected, logs event, no gateway, hold, or notice. Approve places hold and invokes process; process may notify success or failure.
13. No automatic scheduler or static caller in this repository. Cleanup is only run when explicitly invoked; releases holds for missing or failed/rejected/refunded payments.
14. Insufficient funds branch; not saved; no gateway; `insufficient_funds` event and notice.
15. `process` (after exhausted retries), `cleanup_orphan_holds` (orphan/terminal status). Different conditions.
16. No gateway timeout; capture_hold, paid status/event/notice, save; no release_hold or failed event.
17. `approve` sees status rejected and raises ValueError(`payment not under review`).
18. Hold remains in HOLDS even though status paid; balance remains debited. `test_successful_payment` explicitly asserts no hold, so detects it.
19. `test_vip_review_no_hold`, `test_blocked_not_saved`, `test_get_review_payment` return before process. `test_refund_requires_paid` also creates a VIP review and never processes it. `test_review_rejection` creates VIP review then rejects without processing. `test_refund_after_paid` does execute process via initial creation.
20. No external gateway, DB, or Kafka; gateway is deterministic in-memory function, store dictionaries/lists, ledger dictionaries. Scope limited to indexed repository files.

## Caution
- Distinguish all-fail maximum calls from actual calls on success.
- Distinguish functions directly called from state-mediated handoffs.
- Source indentation matters for loop/except/cleanup.
- Memory or playbooks are not repository symbols.
- A graph edge does not imply the branch executes.
