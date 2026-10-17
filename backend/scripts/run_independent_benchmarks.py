"""
scripts/run_independent_benchmarks.py - Independent Benchmark Evaluation Harness.

Runs ASTERION through the actual user-facing query pipeline (GraphInvestigator.investigate_with_report)
against:
1. RelayMesh (10 architectural scenarios: static vs queue, retry counts, failed reservations, replay lifecycle, etc.)
2. SignalForge (10 architectural scenarios: initial state, conditional routing, persistent/transient failures, etc.)
3. SentinelShop (Unseen repository: multi-hop call paths, change impact, negative-path reasoning, shared dependencies)

Grades all answers against independently maintained ground-truth answer keys.
Zero hardcoded responses.
"""

import os
import sys
import time
import json
import logging
from typing import Dict, List, Any

backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.agent.investigator import GraphInvestigator
from app.graph.client import falkor_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BenchmarkHarness")


BENCHMARKS = [
    # -------------------------------------------------------------------------
    # Benchmark 1: RelayMesh
    # -------------------------------------------------------------------------
    {
        "suite": "RelayMesh",
        "repo_id": "repo_relaymesh_asteri_244812",
        "repo_path": os.path.abspath(os.path.join(backend_root, "data", "repos", "repo_relaymesh_asteri_244812", "relaymesh_benchmark")),
        "questions": [
            {
                "id": "RM_Q1",
                "topic": "Static vs Queue-Mediated Execution",
                "question": "What is the complete delivery path to deliver, and do submit or approve directly call dispatch?",
                "expected_keywords": ["run_worker_once", "poll_once", "dispatch", "deliver", "outbox"],
                "negative_keywords": ["submit directly calls dispatch", "approve directly calls dispatch"]
            },
            {
                "id": "RM_Q2",
                "topic": "Initial State Effects",
                "question": "What is the exact state after submitting a standard job: status, credit, reservation, outbox, and delivery attempts?",
                "expected_keywords": ["queued", "credit", "reserved", "outbox", "0"],
                "negative_keywords": ["delivered"]
            },
            {
                "id": "RM_Q3",
                "topic": "Persistent Failure",
                "question": "What happens when transport deliver fails with persistent TimeoutError? How many calls occur and what is the final quota and notice status?",
                "expected_keywords": ["3", "delivery_timeout", "dead_letter", "quota", "release"],
                "negative_keywords": ["delivered"]
            },
            {
                "id": "RM_Q4",
                "topic": "Transient Failure & Retry Counts",
                "question": "If delivery times out once and succeeds on the second attempt, how many calls are made and what is the final credit and receipt?",
                "expected_keywords": ["2", "delivery_timeout", "delivered", "receipt"],
                "negative_keywords": ["dead_letter"]
            },
            {
                "id": "RM_Q5",
                "topic": "Conditional Routing (VIP Review)",
                "question": "How does a VIP high-priority job route through approval? Is it reserved and queued before approval?",
                "expected_keywords": ["review", "approve", "outbox", "worker"],
                "negative_keywords": ["immediate delivery"]
            },
            {
                "id": "RM_Q12",
                "topic": "Replay Lifecycle",
                "question": "When a dead-letter job is replayed, are attempts reset and what is the cumulative call count after one successful retry?",
                "expected_keywords": ["0", "reset", "delivered", "replay"],
                "negative_keywords": []
            },
            {
                "id": "RM_Q14",
                "topic": "Failed Reservations & Replay Budget",
                "question": "Does REPLAY_COUNTS increment before reserve, and what happens if reservation fails?",
                "expected_keywords": ["increment", "reserve", "budget", "replay"],
                "negative_keywords": []
            },
            {
                "id": "RM_Q16",
                "topic": "Queue Ownership & Orphan Sweep",
                "question": "Who calls sweep_orphans in the repository, and does dead letter already release quota?",
                "expected_keywords": ["sweep_orphans", "release", "quota", "stale"],
                "negative_keywords": []
            },
            {
                "id": "RM_Q17",
                "topic": "Crash Consistency & State Pop",
                "question": "Does poll_once dispatch a non-queued job, or does it pop and return without delivery?",
                "expected_keywords": ["poll_once", "pop", "dispatch"],
                "negative_keywords": []
            },
            {
                "id": "RM_Q19",
                "topic": "Test-Impact Accuracy",
                "question": "If worker does not release reservation on success, which test asserts the absence of the job in RESERVED?",
                "expected_keywords": ["reserved", "test_worker_success", "worker"],
                "negative_keywords": []
            }
        ]
    },
    # -------------------------------------------------------------------------
    # Benchmark 2: SignalForge
    # -------------------------------------------------------------------------
    {
        "suite": "SignalForge",
        "repo_id": "repo_signalforge_aste_d53975",
        "repo_path": os.path.abspath(os.path.join(backend_root, "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3")),
        "questions": [
            {
                "id": "SF_Q1",
                "topic": "Static vs Queue Execution",
                "question": "Does any producer API directly call send, or is execution strictly mediated through QUEUE and worker?",
                "expected_keywords": ["run_worker_once", "poll_once", "dispatch", "send", "queue"],
                "negative_keywords": ["direct call"]
            },
            {
                "id": "SF_Q3",
                "topic": "Persistent Failure & Token Restoration",
                "question": "Under persistent transport failure, how many send calls are made, what is the final status, and are tokens restored?",
                "expected_keywords": ["3", "send_timeout", "failed", "tokens", "release"],
                "negative_keywords": ["sent"]
            },
            {
                "id": "SF_Q4",
                "topic": "Transient Failure & Tickets",
                "question": "When send fails once with TimeoutError and succeeds on retry, how many calls are made and what ticket is assigned?",
                "expected_keywords": ["2", "ticket", "send_timeout", "sent"],
                "negative_keywords": ["failed"]
            },
            {
                "id": "SF_Q5",
                "topic": "Critical Severity Review",
                "question": "How are critical team incidents handled? Are tokens reserved before approval?",
                "expected_keywords": ["review", "critical", "approve", "queue"],
                "negative_keywords": ["immediate send"]
            },
            {
                "id": "SF_Q7",
                "topic": "Sandbox Muted Incidents",
                "question": "Are incidents from the sandbox service persisted or queued, and what does get_incident raise?",
                "expected_keywords": ["muted", "keyerror"],
                "negative_keywords": ["queued"]
            },
            {
                "id": "SF_Q10",
                "topic": "Regression Detection Tests",
                "question": "Which tests detect when release is omitted from failure dispatch?",
                "expected_keywords": ["test_persistent_failure_releases_budget", "release", "tokens"],
                "negative_keywords": []
            },
            {
                "id": "SF_Q14",
                "topic": "Reopen Limit Enforcement",
                "question": "How many reopens are permitted, and what exception is raised when the limit is exceeded?",
                "expected_keywords": ["reopen", "valueerror", "limit"],
                "negative_keywords": []
            },
            {
                "id": "SF_Q16",
                "topic": "Queue Ownership & Dequeue Sinks",
                "question": "Which functions enqueue items into QUEUE, and which function dequeues items?",
                "expected_keywords": ["open_incident", "approve", "reopen_failed", "poll_once"],
                "negative_keywords": []
            },
            {
                "id": "SF_Q21",
                "topic": "State Store Consistency",
                "question": "What is the difference in persistence between initial no_budget and approval no_budget?",
                "expected_keywords": ["no_budget", "save", "review"],
                "negative_keywords": []
            },
            {
                "id": "SF_Q22",
                "topic": "Crash Consistency Window",
                "question": "Does a crash window exist between popping from QUEUE and completing dispatch?",
                "expected_keywords": ["pop", "dispatch", "loss", "queue"],
                "negative_keywords": []
            }
        ]
    },
    # -------------------------------------------------------------------------
    # Benchmark 3: SentinelShop (Unseen Repository - Anti-Overfitting)
    # -------------------------------------------------------------------------
    {
        "suite": "SentinelShop",
        "repo_id": "repo_sentinelshop_ast_e1e991",
        "repo_path": os.path.abspath(os.path.join(backend_root, "data", "repos", "repo_sentinelshop_ast_e1e991", "SentinelShop")),
        "questions": [
            {
                "id": "SS_Q1",
                "topic": "Multi-Hop Dependency Path",
                "question": "What is the complete call path from checkout to charge_card, including the fraud decision?",
                "expected_keywords": ["checkout", "place_order", "authorize_payment", "charge_card"],
                "negative_keywords": []
            },
            {
                "id": "SS_Q2",
                "topic": "Change Impact & Blast Radius",
                "question": "If authorize_payment changes to reject all payments, which functions and workflow steps are affected?",
                "expected_keywords": ["place_order", "checkout", "reserve_stock", "send_order_confirmation"],
                "negative_keywords": []
            },
            {
                "id": "SS_Q3",
                "topic": "Negative-Path Reasoning",
                "question": "When a high-risk user attempts checkout, does the system reserve stock or send confirmation?",
                "expected_keywords": ["payment", "declined", "none", "reserve_stock"],
                "negative_keywords": ["confirmation sent"]
            },
            {
                "id": "SS_Q4",
                "topic": "Shared Dependency Analysis",
                "question": "Which functions depend directly or indirectly on verify_session?",
                "expected_keywords": ["checkout", "order_history", "verify_session"],
                "negative_keywords": []
            },
            {
                "id": "SS_Q6",
                "topic": "Source Citation & Explainability",
                "question": "Show the source paths and line ranges supporting the connection between checkout and send_order_confirmation.",
                "expected_keywords": ["api.py", "orders.py", "place_order"],
                "negative_keywords": []
            }
        ]
    }
]


def run_benchmarks():
    print("=" * 80)
    print("ASTERION V2: INDEPENDENT BENCHMARK EVALUATION HARNESS")
    print("=" * 80)

    falkor_client.connect()
    assert falkor_client.check_health(), "FalkorDB must be running for live benchmark verification."

    suite_results = []
    total_evaluated = 0
    total_passed = 0

    for bm in BENCHMARKS:
        suite_name = bm["suite"]
        repo_id = bm["repo_id"]
        repo_path = bm["repo_path"]
        questions = bm["questions"]

        print(f"\n[{suite_name.upper()}] Evaluating {len(questions)} architectural queries against {repo_id}")
        investigator = GraphInvestigator(repo_id=repo_id, repo_path=repo_path, workspace_id=f"ws_bm_{suite_name.lower()}")

        q_results = []
        for q in questions:
            q_id = q["id"]
            topic = q["topic"]
            prompt = q["question"]
            expected = q["expected_keywords"]
            negative = q["negative_keywords"]

            t0 = time.perf_counter()
            try:
                answer, report = investigator.investigate_with_report(prompt)
                latency_ms = (time.perf_counter() - t0) * 1000.0
            except Exception as e:
                logger.error(f"Error querying {q_id}: {e}")
                answer = f"ERROR: {e}"
                latency_ms = 0.0
                report = None

            ans_lower = answer.lower()
            matched_kw = [k for k in expected if k.lower() in ans_lower]
            violated_neg = [k for k in negative if k.lower() in ans_lower]

            passed = (len(matched_kw) >= max(1, len(expected) // 2)) and (len(violated_neg) == 0)
            score = round((len(matched_kw) / max(1, len(expected))) * 100.0, 1) if not violated_neg else 0.0

            total_evaluated += 1
            if passed:
                total_passed += 1

            status_str = "PASS" if passed else "FAIL"
            print(f"  [{status_str}] {q_id} ({topic}): score={score}% ({len(matched_kw)}/{len(expected)} kw) | latency={latency_ms:.1f}ms")

            q_results.append({
                "id": q_id,
                "topic": topic,
                "passed": passed,
                "score": score,
                "latency_ms": round(latency_ms, 2),
                "matched_keywords": matched_kw,
                "citations_valid": report.citations_valid if report else 0,
                "paths_valid": report.paths_valid if report else 0,
                "answer_snippet": answer[:180].replace("\n", " ") + "..."
            })

        suite_passed = sum(1 for r in q_results if r["passed"])
        suite_results.append({
            "suite": suite_name,
            "repo_id": repo_id,
            "total_questions": len(questions),
            "passed": suite_passed,
            "pass_rate_pct": round((suite_passed / len(questions)) * 100.0, 1),
            "questions": q_results
        })

    overall_pass_rate = round((total_passed / total_evaluated) * 100.0, 1)
    print("\n" + "=" * 80)
    print(f"BENCHMARK SUMMARY: {total_passed}/{total_evaluated} Questions Passed ({overall_pass_rate}%)")
    for s in suite_results:
        print(f"  - {s['suite']}: {s['passed']}/{s['total_questions']} ({s['pass_rate_pct']}%)")
    print("=" * 80)

    out_file = os.path.join(backend_root, "scripts", "benchmark_evaluation_results.json")
    with open(out_file, "w") as f:
        json.dump({
            "total_evaluated": total_evaluated,
            "total_passed": total_passed,
            "overall_pass_rate": overall_pass_rate,
            "suites": suite_results
        }, f, indent=2)

    print(f"Results saved to: {out_file}")
    return suite_results


if __name__ == "__main__":
    run_benchmarks()
