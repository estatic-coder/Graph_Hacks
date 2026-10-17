# ASTERION V2: Known Limitations & Technical Roadmap

**Evaluation Date**: October 13, 2026  
**Auditor**: Independent Evaluation Agent  
**Purpose**: Transparent technical assessment of operational boundaries, edge cases, and post-hackathon engineering roadmap.

---

## 1. Executive Summary

In adherence to the core verification principle of **zero fabricated claims and zero hand-waving**, this document provides a candid evaluation of current technical boundaries in ASTERION V2.

While ASTERION V2 successfully passes all 104 core tests, operates with sub-5ms graph traversals on live FalkorDB, and executes verified sandboxed actions, specific architectural trade-offs and external dependencies require documentation for production deployment.

---

## 2. Technical Limitations & Operational Boundaries

### 2.1 Multi-Language Parsing Depth
- **Current State**:
  - **Python**: 100% full AST parsing (`ast.parse`, `PythonASTVisitor`) extracting classes, functions, async definitions, method calls, imports, inheritance hierarchies, and decorator annotations.
  - **TypeScript / JavaScript**: Handled via `generic.py` fallback regex and token analysis. Basic class, function, and import relationships are captured, but type annotations, interfaces, generics, and complex JSX component hierarchies are not yet full AST nodes.
- **Operational Boundary**: Complex TypeScript/React codebases have lower graph density and relationship accuracy compared to Python codebases.
- **Remediation Plan**: Integrate Tree-sitter bindings (`tree-sitter-typescript`, `tree-sitter-javascript`) in the ingestion pipeline to match Python AST fidelity.

---

### 2.2 LLM Quota Exhaustion & Deterministic Fallback Behavior
- **Current State**:
  - Free-tier Gemini API keys face strict daily quota limits (e.g., 20 requests per day on free preview models or 15 RPM).
  - During our independent benchmark evaluation across 25 incident questions, the Gemini API returned `429 RESOURCE_EXHAUSTED`.
- **System Behavior Under Quota Depletion**:
  - ASTERION does **not crash or hang**. Its `ThreeTierExecutionRouter` automatically falls back to **Deterministic Graph Synthesis**.
  - Graph queries, reverse dependency analysis, shortest path calculations, and test selection run at 100% capacity with zero token cost.
  - Overall benchmark accuracy under pure deterministic fallback was **72.0% (18/25 passing)**.
- **Operational Boundary**: Complex conceptual synthesis questions that require natural language prose generation produce more terse, structural summaries rather than rich conversational narratives.
- **Production Recommendation**:
  1. Configure a production Gemini API key or Google Cloud Vertex AI endpoint in `.env`.
  2. Alternatively, configure a local model provider (e.g., Ollama / vLLM running DeepSeek-Coder or Qwen-2.5-Coder) via LiteLLM.

---

### 2.3 Shortest-Path Latency on Dense Multi-Hop Graphs
- **Current State**:
  - Empirical latency: **p50 = 31.66 ms, p95 = 32.22 ms** (50 samples on SignalForge).
  - Target: < 20 ms.
- **Root Cause**:
  - The current query uses variable-length pattern matching:
    ```cypher
    MATCH p=(src {id: $src_id})-[*1..5]-(dst {id: $dst_id})
    RETURN p LIMIT 1
    ```
  - FalkorDB expands all intermediate paths bidirectionally up to depth 5 before pruning to `LIMIT 1`, generating extra traversal overhead in dense graph clusters.
- **Remediation Plan**:
  - Implement bidirectional BFS directly in Python using FalkorDB's adjacency cache, or utilize FalkorDB's built-in `algo.shortestPath` graph algorithm procedure when available in v6.x.

---

### 2.4 Subprocess Sandbox Isolation Level
- **Current State**:
  - Agent Action 1 (`select_tests_by_graph`) executes pytest via `subprocess.run` with:
    - Dedicated working directory confinement (`cwd=repo_path`).
    - Dedicated timeout enforcement (`timeout=30s`).
    - Standard input/output isolation and returncode monitoring.
    - Explicit human-in-the-loop authorization gate (`authorized=True`).
- **Operational Boundary**:
  - Subprocesses run within the host operating system's process namespace under the user executing the backend.
  - While static AST indexing prevents untrusted code execution during repository scanning, executing test suites from malicious untrusted repositories during the action phase could theoretically access the local filesystem or network if authorized by the user.
- **Production Recommendation**:
  - For enterprise multi-tenant SaaS hosting, wrap subprocess test execution in isolated ephemeral Docker containers, gVisor microVMs, or WebAssembly runners (e.g., Pyodide).

---

### 2.5 IDE Companion vs. Native Language Server
- **Current State**:
  - ASTERION exposes a fully functional Model Context Protocol (MCP) server (`app/mcp/server.py`) and REST APIs.
  - The current developer interface is a browser-based React + Cytoscape UI (`frontend/`).
- **Operational Boundary**:
  - A native VS Code extension exists in scaffolded form, but is not yet packaged on the VS Code Marketplace as a standalone extension.
- **Production Recommendation**:
  - Package the companion client into an official VS Code Marketplace extension that binds directly to the local FalkorDB daemon via MCP.

---

## 3. Prioritized Hardening Roadmap

| Priority | Initiative | Target Quarter | Impact |
| :---: | :--- | :---: | :--- |
| **P0** | **Tree-sitter Multi-Language Ingestion Engine** | Q4 2026 | Full AST fidelity for TypeScript, JavaScript, Go, and Rust. |
| **P0** | **Multi-Provider LLM Fallback (Vertex AI + Local Ollama)** | Q4 2026 | Seamless failover when cloud LLM quotas or network boundaries are hit. |
| **P1** | **Containerized Test Execution Sandbox (gVisor/Docker)** | Q1 2027 | Enterprise-grade isolation for running tests on untrusted third-party pull requests. |
| **P1** | **Bidirectional BFS Graph Path Optimization** | Q1 2027 | Reduces multi-hop shortest-path query latency from 31 ms to < 10 ms in FalkorDB. |
| **P2** | **Official VS Code & JetBrains Marketplace Plugins** | Q1 2027 | Native code-lens annotations and in-editor graph exploration. |
| **P2** | **FalkorDB Cluster Sharding & Cold Archive Tier** | Q2 2027 | Support for monorepos exceeding 10,000,000 lines of code. |
