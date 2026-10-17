# NexusPay: ASTERION Graph Reasoning Benchmark

Synthetic, intentionally compact Python payment-processing repository. No real payment provider, Kafka, database, or network service.

## Run

```bash
python -m unittest discover -s tests -v
```

Index the `nexuspay/` package and `tests/` in ASTERION. Ask questions from `QUESTIONS.md` **before** opening `ANSWER_KEY.md`.

## Graph semantics

The graph in `GRAPH.md` includes static CALLS edges and separately marked state-mediated handoffs. An arrow is not proof that a branch executes for every input.
