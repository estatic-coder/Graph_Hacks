# OrbitOps: ASTERION V2 Graph-Native Agent Benchmark

An independent synthetic Python codebase designed to test code graphs, state/retry reasoning, graph-guided test selection, memory, coordination, provenance and company knowledge.

## Usage

1. Run `python -m unittest discover -s tests -v` from this directory.
2. Index only `orbitops/`, `tests/`, `docs/`, `metadata/` into ASTERION. Do NOT index `ANSWER_KEY.md`, `GRAPH.md`, or `QUESTIONS.md`.
3. Ask the 30 questions in `QUESTIONS.md` through the actual user-facing ASTERION pipeline.
4. Grade using `ANSWER_KEY.md` outside the system.
5. For questions 27–30, require observable agent actions, independent sessions, FalkorDB state and execution logs.

The benchmark repository itself uses in-memory dictionaries/lists; persistent graph and agent memory are features ASTERION must supply, not OrbitOps.

This repo uses no third-party Python dependencies. The Company Brain metadata and ADRs are deliberately included for grounded ownership questions.
