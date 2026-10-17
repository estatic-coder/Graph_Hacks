# ASTERION Evaluation Questions

## Q1: Multi-hop dependency
What is the complete call path from `checkout` to `charge_card`, including the fraud decision?
Expected: checkout -> place_order -> authorize_payment -> is_high_risk -> fraud_score; authorize_payment -> charge_card on the approved path. Branch conditions must be explained.

## Q2: Change impact (main demo)
If `authorize_payment` changes to reject all payments, which functions and workflow steps are affected, and which tests should be run?
Expected: direct caller `place_order`; transitive caller `checkout`; downstream successful-order steps `reserve_stock`, `save_order`, and `send_order_confirmation` no longer run; relevant tests `test_payments.py`, `test_orders.py`, and `test_api.py`. The last three are not direct callers of `authorize_payment`.

## Q3: Negative-path reasoning
When a high-risk user attempts checkout, does the system reserve stock or send confirmation?
Expected: no; `authorize_payment` returns None, `place_order` returns `payment_declined` before inventory reservation, persistence, and notification.

## Q4: Shared dependency
Which functions depend directly or indirectly on `verify_session`?
Expected: direct callers `checkout` and `order_history`; the authentication behavior affects both flows.

## Q5: Graph isolation
After indexing SentinelShop alongside sample-repo, does a query for `authorize_payment` return only SentinelShop nodes?
Expected: repository-scoped results; no cross-repository mixing.

## Q6: Explainability
Show the source paths and line ranges supporting the connection between `checkout` and `send_order_confirmation`.
Expected: api.py -> orders.py; checkout calls place_order, and place_order calls send_order_confirmation on successful orders. Cite actual source lines.

## Q7: Test discovery
Which tests directly exercise `authorize_payment`, and which test its behavior indirectly?
Expected: direct: test_payments.py; indirect: test_orders.py and test_api.py.

## Q8: Memory
Save an investigation of declined payments, restart the app, and retrieve the earlier finding. Is the finding marked stale after modifying payments.py?
Expected: persisted investigation with provenance and revision-aware freshness, if memory feature is implemented.

## Q9: Distinguish unrelated code
Does changing `fraud_score` necessarily affect `total_confirmed_spend` directly?
Expected: no direct call/dependency; possible indirect change in confirmed orders, not a direct static dependency.
