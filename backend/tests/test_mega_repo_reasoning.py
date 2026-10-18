"""
backend/tests/test_mega_repo_reasoning.py - Regression Test Suite for ASTERION V3 Graph Reasoning Pipeline.

Tests the five failed/unverified queries against the ASTERION Mega Repository fixture:
1. Strongly Connected Components (QUESTIONS.md #4) - Tarjan's algorithm & actual components
2. Shortest Directed Call Path from gateway to audit (QUESTIONS.md #5) - Directed BFS & ordered hops
3. Function Inbound Degree Ranking (QUESTIONS.md #8) - Deterministic degree calculation & ranked table
4. Transitive Dependencies of payments (QUESTIONS.md #6) - Imports vs calls distinction
5. Change Impact Analysis of services.inventory.repository (QUESTIONS.md #7) - Reverse reachability & affected services/tests
6. Exact path entity resolution priority over basename matches (services/payments/service.py vs service.py)
7. Separation of citation verification from computational correctness
"""

import os
import pytest
from app.repositories.manager import RepositoryManager
from app.ingestion.pipeline import IngestionPipeline
from app.agent.investigator import GraphInvestigator
from app.agent.execution_pipeline import ExecutionPipeline
from app.agent.intent import IntentClassifier
from app.agent.resolver import EntityResolver
from app.agent.verifier import EvidenceVerifier
from app.agent.contracts import CapabilityType, AnswerRequirementsContract
from app.agent.graph_algorithms import (
    compute_strongly_connected_components,
    compute_directed_shortest_path,
    rank_functions_by_inbound_calls,
    compute_transitive_dependencies,
    compute_change_impact_analysis
)

MEGA_REPO_ID = "repo_asterion_mega_re_2ab955"


@pytest.fixture(scope="module")
def mega_repo():
    """Retrieves and indexes the ASTERION Mega Repository."""
    mgr = RepositoryManager()
    repo = mgr.get_repository(MEGA_REPO_ID)
    assert repo is not None, f"Mega repository '{MEGA_REPO_ID}' must be registered"
    assert os.path.isdir(repo.source_path), f"Mega repository path '{repo.source_path}' must exist"
    
    # Ensure indexed
    pipeline = IngestionPipeline(repo_path=repo.source_path, repo_id=repo.id)
    pipeline.index()
    return repo


class TestMegaRepoReasoning:

    def test_intent_classification_for_graph_algorithms(self, mega_repo):
        """Requirement 1: Verify explicit intent classification for graph algorithm queries."""
        classifier = IntentClassifier(repo_id=mega_repo.id, repo_path=mega_repo.source_path)

        # 1. Strongly Connected Components
        res_scc = classifier.classify("Identify strongly connected components in the service dependency graph.")
        assert res_scc.primary_intent == "STRONGLY_CONNECTED_COMPONENTS" or "STRONGLY_CONNECTED_COMPONENTS" in res_scc.secondary_intents
        assert res_scc.confidence >= 0.90

        # 2. Shortest Path
        res_sp = classifier.classify("Find the shortest directed call path from gateway to audit and show each hop.")
        assert res_sp.primary_intent == "SHORTEST_PATH" or "SHORTEST_PATH" in res_sp.secondary_intents

        # 3. Degree Ranking
        res_deg = classifier.classify("Rank the top 20 functions by inbound CALLS degree.")
        assert res_deg.primary_intent == "DEGREE_RANKING" or "DEGREE_RANKING" in res_deg.secondary_intents

        # 4. Dependency Traversal
        res_dt = classifier.classify("Which services depend transitively on payments? Distinguish imports from calls.")
        assert res_dt.primary_intent == "DEPENDENCY_TRAVERSAL" or "DEPENDENCY_TRAVERSAL" in res_dt.secondary_intents

        # 5. Change Impact Analysis
        res_ci = classifier.classify("If services.inventory.repository changes, which services and tests might be affected?")
        assert res_ci.primary_intent == "CHANGE_IMPACT_ANALYSIS" or "CHANGE_IMPACT_ANALYSIS" in res_ci.secondary_intents

    def test_exact_path_entity_resolution_priority(self, mega_repo):
        """Requirement 2: Exact repo-relative path takes priority over basename; never expands into 24 files."""
        resolver = EntityResolver(repo_id=mega_repo.id, repo_path=mega_repo.source_path)

        query = "Explain the architecture of services/payments/service.py"
        resolved = resolver.resolve_query_entities(query)

        assert len(resolved) > 0
        exact_matches = [
            e for e in resolved
            if e.get("source_path") == "services/payments/service.py" or e.get("source_path", "").endswith("services/payments/service.py")
        ]
        assert len(exact_matches) > 0, "Exact file services/payments/service.py must be resolved"
        assert exact_matches[0]["confidence"] == 1.0

        # Crucial check: must NOT have dumped all other 23 service.py files!
        other_service_files = [
            e for e in resolved
            if "service.py" in e.get("source_path", "") and "services/payments/" not in e.get("source_path", "")
        ]
        assert len(other_service_files) == 0, f"Query for services/payments/service.py was expanded into other services: {[e['source_path'] for e in other_service_files]}"

    def test_scc_tarjan_algorithm(self, mega_repo):
        """Requirement 3 & 5 (Query 4): Tarjan's algorithm returns actual components and cycle structure."""
        scc_result = compute_strongly_connected_components(mega_repo.id, mega_repo.source_path)

        assert scc_result["algorithm"] == "Tarjan's strongly connected components"
        assert scc_result["total_services"] == 24
        assert scc_result["total_components"] >= 1
        assert "all_components" in scc_result
        assert isinstance(scc_result["all_components"], list)

        # Test through ExecutionPipeline
        exec_pipe = ExecutionPipeline(repo_id=mega_repo.id, repo_path=mega_repo.source_path)
        q = "Identify strongly connected components in the service dependency graph."
        res = exec_pipe.execute_query(q)
        ans = res["synthesized_answer"]

        assert "Tarjan" in ans
        assert "strongly connected components" in ans.lower()
        assert "24" in ans or "components" in ans.lower()

    def test_shortest_path_directed_bfs(self, mega_repo):
        """Requirement 3 & 5 (Query 5): Directed BFS unweighted shortest path with ordered nodes and edges."""
        sp_result = compute_directed_shortest_path(mega_repo.id, mega_repo.source_path, "gateway", "audit")

        assert sp_result["source_service"] == "gateway"
        assert sp_result["target_service"] == "audit"
        assert sp_result["path_found"] is True
        assert sp_result["total_hops"] >= 1
        assert len(sp_result["ordered_hops"]) == sp_result["total_hops"] + 1

        # Check hops structure
        for hop in sp_result["ordered_hops"]:
            assert "hop_index" in hop
            assert "symbol_name" in hop
            assert "source_path" in hop
            assert "line" in hop
            assert "service" in hop

        # Test through ExecutionPipeline
        exec_pipe = ExecutionPipeline(repo_id=mega_repo.id, repo_path=mega_repo.source_path)
        q = "Find the shortest directed call path from gateway to audit and show each hop."
        res = exec_pipe.execute_query(q)
        ans = res["synthesized_answer"]

        assert "Hop 0" in ans
        assert "Hop 1" in ans
        assert "gateway" in ans
        assert "audit" in ans

    def test_degree_ranking_metric(self, mega_repo):
        """Requirement 3 & 5 (Query 8): In-degree calculations rank top 20 functions with numeric metrics."""
        rank_result = rank_functions_by_inbound_calls(mega_repo.id, mega_repo.source_path, top_k=20)

        rankings = rank_result["rankings"]
        assert len(rankings) == 20
        # Verify strict descending sort
        for i in range(len(rankings) - 1):
            assert rankings[i]["inbound_calls"] >= rankings[i + 1]["inbound_calls"]

        # Check top item
        top_func = rankings[0]
        assert top_func["rank"] == 1
        assert "inbound_calls" in top_func
        assert isinstance(top_func["inbound_calls"], int)
        assert top_func["inbound_calls"] > 0
        assert "source_path" in top_func
        assert "citation" in top_func

        # Test through ExecutionPipeline
        exec_pipe = ExecutionPipeline(repo_id=mega_repo.id, repo_path=mega_repo.source_path)
        q = "Rank the top 20 functions by inbound CALLS degree."
        res = exec_pipe.execute_query(q)
        ans = res["synthesized_answer"]

        assert "| Rank |" in ans
        assert "| #1 |" in ans
        assert "| #20 |" in ans
        assert str(top_func["inbound_calls"]) in ans

    def test_transitive_dependency_traversal(self, mega_repo):
        """Requirement 3 & 5 (Query 6): Transitive dependency traversal distinguishing imports from calls."""
        dep_result = compute_transitive_dependencies(mega_repo.id, mega_repo.source_path, "payments")

        downstream = dep_result["downstream"]
        upstream = dep_result["upstream_dependent_services"]

        assert "direct_imports" in downstream
        assert "direct_calls" in downstream
        assert "transitive_imports" in downstream
        assert "transitive_calls" in downstream

        # Direct dependencies of payments
        assert "billing" in downstream["direct_imports"]
        assert "recommendations" in downstream["direct_imports"]
        assert "billing" in downstream["direct_calls"]
        assert "recommendations" in downstream["direct_calls"]

        # Services directly calling/importing payments
        assert "inventory" in upstream["direct_importers"] or "orders" in upstream["direct_importers"]

        # Test through ExecutionPipeline
        exec_pipe = ExecutionPipeline(repo_id=mega_repo.id, repo_path=mega_repo.source_path)
        q = "Which services depend transitively on payments? Distinguish imports from calls."
        res = exec_pipe.execute_query(q)
        ans = res["synthesized_answer"]

        assert "Direct Imports" in ans
        assert "Direct Calls" in ans
        assert "Transitive Imports" in ans
        assert "billing" in ans
        assert "recommendations" in ans

    def test_change_impact_analysis(self, mega_repo):
        """Requirement 4 & 5 (Query 7): Change-impact traverses reverse dependencies with supporting paths."""
        impact_result = compute_change_impact_analysis(
            mega_repo.id, mega_repo.source_path, "services.inventory.repository"
        )

        assert impact_result["target_module"] == "services.inventory.repository"
        assert "inventory" in impact_result["direct_affected_services"]
        assert len(impact_result["affected_services"]) >= 1
        assert len(impact_result["affected_tests"]) >= 1
        assert len(impact_result["supporting_dependency_paths"]) >= 1

        # Test through ExecutionPipeline
        exec_pipe = ExecutionPipeline(repo_id=mega_repo.id, repo_path=mega_repo.source_path)
        q = "If services.inventory.repository changes, which services and tests might be affected?"
        res = exec_pipe.execute_query(q)
        ans = res["synthesized_answer"]

        assert "Reverse dependency" in ans or "upstream" in ans.lower()
        assert "Affected Services" in ans
        assert "Affected Test" in ans
        assert "inventory" in ans
        assert "Supporting Dependency Paths" in ans

    def test_separation_of_citations_from_computational_correctness(self, mega_repo):
        """Requirement 6: Never label an answer 'VERIFIED' merely because citations point to real symbols."""
        verifier = EvidenceVerifier(repo_id=mega_repo.id, repo_path=mega_repo.source_path)

        # Case A: Answer has valid source citations on disk, but computational requirements are completely missing
        hallucinated_answer = (
            "## Summary\n"
            "The functions are defined in `services/payments/service.py:18-25`.\n"
            "File: `services/payments/service.py` (Lines 18–25)\n"
            "This answer has citations but provides zero algorithm computation, zero ranked tables, zero hops, zero SCCs."
        )

        q = "Rank the top 20 functions by inbound CALLS degree."
        pipeline_data = {
            "question": q,
            "execution_results": {"capability_results": {}},
            "source_evidence": [{"file_path": "services/payments/service.py", "start_line": 18, "end_line": 25}]
        }

        report = verifier.verify(hallucinated_answer, pipeline_data=pipeline_data)

        # Verification must FAIL because computational correctness was not achieved!
        assert report.computational_correctness_verified is False
        assert report.is_verified is False
        assert "COMPUTATIONAL_CORRECTNESS_UNVERIFIED" in report.summary or "INCOMPLETE_RESULT" in report.summary
        assert "VERIFIED: Citation Grounding: Verified" not in report.summary

        # Case B: Answer has both valid citations AND real computational results
        exec_pipe = ExecutionPipeline(repo_id=mega_repo.id, repo_path=mega_repo.source_path)
        real_res = exec_pipe.execute_query(q)
        valid_answer = real_res["synthesized_answer"]
        real_pipeline_data = {
            "question": q,
            "execution_results": real_res,
            "source_evidence": [{"file_path": "services/analytics/service.py", "start_line": 18, "end_line": 25}]
        }

        valid_report = verifier.verify(valid_answer, pipeline_data=real_pipeline_data)
        assert valid_report.computational_correctness_verified is True
        assert valid_report.is_verified is True

    def test_concise_entity_resolution_ui_formatting(self, mega_repo):
        """Requirement 8: Prevent enormous entity dumps from overwhelming UI; use expandable <details>."""
        investigator = GraphInvestigator(repo_id=mega_repo.id, repo_path=mega_repo.source_path, mock_mode=True)

        # Simulate 15 resolved entities
        mock_entities = [
            {"name": f"func_{i}", "type": "Function", "source_path": f"services/s{i}/service.py", "confidence": 0.9}
            for i in range(15)
        ]
        pdata = {
            "question": "What is the architecture?",
            "intent": "GENERAL_QUERY",
            "resolved_entities": mock_entities,
            "graph_paths": [],
            "source_evidence": []
        }

        response = investigator._synthesize_grounded_response(pdata)

        # Verify concise format with <details> and <summary>
        assert "<details>" in response
        assert "<summary>View all 15 resolved entities" in response
        assert "</details>" in response
        assert "Resolved Entities (15)" in response
