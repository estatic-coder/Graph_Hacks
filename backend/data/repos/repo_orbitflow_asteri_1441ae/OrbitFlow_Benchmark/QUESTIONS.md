# OrbitFlow Benchmark: Questions and Expected Answers

Do not ingest this answer key into ASTERION when evaluating it.

1. **Multi-entry paths**: "Find every function call path from create_order() and approve_review() to create_label(). Which functions are shared? Cite each hop."  Expected: create_order -> submit_order -> dispatch -> create_label; approve_review -> dispatch -> create_label. Shared: dispatch, create_label.

2. **Retry semantics**: "If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES=2, and which events, stock changes, and customer notifications follow?" Expected: 3 attempts (while attempts <= 2 with increment before try), 3 carrier_retry events, stock released after exhausted attempts, failed event and notification.

3. **VIP branch**: "A VIP customer submits a low-value order. Is stock reserved, is a shipping label created, and is the customer notified? Cite the exact branches." Expected: no to all; review shipment saved and review event recorded.

4. **Impact**: "If dispatch() stops calling release() on exhausted retries, which workflows and tests are affected? Distinguish automatic orders from manually approved orders." Expected: both submit_order and approve_review paths, inventory may stay decremented; tests/test_workflow.py test_carrier_failure_releases_stock directly detects failure; review path lacks a corresponding failure assertion.

5. **Manual approval**: "Trace a VIP order from create_order() through approve_review() to create_label(). Explain why the second entry point is required." Expected: review returns early from submit_order; later approve_review reserves and dispatches.

6. **Negative evidence**: "Which function publishes shipment events to Kafka, and where is the Kafka producer configured?" Expected: none; append_event only writes in-memory EVENTS; no Kafka integration.

7. **Off-by-one**: "Would changing MAX_RETRIES from 2 to 3 cause three or four carrier attempts? Show the loop condition and increment." Expected: four attempts.

8. **Order visibility**: "Does get_order() return a shipment for an out-of-stock order? Why?" Expected: no, out-of-stock branch returns without save_shipment.

9. **Audit distinction**: "Compare audit events for VIP review, successful shipping, and persistent carrier failure." Expected: review; shipped; carrier_retry repeated three times plus failed. Review approval additionally emits review_approved.

10. **Test gaps**: "Which important failure branch of approve_review() lacks a direct automated test? Show the relevant source branch." Expected: out-of-stock branch in approve_review; no direct test for it. Also no review-approval carrier-failure test.
