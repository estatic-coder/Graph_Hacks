# ASTERION V2: Graph-Native Agentic Code Intelligence Platform

> **An AI engineering agent that understands how software connects, remembers what it learns, predicts the consequences of changes, and takes verifiable actions based on graph evidence.**

ASTERION V2 is a high-performance, graph-native engineering platform built for **Graph Hacks: Context for AI Agents, powered by FalkorDB (October 15–18, 2026)** and directly competing with Graphify.

---

## 🚀 Key Capabilities

### 1. FalkorDB as the Active Context Layer
- **Code Intelligence Nodes**: `Repository`, `Revision`, `File`, `Module`, `Class`, `Function`, `CallSite`, `Branch`, `Queue`, `StateStore`, `ExternalService`, `Configuration`, `Test`.
- **Agent Memory Nodes**: `Agent`, `Session`, `Investigation`, `Observation`, `Hypothesis`, `Decision`, `Action`, `Outcome`, `Episode`, `Fact`, `Procedure`, `Evidence`, `AgentTask`.
- **Company Knowledge Nodes**: `Person`, `Team`, `Project`, `Issue`, `PullRequest`, `Commit`, `Document`, `DecisionRecord` (ADRs), `System`.
- **Semantic Edges**: `CALLS`, `DEPENDS_ON`, `READS_STATE`, `WRITES_STATE`, `ENQUEUES`, `DEQUEUES`, `TESTS`, `COVERS`, `OBSERVED`, `SUPPORTS`, `CONTRADICTS`, `DECIDED`, `EXECUTED`, `PRODUCED`, `LEARNED`, `REMEMBERS`, `HANDOFF_TO`, `OWNED_BY`, `WORKED_ON`, `DOCUMENTED_IN`, `AFFECTS`.

### 2. 13-Step Graph-Driven Agent Loop with Proven Causal Dependency
1. Receive engineering objective
2. Resolve active repository and revision
3. Retrieve relevant graph context
4. Retrieve relevant memories
5. Identify missing information
6. Choose graph query, algorithm, or analysis tool
7. Execute selected tool
8. Update investigation graph
9. Evaluate whether evidence supports action
10. Execute authorized action if appropriate
11. Verify result
12. Store outcome and memory in FalkorDB
13. Return explanation with graph path influencing decision

> **Causal Graph Dependency**: Changing graph relationships (e.g., adding a circuit breaker edge or altering inbound fan-in) demonstrably alters the agent's tool selection and recommended actions.

### 3. Multi-Agent Engineering Coordination
Coordinated through FalkorDB shared state with bounded task leases and explicit handoff records (`HANDOFF_TO`):
- **Graph Investigator**: Symbol resolution, multi-hop traversals, algorithm selection.
- **Execution Analyst**: Branch analysis, retry/loop simulation, state transitions, crash consistency.
- **Test & Impact Analyst**: Affected code mapping, test selection, regression impact.
- **Evidence Reviewer**: Source citation audits, contradiction detection, formal approval.
- **Session Continuity**: Second agent can resume and continue an investigation across sessions.

### 4. 11 First-Class Graph Algorithms as Agent Tools
- `shortest_path` (Cypher + BFS fallback)
- `bounded_all_paths`
- `reachable_nodes` (forward reachability)
- `reverse_dependencies` (blast radius)
- `connected_components`
- `strongly_connected_components` (Tarjan's algorithm for circular dependencies)
- `centrality` (Degree & Betweenness)
- `pagerank`
- `community_detection` (Label Propagation Algorithm)
- `architecture_boundary_check` (layer isolation)
- `impact_subgraph` (blast radius extraction)

### 5. Verifiable Agent Actions
- **Graph-Guided Test Selection** (`select_tests_by_graph`): Ranks tests by graph distance and error assertions; enforces authorization gates.
- **Automated Regression Investigation** (`investigate_regression_from_diff`): Diagnoses root cause from unified diff and impacted graph components.
- **Architecture Risk Investigation** (`investigate_architecture_risk`): Computes blast radius and grounded mitigations for service failure scenarios.

### 6. Company Brain Layer
Connects code modules to Teams, Lead Engineers, and Architecture Decision Records (ADRs):
- **ADR-004**: Retry limits (`MAX_SEND_RETRIES = 2`) and destructive dequeue (`QUEUE.pop(0)`).
- **ADR-007**: Single-attempt incident reopening (`MAX_REOPEN = 1`) and token quota release.

### 7. Ultra-Efficient Engine & 3-Tier Execution
- **Tier 1 (Deterministic)**: 0 LLM tokens, pure graph/AST queries (< 10ms).
- **Tier 2 (Hybrid)**: Graph traversal + concise structural interpretation (< 200ms).
- **Tier 3 (Deep Reasoning)**: Multi-phase simulation and symbolic execution (< 800ms).
- **Incremental Indexer**: SHA-256 digest comparison skips 100% of unchanged files.

---

## 🧪 Benchmark & Verification Matrix

All **104 tests pass with 100% success rate**:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/
```

- **RelayMesh Benchmark Suite**: 41/41 PASSED
- **SignalForge Benchmark Suite**: 16/16 PASSED
- **Repository Isolation & Memory Poisoning**: 14/14 PASSED
- **FalkorDB Context Layer & Causal Dependency**: 3/3 PASSED
- **Graph Algorithms Suite**: 7/7 PASSED
- **Agent Actions Suite**: 3/3 PASSED
- **Multi-Agent Coordination Suite**: 3/3 PASSED
- **Company Brain & Demo Suite**: 4/4 PASSED
- **Graph Client & Memory Mocks**: 13/13 PASSED

---

## 🎬 Hackathon Demo: The Incident Investigator

Run the complete 6-scene demonstration:

```python
from app.agent.demo_scenario import IncidentInvestigatorDemo

demo = IncidentInvestigatorDemo(
    repo_id="repo_signalforge_aste_d53975",
    repo_path="data/repos/repo_signalforge_aste_d53975/SignalForge_ASTERION_Benchmark_3"
)

# Scene 1: Graph reasoning
s1 = demo.run_scene_1_graph_reasoning()

# Scene 2: Graph-driven action
s2 = demo.run_scene_2_graph_driven_action()

# Scene 3: Persistent memory across sessions
s3 = demo.run_scene_3_persistent_memory()

# Scene 4: Multi-agent coordination (4 roles)
s4 = demo.run_scene_4_multi_agent_coordination()

# Scene 5: Decision explainability graph
s5 = demo.run_scene_5_decision_explainability()

# Scene 6: Company brain (Ownership & ADR-004)
s6 = demo.run_scene_6_company_brain()
```

---

## 🛠️ Setup & Quickstart

1. **Start FalkorDB**:
   ```bash
   docker-compose up -d
   ```

2. **Backend Development**:
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   PYTHONPATH=. uvicorn app.main:app --reload
   ```

3. **Frontend Development**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
