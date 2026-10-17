# OrbitFlow: ASTERION Graph Reasoning Benchmark

Synthetic shipment orchestration repository with two entry points into `dispatch`: automatic order submission and manual review approval. Includes branch-dependent inventory changes, a carrier retry loop, audit events, and notification side effects.

Run tests: `python -m unittest discover -s tests -v`.

Import this repository into ASTERION as a separate graph. For blind evaluation, **exclude QUESTIONS.md from ingestion**.

No real carrier, network, payment, or external messaging integrations are used.
