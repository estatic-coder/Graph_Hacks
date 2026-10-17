# RelayMesh: ASTERION Graph Reasoning Benchmark 2

Synthetic, dependency-free Python event-delivery service. Unlike NexusPay, its execution crosses **three entry points** via a persisted job record and an in-memory outbox. Includes retries, approval, quota reservation, dead-letter replay, orphan sweeping, and a deliberate replay-budget bug.

## Run
```bash
python -m unittest discover -s tests -v
```

## Blind test
Index **only** `relaymesh/` and `tests/`. Do not index `QUESTIONS.md`, `ANSWER_KEY.md`, or `GRAPH.md`. Ask the questions in `QUESTIONS.md` and compare results privately against `ANSWER_KEY.md`.

## Important
The outbox and store are **in memory**, not Kafka or a real database. `run_worker_once()` is an explicit invocation, not a background daemon. `MAX_DELIVERY_RETRIES=2` means **three** maximum delivery calls. Replay resets the job attempt counter but not the transport's global call counter.
