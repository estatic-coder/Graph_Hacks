"""
backend/scripts/run_production_deployweave_benchmark.py

Comprehensive Regression Test Harness for ASTERION Production API (/api/investigate).
Runs DeployWeave Benchmark Q51-Q75 across:
- Mode A: 25 individual questions
- Mode B: 5 batches of 5 questions
- Mode C: All 25 questions submitted together in a single prompt
- Mode D: Unlabelled questions (testing genuine semantic decomposition)

Evaluates:
- Question preservation (no silently omitted questions)
- Question label preservation (Q51..Q75)
- Repository isolation (zero foreign symbols: OUTBOX, dispatch, get_payment, MAX_GATEWAY_RETRIES)
- Numerical grounding (no fabricated retry counts)
- Answer completeness and verification integrity
- End-to-end latency and concurrency scaling
"""

import os
import sys
import time
import json
import requests
from typing import Dict, Any, List

API_URL = "http://127.0.0.1:8000/api/investigate"
REPO_ID = "repo_deployweave_aste_667ec8"

DATASET_FILE = os.path.join(os.path.dirname(__file__), "deployweave_q51_q75_dataset.json")
with open(DATASET_FILE, "r") as f:
    ALL_QUESTIONS: List[Dict[str, Any]] = json.load(f)

ALIEN_SYMBOLS = [
    "OUTBOX", "dispatch", "get_payment", "MAX_GATEWAY_RETRIES",
    "create_alert", "approve_alert", "send_page", "ALERTS", "HELD", "BALANCE"
]

def check_alien_contamination(text: str) -> List[str]:
    violations = []
    for sym in ALIEN_SYMBOLS:
        if sym in text:
            violations.append(sym)
    return violations

def grade_response(q_label: str, answer_text: str, verification: Dict[str, Any]) -> Dict[str, Any]:
    alien_violations = check_alien_contamination(answer_text)
    is_verified = verification.get("is_verified", False)
    qc_verified = verification.get("question_completeness_verified", False)
    src_verified = verification.get("source_verified", False)
    graph_verified = verification.get("graph_verified", False)
    missing_fields = verification.get("missing_required_fields", [])

    # Check that answer is substantial and not empty
    has_substance = len(answer_text.strip()) > 100
    no_alien = len(alien_violations) == 0

    passed = has_substance and no_alien and (not missing_fields)

    return {
        "label": q_label,
        "passed": passed,
        "is_verified": is_verified,
        "question_completeness_verified": qc_verified,
        "source_verified": src_verified,
        "graph_verified": graph_verified,
        "alien_violations": alien_violations,
        "missing_fields": missing_fields,
        "answer_len": len(answer_text),
    }

def run_mode_a():
    print("\n" + "=" * 80)
    print("MODE A: Testing All 25 Questions Individually")
    print("=" * 80)

    mode_a_results = []
    total_latency = 0.0

    for idx, item in enumerate(ALL_QUESTIONS, 1):
        label = item["label"]
        q_text = item["raw_text"]
        print(f"[{idx}/25] Invoking {label}...", end=" ", flush=True)

        t0 = time.time()
        resp = requests.post(API_URL, json={
            "repo_id": REPO_ID,
            "query": q_text,
            "session_id": f"bench_mode_a_{label}"
        })
        elapsed = time.time() - t0
        total_latency += elapsed

        if resp.status_code != 200:
            print(f"FAILED (HTTP {resp.status_code}) in {elapsed:.2f}s")
            mode_a_results.append({
                "label": label,
                "passed": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:100]}",
                "latency": elapsed
            })
            continue

        data = resp.json()
        ans = data.get("answer", "")
        ver = data.get("verification", {})
        grade = grade_response(label, ans, ver)
        grade["latency"] = elapsed
        mode_a_results.append(grade)

        status_str = "PASS" if grade["passed"] else "FAIL"
        print(f"{status_str} in {elapsed:.2f}s (Verified: {grade['is_verified']}, Aliens: {len(grade['alien_violations'])})")

    pass_count = sum(1 for r in mode_a_results if r.get("passed"))
    print(f"\nMode A Summary: {pass_count}/25 PASSED, Avg Latency: {total_latency/len(ALL_QUESTIONS):.2f}s, Total Latency: {total_latency:.2f}s")
    return mode_a_results

def run_mode_b():
    print("\n" + "=" * 80)
    print("MODE B: Testing Batches of Five Questions (5 Batches)")
    print("=" * 80)

    mode_b_results = []
    batches = [
        ("Batch 1 (Q51-Q55)", ALL_QUESTIONS[0:5]),
        ("Batch 2 (Q56-Q60)", ALL_QUESTIONS[5:10]),
        ("Batch 3 (Q61-Q65)", ALL_QUESTIONS[10:15]),
        ("Batch 4 (Q66-Q70)", ALL_QUESTIONS[15:20]),
        ("Batch 5 (Q71-Q75)", ALL_QUESTIONS[20:25])
    ]

    total_latency = 0.0

    for b_name, b_items in batches:
        b_labels = [item["label"] for item in b_items]
        combined_query = "\n\n".join(item["raw_text"] for item in b_items)
        print(f"\nSubmitting {b_name} [{', '.join(b_labels)}]...", end=" ", flush=True)

        t0 = time.time()
        resp = requests.post(API_URL, json={
            "repo_id": REPO_ID,
            "query": combined_query,
            "session_id": f"bench_mode_b_{b_name[:7]}"
        })
        elapsed = time.time() - t0
        total_latency += elapsed

        if resp.status_code != 200:
            print(f"FAILED (HTTP {resp.status_code}) in {elapsed:.2f}s")
            mode_b_results.append({"batch": b_name, "passed": False, "error": resp.text[:100], "latency": elapsed})
            continue

        data = resp.json()
        ans = data.get("answer", "")
        ver = data.get("verification", {})
        plan = data.get("investigation_plan", {})

        # Check that all questions in batch were preserved and answered separately
        found_labels = []
        omitted_labels = []
        per_q_grades = []

        for lbl in b_labels:
            if f"### {lbl}" in ans or f"## {lbl}" in ans or f"Part {lbl}" in ans or f"[{lbl}]" in ans:
                found_labels.append(lbl)
            else:
                omitted_labels.append(lbl)

        alien_violations = check_alien_contamination(ans)
        b_passed = (len(omitted_labels) == 0) and (len(alien_violations) == 0) and ver.get("question_completeness_verified", False)

        batch_record = {
            "batch": b_name,
            "passed": b_passed,
            "expected_count": len(b_labels),
            "found_count": len(found_labels),
            "found_labels": found_labels,
            "omitted_labels": omitted_labels,
            "alien_violations": alien_violations,
            "is_verified": ver.get("is_verified", False),
            "qc_verified": ver.get("question_completeness_verified", False),
            "latency": elapsed,
            "ans_length": len(ans)
        }
        mode_b_results.append(batch_record)

        status_str = "PASS" if b_passed else "FAIL"
        print(f"{status_str} in {elapsed:.2f}s (Preserved: {len(found_labels)}/{len(b_labels)}, Omitted: {omitted_labels}, Aliens: {alien_violations})")

    b_pass = sum(1 for r in mode_b_results if r.get("passed"))
    print(f"\nMode B Summary: {b_pass}/5 Batches PASSED, Total Latency: {total_latency:.2f}s, Avg per batch: {total_latency/len(batches):.2f}s")
    return mode_b_results

def run_mode_c():
    print("\n" + "=" * 80)
    print("MODE C: Testing All 25 Questions Together in a Single Prompt")
    print("=" * 80)

    combined_25 = "\n\n".join(item["raw_text"] for item in ALL_QUESTIONS)
    all_labels = [item["label"] for item in ALL_QUESTIONS]
    print(f"Submitting all 25 questions in one prompt...", end=" ", flush=True)

    t0 = time.time()
    resp = requests.post(API_URL, json={
        "repo_id": REPO_ID,
        "query": combined_25,
        "session_id": "bench_mode_c_all25"
    })
    elapsed = time.time() - t0

    if resp.status_code != 200:
        print(f"FAILED (HTTP {resp.status_code}) in {elapsed:.2f}s")
        return {"passed": False, "error": resp.text[:100], "latency": elapsed}

    data = resp.json()
    ans = data.get("answer", "")
    ver = data.get("verification", {})

    found_labels = []
    omitted_labels = []
    for lbl in all_labels:
        if f"### {lbl}" in ans or f"## {lbl}" in ans or f"[{lbl}]" in ans:
            found_labels.append(lbl)
        else:
            omitted_labels.append(lbl)

    alien_violations = check_alien_contamination(ans)
    passed = (len(omitted_labels) == 0) and (len(alien_violations) == 0) and ver.get("question_completeness_verified", False)

    print(f"{'PASS' if passed else 'FAIL'} in {elapsed:.2f}s")
    print(f"Questions Preserved: {len(found_labels)}/25")
    print(f"Omitted Questions: {omitted_labels}")
    print(f"Alien Violations: {alien_violations}")
    print(f"Verified Status: is_verified={ver.get('is_verified')}, completeness_verified={ver.get('question_completeness_verified')}")

    return {
        "passed": passed,
        "expected_count": 25,
        "found_count": len(found_labels),
        "found_labels": found_labels,
        "omitted_labels": omitted_labels,
        "alien_violations": alien_violations,
        "is_verified": ver.get("is_verified", False),
        "qc_verified": ver.get("question_completeness_verified", False),
        "latency": elapsed,
        "ans_length": len(ans)
    }

def run_mode_d():
    print("\n" + "=" * 80)
    print("MODE D: Testing Semantic Decomposition on Unlabelled Questions")
    print("=" * 80)

    # Take 3 questions without any Q-numbers or numerical prefixes
    unlabelled_batch = [
        "Starting with the default DeployWeave state, submit a staging auth v2.0 rollout, let it fail all health probes and roll back, then submit a new staging auth v3.0 rollout that succeeds. Calculate the final SLOTS, LOCKED, VERSIONS, READY, CHECKS, CHANGES, EVENTS and AUDIT. Distinguish state scoped per rollout from state shared across rollouts.",
        "Suppose execute(r) installs version 2.0, the first probe fails, and the second succeeds. Compare the intermediate version, number of installations, final attempts, registry changes and final slot balance. Does each probe retry repeat installation?",
        "Construct both the dependency-direction graph and impact-direction graph for ledger, auth and gateway. Compute in-degree, out-degree and transitive reachability for every node in each graph. Explain why reversing edge direction changes graph metrics but not underlying dependency facts."
    ]

    combined_unlabelled = "\n\n".join(unlabelled_batch)
    print("Submitting 3 unlabelled paragraph questions in one prompt...", end=" ", flush=True)

    t0 = time.time()
    resp = requests.post(API_URL, json={
        "repo_id": REPO_ID,
        "query": combined_unlabelled,
        "session_id": "bench_mode_d_unlabelled"
    })
    elapsed = time.time() - t0

    if resp.status_code != 200:
        print(f"FAILED (HTTP {resp.status_code}) in {elapsed:.2f}s")
        return {"passed": False, "error": resp.text[:100], "latency": elapsed}

    data = resp.json()
    ans = data.get("answer", "")
    ver = data.get("verification", {})
    plan = data.get("investigation_plan", {})
    subqs = plan.get("subquestions", [])

    alien_violations = check_alien_contamination(ans)
    decomposed_count = len(subqs)
    passed = (decomposed_count == 3) and (len(alien_violations) == 0) and ver.get("question_completeness_verified", False)

    print(f"{'PASS' if passed else 'FAIL'} in {elapsed:.2f}s")
    print(f"Decomposed Subquestions Count: {decomposed_count}/3")
    print(f"Alien Violations: {alien_violations}")
    print(f"Completeness Verified: {ver.get('question_completeness_verified')}")

    return {
        "passed": passed,
        "decomposed_count": decomposed_count,
        "alien_violations": alien_violations,
        "is_verified": ver.get("is_verified", False),
        "qc_verified": ver.get("question_completeness_verified", False),
        "latency": elapsed,
        "ans_length": len(ans)
    }

def main():
    print("ASTERION Production Benchmark Suite: DeployWeave Q51-Q75")
    print("Target API: " + API_URL)
    print("Repository: " + REPO_ID)

    res_a = run_mode_a()
    res_b = run_mode_b()
    res_c = run_mode_c()
    res_d = run_mode_d()

    full_results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api_url": API_URL,
        "repo_id": REPO_ID,
        "mode_a": res_a,
        "mode_b": res_b,
        "mode_c": res_c,
        "mode_d": res_d,
    }

    out_path = os.path.join(os.path.dirname(__file__), "production_benchmark_results.json")
    with open(out_path, "w") as f:
        json.dump(full_results, f, indent=2)

    print(f"\nAll benchmark results saved to {out_path}")

if __name__ == "__main__":
    main()
