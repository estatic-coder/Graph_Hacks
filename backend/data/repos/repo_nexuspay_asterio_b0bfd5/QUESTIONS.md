# ASTERION Blind Benchmark Questions

Do not show ASTERION `ANSWER_KEY.md` before evaluation. Request exact file/line citations for every important hop or branch.

1. Enumerate all static call paths from `create_payment()` and `approve_payment()` to `authorize()`. Which functions are shared? What conditions make those paths executable?
2. If `authorize()` always raises `TimeoutError` and `MAX_GATEWAY_RETRIES=2`, how many gateway calls occur? List event counts, hold/balance changes, status, and notices.
3. If the gateway times out exactly once and then succeeds, how many calls happen and which events, holds, and notices result?
4. A VIP submits a payment of 20. Does the gateway run, does a hold exist, and is a notice sent? Trace the early return.
5. Trace a VIP payment from `create_payment()` through later `approve_payment()` to `authorize()`. Is there a static CALLS path from `submit()` to `approve()`?
6. A blocked account submits a payment. Is the result persisted? What happens when `get_payment()` is called for that ID?
7. Hypothetically remove `release_hold()` from `process()` on gateway exhaustion. Which automatic and approved-review workflows are affected? Which tests would detect it, and which gaps remain?
8. If `MAX_GATEWAY_RETRIES` changes from 2 to 3, what is the maximum number of gateway calls? Does the answer change if the first call succeeds?
9. Which failure branches in `approve()` are not directly tested? Distinguish invalid status, insufficient funds, and downstream persistent gateway timeout.
10. Which function publishes payment events to Kafka, and where is the producer configured? Cite exact source lines or establish absence.
11. Does `refund_payment()` restore the account balance? Distinguish `refund()` from `release_hold()` and `capture_hold()` using source evidence.
12. What is the difference between `reject_payment()` and `approve_payment()` regarding holds, gateway calls, and notifications?
13. Does `cleanup_orphan_holds()` run automatically after a failed payment? Identify static callers or scheduling evidence, and explain when it would release a hold.
14. A regular account with balance 2000 submits amount 2500. Is the payment saved? Does it call `authorize()`? What event and notice are emitted?
15. Identify every direct caller of `release_hold()` and determine whether their execution conditions are equivalent.
16. If `authorize()` succeeds immediately, do any `gateway_timeout` events occur? Which success-side statements execute and which failure-side statements do not?
17. A reviewed payment is rejected, then an operator calls `approve_payment()` for the same ID. What exception occurs, and why?
18. Hypothetically remove `capture_hold()` on success. What happens to the hold and available balance, and would current tests detect the residual hold?
19. Which tests statically reach `process()` but do not execute it under their test inputs? Distinguish static graph reachability from feasible execution.
20. Can ASTERION prove that a real payment gateway, external database, or Kafka broker is used? Explain the exact in-memory implementation and scope of the absence claim.
