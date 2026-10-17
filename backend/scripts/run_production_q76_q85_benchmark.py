"""
backend/scripts/run_production_q76_q85_benchmark.py

Regression Protection Benchmark Runner for DeployWeave Q76-Q85.
Executes:
1. Q79-Q85 individually through the production API.
2. Q76-Q85 as a unified batch through the production API.
Records:
- Question coverage
- Answer correctness
- Selected capabilities
- Executed tools
- Relevant evidence (citations and paths)
- Missing fields
- Verification status
- Latency
"""

import os
import sys
import time
import json
import requests
from typing import Dict, Any, List

API_URL = "http://127.0.0.1:8000/api/investigate"
REPO_ID = "repo_deployweave_aste_667ec8"

QUESTIONS_Q76_Q85 = [
    {
        "label": "Q76",
        "question": "Find the direct and indirect impact paths from ledger to gateway."
    },
    {
        "label": "Q77",
        "question": "Simulate a staging auth v2.0 rollout with three failed health probes."
    },
    {
        "label": "Q78",
        "question": "Simulate staging gateway submission with ledger missing."
    },
    {
        "label": "Q79",
        "question": "Starting with the default DeployWeave state, submit a staging auth v2.0 rollout, let it fail all health probes and roll back, then submit a new staging auth v3.0 rollout that succeeds. Calculate the final SLOTS, LOCKED, VERSIONS, READY, CHECKS, CHANGES, EVENTS and AUDIT. Distinguish state scoped per rollout from state shared across rollouts."
    },
    {
        "label": "Q80",
        "question": "Two staging auth rollouts, r1 and r2, are submitted sequentially when SLOTS['auth'] is initially 2. Both are queued. r1 succeeds, but r2 fails all health probes. Trace execution in FIFO order and calculate the final available slots, version, lock state, audit history and registry changes. Explain why r2's rollback target matters."
    },
    {
        "label": "Q81",
        "question": "Suppose a production gateway rollout is submitted while the ledger version is absent. Later the ledger version is restored, but gateway remains blocked. Does calling approve_rollout() now work? Derive the answer from the persisted status and approval guard. Identify the minimum workflow change needed for recovery."
    },
    {
        "label": "Q82",
        "question": "Suppose execute(r) installs version 2.0, the first probe fails, and the second succeeds. Compare the intermediate version, number of installations, final attempts, registry changes and final slot balance. Does each probe retry repeat installation?"
    },
    {
        "label": "Q83",
        "question": "A failed rollout has ROLLBACK_COUNTS[k] = 1 and MAX_ROLLBACKS = 1. An operator manually restores capacity and calls retry_rollout(k). Can capacity availability override the retry limit? Show the first guard that stops execution."
    },
    {
        "label": "Q84",
        "question": "Construct both the dependency-direction graph and impact-direction graph for ledger, auth and gateway. Compute in-degree, out-degree and transitive reachability for every node in each graph. Explain why reversing edge direction changes graph metrics but not underlying dependency facts."
    },
    {
        "label": "Q85",
        "question": "Determine whether DeployWeave can guarantee exactly-once installation when workers run concurrently. Have the agent produce a formal claim, locate supporting or contradicting evidence, design a concurrency test, execute it if authorized, and save the resulting conclusion with an explicit verification level."
    }
]


def execute_single_query(item: Dict[str, str]) -> Dict[str, Any]:
    label = item["label"]
    q_text = item["question"]
    formatted_query = f"{label}. {q_text}"

    t0 = time.time()
    try:
        resp = requests.post(API_URL, json={
            "repo_id": REPO_ID,
            "query": formatted_query,
            "session_id": f"bench_{label}"
        }, timeout=45)
        elapsed = time.time() - t0
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "label": label,
            "question": q_text,
            "status_code": 500,
            "error": str(e),
            "latency_s": elapsed,
            "passed": False
        }

    if resp.status_code != 200:
        return {
            "label": label,
            "question": q_text,
            "status_code": resp.status_code,
            "error": resp.text[:200],
            "latency_s": elapsed,
            "passed": False
        }

    data = resp.json()
    ver = data.get("verification", {})
    plan = data.get("investigation_plan", {})
    steps = plan.get("steps", [])
    trace = data.get("trace", {})
    answer = data.get("answer", "")

    # Selected capabilities & executed tools
    selected_capabilities = [s.get("capability") for s in steps]
    executed_tools = [s.get("tool_called") or s.get("capability") for s in steps]

    is_verified = ver.get("is_verified", False)
    citations_valid = ver.get("citations_valid", 0)
    paths_valid = ver.get("paths_valid", 0)
    missing_fields = ver.get("missing_required_fields", [])
    has_substance = len(answer.strip()) > 80 and "Execution completed successfully" not in answer[:100]

    passed = is_verified and has_substance and (len(missing_fields) == 0)

    return {
        "label": label,
        "question": q_text,
        "status_code": 200,
        "passed": passed,
        "is_verified": is_verified,
        "selected_capabilities": selected_capabilities,
        "executed_tools": executed_tools,
        "citations_valid": citations_valid,
        "paths_valid": paths_valid,
        "missing_fields": missing_fields,
        "verification_summary": ver.get("summary", ""),
        "latency_s": round(elapsed, 3),
        "answer_length": len(answer),
        "trace_stages": [s.get("stage_name") for s in trace.get("stages", [])] if trace else []
    }


def run_benchmark():
    print("=" * 80)
    print("ASTERION Regression Protection Benchmark: DeployWeave Q76-Q85")
    print("=" * 80)

    # 1. Execute Q79-Q85 individually
    print("\n--- PHASE 1: Executing Q79-Q85 Individually ---")
    phase1_results = []
    for item in QUESTIONS_Q76_Q85[3:]:
        lbl = item["label"]
        print(f"Executing {lbl}...", end=" ", flush=True)
        res = execute_single_query(item)
        phase1_results.append(res)
        status = "PASS" if res.get("passed") else "FAIL"
        print(f"{status} in {res.get('latency_s')}s | Cap: {res.get('selected_capabilities')} | Citations: {res.get('citations_valid')} | Paths: {res.get('paths_valid')} | Missing: {res.get('missing_fields')}")

    # Also run Q76-Q78 individually for full coverage table
    print("\n--- PHASE 2: Executing Q76-Q78 Individually ---")
    q76_q78_results = []
    for item in QUESTIONS_Q76_Q85[:3]:
        lbl = item["label"]
        print(f"Executing {lbl}...", end=" ", flush=True)
        res = execute_single_query(item)
        q76_q78_results.append(res)
        status = "PASS" if res.get("passed") else "FAIL"
        print(f"{status} in {res.get('latency_s')}s | Cap: {res.get('selected_capabilities')} | Citations: {res.get('citations_valid')} | Paths: {res.get('paths_valid')} | Missing: {res.get('missing_fields')}")

    # 2. Execute Q76-Q85 as a unified batch
    print("\n--- PHASE 3: Executing Q76-Q85 as a Unified Batch Prompt ---")
    batch_prompt = "\n\n".join(f"{item['label']}. {item['question']}" for item in QUESTIONS_Q76_Q85)
    t0 = time.time()
    batch_resp = requests.post(API_URL, json={
        "repo_id": REPO_ID,
        "query": batch_prompt,
        "session_id": "bench_batch_q76_q85"
    }, timeout=120)
    batch_elapsed = time.time() - t0

    if batch_resp.status_code == 200:
        bdata = batch_resp.json()
        b_ans = bdata.get("answer", "")
        b_ver = bdata.get("verification", {})
        b_trace = bdata.get("trace", {})

        # Count preserved labels in answer
        preserved_labels = []
        missing_labels = []
        for item in QUESTIONS_Q76_Q85:
            lbl = item["label"]
            if f"### {lbl}" in b_ans or f"## {lbl}" in b_ans or f"[{lbl}]" in b_ans:
                preserved_labels.append(lbl)
            else:
                missing_labels.append(lbl)

        batch_result = {
            "status_code": 200,
            "total_questions": len(QUESTIONS_Q76_Q85),
            "preserved_count": len(preserved_labels),
            "preserved_labels": preserved_labels,
            "missing_labels": missing_labels,
            "coverage_pct": (len(preserved_labels) / len(QUESTIONS_Q76_Q85)) * 100.0,
            "is_verified": b_ver.get("is_verified", False),
            "completeness_verified": b_ver.get("question_completeness_verified", False),
            "missing_required_fields": b_ver.get("missing_required_fields", []),
            "latency_s": round(batch_elapsed, 3),
            "answer_length": len(b_ans)
        }
        print(f"Batch Result: Coverage: {len(preserved_labels)}/10 ({batch_result['coverage_pct']}%) in {batch_result['latency_s']}s")
        print(f"Preserved: {preserved_labels}")
        print(f"Missing: {missing_labels}")
        print(f"Verification: is_verified={batch_result['is_verified']}, missing={batch_result['missing_required_fields']}")
    else:
        batch_result = {
            "status_code": batch_resp.status_code,
            "error": batch_resp.text[:300],
            "latency_s": round(batch_elapsed, 3),
            "passed": False
        }
        print(f"Batch Failed with HTTP {batch_resp.status_code}")

    # Combine report
    full_report = {
        "benchmark": "ASTERION_Q76_Q85_REGRESSION_PROTECTION",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "q76_q78_individual": q76_q78_results,
        "q79_q85_individual": phase1_results,
        "q76_q85_batch": batch_result
    }

    out_file = os.path.join(os.path.dirname(__file__), "production_q76_q85_results.json")
    with open(out_file, "w") as f:
        json.dump(full_report, f, indent=2)

    print(f"\nSaved full benchmark results to {out_file}")
    return full_report


if __name__ == "__main__":
    run_benchmark()
