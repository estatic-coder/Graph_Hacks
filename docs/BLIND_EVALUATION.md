# ASTERION V3: Blind Evaluation, Source Grounding & Ontology Verification

**Status**: Verified & Operational  
**Repository**: `DeployWeave` (`repo_deployweave_aste_667ec8`)  
**Evaluation Protocol**: Blind API-driven testing with strict answer-key isolation

---

## 1. Blind Evaluation Architecture & Isolation

To guarantee evaluation integrity and prove that ASTERION does not rely on benchmark answer keys or hardcoded heuristics:
1. **Answer Key Isolation**: `ANSWER_KEY.md` is strictly excluded from FalkorDB indexing, agent context, and prompt injection.
2. **First-Principles Derivation**: All findings are generated via AST static code analysis, FalkorDB Cypher traversals, and sandboxed subprocess execution.
3. **End-to-End API Execution**: Inquiries execute through Asterion's production API and coordinator engines.

---

## 2. Rigorous Epistemological Labeling

To prevent overclaiming, every assertion in ASTERION V3 is explicitly tagged with an epistemological category:

| Tag | Definition | Verified Example from DeployWeave |
| :--- | :--- | :--- |
| **`SOURCE_FACT`** | A verifiable literal statement present directly in the repository source code. | [deployweave/config.py:L1](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/config.py#L1): `MAX_HEALTH_RETRIES = 2`. |
| **`GRAPH_FACT`** | A topological relationship verified through FalkorDB Cypher query or algorithm engine. | `(ledger)-[:IMPACTS]->(auth)` and `(ledger)-[:IMPACTS]->(gateway)`. |
| **`STATIC_INFERENCE`** | A logical deduction derived from AST parsing and control-flow ordering. | Guard line 10 in `intake.py` (`dependencies_healthy`) evaluates before guard line 12 (`choice == 'review'`). |
| **`SYMBOLIC_PREDICTION`** | A model-derived hypothesis regarding downstream test behavior before running tests. | Removing `commit(r)` is predicted to cause exactly `test_success_installs_and_commits` to fail. |
| **`EMPIRICAL_RESULT`** | A machine-readable measurement captured from an isolated subprocess execution. | Mutating `worker.py` produced pytest return code `1`, with 19 passed and 1 failed test. |
| **`HYPOTHETICAL_SCENARIO`** | An architectural counterfactual or theoretical simulation. | Multithreaded concurrent consumers encountering race conditions on `SLOTS` dictionary decrements. |

---

## 3. Reality Bounding: In-Memory Simulation vs Production Cloud

ASTERION V3 strictly bounds its architectural claims to what is present in the codebase:

```
┌───────────────────────────────────────┬────────────────────────────────────────┐
│         IN-MEMORY SIMULATION          │        EXTERNAL INFRASTRUCTURE         │
│          (PRESENT IN REPO)            │          (ABSENT FROM REPO)            │
├───────────────────────────────────────┼────────────────────────────────────────┤
│ • Plain Python dicts (SLOTS, VERSIONS)│ • No Kubernetes API or Pod controllers │
│ • Python list queues (READY.pop(0))   │ • No Docker daemon or container builds │
│ • Pure in-memory state mutation       │ • No Kafka / RabbitMQ message brokers  │
│ • Volatile process memory space       │ • No PostgreSQL / Redis databases      │
└───────────────────────────────────────┴────────────────────────────────────────┘
```

> [!NOTE]
> **Source-Grounded Bounding**:  
> Inquiries regarding crash safety and persistence must explicitly distinguish between the **in-memory simulation** (where a process crash wipes all dictionaries completely) and **real-world production durability** (where active binary traffic shifts persist despite control-plane crashes). ASTERION avoids hallucinating external cloud infrastructure when evaluating codebases that are self-contained unit simulations.

---

## 4. Benchmark Verification Summary (Questions 1–50)

Across the full DeployWeave benchmark suite:
* **Section A (Q1–Q4)**: Static CALLS vs queue handoffs, writers/removers, blast radius DAG, and state stores verified.
* **Section B (Q5–Q15)**: Scenario control-flow tracing, slot exhaustion, retry burn, and guard evaluation verified.
* **Section C (Q16–Q20)**: Mutation predictions verified and backed by pytest subprocess receipts.
* **Section D (Q21–Q25)**: Crash consistency, lack of ACK, and in-memory vs real durability bounded.
* **Section E (Q26–Q30)**: Live graph centrality re-ranking, cross-process persistence and invalidation, 4-agent coordination in FalkorDB, and company brain linkage verified.
* **Advanced Section (Q31–Q50)**: Unscripted multi-agent dispute resolution (Q49), graph schema audit (Q46), auditable mutation receipts (Q43, Q44), resource invariant taxonomy, and NetworkX differential validation verified.
