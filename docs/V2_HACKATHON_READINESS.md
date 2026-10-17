# ASTERION V2: Hackathon Readiness & Demo Playbook

**Target Event**: Graph Hacks: Context for AI Agents, powered by FalkorDB (October 15–18, 2026)  
**Track**: Context for AI Agents  
**Platform Status**: **READY FOR LIVE DEMO**  
**Core Value Proposition**: *An AI engineering agent that understands how software connects, remembers what it learns, predicts the consequences of changes, and takes verifiable actions based on graph evidence.*

---

## 1. Demo Setup & Readiness Checklist

### 1.1 Prerequisites
- **Operating System**: Linux, macOS, or Windows WSL2.
- **Python**: Python 3.10 to 3.14 (Verified on Python 3.14.7).
- **Node.js**: Node 18+ for Vite frontend.
- **FalkorDB**: FalkorDB v6.0.2 / Redis 7+ or 8+ with `falkordb.so` module loaded.
- **Disk Space**: ~250 MB for backend runtime, node_modules, and FalkorDB data.

### 1.2 Verification Checklist
- [x] FalkorDB daemon listening on `127.0.0.1:6379`.
- [x] Health check responding `PONG` to Redis ping and Cypher execution.
- [x] 104/104 core V2 backend tests passing.
- [x] Live subprocess test execution verified on SignalForge.
- [x] Multi-agent lease locking and cold resume verified.
- [x] Deterministic graph synthesis fallback operational (resilient to Gemini API 429 quota exhaustion).

---

## 2. Fast-Start Launch Instructions

### Step 1: Start FalkorDB Engine
If using Docker:
```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
```

If using local Linux binary runtime (without Docker):
```bash
mkdir -p ~/.falkordb_runtime/data
~/.falkordb_runtime/usr/local/bin/redis-server \
  --loadmodule ~/.falkordb_runtime/var/lib/falkordb/bin/falkordb.so \
  --port 6379 \
  --dir ~/.falkordb_runtime/data \
  --bind 127.0.0.1
```

Verify connection:
```bash
redis-cli ping
# Output: PONG
```

### Step 2: Configure Environment
In `backend/.env`:
```env
FALKORDB_URL=redis://localhost:6379
GEMINI_API_KEY=<your_api_key_here>
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### Step 3: Launch Backend API
```bash
cd /home/zeraphynx/Projects/asterion/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API docs available at: `http://localhost:8000/docs`

### Step 4: Launch Frontend UI
```bash
cd /home/zeraphynx/Projects/asterion/frontend
npm run dev
```
Interactive UI available at: `http://localhost:5173`

---

## 3. High-Impact Hackathon Demo Script (5-Minute Walkthrough)

### Demo Narrative: "The Autonomous Incident Engineer"
**Scenario**: An alerting incident occurs in a distributed message processing system (`SignalForge`). A PR recently modified the worker dispatch loop. The presenter demonstrates how ASTERION diagnoses the issue, understands the graph blast radius, refuses to make assumptions, executes real tests, and remembers the solution permanently.

---

### Phase 1: Ingestion & Sub-Second Knowledge Graph (Minute 1)
1. **Action**: Open the UI at `http://localhost:5173`. Point ASTERION to `SignalForge`. Click **"Index Repository"**.
2. **What to show**:
   - The indexing completes in **~320 milliseconds** (20 files, 60 symbols, 275 relationships).
   - Show the Cytoscape graph canvas rendering the architecture: `Worker`, `Budget`, `LeaseManager`, and `Store`.
   - **Talking Point**: *"ASTERION doesn't just parse text into flat tokens. In 320 ms, it constructs an AST-native code knowledge graph in FalkorDB with full inheritance, caller-callee, and import semantics."*

---

### Phase 2: Causal Graph-Driven Decisions (Minute 2)
1. **Action**: In the prompt box, ask:
   > *"What happens if `dispatch()` encounters budget exhaustion? What is our risk?"*
2. **What to show**:
   - The UI reveals the **Decision Flow**:
     - *Step 1*: ASTERION queries FalkorDB for reverse dependencies: 4 upstream caller paths discovered.
     - *Step 2*: Shortest path search probes for `CIRCUIT_BREAKER` or `RETRY_HANDLER` edges.
     - *Step 3*: Evaluates safety: Discovers an unshielded path directly to the storage lease sink.
     - *Step 4*: The agent decision changes from passive explanation to **`SELECT_AND_RUN_TESTS`**.
   - **Talking Point**: *"Notice the agent's decision is causally determined by graph topology. If a circuit breaker protected this path, ASTERION would conclude NO_ACTION_REQUIRED. Because the sink is unshielded, the graph mandates active verification."*

---

### Phase 3: Collaborative Multi-Agent Investigation (Minute 3)
1. **Action**: Watch the multi-agent orchestration panel:
   - **Graph Analyst**: Maps the 3-hop caller tree in 4 ms.
   - **Dynamic Tracer**: Reconstructs the lease state machine (`ACQUIRE -> EXECUTE -> TIMEOUT -> RELEASE`).
   - **Evidence Reviewer**: Cross-checks hypotheses. If an agent asserts a hallucination contradicted by the graph, it triggers `REJECTED_NEEDS_REVISION`.
   - **Action Engine**: Selected the top 5 relevant tests ranked by graph distance.
2. **Talking Point**: *"All 4 agents coordinate through FalkorDB using atomic task lease locks. Each agent's findings are grounded in verified graph provenance."*

---

### Phase 4: Sandboxed Subprocess Test Execution (Minute 4)
1. **Action**: The UI displays:
   > **Authorization Required**: Execute 5 graph-selected tests in sandboxed pytest?
   Click **"Authorize & Run"**.
2. **What to show**:
   - Subprocess executes in an isolated environment.
   - Live pytest logs stream directly to the UI.
   - Shows **5 Passed, 0 Failed (ALL_PASSED)**.
   - Now demonstrate **Mutation Detection**: Inject an artificial bug in `worker.py` (comment out `store.release(lease)`). Re-run.
   - Pytest subprocess catches the regression: **3 Passed, 2 Failed (`FAILURES_DETECTED`)**!
   - Show the newly committed `Action` node in FalkorDB via live Cypher query.
3. **Talking Point**: *"ASTERION isn't a mock simulator. It runs real tests in real subprocesses, traps real regressions, and records the test run as an immutable action node in FalkorDB."*

---

### Phase 5: 4-Tier Memory & Institutional Company Brain (Minute 5)
1. **Action**: Stop the backend server. Re-launch it in a new terminal (simulating a cold restart).
2. **What to show**:
   - Query: *"What was our previous diagnosis of the dispatch lease leak?"*
   - ASTERION executes `resume_investigation()` and retrieves the complete post-mortem, hypothesis, and verified procedure from FalkorDB in **< 1 millisecond**.
   - Show **Company Brain**: Cross-repository ADRs (Architectural Decision Records) linking patterns between `SignalForge` and `RelayMesh`.
3. **Closing Punchline**: *"This is ASTERION V2: not a chatbot with a graph attached, but an AI engineering agent that understands how software connects, remembers what it learns, predicts the consequences of changes, and takes verifiable actions based on graph evidence."*

---

## 4. Troubleshooting & Resilience Protocols

| Issue | Root Cause | Immediate Resolution |
| :--- | :--- | :--- |
| **FalkorDB connection refused on port 6379** | Daemon not running or conflicting Redis instance | Run `ps aux \| grep redis`. Start daemon via provided command in Section 2. Ensure `FALKORDB_URL=redis://localhost:6379`. |
| **Gemini API 429 Quota Exhaustion** | Free-tier daily rate limits reached | ASTERION automatically switches to **Deterministic Graph Synthesis** (Tier 1 Router). All graph traversals, test selection, and report generation continue without error. |
| **Port 8000 already in use** | Stray backend process | Run `lsof -i :8000` and kill previous PID, or launch with `--port 8001`. |
| **Pytest tests not found during Action execution** | `cwd` path mismatch | Ensure repository path is set to absolute directory when creating workspace. |

---

## 5. Judge Q&A Cheat Sheet

- **Q: How does ASTERION use FalkorDB specifically?**  
  *A: FalkorDB is our primary graph and memory store. We use native Cypher for graph modeling (10 node types, 7 relationship types), sub-millisecond neighborhood traversals (p50: 4.02ms), atomic multi-agent lease locking, and 4-tier persistent memory storage.*

- **Q: How is this different from Graphify?**  
  *A: Graphify is a passive information retrieval tool. ASTERION is an active agent: graph topology directly determines agent decisions, drives sandboxed subprocess test execution, coordinates 4 specialized agents via graph leases, and persists verified procedures across cold restarts.*

- **Q: What if the LLM hallucinates?**  
  *A: ASTERION enforces graph evidence verification. The Evidence Reviewer cross-checks LLM claims against Cypher query results, rejecting unsupported assertions. Furthermore, critical actions (like test execution) run in real subprocesses where code truth is indisputable.*
