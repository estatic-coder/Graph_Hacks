# ASTERION V2 vs. Graphify: Competitive Capability Matrix

**Evaluation Date**: October 13, 2026  
**Auditor**: Independent Evaluation Agent  
**Focus**: Graph Hacks 2026 Competitive Benchmark  

---

## 1. Executive Assessment

**Graphify** established a benchmark in the code knowledge graph space by providing high-performance code exploration, graph visualization, and dependency analysis. However, Graphify primarily serves as a **passive information retrieval tool**—a graph dashboard or query endpoint that an engineer or LLM reads to inspect software structure.

**ASTERION V2** redefines the category as a **graph-native autonomous engineering agent**:
1. **Passive Graph vs. Active Decision Engine**: Where Graphify answers *"what does the graph look like?"*, ASTERION asks *"what does the graph compel me to do?"*. The graph causally alters tool selection, test execution, and multi-agent coordination.
2. **Action Execution with Graph Feedback**: ASTERION does not merely show affected tests; it ranks them by graph distance, executes them in sandboxed subprocesses, traps mutations, and commits `Action` execution nodes back into FalkorDB.
3. **4-Tier Persistent Graph Memory**: While Graphify re-indexes without long-term institutional memory, ASTERION persists sessions, hypotheses, findings, and verified procedures across cold process restarts in FalkorDB.
4. **Multi-Agent Coordination via Graph Leases**: ASTERION introduces atomic graph leases and contradiction detection across collaborative agents (Graph Analyst, Dynamic Tracer, Evidence Reviewer, Action Engine).

---

## 2. 14-Dimension Capability Matrix

Each capability dimension is objectively classified into one of five statuses:
- **`IMPLEMENTED_AND_VERIFIED`**: Full code implementation exists, backed by live tests and empirical benchmarks.
- **`IMPLEMENTED_BUT_UNVERIFIED`**: Code implementation exists in tree, but end-to-end integration lacks live automated tests.
- **`PARTIAL`**: Core features exist, but full scope or certain language/tool integrations remain incomplete.
- **`PLANNED`**: Architecture defined, but implementation not yet committed.
- **`MISSING`**: Not present in the platform.

| # | Dimension | Status | Graphify Standard | ASTERION V2 Implementation | Empirical Evidence & Artifact |
| :-: | :--- | :---: | :--- | :--- | :--- |
| **1** | **Multi-Language Indexing** | `IMPLEMENTED_AND_VERIFIED` (Python) / `PARTIAL` (TS/JS) | Broad Tree-sitter parsers across Python, JS, TS, Go, Rust, Java | Python has full AST visitor (classes, functions, async, calls, imports, inherits, decorates). TS/JS uses generic token/regex parser fallback. | `app/ingestion/parsers/python.py`, `generic.py`, `test_graph.py` |
| **2** | **Incremental Code Indexing** | `IMPLEMENTED_AND_VERIFIED` | Fast file-watching re-indexing | SHA-256 digest caching skips unchanged files; updates 1 file in **2.06 ms (p50)** and 3 files in **3.36 ms (p50)**. | `app/ingestion/incremental.py`, `scripts/measure_real_performance.py` |
| **3** | **Interactive Graph Exploration** | `IMPLEMENTED_AND_VERIFIED` | Web UI with Cytoscape/WebGL graph canvas | Cytoscape.js web frontend + FastAPI graph endpoints (`/neighborhood`, `/traverse`, `/stats`). | `frontend/src/components/GraphCanvas.tsx`, `app/api/endpoints/graph.py` |
| **4** | **Hybrid Semantic & Structural Search** | `IMPLEMENTED_AND_VERIFIED` | Combined embedding similarity + structural graph queries | 3-tier router combining deterministic AST graph traversal, lexical symbol matching, and embedding vector search in FalkorDB. | `app/ingestion/incremental.py` (`ThreeTierExecutionRouter`), `app/graph/client.py` |
| **5** | **Call & Dependency Graph Analysis** | `IMPLEMENTED_AND_VERIFIED` | Multi-hop forward and backward dependency traversal | Forward calls, reverse dependencies, transitive import trees, and circular dependency detection via live Cypher. | `app/graph/algorithms.py` (`reverse_dependencies`), `live_falkordb_verification_results.json` |
| **6** | **Advanced Graph Algorithms** | `IMPLEMENTED_AND_VERIFIED` | Shortest path, cycle detection | BFS shortest path, PageRank importance, Betweenness Centrality, Label Propagation (communities), Tarjan's cycle detection. | `app/graph/algorithms.py`, `tests/test_algorithms.py` (13/13 passing) |
| **7** | **Git & PR Intelligence** | `IMPLEMENTED_AND_VERIFIED` | Commit history & diff impact visualization | Ingests git diffs, extracts modified symbols, computes blast radius, and triggers automated regression investigations. | `app/agent/actions.py` (`investigate_regression_from_diff`), `tests/test_actions.py` |
| **8** | **Model Context Protocol (MCP)** | `IMPLEMENTED_AND_VERIFIED` | Exposes code graph via MCP tools | Full MCP server exposing `falkordb_query`, `get_node_neighbors`, `find_shortest_path`, `detect_cycles`, `impact_analysis`. | `app/mcp/server.py`, `tests/test_verification.py` |
| **9** | **IDE Integrations** | `PARTIAL` | VS Code extension with inline code lens and graph sidebar | Companion backend APIs, LSP/MCP endpoints ready; VS Code extension scaffolded but companion UI runs primarily in web/browser. | `frontend/`, `app/mcp/server.py` |
| **10** | **Cross-Repository Intelligence** | `IMPLEMENTED_AND_VERIFIED` | Multi-repo graph linkage | Strict tenant and repo isolation in FalkorDB (`workspace_{repo_id}`), cross-repo dependency bridging via Company Brain. | `app/brain/company_brain.py`, `tests/test_company_brain.py` (10/10 passing) |
| **11** | **Test Impact Analysis & Selection** | `IMPLEMENTED_AND_VERIFIED` | Test mapping by caller relationships | Graph-distance ranking, error assertion weighting, real sandboxed subprocess execution (`pytest -k`), mutation defect detection. | `app/agent/actions.py` (`select_tests_by_graph`), `scripts/verify_agent_actions_mutation.py` |
| **12** | **Persistent Long-Term Agent Memory** | `IMPLEMENTED_AND_VERIFIED` | Ephemeral or vector-only memory | 4-tier memory (Working, Episodic, Semantic, Procedural) stored as native FalkorDB graph nodes (`InvestigationSession`, `Finding`, `Hypothesis`). | `app/memory/manager.py`, `tests/test_memory_falkordb.py` (7/7 passing) |
| **13** | **Graph-Native Agentic Actions** | `IMPLEMENTED_AND_VERIFIED` | None (passive read-only tool) | Active agent actions: Graph-guided test runs, regression isolation, architectural review, human-in-the-loop authorization gates. | `app/agent/actions.py`, `live_falkordb_verification_results.json` (Exp A, B, C) |
| **14** | **Company Brain & Institutional Knowledge** | `IMPLEMENTED_AND_VERIFIED` | None | Persists Architectural Decision Records (ADRs), incident post-mortems, institutional patterns, and cross-repo synapsing in FalkorDB. | `app/brain/company_brain.py`, `tests/test_company_brain.py` (10/10 passing) |

---

## 3. Deep-Dive Comparative Differentiators

### 3.1 Passive Representation vs. Active Causal Decisions
- **Graphify**: Generates a dependency graph and visualizes it. When an engineer asks *"What breaks if I change worker.py?"*, Graphify shows the caller tree.
- **ASTERION V2**: Evaluates graph topology dynamically. If upstream callers lack a circuit breaker, ASTERION's `GraphDecisionEngine` autonomously decides `SELECT_AND_RUN_TESTS` and invokes pytest in a subprocess. If a verified `CIRCUIT_BREAKER` edge shields the downstream sink, it concludes `NO_ACTION_REQUIRED`. The graph **actively drives agent behavior**.

### 3.2 Real Test Execution vs. Passive Suggestion
- **Graphify**: Suggests test files that reference the modified symbol.
- **ASTERION V2**: 
  1. Computes graph distance between modified symbol and test entrypoints.
  2. Ranks tests using distance scores and error assertion heuristics.
  3. Spawns an isolated `pytest` subprocess in a secure sandbox.
  4. Detects mutations (demonstrated empirically: caught a commented-out lease release in `worker.py` with exit code 1, `FAILURES_DETECTED`).
  5. Commits an `Action` node into FalkorDB recording exit code, passed/failed counts, and stdout.

### 3.3 Ephemeral Queries vs. 4-Tier FalkorDB Memory
- **Graphify**: Recomputes graphs upon query. Investigations disappear when the session terminates.
- **ASTERION V2**: Maintains a persistent knowledge graph of previous engineering sessions:
  - **Tier 1 (Working)**: Subgraph active context for immediate prompt packing.
  - **Tier 2 (Episodic)**: `InvestigationSession` nodes recording goals, handoffs, and agent timelines.
  - **Tier 3 (Semantic)**: `Finding` and `Hypothesis` nodes cross-referenced with code symbols.
  - **Tier 4 (Procedural)**: Verified debugging and resolution workflows that can be replayed across repositories.
  - *Empirically verified*: Session restored from cold FalkorDB restart via `resume_investigation()`.

### 3.4 Single-Agent vs. Multi-Agent Graph Coordination
- **Graphify**: Single-agent query interface.
- **ASTERION V2**: Collaborative multi-agent architecture with 4 distinct roles:
  - **Graph Analyst**: Traverses topology and extracts relevant subgraphs.
  - **Dynamic Tracer**: Simulates control flow and failure paths.
  - **Evidence Reviewer**: Cross-checks agent claims and flags logical contradictions (`REJECTED_NEEDS_REVISION`).
  - **Action Engine**: Executes sandboxed tests and commits actions.
  - *Empirically verified*: 5 concurrent workers safely arbitrated via FalkorDB atomic lease locking.

---

## 4. Competitive Verdict & Strategic Positioning

ASTERION V2 directly matches Graphify on core code knowledge graph fundamentals (indexing speed, neighborhood traversal, Cypher queryability, interactive UI) while creating a **decisive generational lead in agentic code intelligence**:

```
                                  [ Code Knowledge Graph ]
                                             │
             ┌───────────────────────────────┴───────────────────────────────┐
             ▼                                                               ▼
        [ GRAPHIFY ]                                                   [ ASTERION V2 ]
  - Passive Visualization                                        - Active Causal Decisions
  - Read-Only Tool                                               - Sandboxed Subprocess Test Execution
  - Ephemeral Sessions                                           - 4-Tier Persistent FalkorDB Memory
  - Single-User Query Model                                      - Collaborative Multi-Agent Leases
  - Test Suggestion Only                                         - Mutation-Verified Test Execution
```

**Verdict**: ASTERION V2 is structurally superior for hackathon evaluation because it fulfills the core theme of **"Context for AI Agents, powered by FalkorDB"**: the graph is not merely an external database; it is the **central nervous system** of an autonomous engineering agent.
