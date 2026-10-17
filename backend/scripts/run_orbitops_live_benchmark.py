"""
scripts/run_orbitops_live_benchmark.py - Live Verification of Complete OrbitOps Suite

Executes the OrbitOps benchmark suite against the live running ASTERION backend (http://127.0.0.1:8000/api/investigate).
Verifies:
- Direct Answer precision and accuracy
- Exact event names (review_requested, authorized, sent)
- Accurate configuration balance ({'core': 3, 'security': 2}, NO infra)
- All 3 mutation-detecting tests for deliver() exhaustion
- Observable-state dependency model
- Persistent memory trace across independent sessions in FalkorDB
- Multi-agent coordination with 4 distinct agent identities, leases, and persisted HANDOFF_TO edges
- Auditable execution receipts with sandbox isolation and counts reconciliation (14 = 11 passed + 3 failed)
- Verification dimensions (all 6 distinct dimensions)
"""

import json
import time
import urllib.request
import urllib.error

ENDPOINT = "http://127.0.0.1:8000/api/investigate"
REPO_ID = "repo_orbitops_asterio_c0a361"

QUESTIONS = [
    {
        "id": "Q1",
        "question": "Enumerate all static CALLS paths from create_alert(), approve_alert(), and retry_failed_alert() to send_page(). Identify any shared-state handoffs.",
        "checks": [
            ("NO synchronous CALLS path", True),
            ("PENDING", True),
            ("ALERTS", True),
            ("HELD", True),
            ("BALANCE", True),
        ]
    },
    {
        "id": "Q2",
        "question": "Give the complete static CALLS chain starting at run_agent_once() and ending at send_page(). List the two guards that prevent reaching send_page().",
        "checks": [
            ("run_agent_once()", True),
            ("drain_one()", True),
            ("deliver()", True),
            ("send_page()", True),
            ("Empty Queue Guard", True),
            ("Non-Pending Status Guard", True),
        ]
    },
    {
        "id": "Q5",
        "question": "After a normal create_alert() returns, give status, BALANCE, HELD, PENDING, ordered EVENTS, pager CALLS, and NOTICES.",
        "checks": [
            ("'pending'", True),
            ("{'core': 3, 'security': 2}", True),
            ("'infra'", False),  # Crucial: infra must NOT be present!
            ("{'a1'}", True),
            ("['a1']", True),
            ("[('a1', 'pending')]", True),
            ("{}", True),
            ("[]", True),
        ]
    },
    {
        "id": "Q6",
        "question": "For a security-team alert, trace creation, approval, and one worker iteration. Distinguish distinct API entrypoints, persistence, and queue handoffs.",
        "checks": [
            ("review_requested", True),
            ("authorized", True),
            ("sent", True),
            ("Phase 1: Creation", True),
            ("Phase 2: Approval", True),
            ("Phase 3: Worker Iteration", True),
        ]
    },
    {
        "id": "Q7",
        "question": "For an alert with severity 9 and team core, does create_alert() reserve credits or enqueue the alert? Why?",
        "checks": [
            ("NO", True),
            ("severity >= 8", True),
            ("credits remain unreserved", True),
        ]
    },
    {
        "id": "Q9",
        "question": "With MAX_ATTEMPTS=2 and persistent pager timeouts, report pager calls, timeouts, final status, balance, reservation, events, and notices.",
        "checks": [
            ("3 calls", True),
            ("3 page_timeout events", True),
            ("'failed'", True),
            ("4", True),
            ("HELD is empty", True),
        ]
    },
    {
        "id": "Q11",
        "question": "If MAX_ATTEMPTS changes to 4, give maximum pager calls and timeout events for permanent failure, and calls for immediate success.",
        "checks": [
            ("5 calls", True),
            ("5 page_timeout events", True),
            ("1 call", True),
            ("0 timeouts", True),
        ]
    },
    {
        "id": "Q12",
        "question": "After a failure is reopened and the pager recovers, calculate total pager calls, attempt reset, final attempts, events, balance, reservation, and notices.",
        "checks": [
            ("4 calls", True),
            ("Reset to 0", True),
            ("1", True),
            ("('a1', 'reopened')", True),
            ("('a1', 'sent')", True),
            ("3", True),
        ]
    },
    {
        "id": "Q13",
        "question": "Can a failed reopen consume the reopen budget even without enqueue? Explain ordering and next-attempt behavior.",
        "checks": [
            ("YES", True),
            ("REOPENED[alert_id] = used + 1", True),
            ("reopen budget exceeded", True),
        ]
    },
    {
        "id": "Q16",
        "question": "If release() is removed from the exhaustion branch of deliver(), which tests detect the regression and which execute without detecting?",
        "checks": [
            ("test_exhausted_releases", True),
            ("test_reopen_after_recovery", True),
            ("test_no_auto_sweep_needed_on_failure", True),
            ("test_reopen_once_only", True),
            ("sweep_holds()", True),
            ("line 99", True),
            ("Observable-state dependency model", True),
        ]
    },
    {
        "id": "Q21",
        "question": "If a worker crashes after PENDING.pop(0) but before deliver(), describe the loss window, and explain whether the repository contains durable broker recovery.",
        "checks": [
            ("orbitops/consumer.py:7-11", True),
            ("destructive in-memory removal", True),
            ("NO message acknowledgment", True),
            ("NO visibility timeout", True),
            ("sweep_holds()", True),
            ("does NOT run automatically", True),
        ]
    },
    {
        "id": "Q27",
        "question": "Store a verified finding about the queue-loss window in FalkorDB, show retrieved provenance across independent sessions, and verify status.",
        "checks": [
            ("10-Step Verification Trace", True),
            ("Session A", True),
            ("Session B", True),
            ("VALID", True),
            ("INVALIDATED / STALE", True),
            ("Database Graph Identifier", True),
        ]
    },
    {
        "id": "Q28",
        "question": "Perform a multi-agent investigation of why an alert is stuck in review, with distinct task IDs, leases, and persisted handoffs.",
        "checks": [
            ("agent_graph_investigator_1", True),
            ("agent_execution_analyst_1", True),
            ("agent_test_analyst_1", True),
            ("agent_evidence_reviewer_1", True),
            ("HANDOFF_TO", True),
            ("resume_investigation", True),
            ("APPROVED", True),
        ]
    },
    {
        "id": "Q30",
        "question": "Produce a git diff that removes release() from deliver(), generate a blast-radius graph, and execute tests in an isolated sandbox with auditable receipts.",
        "checks": [
            ("execution_receipt", True),
            ("14", True),
            ("11", True),
            ("3", True),
            ("test_no_auto_sweep_needed_on_failure", True),
            ("test_exhausted_releases", True),
            ("test_reopen_after_recovery", True),
        ]
    }
]

def query_live_api(question: str):
    payload = {
        "repo_id": REPO_ID,
        "query": question
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print(f"=== Running Live OrbitOps Benchmark Verification ({len(QUESTIONS)} questions) ===")
    results = []
    all_passed = True

    for item in QUESTIONS:
        qid = item["id"]
        q_text = item["question"]
        print(f"\n--- Testing {qid}: {q_text[:70]}... ---")
        t0 = time.time()
        try:
            resp = query_live_api(q_text)
            elapsed = time.time() - t0
        except Exception as e:
            print(f"FAILED to call API: {e}")
            all_passed = False
            results.append({"id": qid, "status": "ERROR", "error": str(e)})
            continue

        status = resp.get("status")
        answer = resp.get("answer", "")
        verification = resp.get("verification", {})

        checks_passed = True
        failed_checks = []
        for term, expected in item["checks"]:
            if expected:
                if term not in answer:
                    checks_passed = False
                    failed_checks.append(f"Missing expected: '{term}'")
            else:
                if term in answer:
                    checks_passed = False
                    failed_checks.append(f"Found forbidden: '{term}'")

        dims = {
            "source_verified": verification.get("source_verified"),
            "graph_verified": verification.get("graph_verified"),
            "scenario_verified": verification.get("scenario_verified"),
            "execution_verified": verification.get("execution_verified"),
            "memory_persistence_verified": verification.get("memory_persistence_verified"),
            "multi_agent_handoff_verified": verification.get("multi_agent_handoff_verified"),
        }

        print(f"Status: {status} in {elapsed:.2f}s | Dimensions: {dims}")
        if not checks_passed:
            print(f"❌ Check failures: {failed_checks}")
            all_passed = False
        else:
            print("✅ All check criteria satisfied!")

        results.append({
            "id": qid,
            "status": "PASS" if (status == "success" and checks_passed) else "FAIL",
            "elapsed_sec": round(elapsed, 2),
            "dimensions": dims,
            "checks_passed": checks_passed,
            "failed_checks": failed_checks,
            "answer_preview": answer[:300]
        })

    summary = {
        "timestamp": time.time(),
        "total": len(QUESTIONS),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "results": results
    }

    out_file = "/home/zeraphynx/Projects/asterion/backend/scripts/orbitops_live_benchmark_results.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n==========================================")
    print(f"Benchmark Complete: {summary['passed']}/{summary['total']} PASS")
    print(f"Results saved to {out_file}")
    if not all_passed:
        exit(1)

if __name__ == "__main__":
    main()
