# ASTERION V3: Resource Invariants Formal Specification

**System**: DeployWeave Capacity & Reservation Architecture  
**Scope**: Invariant Modeling, Failure Modes, and Dynamic Verification

---

## 1. Taxonomic Classification of Resource Invariants

To avoid conflating capacity accounting with lifecycle safety, ASTERION V3 defines four distinct invariants governing resource management.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        RESOURCE INVARIANT HIERARCHY                    │
├──────────────────────────┬─────────────────────────────────────────────┤
│ 1. Conservation Invariant│ Mathematical sum of capacity partitions     │
├──────────────────────────┼─────────────────────────────────────────────┤
│ 2. Lifecycle Invariant   │ Coupling between rollout status and holds   │
├──────────────────────────┼─────────────────────────────────────────────┤
│ 3. Availability Invariant│ Guaranteed liveness and hold release        │
├──────────────────────────┼─────────────────────────────────────────────┤
│ 4. Idempotency Invariant │ Repeatable operations prevent drift         │
└──────────────────────────┴─────────────────────────────────────────────┘
```

---

## 2. Invariant Specifications

### 2.1 The Conservation Invariant

* **Formal Condition**:  
  For each service $s \in \text{Services}$ with initial configured capacity $C_s$:
  $$\text{SLOTS}[s] + |\{r \in \text{LOCKED} \mid r.\text{service} = s\}| + \Delta_{\text{committed}}[s] = C_s$$
  where $\Delta_{\text{committed}}[s]$ represents active live deployments holding occupied production slots.
* **Preconditions**:
  * Single-threaded execution (or synchronized capacity mutators).
  * Capacity partitions are modified strictly through `acquire()`, `refund()`, and `commit()`.
* **Source Evidence**:
  * [deployweave/capacity.py:acquire](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/capacity.py#L3-L8): `SLOTS[r.service] -= 1`, `LOCKED.add(r.rollout_id)`.
  * [deployweave/capacity.py:refund](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/capacity.py#L9-L13): `LOCKED.remove(r.rollout_id)`, `SLOTS[r.service] += 1`.
  * [deployweave/capacity.py:commit](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/capacity.py#L14-L16): `LOCKED.discard(r.rollout_id)`.
* **Violation Scenario**:
  * A worker omits `commit(r)` on success, leaving $r \in \text{LOCKED}$ with status `'deployed'`.
  * A later call to `sweep_locks()` detects `'deployed'`, calls `refund(r)`, and increments `SLOTS[s] += 1`.
* **Observable Consequences**:
  * $\text{SLOTS}[s] + \Delta_{\text{committed}}[s] = C_s + 1 > C_s$.
  * Available capacity is artificially inflated beyond physical limits (oversubscription drift).
* **Verification Method**: **Dynamically Verified** (via `test_success_installs_and_commits` and mutation Q43).

---

### 2.2 The Lifecycle Invariant

* **Formal Condition**:  
  A rollout $r$ in a terminal state must not retain an active reservation in `LOCKED`:
  $$\forall r \in \text{ROLLOUTS}: \quad r.\text{status} \in \{\text{'deployed'}, \text{'rolled\_back'}, \text{'denied'}\} \implies r.\text{rollout\_id} \notin \text{LOCKED} \land r.\text{reserved} = \text{False}$$
* **Preconditions**:
  * Rollouts transition to terminal states exclusively upon completion of `execute()` or `deny()`.
* **Source Evidence**:
  * [deployweave/worker.py:execute](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/worker.py#L13-L21): Calls `commit(r)` before status `'deployed'`, or `refund(r)` before status `'rolled_back'`.
* **Violation Scenario**:
  * Rollback exhaustion branch omits `refund(r)` ([worker.py:line 21](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/worker.py#L21)).
* **Observable Consequences**:
  * $r.\text{status} = \text{'rolled\_back'}$, but $r.\text{rollout\_id} \in \text{LOCKED}$ and $r.\text{reserved} = \text{True}$.
  * A terminal rollout retains an active reservation.
* **Verification Method**: **Statically and Dynamically Verified** (via `test_permanent_bad_rolls_back`).

---

### 2.3 The Availability Invariant

* **Formal Condition**:  
  Unused or abandoned capacity must not remain permanently unallocatable. If a rollout is not actively executing, its reserved slot must either be committed to active production or restored to `SLOTS`:
  $$\lim_{t \to \infty} \left( r \notin \text{READY} \land r.\text{status} \neq \text{'ready'} \implies r.\text{rollout\_id} \notin \text{LOCKED} \right)$$
* **Preconditions**:
  * Worker process liveness or maintenance lock sweeper execution.
* **Source Evidence**:
  * [deployweave/maintenance.py:sweep_locks()](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/maintenance.py#L3-L9): Scans `LOCKED` and refunds leaked reservations for rollouts in terminal states.
* **Violation Scenario**:
  * Consumer pops $r$ from `READY` via `READY.pop(0)` and crashes before calling `execute()`.
  * The rollout remains stuck with `status = 'ready'`.
  * Because `sweep_locks()` only sweeps terminal statuses (`{'deployed', 'rolled_back', 'denied'}`), it ignores rollouts in `'ready'`.
* **Observable Consequences**:
  * The slot is permanently lost from `SLOTS[s]` and can never be recovered by `sweep_locks()`.
* **Verification Method**: **Statically Verified** (via AST control flow audit of `consumer.py` and `maintenance.py`).

---

### 2.4 The Idempotency Invariant

* **Formal Condition**:  
  Repeated execution of cleanup or commit operations must not cause state drift or double-refund:
  $$\text{refund}(\text{refund}(r)) \equiv \text{refund}(r) \quad \land \quad \text{commit}(\text{commit}(r)) \equiv \text{commit}(r)$$
* **Preconditions**:
  * Mutator checks set membership before modifying counters.
* **Source Evidence**:
  * [deployweave/capacity.py:refund()](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/capacity.py#L9-L13):
    ```python
    def refund(r):
        if r.rollout_id in LOCKED:    # Guard prevents double-increment!
            LOCKED.remove(r.rollout_id)
            SLOTS[r.service] += 1
        r.reserved = False
    ```
  * [deployweave/capacity.py:commit()](file:///home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark/deployweave/capacity.py#L14-L16):
    ```python
    def commit(r):
        LOCKED.discard(r.rollout_id)  # discard is idempotent!
        r.reserved = False
    ```
* **Violation Scenario**:
  * If `refund()` had omitted `if r.rollout_id in LOCKED:`, calling `refund(r)` twice would increment `SLOTS[r.service]` twice, creating phantom capacity.
* **Observable Consequences**:
  * DeployWeave's guard successfully prevents idempotency violations during repetitive `sweep_locks()` invocations.
* **Verification Method**: **Statically and Dynamically Verified** (via `test_sweep_not_needed_after_rollback`).

---

## 3. Critical Analytical Distinction: Leaked Hold vs Conservation Violation

> [!IMPORTANT]
> **A leaked reservation does NOT constitute a mathematical conservation violation.**

When a rollout crashes or omits `refund(r)` upon rollback:
* The slot is held in `LOCKED`.
* The mathematical sum $\text{SLOTS}[s] + |\text{LOCKED}_s|$ **remains exactly equal to $C_s$**. Every slot is mathematically accounted for in either available or reserved sets.
* Therefore, the **Conservation Invariant is preserved**.
* However, the **Lifecycle Invariant** and **Availability Invariant** are **violated**:
  * *Lifecycle Violation*: A terminal rollout (`rolled_back`) illegally holds an active reservation.
  * *Availability Violation*: Legitimate subsequent rollouts are blocked due to slot starvation caused by an abandoned lock.

ASTERION V3 explicitly separates mathematical accounting from operational lifecycle invariants.
