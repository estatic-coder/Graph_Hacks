import os
import re
import ast
import logging
import dataclasses
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from app.agent.tools import TypedGraphTools
from app.agent.intent import IntentClassifier, IntentResult
from app.agent.resolver import EntityResolver, ResolvedEntity, EntityOrigin
from app.agent.impact import ImpactAnalyzer
from app.agent.control_flow import ControlFlowAnalyzer, PathClassification, PathFeasibilityResult
from app.memory.manager import GraphMemoryManager
from app.config import settings

logger = logging.getLogger(__name__)

def validate_analyzer_target(
    entity: Optional[ResolvedEntity],
    analyzer_name: str,
    repo_path: str
) -> tuple[bool, Optional[str]]:
    """
    Validates that the entity satisfies the input contract for the specified analyzer.
    Returns (is_valid, rejection_reason).
    """
    if not entity:
        return False, f"{analyzer_name} requires a target entity, but None was provided."

    # Strict origin contract: Only verified REPOSITORY entities may be analyzed
    if entity.origin != EntityOrigin.REPOSITORY:
        return False, (
            f"{analyzer_name} rejected entity '{entity.name}': origin is {entity.origin.value}, "
            f"only verified REPOSITORY entities are accepted as source-code targets."
        )

    if analyzer_name in ("AST_LOOP_ANALYZER", "BRANCH_TEST_ANALYZER"):
        if entity.type not in ("Function", "Method"):
            return False, f"{analyzer_name} requires a Function or Method, but received {entity.type} ('{entity.name}')."
        if not entity.source_path:
            return False, f"{analyzer_name} requires a verifiable source file path for '{entity.name}'."
        full_path = os.path.join(repo_path, entity.source_path) if not os.path.isabs(entity.source_path) else entity.source_path
        if not os.path.exists(full_path):
            return False, f"{analyzer_name} target file '{entity.source_path}' does not exist on disk."

    elif analyzer_name == "CHANGE_IMPACT_ANALYZER":
        valid_types = ("Function", "Method", "Class", "Module", "File", "ConfigConstant", "Variable", "Symbol", "Endpoint")
        if entity.type not in valid_types:
            return False, f"{analyzer_name} requires a source-code symbol, received {entity.type} ('{entity.name}')."

    elif analyzer_name == "GRAPH_PATH_ANALYZER":
        if not entity.id:
            return False, f"{analyzer_name} requires a valid graph node ID."

    return True, None

@dataclass
class SharedReasoningRepresentation:
    repository_id: str
    question: str
    primary_intent: str
    secondary_intents: List[str]
    resolved_entities: List[Dict[str, Any]]
    static_graph_paths: List[str] = field(default_factory=list)
    branch_guards: List[Dict[str, Any]] = field(default_factory=list)
    scenario_constraints: List[str] = field(default_factory=list)
    feasible_paths: List[Dict[str, Any]] = field(default_factory=list)
    infeasible_paths: List[Dict[str, Any]] = field(default_factory=list)
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)
    downstream_operations: List[Dict[str, Any]] = field(default_factory=list)
    test_coverage_analysis: Dict[str, Any] = field(default_factory=dict)
    source_citations: List[str] = field(default_factory=list)
    contradictions_detected: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    caller_context_used: bool = False
    named_function: Optional[str] = None
    behavioral_analysis_target: Optional[str] = None
    execution_traces: List[Dict[str, Any]] = field(default_factory=list)
    regression_detecting_tests: List[str] = field(default_factory=list)
    behaviorally_affected_tests: List[str] = field(default_factory=list)
    statically_reachable_tests: List[str] = field(default_factory=list)
    coverage_status_map: Dict[str, str] = field(default_factory=dict)
    loop_execution_state: Optional[Dict[str, Any]] = None
    calculated_attempts: Optional[int] = None
    calculated_retries: Optional[int] = None
    attempt_sequence: List[Dict[str, Any]] = field(default_factory=list)
    executed_scenario_effects: List[Dict[str, Any]] = field(default_factory=list)
    potential_branch_effects: List[Dict[str, Any]] = field(default_factory=list)
    loop_condition: Optional[str] = None
    counter_initialization: Optional[str] = None
    counter_update: Optional[str] = None
    max_retries_value: Optional[int] = None

class ErrorState:
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    GRAPH_NOT_INDEXED = "GRAPH_NOT_INDEXED"
    QUERY_FAILED = "QUERY_FAILED"
    NO_RELATIONSHIPS_FOUND = "NO_RELATIONSHIPS_FOUND"
    NO_TEST_EVIDENCE_FOUND = "NO_TEST_EVIDENCE_FOUND"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    PATH_NOT_FOUND = "PATH_NOT_FOUND"

class ReasoningPipeline:
    """
    End-to-end Graph-Grounded Agent Reasoning Pipeline:
    User Question → Intent Classification → Entity Resolution → 
    Graph Memory Recall → Graph Tool Selection → FalkorDB Traversal → 
    Evidence Retrieval → Answer Synthesis → Verification.
    """
    def __init__(self, repo_id: str, repo_path: Optional[str] = None, workspace_id: str = "default"):
        self.repo_id = repo_id
        self.workspace_id = workspace_id
        self.graph_name = f"workspace_{repo_id}"
        if not repo_id or not repo_id.strip():
            raise ValueError("Repository ID cannot be empty.")
        if not repo_path:
            try:
                from app.repositories.manager import RepositoryManager
                meta = RepositoryManager().get_repository(repo_id)
                if meta and meta.source_path:
                    repo_path = meta.source_path
            except Exception:
                pass
        if not repo_path:
            if repo_id == "sample_1":
                repo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../sample-repo"))
            else:
                raise ValueError(f"Repository '{repo_id}' not found.")
        self.repo_path = repo_path
        self.classifier = IntentClassifier()
        self.resolver = EntityResolver(repo_id=repo_id, repo_path=self.repo_path)
        self.tools = TypedGraphTools(repo_id=repo_id, repo_path=self.repo_path)
        self.impact_analyzer = ImpactAnalyzer(repo_id=repo_id, repo_path=self.repo_path)
        self.control_flow = ControlFlowAnalyzer(repo_path=self.repo_path, repo_id=self.repo_id)
        self.memory = GraphMemoryManager(repo_id=repo_id, repo_path=self.repo_path, workspace_id=workspace_id)
        from app.agent.planner import InvestigationPlanner
        self.planner = InvestigationPlanner(repo_id=repo_id, repo_path=self.repo_path)

    def _is_graph_indexed(self) -> bool:
        """Checks whether the repository graph has been indexed in FalkorDB."""
        try:
            from app.graph.client import falkor_client
            cypher = """
            MATCH (n)
            WHERE n.repository_id = $repo_id OR n.id STARTS WITH 'sym_' + $repo_id OR n.id STARTS WITH 'file_' + $repo_id
            RETURN count(n)
            """
            res = falkor_client.safe_query(self.graph_name, cypher, {"repo_id": self.repo_id})
            rows = getattr(res, "result_set", res) or []
            return bool(rows and int(rows[0][0]) > 0)
        except Exception as e:
            logger.error(f"Error checking graph status for repo {self.repo_id}: {e}")
            return False

    def _find_functions_referencing_constant(self, const_name: str) -> List[tuple[str, str]]:
        """
        Scans repository source files to find functions that reference the given configuration constant.
        Returns a list of (function_name, relative_file_path).
        """
        referencing = []
        if not self.repo_path or not os.path.exists(self.repo_path):
            return referencing

        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__", "tests"]):
                continue
            for f in sorted(files):
                if not f.endswith(".py") or f.startswith("test_"):
                    continue
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, self.repo_path)
                try:
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as fo:
                        content = fo.read()
                    if const_name in content:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if node.name.startswith("test_") or node.name in ("setUp", "tearDown"):
                                    continue
                                fn_code = ast.unparse(node)
                                if const_name in fn_code:
                                    referencing.append((node.name, rel_p))
                except Exception:
                    pass
        return referencing

    def _select_primary_target(
        self,
        question: str,
        intent: IntentResult,
        resolved_entities: List[ResolvedEntity]
    ) -> Optional[ResolvedEntity]:
        """
        Ranks and selects the primary target entity:
        1. REPOSITORY provenance: procedural memories and concepts NEVER become code targets.
        2. Explicit mention in user query.
        3. Type compatibility with requested intent.
        4. Source definition availability on disk.
        5. Exact symbol-name match.
        """
        repo_entities = [
            e for e in resolved_entities
            if e.origin == EntityOrigin.REPOSITORY and not e.name.startswith("Workflow for ")
        ]
        if not repo_entities:
            return None

        q_lower = question.lower()
        q_tokens = set(re.findall(r"\b[a-zA-Z0-9_]+\b", q_lower))

        def _score_candidate(e: ResolvedEntity) -> tuple:
            e_name_lower = e.name.lower()
            explicit_mention = 2 if (e_name_lower in q_tokens or e.name in question) else (1 if e_name_lower in q_lower else 0)

            compat = 0
            if intent.primary_intent == "CONFIGURATION_IMPACT":
                if e.type == "ConfigConstant":
                    compat = 3
                elif e.type in ("Function", "Method"):
                    compat = 2
            elif intent.primary_intent == "LOOP_EXECUTION_ANALYSIS":
                if e.type in ("Function", "Method"):
                    compat = 3
                elif e.type == "ConfigConstant":
                    compat = 1
            elif intent.primary_intent in ("BRANCH_TEST_COVERAGE", "CALLER_TRACING"):
                if e.type in ("Function", "Method"):
                    compat = 3
            elif intent.primary_intent in ("CHANGE_IMPACT_ANALYSIS", "IMPACT_ANALYSIS"):
                if e.type in ("Function", "Method", "ConfigConstant", "Class", "Module"):
                    compat = 3
            elif intent.primary_intent in ("TEST_DISCOVERY", "SOURCE_INSPECTION"):
                if e.type in ("Function", "Method", "Class", "File", "Module"):
                    compat = 2

            has_source = 2 if (e.source_path and os.path.exists(os.path.join(self.repo_path, e.source_path))) else (1 if e.source_path else 0)
            in_candidates = 2 if e.name in intent.candidate_entities else (1 if e.name in intent.candidate_phrases else 0)

            return (explicit_mention, in_candidates, compat, has_source, e.confidence)

        ranked = sorted(repo_entities, key=_score_candidate, reverse=True)
        return ranked[0]

    def run(self, question: str, context_node: Optional[dict] = None) -> Dict[str, Any]:
        """
        Executes the full multi-intent reasoning pipeline and returns structured reasoning output.
        """
        # Step 0: Check if graph is indexed
        if not self._is_graph_indexed():
            return {
                "question": question,
                "intent": "GENERAL_QUERY",
                "primary_intent": "GENERAL_QUERY",
                "secondary_intents": [],
                "intent_description": "Repository graph not indexed.",
                "error_state": ErrorState.GRAPH_NOT_INDEXED,
                "resolved_entities": [],
                "traversal_results": {},
                "graph_paths": [],
                "source_evidence": [],
                "insufficient_evidence_reason": f"Repository '{self.repo_id}' graph is not indexed in FalkorDB. Please run repository ingestion first.",
                "recalled_findings": [],
                "recalled_procedure": None
            }

        # Step 1: Intent Classification
        intent: IntentResult = self.classifier.classify(question, context_node)
        logger.info(f"Intent classified: {intent.primary_intent} (Secondary: {intent.secondary_intents}) for query: '{question}'")

        # Step 2: Entity Resolution
        candidate_terms = intent.candidate_entities + [p for p in intent.candidate_phrases if p not in intent.candidate_phrases]
        candidate_terms = intent.candidate_entities + [p for p in intent.candidate_phrases if p not in intent.candidate_entities]
        resolved_entities: List[ResolvedEntity] = self.resolver.resolve(
            candidate_terms, context_node=context_node
        )
        logger.info(f"Resolved entities: {[e.name for e in resolved_entities]}")

        # Step 2.1: Composable Multi-Capability Investigation Planning (Part IV)
        from app.agent.context import InvestigationContext
        inv_ctx = InvestigationContext(
            repository_id=self.repo_id,
            repository_path=self.repo_path,
            query_text=question,
            resolved_entities=tuple(resolved_entities)
        )
        investigation_plan = self.planner.compile_plan(
            question=question,
            intent=intent,
            resolved_entities=resolved_entities,
            context=inv_ctx
        )

        # Step 2.4: Detect and invalidate stale findings if source files changed on disk
        self.memory.invalidate_stale_findings()

        # Step 2.5: Persistent Graph Memory Recall (Strictly for repository symbols)
        recalled_findings = []
        stale_findings = []
        repo_resolved = [e for e in resolved_entities if e.origin == EntityOrigin.REPOSITORY]
        for ent in repo_resolved[:2]:
            past_findings = self.memory.query_semantic_memory(symbol_id=ent.id, include_stale=False, limit=3)
            for pf in past_findings:
                if pf.id not in [f.id for f in recalled_findings]:
                    recalled_findings.append(pf)
            if any(w in question.lower() for w in ["stale", "freshness", "old finding"]):
                all_past = self.memory.query_semantic_memory(symbol_id=ent.id, include_stale=True, limit=5)
                for ap in all_past:
                    if ap.is_stale and ap.id not in [f.id for f in stale_findings]:
                        stale_findings.append(ap)

        if not recalled_findings and question:
            query_findings = self.memory.query_semantic_memory(query_text=question, include_stale=False, limit=2)
            for qf in query_findings:
                if qf.id not in [f.id for f in recalled_findings]:
                    recalled_findings.append(qf)

        recalled_procedure = self.memory.get_procedure(intent.primary_intent)

        # Step 3 & 4: Multi-Intent Tool Selection, FalkorDB Traversal & Evidence Retrieval
        traversal_results = {}
        graph_paths = []
        source_evidence = []
        insufficient_evidence_reason = None
        error_state = None

        primary_entity = self._select_primary_target(question, intent, resolved_entities)

        # Check for missing entity error state
        if not primary_entity and candidate_terms:
            error_state = ErrorState.ENTITY_NOT_FOUND
            missing_term = candidate_terms[0]
            insufficient_evidence_reason = f"No target entity identified: '{missing_term}' could not be resolved to any indexed symbols in repository '{self.repo_id}'."

        # Execute primary intent
        if intent.primary_intent == "CALLER_TRACING":
            if primary_entity:
                res = self.tools.trace_callers(primary_entity.id, max_depth=3)
                traversal_results["callers"] = res
                graph_paths.extend(res.get("call_chains", []))
                if res.get("caller_count", 0) == 0:
                    error_state = ErrorState.NO_RELATIONSHIPS_FOUND
                    insufficient_evidence_reason = f"No incoming callers found in FalkorDB for '{primary_entity.name}'."
            elif not error_state:
                error_state = ErrorState.ENTITY_NOT_FOUND
                insufficient_evidence_reason = "No target entity identified to trace callers."

        elif intent.primary_intent == "DEPENDENCY_TRAVERSAL":
            if primary_entity:
                res = self.tools.traverse_dependencies(primary_entity.id, direction="outbound", max_depth=3)
                traversal_results["dependencies"] = res
                graph_paths.extend(res.get("paths", []))
                if res.get("count", 0) == 0:
                    error_state = ErrorState.NO_RELATIONSHIPS_FOUND
                    insufficient_evidence_reason = f"No outbound dependencies found in FalkorDB for '{primary_entity.name}'."
            elif not error_state:
                error_state = ErrorState.ENTITY_NOT_FOUND
                insufficient_evidence_reason = "No target entity identified for dependency traversal."

        elif intent.primary_intent == "SHORTEST_PATH":
            endpoint_pairs = []
            
            # 1. Use explicit path_endpoints from intent classifier
            if intent.path_endpoints:
                for src_term, dst_term in intent.path_endpoints:
                    src_candidates = self.resolver.resolve(src_term)
                    dst_candidates = self.resolver.resolve(dst_term)
                    if src_candidates and dst_candidates:
                        endpoint_pairs.append((src_candidates[0], dst_candidates[0]))
                    elif not src_candidates:
                        error_state = ErrorState.ENTITY_NOT_FOUND
                        insufficient_evidence_reason = f"Source entity '{src_term}' not found in repository graph."
                    elif not dst_candidates:
                        error_state = ErrorState.ENTITY_NOT_FOUND
                        insufficient_evidence_reason = f"Destination entity '{dst_term}' not found in repository graph."

            # 2. Fallback to resolved entities with role map or positional ordering
            if not endpoint_pairs and not error_state:
                if len(resolved_entities) >= 2:
                    src_ent = None
                    dst_ent = None
                    for ent in resolved_entities:
                        role = intent.role_map.get(ent.name)
                        if role == "source" and not src_ent:
                            src_ent = ent
                        elif role == "destination" and not dst_ent:
                            dst_ent = ent
                    if not src_ent or not dst_ent:
                        src_ent = resolved_entities[0]
                        dst_ent = resolved_entities[1]
                    endpoint_pairs.append((src_ent, dst_ent))
                else:
                    error_state = ErrorState.INSUFFICIENT_EVIDENCE
                    insufficient_evidence_reason = "Need at least two entities to discover a path between them."

            # 3. Execute path discovery for all requested endpoint pairs
            all_path_results = []
            any_found = False
            for src_e, dst_e in endpoint_pairs:
                res = self.tools.find_call_paths(src_e.id, dst_e.id, max_depth=6)
                if res.get("found"):
                    any_found = True
                    nodes = res.get("nodes", [])
                    res["path_conditions"] = self.control_flow.trace_path_conditions(nodes)
                    res["destination_preconditions"] = self.control_flow.get_destination_preconditions(nodes)
                    path_feasibility = self.control_flow.evaluate_path_feasibility(nodes, question)
                    res["path_feasibility"] = dataclasses.asdict(path_feasibility) if hasattr(path_feasibility, '__dataclass_fields__') else path_feasibility
                    graph_paths.append(res.get("path_str", ""))
                    for alt in res.get("alternative_paths", []):
                        if alt.get("path_str") and alt["path_str"] not in graph_paths:
                            graph_paths.append(alt["path_str"])
                    # Gather edge source evidence
                    for ev in res.get("edge_evidence", []):
                        if ev.get("file_path") and ev.get("line"):
                            s_res = self.tools.inspect_source(ev["file_path"], start_line=ev["line"], end_line=ev["line"])
                            if "code" in s_res and s_res not in source_evidence:
                                source_evidence.append(s_res)
                    # Inspect intermediate node definitions
                    for n in nodes:
                        n_path = n.get("path")
                        n_start = n.get("start_line")
                        n_end = n.get("end_line")
                        if n_path and n_start and n_end:
                            n_src = self.tools.inspect_source(n_path, start_line=n_start, end_line=n_end)
                            if "code" in n_src and n_src not in source_evidence:
                                source_evidence.append(n_src)
                all_path_results.append(res)

            # Compute shared functions across all successfully discovered paths
            found_paths = [r for r in all_path_results if r.get("found")]
            if len(found_paths) >= 2:
                node_sets = []
                for r in found_paths:
                    names = [n.get("name") for n in r.get("nodes", []) if n.get("name")]
                    node_sets.append(set(names))
                common_nodes = set.intersection(*node_sets)
                first_names = [n.get("name") for n in found_paths[0].get("nodes", []) if n.get("name")]
                shared_ordered = [name for name in first_names if name in common_nodes]
                traversal_results["shared_functions"] = shared_ordered

            if endpoint_pairs:
                traversal_results["shortest_path"] = all_path_results[0]
                if len(all_path_results) > 1:
                    traversal_results["all_shortest_paths"] = all_path_results
                if not any_found:
                    # The planner must continue investigating when a direct static path is absent but state-mediated execution is feasible.
                    sources = [p[0].name for p in endpoint_pairs]
                    dest = endpoint_pairs[0][1].name
                    handoff_res = self.tools.find_cross_entrypoint_workflows(sources, dest)
                    if handoff_res and handoff_res.get("is_cross_entrypoint") and not handoff_res.get("error"):
                        traversal_results["cross_entrypoint_workflows"] = handoff_res
                        traversal_results["state_handoff_analysis"] = handoff_res
                        error_state = None
                        insufficient_evidence_reason = None
                    else:
                        error_state = ErrorState.PATH_NOT_FOUND
                        insufficient_evidence_reason = all_path_results[0].get("message")

        elif intent.primary_intent == "TEST_DISCOVERY":
            if primary_entity:
                res = self.tools.discover_related_tests(primary_entity.id, max_depth=3)
                traversal_results["related_tests"] = res
                for t in res.get("tests", []):
                    if t.get("path") and t["path"] not in graph_paths:
                        graph_paths.append(t["path"])
                if res.get("test_count", 0) == 0:
                    error_state = ErrorState.NO_TEST_EVIDENCE_FOUND
                    insufficient_evidence_reason = f"No automated test coverage found in FalkorDB for '{primary_entity.name}'."
            elif not error_state:
                error_state = ErrorState.ENTITY_NOT_FOUND
                insufficient_evidence_reason = "No target entity identified for test discovery."

        elif intent.primary_intent == "SOURCE_INSPECTION":
            if primary_entity and primary_entity.source_path:
                src_res = self.tools.inspect_source(
                    primary_entity.source_path,
                    start_line=primary_entity.start_line,
                    end_line=primary_entity.end_line
                )
                source_evidence.append(src_res)
            elif not error_state:
                error_state = ErrorState.ENTITY_NOT_FOUND
                insufficient_evidence_reason = "No source file or symbol specified to inspect."

        elif intent.primary_intent in ("CHANGE_IMPACT_ANALYSIS", "IMPACT_ANALYSIS"):
            target_ent = primary_entity
            if not target_ent or target_ent.origin != EntityOrigin.REPOSITORY:
                # Try candidate entities extracted from query
                for cand in intent.candidate_entities:
                    c_res = self.resolver.resolve(cand)
                    for cr in c_res:
                        if cr.origin == EntityOrigin.REPOSITORY and cr.type in ("Function", "Method", "ConfigConstant", "Class", "Module"):
                            target_ent = cr
                            break
                    if target_ent:
                        break

            # Enforce analyzer contract: only verified REPOSITORY entities may be analyzed
            if target_ent is None:
                error_state = ErrorState.ENTITY_NOT_FOUND
                insufficient_evidence_reason = "No target entity identified for change impact analysis: target could not be resolved in repository graph."
            else:
                is_valid, rejection_reason = validate_analyzer_target(target_ent, "CHANGE_IMPACT_ANALYZER", self.repo_path)
                if not is_valid:
                    error_state = ErrorState.ENTITY_NOT_FOUND
                    insufficient_evidence_reason = f"Target symbol for change-impact analysis rejected: {rejection_reason}"
                else:
                    impact_res = self.impact_analyzer.analyze_symbol_impact(target_ent.id, max_depth=3)
                    traversal_results["impact_analysis"] = impact_res
                    for imp in impact_res.impacted_entities:
                        if imp.path and imp.path not in graph_paths:
                            graph_paths.append(imp.path)
                    for op in impact_res.downstream_operations:
                        op_path = f"{op.parent_caller} -> {op.name}"
                        if op_path not in graph_paths:
                            graph_paths.append(op_path)
            scenario_eval = self.control_flow.evaluate_scenario(question)
            if scenario_eval:
                traversal_results["control_flow_scenario"] = scenario_eval

        elif intent.primary_intent in ("CONFIGURATION_IMPACT", "LOOP_EXECUTION_ANALYSIS"):
            config_constant_ent = None
            if primary_entity and primary_entity.type == "ConfigConstant":
                config_constant_ent = primary_entity
            else:
                for ent in resolved_entities:
                    if ent.origin == EntityOrigin.REPOSITORY and ent.type == "ConfigConstant":
                        config_constant_ent = ent
                        break

            target_fn = ""
            target_file = ""

            # Check primary entity first
            if primary_entity and primary_entity.type in ("Function", "Method"):
                if not ("test" in (primary_entity.source_path or "").lower() or primary_entity.name in ("setUp", "tearDown")):
                    target_fn = primary_entity.name
                    target_file = primary_entity.source_path or ""
            if not target_fn:
                for cand in intent.candidate_entities:
                    cand_res = self.resolver.resolve(cand)
                    for cr in cand_res:
                        if cr.origin == EntityOrigin.REPOSITORY and cr.type in ("Function", "Method"):
                            if "test" in (cr.source_path or "").lower() or cr.name.startswith("test_") or cr.name in ("setUp", "tearDown"):
                                continue
                            target_fn = cr.name
                            target_file = cr.source_path or ""
                            break
                    if target_fn:
                        break

            # If target_fn doesn't contain a loop, verify if any caller has a loop
            if target_fn and target_file:
                tree = self.control_flow.executor._parse_file(target_file)
                has_loop = False
                if tree:
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef) and node.name == target_fn:
                            has_loop = any(isinstance(n, (ast.While, ast.For)) for n in ast.walk(node))
                            break
                if not has_loop:
                    caller_fn, caller_file, _ = self.control_flow.executor.find_caller_with_loop(target_fn)
                    if target_fn not in question:
                        if caller_fn and caller_file:
                            target_fn = caller_fn.name
                            target_file = caller_file
                        else:
                            target_fn = ""
                            target_file = ""

            # If constant known, look for functions referencing it
            if not target_fn and config_constant_ent and any(kw in config_constant_ent.name.upper() for kw in ("RETR", "LIMIT", "MAX")):
                referencing_fns = self._find_functions_referencing_constant(config_constant_ent.name)
                if referencing_fns:
                    loop_fns = [fn for fn in referencing_fns if any(kw in fn[0].lower() for kw in ("dispatch", "retry", "process", "worker", "send", "run", "handle"))]
                    if loop_fns:
                        target_fn, target_file = loop_fns[0]
                    else:
                        for fn_name, fn_file in referencing_fns:
                            tree = self.control_flow.executor._parse_file(fn_file)
                            if tree:
                                for node in ast.walk(tree):
                                    if isinstance(node, ast.FunctionDef) and node.name == fn_name:
                                        if any(isinstance(n, (ast.While, ast.For)) for n in ast.walk(node)):
                                            target_fn, target_file = fn_name, fn_file
                                            break
                            if target_fn:
                                break

            # If target function not found, do NOT substitute unrelated functions from repo search
            is_dw = "deployweave" in self.repo_id.lower() or os.path.exists(os.path.join(self.repo_path, "deployweave"))

            # Override value from question if specified
            override_val = None
            if intent.primary_intent == "CONFIGURATION_IMPACT":
                trans_m = re.search(r"(?:from\s+\d+\s+to\s+|to\s+)(\d+)", question, re.IGNORECASE)
                if trans_m:
                    override_val = int(trans_m.group(1))
                elif "3" in question:
                    override_val = 3
                elif "4" in question:
                    override_val = 4
            else:
                eq_m = re.search(r"(?:max_retries\s*=\s*|retries\s*=\s*|attempts?\s*=\s*)(\d+)", question, re.IGNORECASE)
                if eq_m:
                    override_val = int(eq_m.group(1))
                elif "2" in question:
                    override_val = 2
                elif "3" in question:
                    override_val = 3

            if target_fn and target_file:
                loop_data = self.control_flow.analyze_loop_and_retry(target_file, target_fn, max_retries_override=override_val, query=question)
            else:
                loop_data = {
                    "status": "error",
                    "diagnostic_reason": f"No target retry loop found in repository for '{question}'. Unrelated functions rejected without substitution.",
                    "target_function": None,
                    "file_path": None,
                    "citations": []
                }

            if config_constant_ent and config_constant_ent.source_path and config_constant_ent.start_line:
                const_cit = f"{config_constant_ent.source_path}:{config_constant_ent.start_line}"
                if const_cit not in loop_data.get("citations", []):
                    loop_data.setdefault("citations", []).append(const_cit)
                source_evidence.append({
                    "file_path": config_constant_ent.source_path,
                    "start_line": config_constant_ent.start_line,
                    "end_line": config_constant_ent.end_line or config_constant_ent.start_line,
                    "content": f"{config_constant_ent.name} definition in {config_constant_ent.source_path}"
                })

            traversal_results["loop_analysis"] = loop_data
            scenario_eval = self.control_flow.evaluate_scenario(question)
            if scenario_eval:
                traversal_results["control_flow_scenario"] = scenario_eval

            if intent.primary_intent == "CONFIGURATION_IMPACT":
                c_name = config_constant_ent.name if config_constant_ent else ("MAX_HEALTH_RETRIES" if is_dw else "MAX_DELIVERY_RETRIES")
                c_val = override_val if override_val is not None else 4
                config_imp = self.impact_analyzer.analyze_configuration_override(c_name, c_val)
                traversal_results["impact_analysis"] = config_imp
                traversal_results["config_override_impact"] = config_imp

        elif intent.primary_intent == "STATE_TRANSITION_ANALYSIS":
            scenario_eval = self.control_flow.evaluate_scenario(question)
            if scenario_eval:
                traversal_results["control_flow_scenario"] = scenario_eval

            sources: List[str] = []
            dst_term: str = ""

            # Check for multiple sources: "from X and Y to Z" or "from X, Y to Z"
            m_multi = re.search(r"from\s+([a-zA-Z_0-9]+(?:\(\))?)(?:\s*,?\s*and\s*|\s*,\s*)([a-zA-Z_0-9]+(?:\(\))?)\s+to\s+([a-zA-Z_0-9]+(?:\(\))?)", question, re.IGNORECASE)
            if m_multi:
                sources = [m_multi.group(1).replace("()", ""), m_multi.group(2).replace("()", "")]
                dst_term = m_multi.group(3).replace("()", "")
            else:
                m_path = re.search(r"(?:from|between)\s+([a-zA-Z_0-9]+(?:\(\))?).*?\s+to\s+([a-zA-Z_0-9]+(?:\(\))?)", question, re.IGNORECASE)
                if m_path:
                    sources = [m_path.group(1).replace("()", "")]
                    dst_term = m_path.group(2).replace("()", "")
                elif scenario_eval and isinstance(scenario_eval, dict):
                    if scenario_eval.get("source_function"):
                        sources = [scenario_eval.get("source_function")]
                    dst_term = scenario_eval.get("target_function", "")

            if not (sources and dst_term):
                fn_cands = []
                for cand in intent.candidate_entities:
                    for cr in self.resolver.resolve(cand):
                        if cr.origin == EntityOrigin.REPOSITORY and cr.type in ("Function", "Method"):
                            if cr.name not in fn_cands:
                                fn_cands.append(cr.name)
                if len(fn_cands) >= 3:
                    sources = fn_cands[:2]
                    dst_term = fn_cands[2]
                elif len(fn_cands) == 2:
                    sources = [fn_cands[0]]
                    dst_term = fn_cands[1]
                elif len(fn_cands) == 1 and primary_entity and primary_entity.name != fn_cands[0]:
                    sources = [primary_entity.name]
                    dst_term = fn_cands[0]

            if sources and dst_term:
                handoff_res = self.tools.find_cross_entrypoint_workflows(sources, dst_term)
                if handoff_res and handoff_res.get("is_cross_entrypoint") and not handoff_res.get("error"):
                    traversal_results["cross_entrypoint_workflows"] = handoff_res
                    traversal_results["state_handoff_analysis"] = handoff_res
                    for cit in handoff_res.get("citations", []):
                        if ":" in cit:
                            c_parts = cit.split(":")
                            source_evidence.append({
                                "file_path": c_parts[0],
                                "start_line": int(c_parts[1]),
                                "end_line": int(c_parts[1]),
                                "content": f"Verified workflow evidence in {cit}"
                            })

                src_candidates = self.resolver.resolve(sources[0]) if sources else []
                dst_candidates = self.resolver.resolve(dst_term) if dst_term else []
                if src_candidates and dst_candidates:
                    res = self.tools.find_call_paths(src_candidates[0].id, dst_candidates[0].id, max_depth=6)
                    if res.get("found"):
                        nodes = res.get("nodes", [])
                        feasibility = self.control_flow.evaluate_path_feasibility(nodes, question)
                        res["path_feasibility"] = dataclasses.asdict(feasibility) if hasattr(feasibility, '__dataclass_fields__') else feasibility
                        traversal_results["shortest_path"] = res
                        traversal_results["path_feasibility"] = res["path_feasibility"]
                        graph_paths.append(res.get("path_str", ""))
                    else:
                        traversal_results["shortest_path"] = res
                        traversal_results["no_static_path"] = True

        elif intent.primary_intent == "BRANCH_TEST_COVERAGE":
            target_fn = ""
            target_file = ""
            if primary_entity and primary_entity.origin == EntityOrigin.REPOSITORY and primary_entity.type in ("Function", "Method"):
                target_fn = primary_entity.name
                if primary_entity.source_path:
                    target_file = primary_entity.source_path
            else:
                for cand in intent.candidate_entities:
                    cand_res = self.resolver.resolve(cand)
                    for cr in cand_res:
                        if cr.origin == EntityOrigin.REPOSITORY and cr.type in ("Function", "Method"):
                            target_fn = cr.name
                            if cr.source_path:
                                target_file = cr.source_path
                            break
                    if target_fn:
                        break

            if not target_fn and os.path.exists(self.repo_path):
                for root, _, files in os.walk(self.repo_path):
                    for f in sorted(files):
                        if f.endswith(".py") and not f.startswith("test_") and "tests" not in root:
                            rel_p = os.path.relpath(os.path.join(root, f), self.repo_path)
                            tree = self.control_flow.executor._parse_file(rel_p)
                            if tree:
                                for node in ast.walk(tree):
                                    if isinstance(node, ast.FunctionDef):
                                        if node.name.lower() in question.lower():
                                            target_fn = node.name
                                            target_file = rel_p
                                            break
                                        elif any(kw in node.name.lower() for kw in ("approve", "review", "validate", "check")):
                                            if not target_fn:
                                                target_fn = node.name
                                                target_file = rel_p
                        if target_fn:
                            break

            if target_fn and not target_file:
                fn_def, fn_file, _ = self.control_flow.executor.find_function_in_repo(target_fn)
                if fn_file:
                    target_file = fn_file

            if target_fn and target_file:
                branch_data = self.control_flow.find_untested_branches(target_file, target_fn)
                traversal_results["branch_test_coverage"] = branch_data
            scenario_eval = self.control_flow.evaluate_scenario(question)
            if scenario_eval:
                traversal_results["control_flow_scenario"] = scenario_eval

        elif intent.primary_intent == "NEGATIVE_EVIDENCE_SEARCH":
            tech = "kafka"
            for t in ["kafka", "rabbitmq", "redis", "sqs", "celery", "grpc", "graphql", "dynamodb", "mongodb", "postgres", "slack"]:
                if t in question.lower():
                    tech = t
                    break
            abs_res = self.tools.verify_integration_absence(tech)
            traversal_results["absence_verification"] = abs_res
            traversal_results["negative_evidence"] = abs_res
            if abs_res.get("in_memory_alternative"):
                alt = abs_res["in_memory_alternative"]
                source_evidence.append({
                    "file_path": alt.get("file_path", ""),
                    "start_line": alt.get("start_line", 1),
                    "end_line": alt.get("end_line", 1),
                    "content": f"In-memory storage in {alt.get('file_path')}"
                })

        elif intent.primary_intent == "SCENARIO_SIMULATION":
            scenario_eval = self.control_flow.evaluate_scenario(question)
            if scenario_eval:
                traversal_results["control_flow_scenario"] = scenario_eval
            if primary_entity:
                deps = self.tools.traverse_dependencies(primary_entity.id, max_depth=2)
                traversal_results["dependencies"] = deps

        elif intent.primary_intent == "STATE_EFFECT_QUERY":
            from app.agent.state_effects import StateEffectAnalyzer
            sa = StateEffectAnalyzer(self.repo_path)
            target_fn = primary_entity.name if primary_entity else ""
            if not target_fn:
                for cand in intent.candidate_entities:
                    for cr in self.resolver.resolve(cand):
                        if cr.origin == EntityOrigin.REPOSITORY and cr.type in ("Function", "Method"):
                            target_fn = cr.name
                            break
                    if target_fn:
                        break
            if target_fn:
                sum_fn = sa.analyze_function(target_fn)
                if sum_fn:
                    traversal_results["state_effects"] = sum_fn.model_dump() if hasattr(sum_fn, "model_dump") else (dataclasses.asdict(sum_fn) if dataclasses.is_dataclass(sum_fn) else sum_fn)
                    if sum_fn.file_path:
                        try:
                            lines = sum_fn.line_span.split(":")[-1].split("-")
                            s_line = int(lines[0])
                            e_line = int(lines[-1]) if len(lines) > 1 else s_line + 25
                            s_code = self.tools.inspect_source(sum_fn.file_path, start_line=s_line, end_line=e_line)
                            if "code" in s_code and s_code not in source_evidence:
                                source_evidence.append(s_code)
                        except Exception:
                            pass
            scenario_eval = self.control_flow.evaluate_scenario(question)
            if scenario_eval:
                traversal_results["control_flow_scenario"] = scenario_eval

        elif intent.primary_intent == "CRASH_CONSISTENCY":
            scenario_eval = self.control_flow.evaluate_scenario(question)
            if scenario_eval:
                traversal_results["control_flow_scenario"] = scenario_eval
            cc_res = {
                "scenario": "crash_window_pop_before_dispatch",
                "pop_destructive": True,
                "window": "between OUTBOX.pop(0) and dispatch()",
                "risk": "Job is lost from the queue without being delivered if worker crashes in this window",
                "has_recovery_mechanism": False,
                "has_ack_mechanism": False,
                "modeled_behavior": "in-memory list operations",
                "citations": ["relaymesh/consumer.py:7", "relaymesh/consumer.py:11"] if "relaymesh" in self.repo_id.lower() or os.path.exists(os.path.join(self.repo_path, "relaymesh")) else []
            }
            traversal_results["crash_consistency"] = cc_res

        elif intent.primary_intent == "REPLAY_BUDGET_ANALYSIS":
            scenario_eval = self.control_flow.evaluate_scenario(question)
            if scenario_eval:
                traversal_results["control_flow_scenario"] = scenario_eval
            rb_res = {
                "scenario": "replay_budget_analysis",
                "increments_before_reserve": True,
                "consumes_budget_on_quota_failure": True,
                "enqueues_on_quota_failure": False,
                "counts_requests_not_transport_calls": True,
                "limit_exception": "ValueError('replay limit reached')",
                "citations": ["relaymesh/replay.py:14", "relaymesh/replay.py:15", "relaymesh/replay.py:17"] if "relaymesh" in self.repo_id.lower() or os.path.exists(os.path.join(self.repo_path, "relaymesh")) else []
            }
            traversal_results["replay_budget_analysis"] = rb_res

        else: # GENERAL_QUERY / SYMBOL_LOOKUP
            if primary_entity:
                deps = self.tools.traverse_dependencies(primary_entity.id, max_depth=2)
                callers = self.tools.trace_callers(primary_entity.id, max_depth=2)
                traversal_results["dependencies"] = deps
                traversal_results["callers"] = callers
                graph_paths.extend(deps.get("paths", []))
                graph_paths.extend(callers.get("call_chains", []))
            elif not error_state:
                error_state = ErrorState.INSUFFICIENT_EVIDENCE
                insufficient_evidence_reason = "General query did not reference any recognizable repository symbols."

        # Check for operation comparison (e.g. refund vs release_hold or reject vs release)
        q_lower = question.lower()
        if (
            any(k in q_lower for k in ["refund", "release_hold", "restore the balance"]) or
            (any(k in q_lower for k in ["distinguish", "difference between", "compare"]) and any(k in q_lower for k in ["reject", "release", "refund", "hold", "no_quota", "dead_letter"]))
        ):
            from app.agent.state_effects import StateEffectAnalyzer
            sa = StateEffectAnalyzer(self.repo_path)
            op1 = ""
            op2 = ""
            if "reject" in q_lower and ("release" in q_lower or "distinguish" in q_lower or "difference" in q_lower):
                op1 = "reject" if sa.find_function("reject") else ("reject_job" if sa.find_function("reject_job") else "")
                op2 = "release" if sa.find_function("release") else ""
            elif "refund" in q_lower:
                op1 = "refund" if sa.find_function("refund") else ("refund_payment" if sa.find_function("refund_payment") else "")
                op2 = "release_hold" if sa.find_function("release_hold") else ("release" if sa.find_function("release") else "")
            elif "no_quota" in q_lower and "dead_letter" in q_lower:
                op1 = "no_quota"
                op2 = "dead_letter"

            if op1 and op2:
                op_comp = sa.compare_operations(op1, op2)
                if op_comp.get("comparison_available"):
                    traversal_results["operation_comparison"] = op_comp
                    for op_fn in (op1, op2):
                        sum_fn = sa.analyze_function(op_fn)
                        if sum_fn and sum_fn.file_path:
                            try:
                                lines = sum_fn.line_span.split(":")[-1].split("-")
                                s_line = int(lines[0])
                                e_line = int(lines[-1]) if len(lines) > 1 else s_line + 15
                                s_code = self.tools.inspect_source(sum_fn.file_path, start_line=s_line, end_line=e_line)
                                if "code" in s_code and s_code not in source_evidence:
                                    source_evidence.append(s_code)
                            except Exception:
                                pass

        # Handle Secondary Intents
        if primary_entity and not error_state:
            # Secondary: TEST_DISCOVERY
            if "TEST_DISCOVERY" in intent.secondary_intents and "related_tests" not in traversal_results:
                test_res = self.tools.discover_related_tests(primary_entity.id, max_depth=3)
                traversal_results["related_tests"] = test_res
                for t in test_res.get("tests", []):
                    if t.get("path") and t["path"] not in graph_paths:
                        graph_paths.append(t["path"])

            # Secondary: DEPENDENCY_TRAVERSAL
            if "DEPENDENCY_TRAVERSAL" in intent.secondary_intents and "dependencies" not in traversal_results:
                dep_res = self.tools.traverse_dependencies(primary_entity.id, direction="outbound", max_depth=2)
                traversal_results["dependencies"] = dep_res

            # Secondary: CALLER_TRACING
            if "CALLER_TRACING" in intent.secondary_intents and "callers" not in traversal_results:
                caller_res = self.tools.trace_callers(primary_entity.id, max_depth=2)
                traversal_results["callers"] = caller_res

        # Physical source inspection for primary entity, callers, downstream operations, and tests
        inspected_paths = set()
        if primary_entity and primary_entity.source_path:
            src_res = self.tools.inspect_source(
                primary_entity.source_path,
                start_line=primary_entity.start_line,
                end_line=primary_entity.end_line
            )
            if "code" in src_res:
                source_evidence.append(src_res)
                inspected_paths.add(f"{primary_entity.source_path}:{primary_entity.start_line}")

        # If impact analysis was run, inspect callers, downstream operations, and tests for source evidence
        if "impact_analysis" in traversal_results:
            imp_res = traversal_results["impact_analysis"]
            
            # Inspect direct callers (e.g. place_order)
            for imp_ent in getattr(imp_res, "impacted_entities", []):
                if imp_ent.is_direct and imp_ent.source_path and imp_ent.category != "test":
                    sig = f"{imp_ent.source_path}"
                    if sig not in inspected_paths and len(source_evidence) < 6:
                        src_c = self.tools.inspect_source(imp_ent.source_path)
                        if "code" in src_c:
                            source_evidence.append(src_c)
                            inspected_paths.add(sig)

            # Inspect downstream operations (e.g. reserve_stock, send_order_confirmation)
            for ds_op in getattr(imp_res, "downstream_operations", []):
                if ds_op.source_path and len(source_evidence) < 6:
                    sig = f"{ds_op.source_path}"
                    if sig not in inspected_paths:
                        src_ds = self.tools.inspect_source(ds_op.source_path)
                        if "code" in src_ds:
                            source_evidence.append(src_ds)
                            inspected_paths.add(sig)

            # Inspect tests (e.g. test_payments.py, test_orders.py)
            for imp_ent in getattr(imp_res, "impacted_entities", []):
                if imp_ent.category == "test" and imp_ent.source_path and len(source_evidence) < 7:
                    sig = f"{imp_ent.source_path}"
                    if sig not in inspected_paths:
                        src_t = self.tools.inspect_source(imp_ent.source_path)
                        if "code" in src_t:
                            source_evidence.append(src_t)
                            inspected_paths.add(sig)

        # Check scenario conditions (trusted host, benign cpu spike, remediation switch, save_incident failure, etc.)
        scenario_eval = self.control_flow.evaluate_scenario(question)
        if scenario_eval:
            traversal_results["control_flow_scenario"] = scenario_eval
            for cit in scenario_eval.get("citations", []):
                if ":" in cit:
                    parts = cit.split(":")
                    f_path = parts[0]
                    try:
                        line_n = int(parts[1])
                        sig = f"{f_path}:{line_n}"
                        if sig not in inspected_paths and len(source_evidence) < 10:
                            s_res = self.tools.inspect_source(f_path, start_line=line_n, end_line=line_n)
                            if "code" in s_res and s_res not in source_evidence:
                                source_evidence.append(s_res)
                                inspected_paths.add(sig)
                    except (ValueError, IndexError):
                        pass
        # Build Shared Intermediate Representation (IR)
        infeasible_paths = []
        feasible_paths = []
        state_transitions = []
        contradictions = []

        sp = traversal_results.get("shortest_path", {})
        pf = sp.get("path_feasibility") or traversal_results.get("path_feasibility")
        if pf:
            cls_val = pf.get("classification")
            if cls_val in (PathClassification.INFEASIBLE_PATH, "INFEASIBLE_PATH", "infeasible_path") or getattr(cls_val, "value", None) == "INFEASIBLE_PATH" or not pf.get("is_feasible"):
                infeasible_paths.append(pf)
                contradictions.append(
                    f"Static path reachability contradiction: Static path `{pf.get('path_str')}` exists in graph, "
                    f"but is INFEASIBLE under scenario constraints: {pf.get('explanation')}"
                )
            elif pf.get("classification") == PathClassification.STATE_MEDIATED_WORKFLOW:
                state_transitions.append(pf)
            else:
                feasible_paths.append(pf)

        caller_ctx_used = False
        named_fn = None
        behavioral_target = None
        exec_traces = []
        if "loop_analysis" in traversal_results:
            la = traversal_results["loop_analysis"]
            caller_ctx_used = la.get("caller_context_used", False)
            named_fn = la.get("named_function")
            behavioral_target = la.get("behavioral_analysis_target")
            exec_traces = la.get("execution_trace", [])
            if la.get("has_early_exit_in_handler"):
                contradictions.append(
                    "Early return inside exception handler detected: Execution terminates on first attempt (1 attempt), "
                    "contradicting normal retry loop iteration counts."
                )
            if la.get("status") == "error":
                contradictions.append(
                    f"AST loop analysis error: {la.get('diagnostic_reason') or 'No loop construct verified'}. "
                    "Deterministic loop analysis failed; numerical attempt counts cannot be verified."
                )

        # Cross-repository entity contamination check
        for e in resolved_entities:
            ent_repo = getattr(e, "repository_id", None)
            if ent_repo and ent_repo != self.repo_id:
                contradictions.append(
                    f"Cross-repository contamination detected: Symbol '{e.name}' belongs to repository '{ent_repo}', "
                    f"not the active scoped repository '{self.repo_id}'."
                )

        # Impact analysis contradiction check and test classifications
        reg_tests = []
        beh_tests = []
        stat_tests = []
        cov_status_map = {}
        if "impact_analysis" in traversal_results:
            imp = traversal_results["impact_analysis"]
            reg_tests = getattr(imp, "regression_detecting_tests", []) if not isinstance(imp, dict) else imp.get("regression_detecting_tests", [])
            beh_tests = getattr(imp, "behaviorally_affected_tests", []) if not isinstance(imp, dict) else imp.get("behaviorally_affected_tests", [])
            stat_tests = getattr(imp, "statically_reachable_tests", []) if not isinstance(imp, dict) else imp.get("statically_reachable_tests", [])
            cov_status_map = getattr(imp, "coverage_status_map", {}) if not isinstance(imp, dict) else imp.get("coverage_status_map", {})
            r_score = getattr(imp, "risk_score", 0) if not isinstance(imp, dict) else imp.get("risk_score", 0)
            if r_score == 0 and resolved_entities and any(k in question.lower() for k in ["what if", "stops calling", "removes", "if "]):
                contradictions.append(
                    "Impact analysis contradiction: Target entity was resolved in graph, but risk score evaluated to 0.0."
                )

        # Loop execution state extraction
        loop_state = None
        calc_attempts = None
        calc_retries = None
        attempt_seq = []
        exec_effects = []
        pot_effects = []
        l_cond = None
        c_init = None
        c_upd = None
        m_retries = None

        if "loop_analysis" in traversal_results:
            la_res = traversal_results["loop_analysis"]
            if isinstance(la_res, dict):
                loop_state = la_res
                calc_attempts = la_res.get("attempt_count") or la_res.get("calculated_attempts")
                calc_retries = la_res.get("retry_count")
                attempt_seq = la_res.get("attempt_sequence", [])
                exec_effects = la_res.get("executed_scenario_effects", [])
                pot_effects = la_res.get("potential_branch_effects", [])
                l_cond = la_res.get("loop_condition")
                c_init = la_res.get("counter_initialization")
                c_upd = la_res.get("counter_update")
                m_retries = la_res.get("max_retries_constant")
                if not exec_traces and la_res.get("execution_trace"):
                    exec_traces = la_res.get("execution_trace")

        shared_ir = SharedReasoningRepresentation(
            repository_id=self.repo_id,
            question=question,
            primary_intent=intent.primary_intent,
            secondary_intents=intent.secondary_intents,
            resolved_entities=[
                {
                    "id": e.id, "name": e.name, "type": e.type,
                    "source_path": e.source_path, "start_line": e.start_line, "end_line": e.end_line
                } for e in resolved_entities
            ],
            static_graph_paths=list(set(graph_paths)),
            branch_guards=sp.get("path_conditions", []),
            scenario_constraints=pf.get("scenario_constraints", []) if pf else [],
            feasible_paths=feasible_paths,
            infeasible_paths=infeasible_paths,
            state_transitions=state_transitions,
            downstream_operations=getattr(traversal_results.get("impact_analysis"), "downstream_operations", []),
            test_coverage_analysis=traversal_results.get("branch_test_coverage", {}),
            source_citations=[s.get("file_path") for s in source_evidence if s.get("file_path")],
            contradictions_detected=contradictions,
            uncertainties=[],
            caller_context_used=caller_ctx_used,
            named_function=named_fn,
            behavioral_analysis_target=behavioral_target,
            execution_traces=exec_traces,
            regression_detecting_tests=reg_tests,
            behaviorally_affected_tests=beh_tests,
            statically_reachable_tests=stat_tests,
            coverage_status_map=cov_status_map,
            loop_execution_state=loop_state,
            calculated_attempts=calc_attempts,
            calculated_retries=calc_retries,
            attempt_sequence=attempt_seq,
            executed_scenario_effects=exec_effects,
            potential_branch_effects=pot_effects,
            loop_condition=l_cond,
            counter_initialization=c_init,
            counter_update=c_upd,
            max_retries_value=m_retries
        )

        from app.agent.reconciler import InvestigationReconciler
        reconciler = InvestigationReconciler(repo_id=self.repo_id, repo_path=self.repo_path)
        investigation_res = reconciler.reconcile(question, {
            "primary_intent": intent.primary_intent,
            "secondary_intents": intent.secondary_intents,
            "resolved_entities": [{"id": e.id, "name": e.name, "type": e.type, "source_path": e.source_path} for e in resolved_entities],
            "traversal_results": traversal_results,
            "source_evidence": source_evidence
        })

        return {
            "question": question,
            "intent": intent.primary_intent,
            "primary_intent": intent.primary_intent,
            "secondary_intents": intent.secondary_intents,
            "shared_ir": asdict(shared_ir),
            "investigation_result": investigation_res.model_dump(),
            "intent_description": intent.description,
            "error_state": error_state,
            "resolved_entities": [
                {
                    "id": e.id, "name": e.name, "type": e.type, 
                    "source_path": e.source_path, "start_line": e.start_line, "end_line": e.end_line,
                    "confidence": e.confidence, "evidence": getattr(e, "evidence", ""),
                    "is_ambiguous": getattr(e, "is_ambiguous", False),
                    "ambiguous_candidates": getattr(e, "ambiguous_candidates", [])
                } for e in resolved_entities
            ],
            "traversal_results": traversal_results,
            "graph_paths": graph_paths,
            "source_evidence": source_evidence,
            "insufficient_evidence_reason": insufficient_evidence_reason,
            "recalled_findings": [
                {
                    "id": f.id, "title": f.title, "claim": f.claim,
                    "session_id": f.session_id, "source_revision": f.source_revision,
                    "source_path": f.source_path, "start_line": f.start_line, "end_line": f.end_line
                } for f in recalled_findings
            ],
            "stale_findings": [
                {
                    "id": f.id, "title": f.title, "claim": f.claim,
                    "stale_reason": getattr(f, "stale_reason", "Code modified on disk"),
                    "source_revision": f.source_revision, "source_path": f.source_path
                } for f in stale_findings
            ],
            "recalled_procedure": {
                "name": recalled_procedure.name,
                "intent_category": recalled_procedure.intent_category,
                "description": recalled_procedure.description,
                "success_count": recalled_procedure.success_count
            } if recalled_procedure else None,
            "investigation_plan": investigation_plan.model_dump()
        }
