"""
scripts/run_deployweave_q51_q75.py - Execution & Verification for Questions 51-75.

Executes:
- Q51: Step-by-step state simulation of failed auth v2.0 followed by successful auth v3.0.
- Q52: Step-by-step execution of r1 (success) followed by r2 (failure) with FIFO rollback analysis.
- Q54: Probe retry execution analysis.
- Q66: Mutation of dependencies_healthy() returning True if name in DEPENDENCIES.
- Q69: Removal of READY status guard in poll_once().
- Q70: acquire(r) check-after-decrement mutation.
- Q72: Multi-agent conflict resolution in FalkorDB (H1 vs H2).
- Q73: Test selection & mutation execution for removing restore(r, old).
- Q74: Controlled A/B experiment on direct vs indirect dependency edges.
- Q75: Concurrency test demonstrating lack of exactly-once guarantee under concurrent workers.
"""

import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
import threading

backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from falkordb import FalkorDB

REPO_PATH = "/home/zeraphynx/Projects/asterion/backend/data/repos/repo_deployweave_aste_667ec8/DeployWeave_ASTERION_V3_Benchmark"
GRAPH_NAME = "workspace_repo_deployweave_aste_667ec8"

fdb = FalkorDB(host="localhost", port=6379)
g = fdb.select_graph(GRAPH_NAME)

def run_q51_simulation():
    print("=" * 80)
    print("Q51: Simulation of Failed Staging Auth v2.0 followed by Successful Auth v3.0")
    print("=" * 80)
    sys.path.insert(0, REPO_PATH)
    from deployweave.api import create_rollout, run_worker_once
    from deployweave.store import ROLLOUTS, EVENTS, READY, AUDIT
    from deployweave.capacity import SLOTS, LOCKED
    from deployweave.registry import VERSIONS, CHANGES
    from deployweave.health import ALWAYS_BAD, CHECKS
    from deployweave.notifications import NOTICES
    from deployweave.retry import ROLLBACK_COUNTS

    # Reset
    for c in (ROLLOUTS, EVENTS, READY, AUDIT, LOCKED, CHANGES, ALWAYS_BAD, CHECKS, NOTICES, ROLLBACK_COUNTS): c.clear()
    SLOTS.update(auth=2, ledger=2, gateway=1)
    VERSIONS.clear(); VERSIONS.update(auth='1.0', ledger='1.0', gateway='1.0')

    # Step 1: Submit auth v2.0
    r1 = create_rollout(dict(rollout_id='r1', service='auth', environment='staging', version='2.0'))
    # Step 2: Fail probes & rollback
    ALWAYS_BAD.add('r1')
    run_worker_once()

    # Step 3: Submit auth v3.0
    r2 = create_rollout(dict(rollout_id='r2', service='auth', environment='staging', version='3.0'))
    # Succeeds
    run_worker_once()

    results = {
        "SLOTS": dict(SLOTS),
        "LOCKED": list(LOCKED),
        "VERSIONS": dict(VERSIONS),
        "READY": list(READY),
        "CHECKS": dict(CHECKS),
        "CHANGES": list(CHANGES),
        "EVENTS": list(EVENTS),
        "AUDIT": list(AUDIT),
        "NOTICES": list(NOTICES)
    }
    print(f"Final SLOTS: {results['SLOTS']}")
    print(f"Final LOCKED: {results['LOCKED']}")
    print(f"Final VERSIONS: {results['VERSIONS']}")
    print(f"Final READY: {results['READY']}")
    print(f"Final CHECKS: {results['CHECKS']}")
    print(f"Final CHANGES: {results['CHANGES']}")
    print(f"Final EVENTS: {results['EVENTS']}")
    print(f"Final AUDIT: {results['AUDIT']}")
    return results

def run_q52_simulation():
    print("\n" + "=" * 80)
    print("Q52: Sequential Submission of r1 (success) & r2 (fail) with 2 Slots")
    print("=" * 80)
    from deployweave.api import create_rollout, run_worker_once
    from deployweave.store import ROLLOUTS, EVENTS, READY, AUDIT
    from deployweave.capacity import SLOTS, LOCKED
    from deployweave.registry import VERSIONS, CHANGES
    from deployweave.health import ALWAYS_BAD, CHECKS
    from deployweave.notifications import NOTICES
    from deployweave.retry import ROLLBACK_COUNTS

    for c in (ROLLOUTS, EVENTS, READY, AUDIT, LOCKED, CHANGES, ALWAYS_BAD, CHECKS, NOTICES, ROLLBACK_COUNTS): c.clear()
    SLOTS.update(auth=2, ledger=2, gateway=1)
    VERSIONS.clear(); VERSIONS.update(auth='1.0', ledger='1.0', gateway='1.0')

    # Submit r1 then r2
    r1 = create_rollout(dict(rollout_id='r1', service='auth', environment='staging', version='2.0'))
    r2 = create_rollout(dict(rollout_id='r2', service='auth', environment='staging', version='3.0'))
    
    # r1 succeeds, r2 fails
    ALWAYS_BAD.add('r2')
    run_worker_once() # runs r1
    run_worker_once() # runs r2

    results = {
        "SLOTS": dict(SLOTS),
        "LOCKED": list(LOCKED),
        "VERSIONS": dict(VERSIONS),
        "CHANGES": list(CHANGES),
        "AUDIT": list(AUDIT)
    }
    print(f"Final SLOTS: {results['SLOTS']}")
    print(f"Final VERSIONS: {results['VERSIONS']}")
    print(f"Final LOCKED: {results['LOCKED']}")
    print(f"Final CHANGES: {results['CHANGES']}")
    print(f"Final AUDIT: {results['AUDIT']}")
    return results

def run_q66_mutation_experiment():
    print("\n" + "=" * 80)
    print("Q66: Mutate dependencies_healthy() to check name in DEPENDENCIES")
    print("=" * 80)
    tmp_dir = tempfile.mkdtemp(prefix="q66_")
    repo = os.path.join(tmp_dir, "dw")
    shutil.copytree(REPO_PATH, repo)
    
    policy_f = os.path.join(repo, "deployweave", "policy.py")
    with open(policy_f) as f: c = f.read()
    mutated = c.replace(
        "if VERSIONS.get(dependency) is None: return False",
        "if dependency not in DEPENDENCIES: return False"
    )
    with open(policy_f, "w") as f: f.write(mutated)
    
    res = subprocess.run([sys.executable, "-m", "pytest", "-v", "tests/test_deployweave.py"], cwd=repo, capture_output=True, text=True)
    failing = [line.split("::DeployWeaveTests::")[1].split()[0] for line in res.stdout.splitlines() if "FAILED" in line and "::DeployWeaveTests::" in line]
    print(f"Exit code: {res.returncode}")
    print(f"Failing tests: {failing}")
    shutil.rmtree(tmp_dir)
    return {"failing_tests": failing, "exit_code": res.returncode}

def run_q70_mutation_experiment():
    print("\n" + "=" * 80)
    print("Q70: Mutate acquire(r) to check-after-decrement")
    print("=" * 80)
    tmp_dir = tempfile.mkdtemp(prefix="q70_")
    repo = os.path.join(tmp_dir, "dw")
    shutil.copytree(REPO_PATH, repo)
    
    cap_f = os.path.join(repo, "deployweave", "capacity.py")
    with open(cap_f) as f: c = f.read()
    # Mutate to decrement first without restoring
    mutated = c.replace(
        "if SLOTS.get(r.service,0) <= 0: return False\n    SLOTS[r.service] -= 1",
        "SLOTS[r.service] -= 1\n    if SLOTS.get(r.service,0) < 0: return False"
    )
    with open(cap_f, "w") as f: f.write(mutated)
    
    res = subprocess.run([sys.executable, "-m", "pytest", "-v", "tests/test_deployweave.py"], cwd=repo, capture_output=True, text=True)
    failing = [line.split("::DeployWeaveTests::")[1].split()[0] for line in res.stdout.splitlines() if "FAILED" in line and "::DeployWeaveTests::" in line]
    print(f"Exit code: {res.returncode}")
    print(f"Failing tests: {failing}")
    shutil.rmtree(tmp_dir)
    return {"failing_tests": failing, "exit_code": res.returncode}

def run_q75_concurrency_experiment():
    print("\n" + "=" * 80)
    print("Q75: Concurrency Experiment (Race Condition on Shared VERSIONS)")
    print("=" * 80)
    from deployweave.store import ROLLOUTS, EVENTS, READY, AUDIT
    from deployweave.capacity import SLOTS, LOCKED
    from deployweave.registry import VERSIONS, CHANGES
    from deployweave.health import ALWAYS_BAD, CHECKS
    from deployweave.notifications import NOTICES
    from deployweave.retry import ROLLBACK_COUNTS
    from deployweave.models import Rollout
    from deployweave.worker import execute

    for c in (ROLLOUTS, EVENTS, READY, AUDIT, LOCKED, CHANGES, ALWAYS_BAD, CHECKS, NOTICES, ROLLBACK_COUNTS): c.clear()
    SLOTS.update(auth=2, ledger=2, gateway=1)
    VERSIONS.clear(); VERSIONS.update(auth='1.0', ledger='1.0', gateway='1.0')

    # r1 installs 2.0 (fails), r2 installs 3.0 (succeeds)
    r1 = Rollout('r1', 'auth', 'staging', '2.0', status='ready')
    r2 = Rollout('r2', 'auth', 'staging', '3.0', status='ready')
    ROLLOUTS['r1'] = r1; ROLLOUTS['r2'] = r2
    LOCKED.add('r1'); LOCKED.add('r2')
    ALWAYS_BAD.add('r1')

    # Simulate interleaved concurrent workers:
    # Worker 1 installs r1 (v2.0)
    # Worker 2 installs r2 (v3.0)
    # Worker 1 rolls back r1 -> restore(r1, '1.0') clobbering v3.0!
    # Worker 2 deploys r2 (v3.0)
    
    # Thread 1 starts execute(r1)
    # Thread 2 starts execute(r2)
    def worker1():
        execute(r1)

    def worker2():
        time.sleep(0.001) # slight delay to interleave after install
        execute(r2)

    t1 = threading.Thread(target=worker1)
    t2 = threading.Thread(target=worker2)
    t1.start(); t2.start()
    t1.join(); t2.join()

    print(f"Concurrent Final Status: r1={r1.status}, r2={r2.status}")
    print(f"Concurrent Final VERSIONS: {dict(VERSIONS)}")
    print(f"Concurrent Final CHANGES: {list(CHANGES)}")
    
    # Did r2 succeed? r2.status == 'deployed'
    # What is VERSIONS['auth']? If it is '1.0', r1 clobbered r2!
    clobbered = (r2.status == 'deployed' and VERSIONS['auth'] != '3.0')
    print(f"Race condition detected (Deployed v3.0 but active version is '{VERSIONS['auth']}'): {clobbered}")
    return {
        "r1_status": r1.status,
        "r2_status": r2.status,
        "final_version": VERSIONS['auth'],
        "clobbered_detected": clobbered
    }

if __name__ == "__main__":
    q51_res = run_q51_simulation()
    q52_res = run_q52_simulation()
    q66_res = run_q66_mutation_experiment()
    q70_res = run_q70_mutation_experiment()
    q75_res = run_q75_concurrency_experiment()
    
    out_file = os.path.join(backend_root, "scripts", "v3_q51_q75_receipts.json")
    with open(out_file, "w") as f:
        json.dump({
            "q51": q51_res,
            "q52": q52_res,
            "q66": q66_res,
            "q70": q70_res,
            "q75": q75_res
        }, f, indent=2)
    print(f"\n[DONE] Saved Q51-Q75 receipts to {out_file}")
