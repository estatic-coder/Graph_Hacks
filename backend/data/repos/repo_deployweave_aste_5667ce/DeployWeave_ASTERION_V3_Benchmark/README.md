# DeployWeave: ASTERION V3 benchmark

Synthetic Python deployment orchestrator with a dependency DAG, review gates, reservation slots, in-memory rollout queue, version install / rollback, health retries, retry budget and maintenance sweep. No external libraries required.

**Important:** It simulates deploy operations in Python dictionaries; it does not control any real infrastructure.

## Setup
From the benchmark root:

```bash
python -m unittest discover -s tests -v
```

## Indexing instructions
Index `deployweave/` and optionally `tests/` in ASTERION. Do **NOT** index `ANSWER_KEY.md`, `QUESTIONS.md` or `GRAPH.md`. These are evaluator resources.

## Modes
- Q1–25: code graph and behavior questions, no external actions required.
- Q26–30: test actual agentic capabilities against live FalkorDB. A textual simulation alone does not count.

All test scenarios begin with isolated in-memory reset. Default rollout values: `r1`, `auth`, `staging`, version `2.0`.
