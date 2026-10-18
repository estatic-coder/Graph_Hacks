# ASTERION V3: Implementation Plan

**Author**: Principal Architect / AI Systems Lead  
**Date**: 2026-10-18  
**Based on**: Phase 0 Repository Audit

---

## 1. Current Architecture (Verified)

### 1.1 Runtime Environment

| Item | Verified State |
|---|---|
| Python | 3.14.7 |
| FastAPI | Installed |
| FalkorDB client | Installed (falkordb + google-genai 2.29.0) |
| Tree-sitter | **NOT installed** |
| OpenAI / Anthropic SDKs | **NOT installed** |
| Docker Python SDK | **NOT installed** |
| Frontend | React 18 + Vite + TailwindCSS 3 + Cytoscape 3.28.1 |

### 1.2 Backend Module Map

```
backend/app/
├── config.py              — Settings (falkordb_url, gemini_api_key, env)
├── main.py                — FastAPI routes (17KB, 407 lines, ALL routes inline — no routers)
├── graph/
│   ├── client.py          — FalkorClient + MockFalkorClient (446 lines)
│   ├── schema.py          — NodeType/RelType enums + NodeBase/EdgeBase models
│   └── algorithms.py      — 11 graph algorithms (BFS, centrality, pagerank, etc.)
├── ingestion/
│   ├── pipeline.py        — 2-pass IngestionPipeline
│   ├── incremental.py     — IncrementalIndexer (SHA-256) + ThreeTierExecutionRouter
│   ├── models.py          — ParsedSymbol, ParsedRelationship
│   └── parsers/
│       ├── base.py        — BaseParser ABC
│       ├── python.py      — Full Python AST parser (274 lines)
│       ├── fallback.py    — RegexFallbackParser for JS/TS (~30 lines, function names only)
│       └── generic.py     — C-like regex + ConfigParser + MarkdownParser
├── agent/
│   ├── impact.py          — ImpactAnalyzer (1,419 lines) — HAS BUG
│   ├── investigator.py    — GraphInvestigator (13-step loop)
│   ├── multi_agent.py     — Multi-agent coordination (FalkorDB leases)
│   ├── tools.py           — Graph algorithm tools
│   └── [10+ more files]
├── memory/manager.py      — GraphMemoryManager (4-tier memory, 35KB)
├── knowledge/company_brain.py — ADR / Team / Project knowledge
├── repositories/manager.py   — RepositoryManager (zip, local, GitHub clone)
└── services/              — EMPTY (placeholder)
```

### 1.3 Frontend Module Map

```
frontend/src/
├── App.tsx                — Monolithic 910-line component (ALL logic inline)
├── components/
│   ├── GraphExplorer.tsx  — Cytoscape.js wrapper
│   ├── RepositorySelector.tsx
│   └── ImportRepositoryModal.tsx
```

### 1.4 API Surface (Verified)

| Method | Route | Purpose |
|---|---|---|
| GET | /health, /api/health | Health + FalkorDB status |
| GET | /api/repositories | List repos |
| POST | /api/repositories/import | Import local path |
| POST | /api/repositories/upload | Upload ZIP |
| POST | /api/repositories/github | Clone GitHub URL |
| GET/DELETE | /api/repositories/{id} | Get/delete repo |
| POST | /api/repositories/{id}/index | Run ingestion |
| GET | /api/repositories/{id}/status | Status |
| POST | /api/ingest | Raw ingest (legacy) |
| GET | /api/graph/{id} | Get Cytoscape elements |
| POST | /api/investigate | Agent investigation |
| POST | /api/impact | Change impact analysis |
| GET | /api/memory/* | Memory sessions/findings/hypotheses |
| POST | /api/memory/invalidate | Invalidate stale memory |

---

## 2. Test Suite Audit (Verified Results)

**Actual: 153 passed, 112 failed, 5 skipped, 9 errors** (out of ~279 collected)

> WARNING: The V2 README claim of "104/104 tests passing" is inaccurate.
> The suite has grown to 279 tests; 112 are currently failing due to bugs.

### Confirmed Root Causes of Failures

1. **impact.py `_map_lines_to_symbols` bug** — Bare `r[4]`, `r[5]` indexing fails with mock client
   (returns `list index out of range`). Affects `test_change_impact.py` 6/7 tests.
2. **`test_investigation_regression.py`** — 9 errors: AttributeError indicating API drift
   between test fixtures and GraphInvestigator internals.
3. **`test_v2_multi_agent_coordination.py`** — 3 failures in task claiming and cross-session.
4. **Reasoning benchmark tests** — ~100 scenario-based tests failing due to agent
   output format changes vs expected strings.

### Stable Passing Groups

- test_ingestion.py 1/1, test_graph_mock.py 6/6, test_repositories.py 8/8
- test_v2_graph_algorithms.py 7/7, test_v2_agent_actions.py 3/3, test_v2_falkordb_context_layer.py 3/3

---

## 3. Existing Capabilities

| Capability | Exists | Quality |
|---|---|---|
| Python AST parsing | YES | High — full visitor with inheritance, async, decorators |
| JS/TS parsing | PARTIAL | Very low — regex function names only (~30 lines) |
| Incremental indexing (SHA-256 detection) | YES | Partial — detects changes but does NOT write to graph |
| FalkorDB graph storage | YES | Solid — MERGE-based upsert |
| 11 graph algorithms | YES | Solid |
| Change impact analysis | YES | Buggy — crashes with mock client |
| Multi-agent coordination | YES | Partial — leases work, roles informal |
| 4-tier memory (FalkorDB) | YES | Solid |
| Company brain / ADRs | YES | Exists in single file |
| Hybrid retrieval | PARTIAL | Keyword only, no BM25/semantic |
| Multi-provider LLM routing | NO | Gemini only; config.py has ai_provider field but no routing |
| Isolated code execution | PARTIAL | subprocess.run on host only |
| Frontend components | PARTIAL | Works but App.tsx is 910-line monolith |

---

## 4. Missing Capabilities (by Phase)

| Capability | Phase |
|---|---|
| Tree-sitter JS/TS/TSX parser | 1 |
| Incremental graph write-back | 2 |
| Stale edge pruning on file change | 2 |
| Impact analysis mock-client fix | 3 |
| BM25/semantic hybrid retrieval | 4 |
| Multi-provider LLM router | 5 |
| Circuit breaker + retry backoff | 5 |
| Docker-sandboxed execution | 6 |
| Structured agent role interfaces | 7 |
| Frontend decomposition | 8 |
| Impact visualization in Cytoscape | 8 |
| Pathfinder optimization | 9 |
| Full test coverage | 10 |

---

## 5. Implementation Order

```
Phase 0-Fix  → Fix impact.py bug (prerequisite for correctness baseline)
Phase 1      → Tree-sitter parsers (isolated, JS/TS/TSX)
Phase 2      → Incremental graph write-back (builds on Phase 1)
Phase 3      → Impact analysis correctness + MockFalkorClient fixes
Phase 4      → Hybrid retrieval (BM25 + graph traversal)
Phase 5      → LLM router (isolated service)
Phase 6      → Secure executor (opt-in Docker backend)
Phase 7      → Agent role interfaces + approval gates
Phase 8      → Frontend decomposition + impact visualization
Phase 9      → Performance profiling + path optimization
Phase 10     → Test sweep + documentation
```

---

## 6. Phase Details

### Phase 0-Fix: Stabilize Test Baseline

Fix `_map_lines_to_symbols` in `app/agent/impact.py`:
- Add `_safe_row_get(row, index, default=None)` helper
- Replace all bare `r[N]` with guarded access
- Update MockFalkorClient to handle `MATCH (f:File)-[:DEFINES]->(s)` pattern

Files: `backend/app/agent/impact.py`, `backend/app/graph/client.py`
Expected: `test_change_impact.py` 6/7 → pass

### Phase 1: Tree-sitter Multi-Language Parsing

- Add `tree-sitter`, `tree-sitter-javascript`, `tree-sitter-typescript` to requirements.txt
- Create `app/ingestion/parsers/typescript.py` — TypeScriptParser(BaseParser) extracting:
  classes, functions, arrow functions, imports/exports, inheritance, JSX components
- Create `app/ingestion/parsers/javascript.py` — JavaScriptParser(BaseParser)
- Update pipeline.py to map .ts/.tsx/.js/.jsx to new parsers
- Add `language` field to ParsedSymbol for source attribution
- Mark tree-sitter rels as confidence=1.0, is_inferred=False
- Graceful fallback to regex if tree-sitter grammars unavailable on Python 3.14

New files: `parsers/typescript.py`, `parsers/javascript.py`
New tests: `test_parser_typescript.py`, `test_parser_javascript.py`
Modified: `pipeline.py`, `requirements.txt`, `models.py`

### Phase 2: Incremental Graph Write-Back

Current IncrementalIndexer detects changes but never writes to FalkorDB.

- Add `index_files(file_list)` to IngestionPipeline for targeted indexing
- Extend IncrementalIndexer:
  - DELETED files: DETACH DELETE nodes WHERE source_path = path AND repository_id = repo_id
  - MODIFIED files: delete old symbols for that file, re-run index_files()
  - Persist _file_hashes as JSON sidecar or FalkorDB Meta node to survive restarts
  - Cross-file ref reconciliation after changed-file processing

New tests: `test_incremental_indexing.py`
Modified: `incremental.py`, `pipeline.py`

### Phase 3: Impact Analysis Fixes

Consolidates Phase 0-Fix with additional MockFalkorClient improvements:
- Correct DEFINES pattern handling in mock
- Ensure test_change_impact.py 7/7 pass

### Phase 4: Hybrid Retrieval

Create `app/services/retrieval.py`:
```
HybridRetriever.retrieve(query, repo_id, top_k=10, token_budget=4000)
  -> List[RetrievalResult(symbol_id, file_path, line_start, line_end, content, score, source)]
```
Steps: symbol lookup → graph traversal (1-2 hops) → BM25 → deduplicate → rank → truncate
Add GET /api/retrieve endpoint
Use rank_bm25 (pure Python, no API dependency)

New files: `services/retrieval.py`, `tests/test_retrieval.py`
Modified: `main.py`, `requirements.txt`

### Phase 5: Multi-Provider LLM Router

Create `app/services/llm_router.py`:
- Abstract LLMProvider base class
- GeminiProvider, OpenAIProvider, AnthropicProvider, OllamaProvider, DeterministicFallback
- LLMRouter: try providers in config order, exponential backoff, 429/503 → next provider
- Circuit breaker: disable provider after N consecutive failures
- Token usage logging (never log key values)
- Config: openai_api_key, anthropic_api_key, ollama_url, llm_provider_order, llm_timeout_seconds
- Injectable for testing (no real credentials needed in tests)

New files: `services/llm_router.py`, `tests/test_llm_router.py`
Modified: `config.py`, `requirements.txt`, `agent/investigator.py`

### Phase 6: Secure Executor

Create `app/services/executor.py`:
- ExecutionBackend ABC: run_tests(repo_path, test_paths, timeout) -> ExecutionResult
- HostSubprocessExecutor: current subprocess.run behavior (dev default)
- DockerExecutor: docker run --rm --network none --memory 512m --cpus 0.5
  --read-only -v repo_path:/workspace:ro --user 1000:1000
  (NEVER mounts docker socket; Docker ≠ hypervisor isolation — documented)
- ExecutorFactory: creates DockerExecutor if docker available + config says "docker", else host
- config: executor_backend = "host" | "docker"
- Preserve authorized=True approval gate

New files: `services/executor.py`, `tests/test_executor.py`
Modified: `agent/actions.py`, `config.py`

### Phase 7: Agent Role Interfaces

- Create `app/agents/base_agent.py` — BaseAgent(ABC) with execute(task) -> AgentResult
- Concrete: PlannerAgent, CodeIntelligenceAgent, ImpactAnalysisAgent, ReviewAgent
- Each writes AgentTask nodes to FalkorDB with status transitions
- ApprovalGate: require approved=True if risk_score > HIGH or files_affected > 10
- Add GET /api/agents/tasks endpoint
- Preserve existing multi_agent.py coordination

New files: `agents/base_agent.py`, `agents/planner.py`, `agents/impact_agent.py`, `agents/review_agent.py`
Modified: `agent/multi_agent.py`, `main.py`

### Phase 8: Frontend Upgrade

Decompose App.tsx (910 lines) into:
```
hooks/useRepository.ts, useInvestigation.ts, useImpactAnalysis.ts
services/api.ts (typed API client), services/types.ts
components/impact/ImpactPanel.tsx, RiskIndicator.tsx, DependencyPath.tsx
components/graph/ImpactOverlay.tsx (highlights affected_node_ids in Cytoscape)
components/chat/ChatPanel.tsx, ChatMessage.tsx, VerificationBadge.tsx
components/layout/Sidebar.tsx, Header.tsx
```
ImpactOverlay: color-codes affected nodes (red=high, orange=med, yellow=low)
Add error boundaries, loading states, accessibility attributes

Target: App.tsx < 200 lines

### Phase 9: Performance

- Profile shortest-path query (current: p50 ~31ms, target: <15ms)
- Create `app/graph/pathfinder.py`: try FalkorDB algo.shortestPath, fallback to Python BFS
- Benchmark with hardware + dataset documented (no fabricated numbers)
- BM25 index caching in retrieval service

New files: `graph/pathfinder.py`, `scripts/benchmark_pathfinding.py`

### Phase 10: Tests + Documentation

- Verify all 153 previously passing tests still pass
- Net new tests >= 30
- Update README.md to V3
- Create docs/V3_RELEASE_READINESS.md with verified results

---

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| tree-sitter wheels unavailable for Python 3.14 | Medium | Import-time detection, graceful fallback to regex |
| MockFalkorClient gaps for new query patterns | High | Extend mock incrementally with each new query |
| impact.py fix breaks currently-passing tests | Low | Run full suite after each change |
| Docker unavailable in dev | Medium | DockerExecutor opt-in; host default |
| Frontend decomposition regressions | Medium | Extract one component at a time |
| LLM credentials not configured | High (expected) | Router degrades to deterministic fallback |

---

## 8. Acceptance Criteria

- Phase 0-Fix: test_change_impact.py 7/7 pass
- Phase 1: test_parser_typescript.py and test_parser_javascript.py fully pass
- Phase 2: test_incremental_indexing.py passes add/modify/delete scenarios
- Phase 4: GET /api/retrieve returns ranked source-backed results
- Phase 5: test_llm_router.py passes with zero API credentials
- Phase 6: test_executor.py passes; Docker tests skip gracefully if unavailable
- Phase 7: GET /api/agents/tasks works; test_v2_multi_agent_coordination.py 3/3 pass
- Phase 8: App.tsx < 200 lines; ImpactPanel renders risk + affected nodes
- Phase 9: Pathfinding p50 measured and documented
- Phase 10: >= 153 + 30 tests passing; README and V3_RELEASE_READINESS.md updated

---

## 9. Out of Scope

- VS Code Marketplace extension (requires registration)
- MCP server (not in codebase, high complexity)
- Vertex AI provider (requires GCP project)
- FalkorDB cluster sharding (infrastructure change)
- Vector database for dense embeddings (BM25 used as proxy)
- Autonomous PR/commit/deploy actions (prohibited)

---

*Progress tracked in docs/V3_PROGRESS.md*
