"""
scripts/verify_agent_actions_mutation.py - Verification of Real Agent Actions & Mutation-Confirmed Regression.

Verifies:
1. Mutate a function in an isolated copy of SignalForge benchmark.
2. Identify impacted functions through graph traversal.
3. Select appropriate tests based on graph distance and failure assertions.
4. Run selected tests in an isolated sandbox subprocess.
5. Collect real exit codes, stdout, stderr, and failure traces.
6. Record action and execution outcomes in FalkorDB.
7. Revert the mutation and verify that tests transition from FAIL (exit code 1) to PASS (exit code 0).
8. Distinguish:
   - Test Recommendation (graph candidate discovery)
   - Test Selection (priority ranking by topological distance)
   - Test Execution (sandboxed subprocess invocation)
   - Mutation-Confirmed Regression Detection (detecting injected defect)
"""

import os
import sys
import time
import shutil
import tempfile
import json
import logging

backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.agent.actions import AgentActionEngine
from app.graph.client import FalkorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_mutation_verification():
    print("=" * 80)
    print("ASTERION V2: MUTATION-CONFIRMED REGRESSION & ACTION VERIFICATION")
    print("=" * 80)

    # 1. Create an isolated copy of SignalForge in a sandbox directory
    src_sf = os.path.abspath(os.path.join(
        backend_root, "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3"
    ))
    sandbox_dir = tempfile.mkdtemp(prefix="asterion_sandbox_")
    sandbox_repo = os.path.join(sandbox_dir, "SignalForge")
    shutil.copytree(src_sf, sandbox_repo)
    print(f"[STEP 1] Created isolated sandbox repository at: {sandbox_repo}")

    repo_id = f"repo_mutant_{int(time.time())}"
    from app.ingestion.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(repo_path=sandbox_repo, repo_id=repo_id)
    pipeline.index()
    print(f"  Indexed sandbox repository into FalkorDB graph 'workspace_{repo_id}'")

    engine = AgentActionEngine(repo_id=repo_id, repo_path=sandbox_repo, workspace_id="ws_sandbox")

    # 2. Phase 1: Baseline clean test selection & execution
    print("\n[STEP 2] Baseline Clean Execution: Graph-Guided Test Selection on 'dispatch'")
    baseline_res = engine.select_tests_by_graph(
        target_symbol="dispatch",
        max_graph_distance=3,
        auto_run=True,
        authorized=True
    )
    print(f"  Recommended tests: {baseline_res['total_candidate_tests']}")
    print(f"  Selected tests: {len(baseline_res['selected_tests'])}")
    print(f"  Baseline Execution Status: {baseline_res['test_run_results']['status']}")
    print(f"  Baseline Exit Code: {baseline_res['test_run_results']['exit_code']}")
    assert baseline_res["test_run_results"]["status"] == "ALL_PASSED"
    assert baseline_res["test_run_results"]["exit_code"] == 0

    # 3. Phase 2: Inject Mutation (delete budget release upon persistent failure)
    print("\n[STEP 3] Injecting defect/mutation into 'signalforge/worker.py'")
    worker_file = os.path.join(sandbox_repo, "signalforge", "worker.py")
    with open(worker_file, "r") as f:
        worker_code = f.read()

    # Mutation: remove release(i) on line 17
    mutated_code = worker_code.replace("release(i)", "# release(i) removed")
    assert mutated_code != worker_code, "Failed to apply mutation to worker.py"
    with open(worker_file, "w") as f:
        f.write(mutated_code)
    print("  Mutated 'run_worker_once': commented out 'release(inc)' upon persistent failure.")

    # 4. Phase 3: Graph Traversal identifies impacted functions
    print("\n[STEP 4] Identifying impacted functions via Graph Traversal")
    # worker -> release -> TOKENS / RESERVED
    impact = engine.investigate_regression_from_diff(
        diff_text="--- a/signalforge/worker.py\n+++ b/signalforge/worker.py\n@@ -15,2 +15,2 @@\n-    release(inc)\n+    # release(inc) removed\n",
        failing_test_name="test_persistent_failure_releases_budget"
    )
    print(f"  Modified symbols: {impact['modified_symbols']}")
    print(f"  Blast radius: {impact['impact_analysis'][0]['blast_radius_count']} node(s)")

    # 5. Phase 4: Run selected tests against mutated code in sandbox
    print("\n[STEP 5] Running Graph-Selected Tests against Mutated Code in Sandbox")
    mutated_run_res = engine.select_tests_by_graph(
        target_symbol="dispatch",
        max_graph_distance=3,
        auto_run=True,
        authorized=True
    )
    test_results = mutated_run_res["test_run_results"]
    print(f"  Tests Executed: {test_results['tests_run']}")
    print(f"  Passed: {test_results['passed']}")
    print(f"  Failed: {test_results['failed']}")
    print(f"  Real Process Exit Code: {test_results['exit_code']}")
    print(f"  Status: {test_results['status']}")

    assert test_results["subprocess_executed"] is True
    assert test_results["failed"] > 0, "Mutated code should have caused test failure!"
    assert test_results["exit_code"] != 0, "Exit code must be non-zero for failed tests!"
    assert test_results["status"] == "FAILURES_DETECTED"
    print("  [CONFIRMED] Real subprocess caught the regression with non-zero exit code!")

    # 6. Phase 5: Revert Mutation and re-verify pass
    print("\n[STEP 6] Reverting mutation to verify healing")
    with open(worker_file, "w") as f:
        f.write(worker_code)
    healed_res = engine.select_tests_by_graph(
        target_symbol="dispatch",
        max_graph_distance=3,
        auto_run=True,
        authorized=True
    )
    assert healed_res["test_run_results"]["status"] == "ALL_PASSED"
    assert healed_res["test_run_results"]["exit_code"] == 0
    print("  [CONFIRMED] Restored code passes all graph-selected tests (exit code 0).")

    # 7. Phase 6: Verify FalkorDB persistence of Action records
    print("\n[STEP 7] Verifying Action & Execution provenance in FalkorDB")
    client = FalkorClient(url="redis://localhost:6379")
    client.connect()
    graph_name = f"workspace_{repo_id}"
    act_cypher = "MATCH (a:Action) RETURN a.type, a.tests_run, a.passed, a.failed, a.exit_code ORDER BY a.timestamp"
    act_records = client.safe_query(graph_name, act_cypher)
    print(f"  FalkorDB Action records persisted: {len(act_records.result_set)}")
    for r in act_records.result_set:
        print(f"    Action({r[0]}): tests_run={r[1]}, passed={r[2]}, failed={r[3]}, exit_code={r[4]}")
    assert len(act_records.result_set) >= 3

    # Cleanup sandbox
    shutil.rmtree(sandbox_dir, ignore_errors=True)

    result_summary = {
        "baseline": {"status": baseline_res["test_run_results"]["status"], "exit_code": 0},
        "mutant_detected": {
            "status": test_results["status"],
            "exit_code": test_results["exit_code"],
            "failed_count": test_results["failed"],
            "passed_count": test_results["passed"]
        },
        "healed": {"status": "ALL_PASSED", "exit_code": 0},
        "falkordb_actions_count": len(act_records.result_set),
        "distinction_demonstrated": {
            "recommendation": baseline_res["total_candidate_tests"],
            "selection": len(baseline_res["selected_tests"]),
            "execution": test_results["tests_run"],
            "mutation_detection": "CONFIRMED"
        }
    }

    out_file = os.path.join(backend_root, "scripts", "mutation_action_verification_results.json")
    with open(out_file, "w") as f:
        json.dump(result_summary, f, indent=2)
    print(f"\n[COMPLETE] Mutation action verification passed! Summary saved to {out_file}")
    return result_summary


if __name__ == "__main__":
    run_mutation_verification()
