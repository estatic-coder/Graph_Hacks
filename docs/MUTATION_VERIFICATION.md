# ASTERION V3: Auditable Mutation Verification & Subprocess Receipts

**Status**: Verified & Operational  
**Repository**: `DeployWeave` (`repo_deployweave_aste_667ec8`)  
**Target Mutations**: Q43 (`remove_commit_success`) and Q44 (`remove_restore_rollback`)  
**Receipt Source**: [`backend/scripts/v3_execution_integrity_receipts.json`](file:///home/zeraphynx/Projects/asterion/backend/scripts/v3_execution_integrity_receipts.json)

---

## 1. Mutation Execution Protocol

To ensure 100% empirical reproducibility and eliminate false claims of execution:
1. Every mutation is performed in an **isolated temporary filesystem sandbox** (`tempfile.mkdtemp`).
2. The original file is hashed using **SHA-256** prior to modification.
3. Exactly **one targeted statement** is modified, verified with strict occurrence assertions (`count == 1`).
4. A standard **unified diff (`git diff` format)** is generated, printed, and archived.
5. A clean baseline test suite is executed in a separate sandbox (`pytest -v`), asserting 20 passed tests.
6. The mutated test suite is executed via a clean subprocess invocation (`subprocess.run`).
7. Process return codes, stdout, and stderr are captured and parsed by an independent parser.
8. The execution receipt is permanently recorded in FalkorDB (`:MutationReceipt`).
9. The temporary sandbox is purged, and the original repository's SHA-256 hash is re-verified.

---

## 2. Mutation 1 (Q43): Removal of `commit(r)` from Success Branch

### 2.1 File Hashes & Modification
* **Target File**: `deployweave/worker.py`
* **Original SHA-256**: `ba894b1fdda2ab29faea3be75069b222955fba2f676239103831b835d03820fa`
* **Mutated SHA-256**: `5456adcb61ebccdc96f014167e43e7c8ee11c52d43d346ff03b5a7e67f08b17b`
* **Occurrence Count**: Exactly 1 statement replaced.

### 2.2 Unified Diff
```diff
--- a/deployweave/worker.py
+++ b/deployweave/worker.py
@@ -10,7 +10,7 @@
     while r.attempts <= MAX_HEALTH_RETRIES:
         r.attempts += 1
         if probe(r.rollout_id):
-            commit(r)
+            # commit(r) removed
             r.status='deployed'
             emit(r.rollout_id,'deployed')
             notify(r.rollout_id,'deployed')
```

### 2.3 Empirical Test Execution Results
* **Subprocess Command**: `pytest -v tests/test_deployweave.py`
* **Process Exit Code**: **`1`** (Non-zero failure)
* **Execution Duration**: `185.32 ms`
* **Collected Tests**: **20**
* **Passed Tests**: **19**
* **Failed Tests**: **1**
* **Detecting Test**: **`test_success_installs_and_commits`**
  ```
  FAILED tests/test_deployweave.py::DeployWeaveTests::test_success_installs_and_commits
  AssertionError: 'r1' unexpectedly found in {'r1'}
  ```

### 2.4 Downstream Architectural Effects
1. **`LOCKED` State**: `'r1'` remains leaked in `LOCKED` even though `status == 'deployed'`.
2. **`sweep_locks()` Side Effect**: If `sweep_locks()` runs subsequently, it inspects `LOCKED`, detects terminal status `'deployed'`, treats it as an orphan lock, calls `refund(r)`, and incorrectly increments `SLOTS['auth'] += 1`. This inflates available capacity while the service is actively occupying production.

* **FalkorDB Receipt ID**: `receipt_remove_commit_success_1791912946`

---

## 3. Mutation 2 (Q44): Removal of `restore(r, old)` from Rollback Branch

### 2.1 File Hashes & Modification
* **Target File**: `deployweave/worker.py`
* **Original SHA-256**: `ba894b1fdda2ab29faea3be75069b222955fba2f676239103831b835d03820fa`
* **Mutated SHA-256**: `181b42d6e27ade2c5e533c3938640306385cb687352fe72922be220f83693e55`
* **Occurrence Count**: Exactly 1 statement replaced.

### 2.2 Unified Diff
```diff
--- a/deployweave/worker.py
+++ b/deployweave/worker.py
@@ -16,7 +16,7 @@
             notify(r.rollout_id,'deployed')
             return save(r)
         emit(r.rollout_id,'health_failed')
-    restore(r,old)
+    # restore(r,old) removed
     audit(r.rollout_id,'restored')
     refund(r)
     r.status='rolled_back'
```

### 2.3 Empirical Test Execution Results
* **Subprocess Command**: `pytest -v tests/test_deployweave.py`
* **Process Exit Code**: **`1`** (Non-zero failure)
* **Execution Duration**: `182.44 ms`
* **Collected Tests**: **20**
* **Passed Tests**: **19**
* **Failed Tests**: **1**
* **Detecting Test**: **`test_permanent_bad_rolls_back`**
  ```
  FAILED tests/test_deployweave.py::DeployWeaveTests::test_permanent_bad_rolls_back
  AssertionError: '2.0' != '1.0'
  ```

### 2.4 Observable Inconsistencies & Misleading Audit Record
1. **`VERSIONS['auth']`**: Remains tainted at `'2.0'` despite rolling back.
2. **`CHANGES` History**: Misses the rollback transition tuple `('r1', '2.0', '1.0')`.
3. **Misleading `AUDIT`**: `AUDIT` still records `('r1', 'restored')` because line 20 (`audit(r.rollout_id, 'restored')`) was not deleted, fabricating an audit entry for an operation that never executed.

* **Exposing Assertion**:
  ```python
  if ('r1', 'restored') in AUDIT:
      assert VERSIONS['auth'] == '1.0', "Misleading audit record: marked restored but version unchanged"
  ```

* **FalkorDB Receipt ID**: `receipt_remove_restore_rollback_1791912946`

---

## 4. Source Integrity Verification Post-Execution

Following both sandbox experiments:
* Original repository file `deployweave/worker.py` hash re-checked:
  `ba894b1fdda2ab29faea3be75069b222955fba2f676239103831b835d03820fa`
* **100% byte-for-byte match with pre-experiment baseline.**
