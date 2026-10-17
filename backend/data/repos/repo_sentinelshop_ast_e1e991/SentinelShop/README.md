# SentinelShop
A synthetic Python e-commerce backend built to test ASTERION graph ingestion, multi-hop reasoning, and change impact. No external services, secrets, or dependencies are required. All transactions are simulated in memory.

## Workflow
`checkout` -> `place_order` -> `authorize_payment` -> `fraud_score` -> `charge_card`; successful orders then `reserve_stock`, `save_order`, and `send_order_confirmation`. On declined payments, checkout returns without reserving inventory or sending confirmation.

## Test
From the repository root: `python -m unittest discover -s tests -v`.

## Notes
This is a deterministic demonstration, not a production payment system. `authorize_payment` does not directly call inventory or notifications; these are downstream steps in `place_order`, so impact analysis should distinguish direct callers from potentially affected workflow steps.
