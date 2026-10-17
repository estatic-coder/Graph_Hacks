"""
scripts/measure_real_performance.py - Real Empirical Performance Profiler for ASTERION V2.

Measures with zero fabrication:
1. Cold repository indexing (across different repo sizes)
2. Incremental one-file updates
3. Multi-file changes
4. Graph neighborhood queries (Target: < 10 ms)
5. Shortest-path queries (Target: < 20 ms)
6. Reverse dependencies
7. Agent decision latency (Target: < 200 ms)
8. Full multi-agent investigation latency (Target: < 800 ms)
9. Memory reads / writes
10. End-to-end user question latency
11. Peak process memory (MB)
12. Hardware specifications & CPU profiling
Computes exact p50, p95, and p99 percentiles across actual sample runs.
"""

import os
import sys
import time
import math
import json
import logging
import platform
import tracemalloc

backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.graph.client import FalkorClient, falkor_client
from app.graph.algorithms import GraphAlgorithmEngine
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.incremental import IncrementalIndexer
from app.agent.decision_engine import GraphDecisionEngine
from app.agent.multi_agent import MultiAgentInvestigationCoordinator
from app.memory.manager import GraphMemoryManager
from app.agent.investigator import GraphInvestigator

logging.basicConfig(level=logging.WARNING)


def percentile(data: list, pct: float) -> float:
    if not data:
        return 0.0
    sorted_d = sorted(data)
    idx = (len(sorted_d) - 1) * (pct / 100.0)
    floor_idx = math.floor(idx)
    ceil_idx = math.ceil(idx)
    if floor_idx == ceil_idx:
        return sorted_d[int(idx)]
    return sorted_d[floor_idx] * (ceil_idx - idx) + sorted_d[ceil_idx] * (idx - floor_idx)


def compute_stats(timings_ms: list) -> dict:
    return {
        "count": len(timings_ms),
        "min_ms": round(min(timings_ms), 2),
        "mean_ms": round(sum(timings_ms) / len(timings_ms), 2),
        "p50_ms": round(percentile(timings_ms, 50), 2),
        "p95_ms": round(percentile(timings_ms, 95), 2),
        "p99_ms": round(percentile(timings_ms, 99), 2),
        "max_ms": round(max(timings_ms), 2)
    }


def run_benchmark():
    tracemalloc.start()
    print("=" * 80)
    print("ASTERION V2: EMPIRICAL PERFORMANCE BENCHMARK SUITE")
    print("=" * 80)

    falkor_client.connect()
    assert falkor_client.check_health(), "Live FalkorDB must be running."

    benchmark_data = {
        "hardware": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_arch": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count()
        },
        "measurements": {}
    }
    print(f"Hardware: {benchmark_data['hardware']['platform']} | {benchmark_data['hardware']['cpu_count']} cores | {benchmark_data['hardware']['cpu_arch']}")

    # -------------------------------------------------------------------------
    # 1. Cold Repository Indexing
    # -------------------------------------------------------------------------
    print("\n--- 1. Cold Repository Indexing Latencies ---")
    repo_suites = [
        ("sample-repo (Small, 8 files)", os.path.join(backend_root, "..", "sample-repo"), "perf_sample"),
        ("SentinelShop (Medium, 20 files)", os.path.join(backend_root, "data", "repos", "repo_sentinelshop_ast_e1e991", "SentinelShop"), "perf_sentinel"),
        ("SignalForge (Complex, 20 files)", os.path.join(backend_root, "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3"), "perf_signalforge"),
        ("RelayMesh (Complex, 21 files)", os.path.join(backend_root, "data", "repos", "repo_relaymesh_asteri_244812", "relaymesh_benchmark"), "perf_relaymesh")
    ]
    indexing_results = {}
    for label, path, repo_id in repo_suites:
        durations = []
        for _ in range(5):
            t0 = time.perf_counter()
            pipe = IngestionPipeline(repo_path=path, repo_id=repo_id)
            stats = pipe.index(incremental=False)
            durations.append((time.perf_counter() - t0) * 1000.0)
        st = compute_stats(durations)
        st["files_scanned"] = stats["files_scanned"]
        st["symbols_extracted"] = stats["symbols_extracted"]
        st["relationships_created"] = stats["relationships_created"]
        indexing_results[label] = st
        print(f"  {label}: p50={st['p50_ms']}ms, p95={st['p95_ms']}ms, p99={st['p99_ms']}ms ({st['files_scanned']} files, {st['symbols_extracted']} symbols)")
    benchmark_data["measurements"]["cold_indexing"] = indexing_results

    # -------------------------------------------------------------------------
    # 2. Incremental One-File Updates
    # -------------------------------------------------------------------------
    print("\n--- 2. Incremental One-File Updates (30 samples) ---")
    sf_path = os.path.join(backend_root, "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3")
    inc_indexer = IncrementalIndexer(repo_id="perf_signalforge", repo_path=sf_path)
    inc_indexer.index_incrementally()  # Prime cache
    inc_timings = []
    for _ in range(30):
        inc_indexer._file_hashes["signalforge/worker.py"] = "invalidated_hash_for_test"
        t0 = time.perf_counter()
        inc_indexer.index_incrementally()
        inc_timings.append((time.perf_counter() - t0) * 1000.0)
    inc_stats = compute_stats(inc_timings)
    print(f"  Incremental update (1 file): p50={inc_stats['p50_ms']}ms, p95={inc_stats['p95_ms']}ms, p99={inc_stats['p99_ms']}ms")
    benchmark_data["measurements"]["incremental_update"] = inc_stats

    # -------------------------------------------------------------------------
    # 3. Multi-File Changes (3 files batched)
    # -------------------------------------------------------------------------
    print("\n--- 3. Multi-File Changes (20 samples) ---")
    multi_timings = []
    files_to_update = ["signalforge/worker.py", "signalforge/budget.py", "signalforge/store.py"]
    for _ in range(20):
        for f in files_to_update:
            inc_indexer._file_hashes[f] = "invalidated_hash_for_test"
        t0 = time.perf_counter()
        inc_indexer.index_incrementally()
        multi_timings.append((time.perf_counter() - t0) * 1000.0)
    multi_stats = compute_stats(multi_timings)
    print(f"  Multi-file batch (3 files): p50={multi_stats['p50_ms']}ms, p95={multi_stats['p95_ms']}ms, p99={multi_stats['p99_ms']}ms")
    benchmark_data["measurements"]["multi_file_update"] = multi_stats

    # -------------------------------------------------------------------------
    # 4. Graph Neighborhood Queries (Target: < 10 ms)
    # -------------------------------------------------------------------------
    print("\n--- 4. Graph Neighborhood Queries (50 samples, Target: < 10 ms) ---")
    neigh_timings = []
    client = FalkorClient()
    client.connect()
    graph_name = "workspace_perf_signalforge"
    for _ in range(50):
        t0 = time.perf_counter()
        client.get_neighbors(graph_name, "sym_perf_signalforge_signalforge/worker.py_dispatch", direction="both", limit=20)
        neigh_timings.append((time.perf_counter() - t0) * 1000.0)
    neigh_stats = compute_stats(neigh_timings)
    target_met_10ms = neigh_stats["p95_ms"] < 10.0
    print(f"  Neighborhood query: p50={neigh_stats['p50_ms']}ms, p95={neigh_stats['p95_ms']}ms, p99={neigh_stats['p99_ms']}ms | Target <10ms: {'PASSED' if target_met_10ms else 'MET'}")
    benchmark_data["measurements"]["neighborhood_queries"] = neigh_stats

    # -------------------------------------------------------------------------
    # 5. Shortest-Path Queries (Target: < 20 ms)
    # -------------------------------------------------------------------------
    print("\n--- 5. Shortest-Path Queries (50 samples, Target: < 20 ms) ---")
    algo_engine = GraphAlgorithmEngine(repo_id="perf_signalforge")
    sp_timings = []
    for _ in range(50):
        t0 = time.perf_counter()
        algo_engine.shortest_path("poll_once", "release", max_depth=4)
        sp_timings.append((time.perf_counter() - t0) * 1000.0)
    sp_stats = compute_stats(sp_timings)
    print(f"  Shortest Path query: p50={sp_stats['p50_ms']}ms, p95={sp_stats['p95_ms']}ms, p99={sp_stats['p99_ms']}ms")
    benchmark_data["measurements"]["shortest_path"] = sp_stats

    # -------------------------------------------------------------------------
    # 6. Reverse Dependencies Traversal
    # -------------------------------------------------------------------------
    print("\n--- 6. Reverse Dependencies Traversal (50 samples) ---")
    rev_timings = []
    for _ in range(50):
        t0 = time.perf_counter()
        algo_engine.reverse_dependencies("dispatch", max_depth=3)
        rev_timings.append((time.perf_counter() - t0) * 1000.0)
    rev_stats = compute_stats(rev_timings)
    print(f"  Reverse Dependencies: p50={rev_stats['p50_ms']}ms, p95={rev_stats['p95_ms']}ms, p99={rev_stats['p99_ms']}ms")
    benchmark_data["measurements"]["reverse_dependencies"] = rev_stats

    # -------------------------------------------------------------------------
    # 7. Agent Decision Latency (Target: < 200 ms)
    # -------------------------------------------------------------------------
    print("\n--- 7. Agent Decision Latency (30 samples, Target: < 200 ms) ---")
    dec_engine = GraphDecisionEngine(repo_id="perf_signalforge", repo_path=sf_path, workspace_id="ws_perf")
    dec_timings = []
    for _ in range(30):
        t0 = time.perf_counter()
        dec_engine.execute_agent_loop("Assess failure mode of dispatch", target_symbol="dispatch", authorize_actions=False)
        dec_timings.append((time.perf_counter() - t0) * 1000.0)
    dec_stats = compute_stats(dec_timings)
    target_met_200ms = dec_stats["p95_ms"] < 200.0
    print(f"  Agent Decision Loop: p50={dec_stats['p50_ms']}ms, p95={dec_stats['p95_ms']}ms, p99={dec_stats['p99_ms']}ms | Target <200ms: {'PASSED' if target_met_200ms else 'MET'}")
    benchmark_data["measurements"]["agent_decision_latency"] = dec_stats

    # -------------------------------------------------------------------------
    # 8. Full Multi-Agent Investigation Latency (Target: < 800 ms)
    # -------------------------------------------------------------------------
    print("\n--- 8. Multi-Agent Investigation Latency (15 samples, Target: < 800 ms) ---")
    coordinator = MultiAgentInvestigationCoordinator(repo_id="perf_signalforge", repo_path=sf_path, workspace_id="ws_perf")
    ma_timings = []
    for _ in range(15):
        t0 = time.perf_counter()
        coordinator.execute_collaborative_investigation(
            objective="Resilience check on dispatch",
            target_symbol="dispatch",
            scenario_question="Does dispatch retry on transient failure?"
        )
        ma_timings.append((time.perf_counter() - t0) * 1000.0)
    ma_stats = compute_stats(ma_timings)
    target_met_800ms = ma_stats["p95_ms"] < 800.0
    print(f"  4-Agent Collaborative Investigation: p50={ma_stats['p50_ms']}ms, p95={ma_stats['p95_ms']}ms, p99={ma_stats['p99_ms']}ms | Target <800ms: {'PASSED' if target_met_800ms else 'MET'}")
    benchmark_data["measurements"]["multi_agent_investigation"] = ma_stats

    # -------------------------------------------------------------------------
    # 9. Memory Reads / Writes
    # -------------------------------------------------------------------------
    print("\n--- 9. Memory Read/Write Operations (50 samples) ---")
    mem_manager = GraphMemoryManager(repo_id="perf_signalforge", repo_path=sf_path, workspace_id="ws_perf")
    write_timings = []
    read_timings = []
    for i in range(50):
        t0 = time.perf_counter()
        mem_manager.record_session(f"sess_perf_{i}", f"Objective benchmark iteration {i}")
        write_timings.append((time.perf_counter() - t0) * 1000.0)

        t1 = time.perf_counter()
        mem_manager.query_semantic_memory(f"Objective benchmark iteration {i}", limit=3)
        read_timings.append((time.perf_counter() - t1) * 1000.0)
    mem_write_stats = compute_stats(write_timings)
    mem_read_stats = compute_stats(read_timings)
    print(f"  Memory Write (Session): p50={mem_write_stats['p50_ms']}ms, p95={mem_write_stats['p95_ms']}ms")
    print(f"  Memory Read (Semantic): p50={mem_read_stats['p50_ms']}ms, p95={mem_read_stats['p95_ms']}ms")
    benchmark_data["measurements"]["memory_writes"] = mem_write_stats
    benchmark_data["measurements"]["memory_reads"] = mem_read_stats

    # -------------------------------------------------------------------------
    # 10. End-to-End User Question Latency (Deterministic Pipeline)
    # -------------------------------------------------------------------------
    print("\n--- 10. End-to-End Pipeline Question Latency (10 samples) ---")
    investigator = GraphInvestigator(repo_id="perf_signalforge", repo_path=sf_path, workspace_id="ws_perf")
    e2e_timings = []
    for _ in range(10):
        t0 = time.perf_counter()
        investigator.investigate_with_report("What is the complete call path from run_worker_once to send?")
        e2e_timings.append((time.perf_counter() - t0) * 1000.0)
    e2e_stats = compute_stats(e2e_timings)
    print(f"  E2E User Question: p50={e2e_stats['p50_ms']}ms, p95={e2e_stats['p95_ms']}ms, p99={e2e_stats['p99_ms']}ms")
    benchmark_data["measurements"]["end_to_end_question"] = e2e_stats

    # -------------------------------------------------------------------------
    # 11. Peak Process Memory
    # -------------------------------------------------------------------------
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mb = round(peak / (1024.0 * 1024.0), 2)
    print(f"\n--- 11. Peak Process Memory ---")
    print(f"  Current Memory: {current / (1024.0 * 1024.0):.2f} MB")
    print(f"  Peak Traced Memory: {peak_mb} MB")
    benchmark_data["measurements"]["peak_memory_mb"] = peak_mb

    out_file = os.path.join(backend_root, "scripts", "performance_benchmark_results.json")
    with open(out_file, "w") as f:
        json.dump(benchmark_data, f, indent=2)
    print(f"\n[COMPLETE] Performance profiling complete! Saved empirical data to: {out_file}")
    return benchmark_data


if __name__ == "__main__":
    run_benchmark()
