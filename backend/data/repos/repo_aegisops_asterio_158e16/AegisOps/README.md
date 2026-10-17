# AegisOps: ASTERION Graph Reasoning Benchmark

An original, intentionally small Python incident-response system for testing repository ingestion, multi-hop call paths, branching logic, dependency impact, and test discovery.

This is **synthetic demo code**, not a production security system. No network or firewall changes occur; isolation is represented by an in-memory set.

## Import into ASTERION

Upload the ZIP, select the AegisOps repository, and run ingestion. The graph should include code symbols, import edges, call edges, and test relationships. The expected paths must be discovered from code, not inserted as canned graph data.

## Run tests

From the extracted repository root:

```bash
python -m unittest discover -s tests -v
```

See `QUESTIONS.md` for benchmark questions and expected results. Tests use in-memory shared state and are designed for sequential unittest discovery.
