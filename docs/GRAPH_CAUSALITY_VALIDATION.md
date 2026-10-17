# ASTERION V3: Graph Causality & Query Execution Validation

**Status**: Verified & Operational  
**Repository**: `DeployWeave` (`repo_deployweave_aste_667ec8`)  
**Reference Tool**: NetworkX 3.4+ / FalkorDB 0.5+  
**Receipt Source**: [`backend/scripts/v3_execution_integrity_receipts.json`](file:///home/zeraphynx/Projects/asterion/backend/scripts/v3_execution_integrity_receipts.json)

---

## 1. Graph Query Classification Hierarchy

To prevent speculative or hallucinated query outputs from masquerading as empirical data, ASTERION V3 enforces an explicit four-state query taxonomy:

| Query State | Definition | Example / Behavior |
| :--- | :--- | :--- |
| **`PROPOSED_QUERY`** | A query hypothesized by an agent based on assumed schema or preliminary reasoning, **not yet executed**. | `MATCH (s:Service {name: 'auth'}) RETURN s.version` (Assumes `version` property exists on node). |
| **`EXECUTED_QUERY`** | A query actually submitted to FalkorDB or graph engine, returning raw response packets and measured latency. | `MATCH (s:Service) RETURN s.name, keys(s) as properties LIMIT 5` (Executed in 0.69 ms). |
| **`VERIFIED_GRAPH_RESULT`** | An empirical graph dataset validated against schema invariants and ground-truth source code. | Downstream reachability: `ledger` reaches `{'auth', 'gateway'}` (Validated by NetworkX). |
| **`GRAPH_QUERY_FAILED`** | A query rejected by the engine due to syntax error, missing index, or schema mismatch. | `MATCH (n:NoSuchLabel) ...` |

---

## 2. Q46 Schema Audit: Graph Schema vs Source Configuration

### 2.1 The Speculative Query Assumption
In earlier iterations, an agent proposed:
```cypher
/* PROPOSED_QUERY (Rejected as speculative) */
MATCH (s:Service {name: 'auth'})-[:DEPENDS_ON]->(dep:Service {name: 'ledger'})
RETURN dep.name, dep.version, dep.status
```

### 2.2 Empirical FalkorDB Schema Audit
ASTERION V3 executed a schema audit query against `workspace_repo_deployweave_aste_667ec8`:
```cypher
/* EXECUTED_QUERY */
MATCH (s:Service) RETURN s.name, keys(s) as properties LIMIT 5
```
* **Execution Status**: `EXECUTED_QUERY`
* **Execution Latency**: `0.69 ms`
* **Raw Returned Records**:
  ```json
  {
    "ledger": ["name"],
    "auth": ["name"],
    "gateway": ["name"],
    "reporting": ["name"]
  }
  ```

### 2.3 Verified Ground-Truth Conclusion
1. **Schema Fact**: FalkorDB graph nodes for `:Service` **only store architectural identity (`name`)**.
2. **Missing Properties**: Neither `version` nor `status` exist as properties on `:Service` graph nodes in the indexed schema.
3. **Source Grounding**: Runtime versions in DeployWeave are volatile in-memory dictionary keys located in [deployweave/registry.py:VERSIONS](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/registry.py#L1).
4. **Resolution**: An investigation into why an auth rollout is blocked must inspect `deployweave/registry.py:VERSIONS` rather than querying hypothetical node properties in FalkorDB.

---

## 3. Differential Graph Validation (NetworkX Reference Comparison)

To guarantee algorithm correctness, all graph traversal metrics computed by ASTERION were benchmarked against an independent reference implementation using **NetworkX**.

### 3.1 Base Topological Invariants
Edges modeled in **impact direction** ($A \rightarrow B$ indicates changes in $A$ impact $B$):
* `ledger` $\rightarrow$ `auth`
* `ledger` $\rightarrow$ `gateway`
* `auth` $\rightarrow$ `gateway`

| Algorithm / Metric | NetworkX Reference Result | FalkorDB Cypher Result | Concordance |
| :--- | :--- | :--- | :--- |
| **Reachability (`ledger`)** | `['auth', 'gateway']` (count: 2) | `['auth', 'gateway']` (count: 2) | **100% Match** |
| **Reachability (`auth`)** | `['gateway']` (count: 1) | `['gateway']` (count: 1) | **100% Match** |
| **Reachability (`gateway`)** | `[]` (count: 0) | `[]` (count: 0) | **100% Match** |
| **Simple Paths (`ledger` $\rightarrow$ `gateway`)** | 1. `['ledger', 'gateway']`<br>2. `['ledger', 'auth', 'gateway']` | 1. Direct path (len 1)<br>2. Transitive path (len 2) | **100% Match** |
| **Strongly Connected Components** | 3 singletons: `[{'ledger'}, {'auth'}, {'gateway'}]` | 3 trivial components | **100% Match** |
| **Cycles** | `[]` (0 cycles) | Acyclic DAG verified | **100% Match** |
| **Topological Sort (Impact Order)** | `['ledger', 'auth', 'gateway']` | Precedence order | **100% Match** |

---

## 4. Controlled A/B Graph Causality Experiments

To verify that FalkorDB graph state causally shapes agent decisions rather than acting as a static sidecar, two controlled A/B experiments were executed.

```
       [Base Graph]                     [Experiment A: Relevant]          [Experiment B: Irrelevant]
          ledger                                ledger                              ledger
         /      \                              /      \                            /      \
      auth ----> gateway                    auth ----> gateway                  auth ----> gateway
                                                          |
                                                      reporting                       (docs) [isolated]
```

### 4.1 Experiment A: Relevant Graph Change
* **Mutation**: Added a downstream dependency edge: `reporting` depends on `gateway` (`gateway` $\rightarrow$ `reporting`).
* **Before**: Reachability from `ledger` = `['auth', 'gateway']` (count = 2).
* **After**: Reachability from `ledger` = `['auth', 'gateway', 'reporting']` (count = 3).
* **Decision Impacted**: **YES.**  
  Blast radius calculation increased from 2 to 3. The agent updated risk tier for `ledger` from *Medium* to *High (Systemic)*.

### 4.2 Experiment B: Irrelevant Graph Change
* **Mutation**: Added a disconnected documentation node `docs` with 0 incident edges.
* **Before**: Reachability from `ledger` = `['auth', 'gateway']` (count = 2).
* **After**: Reachability from `ledger` = `['auth', 'gateway']` (count = 2).
* **Decision Impacted**: **NO.**  
  Blast radius remained identical at 2. The agent correctly determined zero impact on routing or deployment risk.

---

## 5. Audit Conclusion
ASTERION V3 demonstrably couples its decision engine directly to graph topology. Relevant structural changes trigger proportional downstream updates, while irrelevant topological noise is filtered without false positives.
