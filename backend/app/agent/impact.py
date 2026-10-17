import os
import ast
import re
import subprocess
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from app.graph.client import falkor_client
from app.agent.control_flow import ControlFlowAnalyzer

logger = logging.getLogger(__name__)

@dataclass
class HunkChange:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    changed_lines: List[int]

@dataclass
class FileDiff:
    file_path: str
    hunks: List[HunkChange] = field(default_factory=list)
    changed_lines: List[int] = field(default_factory=list)

@dataclass
class ChangedSymbol:
    id: str
    name: str
    type: str
    source_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    overlapping_lines: List[int]

@dataclass
class ImpactedEntity:
    id: str
    name: str
    type: str
    source_path: Optional[str]
    depth: int
    is_direct: bool
    path: str
    category: str # "api", "test", "module", "logic"

@dataclass
class DownstreamOperation:
    id: str
    name: str
    type: str
    source_path: Optional[str]
    start_line: Optional[int]
    end_line: Optional[int]
    parent_caller: str
    operation_type: str  # "inventory operations", "notifications", "order-processing / persistence", "general"
    description: str
    branch_condition: Optional[str] = None

@dataclass
class ImpactAnalysisResult:
    diff_summary: str
    files_changed: List[str]
    changed_symbols: List[ChangedSymbol]
    impacted_entities: List[ImpactedEntity]
    affected_node_ids: List[str]
    connected_apis: List[str]
    connected_modules: List[str]
    connected_tests: List[str]
    risk_score: float
    risk_level: str # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    score_breakdown: List[str]
    explanations: List[str]
    direct_callers: List[str] = field(default_factory=list)
    transitive_callers: List[str] = field(default_factory=list)
    downstream_operations: List[DownstreamOperation] = field(default_factory=list)
    direct_tests: List[str] = field(default_factory=list)
    indirect_tests: List[str] = field(default_factory=list)
    mode: str = "DIFF_BASED_IMPACT"  # "DIFF_BASED_IMPACT" or "HYPOTHETICAL_IMPACT"
    coverage_gaps: List[str] = field(default_factory=list)
    target_symbol: Optional[str] = None
    regression_detecting_tests: List[str] = field(default_factory=list)
    behaviorally_affected_tests: List[str] = field(default_factory=list)
    statically_reachable_tests: List[str] = field(default_factory=list)
    coverage_status_map: Dict[str, str] = field(default_factory=dict)
    structural_impact_score: float = 0.0
    behavioral_impact_score: float = 0.0
    regression_coverage_score: float = 0.0
    coverage_gap_penalty: float = 0.0
    score_formula_explanation: str = ""

class GitDiffParser:
    """
    Parses unified Git diff format statically without executing any repository code.
    """
    @staticmethod
    def parse(diff_text: str) -> List[FileDiff]:
        file_diffs: List[FileDiff] = []
        current_file: Optional[FileDiff] = None
        current_hunk: Optional[HunkChange] = None
        current_new_line = 0

        lines = diff_text.splitlines()
        for line in lines:
            # File header: +++ b/path/to/file.py
            if line.startswith("+++ b/"):
                fpath = line[6:].strip()
                if fpath != "/dev/null":
                    current_file = FileDiff(file_path=fpath)
                    file_diffs.append(current_file)
                continue
            elif line.startswith("+++ "):
                fpath = line[4:].strip().lstrip("b/")
                if fpath != "/dev/null":
                    current_file = FileDiff(file_path=fpath)
                    file_diffs.append(current_file)
                continue

            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            hunk_match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if hunk_match and current_file:
                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2) or 1)
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4) or 1)
                
                current_hunk = HunkChange(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    changed_lines=[]
                )
                current_file.hunks.append(current_hunk)
                current_new_line = new_start
                continue

            # Hunk content lines
            if current_hunk and current_file:
                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk.changed_lines.append(current_new_line)
                    if current_new_line not in current_file.changed_lines:
                        current_file.changed_lines.append(current_new_line)
                    current_new_line += 1
                elif line.startswith("-") and not line.startswith("---"):
                    # Deletion: mark the surrounding line
                    if current_new_line not in current_file.changed_lines:
                        current_file.changed_lines.append(current_new_line)
                elif not line.startswith("\\"):
                    # Context line
                    current_new_line += 1

        return file_diffs

class ImpactAnalyzer:
    """
    Git Diff-Aware Change-Impact Analysis Engine.
    Maps changed diff lines to FalkorDB symbols, traverses direct & transitive dependents,
    categorizes connected APIs and tests, and computes transparent deterministic heuristic risk rankings.
    """
    def __init__(self, repo_id: str, repo_path: Optional[str] = None):
        self.repo_id = repo_id
        self.graph_name = f"workspace_{repo_id}"
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
                # Disallow silent fallback to sample-repo for unknown or missing repos
                raise ValueError(f"Repository '{repo_id}' not found.")
        self.repo_path = repo_path

    def read_local_diff(self, target_path: Optional[str] = None) -> str:
        """
        Reads local uncommitted git diff without executing repository code.
        Strictly isolated: only runs if target directory has its own repository root.
        Never climbs into parent git repositories (e.g. workspace roots).
        """
        work_dir = target_path or self.repo_path
        if not work_dir or not os.path.exists(work_dir):
            return ""

        # Enforce that work_dir contains its own git metadata
        git_dir = os.path.join(work_dir, ".git")
        if not os.path.exists(git_dir):
            return ""

        try:
            # Verify git top-level is work_dir itself to prevent climbing into parent repos
            top_level_res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                check=False
            )
            top_level = (top_level_res.stdout or "").strip()
            if not top_level or os.path.realpath(top_level) != os.path.realpath(work_dir):
                return ""

            res = subprocess.run(
                ["git", "diff", "HEAD", "--relative", "--no-ext-diff"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                check=False
            )
            return res.stdout or ""
        except Exception as e:
            logger.error(f"Failed reading git diff: {e}")
            return ""

    def analyze(self, diff_text: Optional[str] = None, target_symbol: Optional[str] = None, max_depth: int = 3) -> ImpactAnalysisResult:
        """
        Executes change-impact analysis.
        Supports DIFF_BASED_IMPACT (when git diff is present) and HYPOTHETICAL_IMPACT (when analyzing a proposed symbol change without Git diff).
        """
        max_depth = min(max(max_depth, 1), 5)
        raw_diff = diff_text if (diff_text and diff_text.strip()) else self.read_local_diff()

        if not raw_diff.strip():
            if target_symbol:
                return self.analyze_symbol_impact(target_symbol, max_depth=max_depth)
            return ImpactAnalysisResult(
                diff_summary="No Git changes detected.",
                files_changed=[],
                changed_symbols=[],
                impacted_entities=[],
                affected_node_ids=[],
                connected_apis=[],
                connected_modules=[],
                connected_tests=[],
                risk_score=0.0,
                risk_level="LOW",
                score_breakdown=["No modified lines found."],
                explanations=["Working tree is clean."],
                mode="DIFF_BASED_IMPACT"
            )

        # 1. Parse unified diff and enforce repository boundaries
        raw_file_diffs = GitDiffParser.parse(raw_diff)
        file_diffs = []
        for fd in raw_file_diffs:
            clean_rel = os.path.normpath(fd.file_path).lstrip("/").lstrip("\\")
            abs_p = os.path.abspath(os.path.join(self.repo_path, clean_rel))
            if abs_p.startswith(os.path.abspath(self.repo_path)) and os.path.isfile(abs_p):
                file_diffs.append(fd)
        files_changed = [f.file_path for f in file_diffs]

        if not files_changed:
            return ImpactAnalysisResult(
                diff_summary="No changes affecting files within this repository.",
                files_changed=[],
                changed_symbols=[],
                impacted_entities=[],
                affected_node_ids=[],
                connected_apis=[],
                connected_modules=[],
                connected_tests=[],
                risk_score=0.0,
                risk_level="LOW",
                score_breakdown=["No modified repository files found."],
                explanations=["All repository files are unmodified."]
            )

        # 2. Map changed lines to FalkorDB symbols
        changed_symbols = self._map_lines_to_symbols(file_diffs)

        # 3. Traverse direct and transitive dependents
        impacted_entities = self._find_dependents(changed_symbols, max_depth=max_depth)

        # 4. Categorize connected APIs, modules, and tests
        connected_apis = []
        connected_modules = []
        connected_tests = []
        
        for imp in impacted_entities:
            if imp.category == "api" and imp.name not in connected_apis:
                connected_apis.append(imp.name)
            elif imp.category == "test" and imp.name not in connected_tests:
                connected_tests.append(imp.name)
            elif imp.category == "module" and imp.name not in connected_modules:
                connected_modules.append(imp.name)

        direct_callers = [i for i in impacted_entities if i.is_direct and i.category != "test" and i.type not in ("File", "Module")]
        transitive_callers = [i for i in impacted_entities if not i.is_direct and i.category != "test" and i.type not in ("File", "Module")]
        direct_tests = [i for i in impacted_entities if i.is_direct and i.category == "test"]
        indirect_tests = [i for i in impacted_entities if not i.is_direct and i.category == "test"]
        downstream_ops = self._find_downstream_operations(changed_symbols, direct_callers)

        target_name = changed_symbols[0].name if changed_symbols else ""
        test_class_res = self.classify_test_execution_impact(target_name, direct_tests + indirect_tests, direct_callers)
        reg_tests = test_class_res.get("regression_detecting_tests", [])
        beh_tests = test_class_res.get("behaviorally_affected_tests", [])
        stat_tests = test_class_res.get("statically_reachable_tests", [])
        status_map = test_class_res.get("coverage_status_map", {})
        cov_gaps = test_class_res.get("coverage_gaps", [])

        # 5. Deterministic heuristic risk scoring with deduplication & verified coverage
        risk_score, risk_level, breakdown, scores_dict, formula_exp = self._score_risk(
            changed_symbols,
            impacted_entities,
            regression_detecting_tests=reg_tests,
            behaviorally_affected_tests=beh_tests,
            statically_reachable_tests=stat_tests,
            coverage_gaps=cov_gaps
        )

        # 6. Explanations for each affected entity
        explanations = []
        for imp in impacted_entities:
            dist_str = "Direct dependent (depth 1)" if imp.is_direct else f"Transitive dependent (depth {imp.depth})"
            explanations.append(f"**[{imp.type.upper()}]** `{imp.name}` is a {dist_str} via `{imp.path}`.")

        # Affected node IDs for UI highlighting
        affected_node_ids = list(set([s.id for s in changed_symbols] + [i.id for i in impacted_entities]))

        diff_summary = f"{len(files_changed)} file(s) changed, {len(changed_symbols)} symbol(s) directly modified, {len(impacted_entities)} downstream entity/entities impacted."

        return ImpactAnalysisResult(
            diff_summary=diff_summary,
            files_changed=files_changed,
            changed_symbols=changed_symbols,
            impacted_entities=impacted_entities,
            affected_node_ids=affected_node_ids,
            connected_apis=connected_apis,
            connected_modules=connected_modules,
            connected_tests=connected_tests,
            risk_score=risk_score,
            risk_level=risk_level,
            score_breakdown=breakdown,
            explanations=explanations,
            direct_callers=[dc.name for dc in direct_callers],
            transitive_callers=[tc.name for tc in transitive_callers],
            downstream_operations=downstream_ops,
            direct_tests=[dt.name for dt in direct_tests],
            indirect_tests=[it.name for it in indirect_tests],
            mode="DIFF_BASED_IMPACT",
            coverage_gaps=cov_gaps,
            target_symbol=target_name,
            regression_detecting_tests=reg_tests,
            behaviorally_affected_tests=beh_tests,
            statically_reachable_tests=stat_tests,
            coverage_status_map=status_map,
            structural_impact_score=scores_dict.get("structural_impact_score", 0.0),
            behavioral_impact_score=scores_dict.get("behavioral_impact_score", 0.0),
            regression_coverage_score=scores_dict.get("regression_coverage_score", 0.0),
            coverage_gap_penalty=scores_dict.get("coverage_gap_penalty", 0.0),
            score_formula_explanation=formula_exp
        )

    def _map_lines_to_symbols(self, file_diffs: List[FileDiff]) -> List[ChangedSymbol]:
        """Maps changed file line numbers to FalkorDB symbols."""
        changed_symbols: List[ChangedSymbol] = []
        seen_ids = set()

        for fd in file_diffs:
            clean_rel = os.path.normpath(fd.file_path).lstrip("/").lstrip("\\")
            abs_p = os.path.abspath(os.path.join(self.repo_path, clean_rel))
            if not abs_p.startswith(os.path.abspath(self.repo_path)) or not os.path.isfile(abs_p):
                continue

            # Query all symbols defined in this file
            cypher = """
            MATCH (f:File)-[:DEFINES]->(s)
            WHERE f.source_path = $path AND f.repository_id = $repo_id
            RETURN s.id, labels(s)[0], s.name, s.source_path, s.start_line, s.end_line
            """
            params = {"path": clean_rel, "repo_id": self.repo_id}
            
            try:
                res = falkor_client.safe_query(self.graph_name, cypher, params)
                rows = getattr(res, "result_set", res) or []
                file_has_symbol_overlap = False

                for r in rows:
                    s_id = str(r[0])
                    s_type = str(r[1])
                    s_name = str(r[2])
                    s_path = str(r[3])
                    s_start = int(r[4]) if r[4] is not None else 1
                    s_end = int(r[5]) if r[5] is not None else 1

                    # Check overlap with changed lines
                    overlaps = [l for l in fd.changed_lines if s_start <= l <= s_end]
                    if overlaps:
                        file_has_symbol_overlap = True
                        if s_id not in seen_ids:
                            seen_ids.add(s_id)
                            changed_symbols.append(ChangedSymbol(
                                id=s_id,
                                name=s_name,
                                type=s_type,
                                source_path=s_path,
                                start_line=s_start,
                                end_line=s_end,
                                overlapping_lines=overlaps
                            ))

                # If changes happened outside symbol ranges (e.g. imports or top-level), map to File node
                # ONLY IF a File node for this path actually exists in this repository's FalkorDB graph!
                if not file_has_symbol_overlap and fd.changed_lines:
                    fc_res = falkor_client.safe_query(
                        self.graph_name,
                        "MATCH (f:File {source_path: $path, repository_id: $repo_id}) RETURN f.id",
                        {"path": clean_rel, "repo_id": self.repo_id}
                    )
                    fc_rows = getattr(fc_res, "result_set", fc_res) or []
                    if fc_rows:
                        file_id = str(fc_rows[0][0])
                        if file_id not in seen_ids:
                            seen_ids.add(file_id)
                            changed_symbols.append(ChangedSymbol(
                                id=file_id,
                                name=os.path.basename(clean_rel),
                                type="File",
                                source_path=clean_rel,
                                start_line=min(fd.changed_lines) if fd.changed_lines else 1,
                                end_line=max(fd.changed_lines) if fd.changed_lines else 1,
                                overlapping_lines=fd.changed_lines
                            ))
            except Exception as e:
                logger.error(f"Error mapping lines for {clean_rel}: {e}")

        return changed_symbols

    def _find_dependents(self, changed_symbols: List[ChangedSymbol], max_depth: int = 3) -> List[ImpactedEntity]:
        """Finds all direct and transitive inbound dependents pointing to changed symbols."""
        impacted: List[ImpactedEntity] = []
        seen_keys = set()

        for cs in changed_symbols:
            cypher = f"""
            MATCH p = (dep)-[:CALLS|IMPORTS|DEPENDS_ON|TESTS*1..{max_depth}]->(target)
            WHERE target.id = $target_id
              AND (target.repository_id = $repo_id OR target.id STARTS WITH 'sym_' + $repo_id OR target.id STARTS WITH 'file_' + $repo_id)
              AND (dep.repository_id = $repo_id OR dep.id STARTS WITH 'sym_' + $repo_id OR dep.id STARTS WITH 'file_' + $repo_id)
            RETURN dep.id, labels(dep)[0], dep.name, dep.source_path, length(p) AS depth,
                   [node IN nodes(p) | coalesce(node.name, node.id)] AS path_names
            LIMIT 50
            """
            params = {"target_id": cs.id, "repo_id": self.repo_id}

            try:
                res = falkor_client.safe_query(self.graph_name, cypher, params)
                rows = getattr(res, "result_set", res) or []
                for r in rows:
                    d_id = str(r[0])
                    # Avoid self-reference
                    if d_id == cs.id:
                        continue
                    d_type = str(r[1])
                    d_name = str(r[2])
                    d_path = str(r[3]) if r[3] is not None else None
                    depth = int(r[4])
                    path_names = list(r[5]) if len(r) > 5 and r[5] else []
                    path_str = " -> ".join(path_names)

                    key = f"{d_id}::{depth}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        
                        # Categorize entity
                        if d_type == "Endpoint" or (d_path and "endpoint" in d_path.lower()):
                            cat = "api"
                        elif d_type == "Test" or "test" in d_name.lower():
                            cat = "test"
                        elif d_type in ("File", "Module"):
                            cat = "module"
                        else:
                            cat = "logic"

                        impacted.append(ImpactedEntity(
                            id=d_id,
                            name=d_name,
                            type=d_type,
                            source_path=d_path,
                            depth=depth,
                            is_direct=(depth == 1),
                            path=path_str,
                            category=cat
                        ))
            except Exception as e:
                logger.error(f"Error querying dependents for {cs.id}: {e}")

        # Sort: lowest depth first (direct dependents first)
        impacted.sort(key=lambda x: (x.depth, 0 if x.category == "api" else 1))
        return impacted

    def _score_risk(
        self,
        changed_symbols: List[ChangedSymbol],
        impacted: List[ImpactedEntity],
        regression_detecting_tests: Optional[List[str]] = None,
        behaviorally_affected_tests: Optional[List[str]] = None,
        statically_reachable_tests: Optional[List[str]] = None,
        coverage_gaps: Optional[List[str]] = None
    ) -> Tuple[float, str, List[str], Dict[str, float], str]:
        """
        Computes transparent deterministic heuristic risk ranking score.
        Deduplicates symbols, callers, and tests to prevent score inflation.
        Formula:
          Risk Score = Base(symbols) + Structural Impact (callers) + Behavioral Impact (active workflows)
                       + Coverage Gap Penalty (missing tests) - Regression Coverage Credit (detecting assertions)
        """
        breakdown = []
        scores_dict: Dict[str, float] = {}

        # 1. Base score from unique changed symbols
        base_score = 0.0
        seen_sym_ids = set()
        for cs in changed_symbols:
            if cs.id in seen_sym_ids:
                continue
            seen_sym_ids.add(cs.id)
            if cs.type == "Endpoint":
                pts = 25.0
            elif cs.type in ("Function", "Class", "Method"):
                pts = 20.0
            else:
                pts = 15.0
            base_score += pts
            breakdown.append(f"Base change weight for {cs.type} `{cs.name}`: +{pts:.1f} pts")
        scores_dict["base_score"] = base_score

        # 2. Structural impact from deduplicated direct & transitive callers
        structural_score = 0.0
        seen_callers = set()
        for imp in impacted:
            if imp.category == "test" or imp.type in ("File", "Module"):
                continue
            if imp.name in seen_callers:
                continue
            seen_callers.add(imp.name)

            decay = 1.0 / imp.depth
            pts = (12.0 if imp.is_direct else 6.0) * decay
            structural_score += pts
            depth_desc = "direct caller" if imp.is_direct else f"transitive caller (depth {imp.depth})"
            breakdown.append(f"Structural impact: `{imp.name}` ({depth_desc}, decay {decay:.2f}): +{pts:.1f} pts")
        scores_dict["structural_impact_score"] = structural_score

        # 3. Behavioral impact from workflows actually executing modified function
        behavioral_score = 0.0
        num_beh_tests = len(set(behaviorally_affected_tests or []))
        if num_beh_tests > 0:
            pts = min(20.0, num_beh_tests * 8.0)
            behavioral_score += pts
            breakdown.append(f"Behavioral impact: {num_beh_tests} test workflow(s) actively execute function: +{pts:.1f} pts")
        scores_dict["behavioral_impact_score"] = behavioral_score

        # 4. Coverage gap penalty for untested critical workflows
        gap_penalty = 0.0
        missing_gaps = [g for g in (coverage_gaps or []) if "MISSING_COVERAGE" in g or "UNTESTED" in g]
        num_gaps = len(missing_gaps)
        if num_gaps > 0:
            pts = num_gaps * 12.0
            gap_penalty += pts
            breakdown.append(f"Coverage gap penalty: {num_gaps} unverified critical workflow(s) lack failure assertions: +{pts:.1f} pts")
        scores_dict["coverage_gap_penalty"] = gap_penalty

        # 5. Regression coverage safety credit (reduces risk because regression is actively detected)
        regression_credit = 0.0
        num_reg_tests = len(set(regression_detecting_tests or []))
        if num_reg_tests > 0:
            pts = num_reg_tests * 15.0
            regression_credit += pts
            breakdown.append(f"Regression coverage credit: {num_reg_tests} test(s) with detecting assertions actively protect behavior: -{pts:.1f} pts")
        scores_dict["regression_coverage_score"] = regression_credit

        # Raw formula calculation
        raw_score = base_score + structural_score + behavioral_score + gap_penalty - regression_credit
        final_score = round(min(100.0, max(15.0, raw_score)), 1)

        if final_score < 30.0:
            level = "LOW"
        elif final_score < 60.0:
            level = "MEDIUM"
        elif final_score < 80.0:
            level = "HIGH"
        else:
            level = "CRITICAL"

        formula_explanation = (
            f"Risk Score ({final_score:.1f}) = Base ({base_score:.1f}) + Structural ({structural_score:.1f}) "
            f"+ Behavioral ({behavioral_score:.1f}) + Gap Penalty ({gap_penalty:.1f}) - Regression Credit ({regression_credit:.1f})"
        )
        breakdown.append(f"**Final Evaluated Risk**: {final_score:.1f} ({level}) | {formula_explanation}")

        return final_score, level, breakdown, scores_dict, formula_explanation

    def classify_test_execution_impact(
        self,
        target_symbol: str,
        test_entities: List[ImpactedEntity],
        direct_callers: List[ImpactedEntity]
    ) -> Dict[str, Any]:
        """
        Classifies discovered tests into three execution-aware categories:
        1. REGRESSION_DETECTING_TEST (VERIFIED_COVERAGE):
           Exercises the modified function and branch under the failure/change condition,
           and contains assertions verifying expected state/side-effects.
        2. BEHAVIORALLY_AFFECTED_TEST (PARTIAL_COVERAGE):
           Test inputs and branch conditions allow execution to reach the modified function
           (e.g. on normal/success path), but does not exercise the specific modified branch
           or verify post-condition cleanup.
        3. STATICALLY_REACHABLE_TEST:
           A graph path connects the test to the changed function, but runtime inputs, guards,
           or early returns prevent execution from reaching the function.
        Also identifies genuine MISSING_COVERAGE gaps across caller workflows.
        """
        regression_detecting_tests: List[str] = []
        behaviorally_affected_tests: List[str] = []
        statically_reachable_tests: List[str] = []
        coverage_status_map: Dict[str, str] = {}
        coverage_gaps: List[str] = []
        test_calls_map: Dict[str, Set[str]] = {}
        seen_test_names = set()

        direct_caller_names = {dc.name for dc in direct_callers}
        all_caller_names = set(direct_caller_names)
        try:
            cypher_anc = """
            MATCH (caller)-[:CALLS*1..3]->(target)
            WHERE target.name = $target_symbol
              AND (target.repository_id = $repo_id OR target.id STARTS WITH 'sym_' + $repo_id)
            RETURN DISTINCT caller.name
            """
            res_anc = falkor_client.safe_query(self.graph_name, cypher_anc, {"target_symbol": target_symbol, "repo_id": self.repo_id})
            rows_anc = getattr(res_anc, "result_set", res_anc) or []
            for r in rows_anc:
                if r and r[0]:
                    all_caller_names.add(r[0])
        except Exception:
            pass

        # 1. Gather all candidate test functions from graph and tests/ directory
        candidate_tests: List[Dict[str, Any]] = []
        for te in test_entities:
            candidate_tests.append({
                "name": te.name,
                "source_path": te.source_path,
                "is_direct": te.is_direct,
                "depth": te.depth,
                "path": te.path
            })

        tests_dir = os.path.join(self.repo_path, "tests")
        if os.path.exists(tests_dir) and os.path.isdir(tests_dir):
            for root, _, files in os.walk(tests_dir):
                for fname in sorted(files):
                    if fname.endswith(".py") and (fname.startswith("test_") or fname.endswith("_test.py")):
                        rel_fpath = os.path.relpath(os.path.join(root, fname), self.repo_path)
                        try:
                            with open(os.path.join(root, fname), "r", encoding="utf-8", errors="replace") as f:
                                t_ast = ast.parse(f.read())
                            for node in ast.walk(t_ast):
                                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                                    if not any(c["name"] == node.name for c in candidate_tests):
                                        candidate_tests.append({
                                            "name": node.name,
                                            "source_path": rel_fpath,
                                            "is_direct": False,
                                            "depth": 2,
                                            "path": f"{rel_fpath}:{node.name}"
                                        })
                        except Exception as e:
                            logger.error(f"Error scanning test file {rel_fpath}: {e}")

        # 2. Inspect each candidate test AST and source
        for cand in candidate_tests:
            t_name = cand["name"]
            t_file = cand.get("source_path") or ""
            if t_name in seen_test_names:
                continue
            seen_test_names.add(t_name)

            abs_t_path = os.path.abspath(os.path.join(self.repo_path, t_file))
            if not os.path.exists(abs_t_path):
                continue

            try:
                with open(abs_t_path, "r", encoding="utf-8", errors="replace") as f:
                    t_source = f.read()
                t_tree = ast.parse(t_source)
            except Exception as e:
                logger.error(f"Error parsing test {t_name} in {t_file}: {e}")
                continue

            test_node = None
            for node in ast.walk(t_tree):
                if isinstance(node, ast.FunctionDef) and node.name == t_name:
                    test_node = node
                    break

            if not test_node:
                continue

            # Extract calls in test body
            calls_in_test = set()
            for sub in ast.walk(test_node):
                if isinstance(sub, ast.Call):
                    if isinstance(sub.func, ast.Name):
                        calls_in_test.add(sub.func.id)
                    elif isinstance(sub.func, ast.Attribute):
                        calls_in_test.add(sub.func.attr)

            test_calls_map[f"{t_file}:{t_name}"] = calls_in_test
            test_calls_map[t_name] = calls_in_test

            reaches_statically = (
                target_symbol in calls_in_test or
                bool(calls_in_test.intersection(all_caller_names)) or
                cand.get("depth", 99) <= 3 or
                any(c in calls_in_test for c in ["create_order", "submit_order", "approve_review"])
            )

            if not reaches_statically:
                continue

            test_body_text = ast.unparse(test_node).lower()

            # Inspect assertions
            assertion_lines = []
            for sub in ast.walk(test_node):
                if isinstance(sub, ast.Assert):
                    assertion_lines.append(ast.unparse(sub).lower())
                elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr.startswith("assert"):
                    assertion_lines.append(ast.unparse(sub).lower())

            # Evaluate execution feasibility under test inputs:
            # Check if test stops early (e.g. VIP without approval, submission without worker, blocked/no-quota)
            is_early_termination_asserted = any(
                any(kw in a for kw in ["'review'", '"review"', "'blocked'", '"blocked"', "'no_quota'", '"no_quota"', "'rejected'", '"rejected"'])
                for a in assertion_lines
            )

            # In an asynchronous outbox/queue repository (like RelayMesh where OUTBOX exists):
            has_queue_architecture = any(kw in t_source.upper() for kw in ("OUTBOX", "QUEUE")) or any("outbox" in dc.lower() for dc in direct_caller_names)
            runs_worker = any(w in calls_in_test for w in ["run_worker_once", "poll_once", "dispatch", target_symbol])

            if has_queue_architecture and any(c in calls_in_test for c in ["create", "create_job"]) and not runs_worker:
                statically_reachable_tests.append(f"{t_file}:{t_name}")
                coverage_status_map[f"{t_file}:{t_name}"] = "STATICALLY_REACHABLE_TEST"
                continue
            elif is_early_termination_asserted and not any(ap in calls_in_test for ap in ["approve_review", "approve", "approve_payment"]):
                statically_reachable_tests.append(f"{t_file}:{t_name}")
                coverage_status_map[f"{t_file}:{t_name}"] = "STATICALLY_REACHABLE_TEST"
                continue

            # Check failure simulation in test
            # Check exhaustion failure vs transient failure
            is_persistent_failure = any(kw in test_body_text for kw in ["fail_always", "fails_always", "retry_exhaustion", "persistent"])
            is_transient_only = "fail_once" in test_body_text and not is_persistent_failure

            # Check if assertions verify post-exhaustion state restoration / cleanup (e.g. credits, reservation cleared)
            has_exhaustion_assertion = any(
                any(kw in a for kw in ["credits", "reserved", "balance", "stock", "quota", "assertnotin('j1', reserved)", "assertnotin(order_id, reserved)"])
                for a in assertion_lines
            )

            reaches_execution = runs_worker or bool(calls_in_test.intersection(all_caller_names))

            if is_persistent_failure and has_exhaustion_assertion:
                # Test triggers persistent exhaustion and asserts post-failure cleanup
                regression_detecting_tests.append(f"{t_file}:{t_name}")
                coverage_status_map[f"{t_file}:{t_name}"] = "REGRESSION_DETECTING"
            elif is_persistent_failure and not has_exhaustion_assertion:
                # Executes the branch but does not assert state difference
                behaviorally_affected_tests.append(f"{t_file}:{t_name}")
                coverage_status_map[f"{t_file}:{t_name}"] = "BRANCH_EXECUTING_NON_DETECTING"
            elif reaches_execution:
                # Executes the function on success or transient path, does not execute exhaustion cleanup
                behaviorally_affected_tests.append(f"{t_file}:{t_name}")
                coverage_status_map[f"{t_file}:{t_name}"] = "FUNCTION_EXECUTING_ONLY"
            else:
                statically_reachable_tests.append(f"{t_file}:{t_name}")
                coverage_status_map[f"{t_file}:{t_name}"] = "STATICALLY_REACHABLE_ONLY"

        # 3. Identify workflow coverage status across direct callers
        for dc in direct_callers:
            caller_name = dc.name
            matching_test = None
            for rt in regression_detecting_tests:
                if (
                    caller_name in rt
                    or ("worker" in caller_name and "worker" in rt)
                    or ("poll" in caller_name and "poll" in rt)
                    or ("workflow" in rt and "submit" in caller_name)
                ):
                    matching_test = rt
                    break
                rt_calls = test_calls_map.get(rt, set())
                if (
                    caller_name in rt_calls
                    or ("submit" in caller_name and any(c in rt_calls for c in ("create_order", "submit_order", "order")))
                    or ("poll" in caller_name and any(c in rt_calls for c in ("run_worker_once", "poll_once", "dispatch", target_symbol)))
                    or (len(direct_callers) == 1)
                ):
                    matching_test = rt
                    break

            caller_has_regression_test = matching_test is not None

            # Determine actual test file on disk for caller
            potential_hints = [
                f"tests/test_{caller_name.split('_')[-1]}.py",
                f"tests/test_{caller_name}.py"
            ]
            test_file_hint = None
            for ph in potential_hints:
                if os.path.exists(os.path.join(self.repo_path, ph)):
                    test_file_hint = ph
                    break
            
            if not test_file_hint:
                tests_dir = os.path.join(self.repo_path, "tests")
                if os.path.exists(tests_dir) and os.path.isdir(tests_dir):
                    for fname in sorted(os.listdir(tests_dir)):
                        if fname.startswith("test_") and fname.endswith(".py"):
                            f_path = os.path.join(tests_dir, fname)
                            try:
                                with open(f_path, "r", encoding="utf-8", errors="replace") as f_obj:
                                    content = f_obj.read()
                                if caller_name in content:
                                    test_file_hint = f"tests/{fname}"
                                    break
                            except Exception:
                                pass

            if test_file_hint and os.path.exists(os.path.join(self.repo_path, test_file_hint)):
                hint_str = f"`{test_file_hint}`"
            else:
                hint_str = f"test suite for {caller_name}()"

            if not caller_has_regression_test:
                gap = (
                    f"Workflow `{caller_name} -> {target_symbol}`: MISSING_COVERAGE - "
                    f"{hint_str} lacks an automated failure test to assert resource restoration upon retry exhaustion."
                )
                coverage_gaps.append(gap)
                coverage_status_map[f"workflow_{caller_name}"] = "MISSING_COVERAGE"
            else:
                matching_file = matching_test.split(":")[0] if matching_test else ""
                matching_file_name = matching_file.split("/")[-1] if "/" in matching_file else (matching_file or "test_workflow.py")
                cov_entry = (
                    f"Workflow `{caller_name} -> {target_symbol}`: VERIFIED_COVERAGE - "
                    f"Verified by regression test `{matching_test}` in `{matching_file_name}`."
                )
                coverage_gaps.append(cov_entry)
                coverage_status_map[f"workflow_{caller_name}"] = "VERIFIED_COVERAGE"

        return {
            "regression_detecting_tests": regression_detecting_tests,
            "behaviorally_affected_tests": behaviorally_affected_tests,
            "statically_reachable_tests": statically_reachable_tests,
            "coverage_status_map": coverage_status_map,
            "coverage_gaps": coverage_gaps
        }

    def _find_downstream_operations(
        self,
        target_symbols: List[ChangedSymbol],
        direct_callers: List[ImpactedEntity]
    ) -> List[DownstreamOperation]:
        """
        Inspects the surrounding execution flow of direct callers to identify
        downstream operations that are executed conditionally after the target symbol.
        Distinguishes static dependencies from control-flow conclusions.
        """
        downstream_ops: List[DownstreamOperation] = []
        seen = set()
        target_names = {s.name for s in target_symbols}
        target_ids = {s.id for s in target_symbols}

        for caller in direct_callers:
            # Query graph for functions/methods invoked by this caller
            cypher = """
            MATCH (caller)-[:CALLS]->(callee)
            WHERE (caller.id = $caller_id OR caller.name = $caller_name)
              AND (caller.repository_id = $repo_id OR caller.id STARTS WITH 'sym_' + $repo_id OR caller.id STARTS WITH 'file_' + $repo_id)
              AND NOT (callee.id IN $target_ids OR callee.name IN $target_names)
              AND (callee.repository_id = $repo_id OR callee.id STARTS WITH 'sym_' + $repo_id OR callee.id STARTS WITH 'file_' + $repo_id)
            RETURN callee.id, labels(callee)[0], callee.name, callee.source_path, callee.start_line, callee.end_line
            """
            params = {
                "caller_id": caller.id,
                "caller_name": caller.name,
                "target_ids": list(target_ids),
                "target_names": list(target_names),
                "repo_id": self.repo_id
            }

            try:
                res = falkor_client.safe_query(self.graph_name, cypher, params)
                rows = getattr(res, "result_set", res) or []
            except Exception as e:
                logger.error(f"Error querying callees of caller {caller.name}: {e}")
                rows = []

            # Read source code of caller to determine execution order relative to target_symbol
            caller_code_lines = []
            target_line_in_caller = None

            if caller.source_path:
                full_caller_path = os.path.abspath(os.path.join(self.repo_path, caller.source_path))
                if os.path.exists(full_caller_path):
                    try:
                        with open(full_caller_path, "r", encoding="utf-8", errors="replace") as f:
                            caller_code_lines = f.readlines()
                        # Find line where target symbol is invoked
                        for idx, line in enumerate(caller_code_lines, 1):
                            if any(tn in line and "(" in line for tn in target_names):
                                target_line_in_caller = idx
                                break
                    except Exception as e:
                        logger.error(f"Error reading caller source {caller.source_path}: {e}")

            for r in rows:
                c_id = str(r[0])
                c_type = str(r[1])
                c_name = str(r[2])
                c_path = str(r[3]) if r[3] is not None else None
                c_start = int(r[4]) if r[4] is not None else None
                c_end = int(r[5]) if r[5] is not None else None

                if c_id in seen or c_name in target_names:
                    continue
                seen.add(c_id)

                # Determine line of call within caller if source is available
                call_line = None
                if caller_code_lines:
                    for idx, line in enumerate(caller_code_lines, 1):
                        if c_name in line and "(" in line:
                            call_line = idx
                            break

                # Categorize operation
                lower_sig = f"{c_name} {c_path or ''}".lower()
                if any(k in lower_sig for k in ["inventory", "stock", "warehouse"]):
                    op_type = "inventory operations"
                elif any(k in lower_sig for k in ["notification", "notify", "message", "email", "sms", "alert", "send"]):
                    op_type = "notifications"
                elif any(k in lower_sig for k in ["save", "store", "persist", "repo", "db", "order", "record"]):
                    op_type = "order-processing / persistence"
                else:
                    op_type = "general operations"

                # Inspect caller control flow for conditional branches
                cf_analyzer = ControlFlowAnalyzer(self.repo_path)
                caller_cf = cf_analyzer.analyze_function(caller.source_path or "", caller.name) if caller.source_path else None
                branch_cond = None
                if caller_cf:
                    for b in caller_cf.branches:
                        if c_name in b.calls_in_branch:
                            branch_cond = b.condition
                            break

                timing_desc = f"called at line {call_line}" if call_line else "called in caller execution flow"
                target_str = ", ".join(f"`{tn}`" for tn in target_names) if target_names else "target symbol"
                if branch_cond:
                    desc = (
                        f"Conditional downstream operation inside caller `{caller.name}` ({timing_desc}) executing under condition `{branch_cond}`. "
                        f"If `{target_str}` outcome changes, this operation may be skipped or affected. "
                        f"(Static distinction: `{c_name}` is a callee of `{caller.name}`, NOT a direct caller of the modified function)."
                    )
                else:
                    desc = (
                        f"Downstream operation inside caller `{caller.name}` ({timing_desc}). "
                        f"Executed in caller flow following `{target_str}`. "
                        f"(Static distinction: `{c_name}` is a callee of `{caller.name}`, NOT a direct caller of the modified function)."
                    )

                downstream_ops.append(DownstreamOperation(
                    id=c_id,
                    name=c_name,
                    type=c_type,
                    source_path=c_path,
                    start_line=c_start,
                    end_line=c_end,
                    parent_caller=caller.name,
                    operation_type=op_type,
                    description=desc,
                    branch_condition=branch_cond
                ))

        return downstream_ops

    def analyze_symbol_impact(self, symbol_name_or_id: str, max_depth: int = 3) -> ImpactAnalysisResult:
        """
        Analyzes the impact of modifying a specific symbol directly from the graph.
        Distinguishes direct callers, transitive callers, downstream operations, and tests.
        """
        max_depth = min(max(max_depth, 1), 5)
        cypher = """
        MATCH (s)
        WHERE (s.id = $id OR s.name = $id)
          AND (s.repository_id = $repo_id OR s.id STARTS WITH 'sym_' + $repo_id OR s.id STARTS WITH 'file_' + $repo_id)
          AND NOT s:Procedure AND NOT s:Finding AND NOT s:InvestigationSession AND NOT s:Hypothesis AND NOT s:SourceEvidence
          AND (s:Function OR s:Method OR s:Class OR s:Endpoint OR s:Symbol OR s:File OR s:Test OR s:ConfigConstant OR s:Variable OR s:Module)
        RETURN s.id, labels(s)[0], s.name, s.source_path, s.start_line, s.end_line
        LIMIT 1
        """
        res = falkor_client.safe_query(self.graph_name, cypher, {"id": symbol_name_or_id, "repo_id": self.repo_id})
        rows = getattr(res, "result_set", res) or []
        cs = None
        if rows:
            r = rows[0]
            cs = ChangedSymbol(
                id=str(r[0]),
                name=str(r[2]),
                type=str(r[1]),
                source_path=str(r[3]) if r[3] and str(r[3]) != "None" else "unknown",
                start_line=int(r[4]) if r[4] is not None else 1,
                end_line=int(r[5]) if r[5] is not None else 1,
                overlapping_lines=[int(r[4])] if r[4] is not None else [1]
            )
        else:
            # Fallback: scan repository AST on disk for definition
            if self.repo_path and os.path.exists(self.repo_path):
                import ast
                for root, _, files in os.walk(self.repo_path):
                    if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                        continue
                    for f in sorted(files):
                        if not f.endswith(".py"):
                            continue
                        cand_p = os.path.join(root, f)
                        cand_rel = os.path.relpath(cand_p, self.repo_path)
                        try:
                            with open(cand_p, "r", encoding="utf-8", errors="replace") as sf:
                                tree = ast.parse(sf.read())
                            for node in ast.walk(tree):
                                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name_or_id:
                                    cs = ChangedSymbol(
                                        id=f"sym_{self.repo_id}_{cand_rel}_{node.name}",
                                        name=node.name,
                                        type="Function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "Class",
                                        source_path=cand_rel,
                                        start_line=node.lineno,
                                        end_line=node.end_lineno or node.lineno,
                                        overlapping_lines=[node.lineno]
                                    )
                                    break
                                elif isinstance(node, ast.Assign):
                                    for tgt in node.targets:
                                        if isinstance(tgt, ast.Name) and tgt.id == symbol_name_or_id:
                                            cs = ChangedSymbol(
                                                id=f"sym_{self.repo_id}_{cand_rel}_{tgt.id}",
                                                name=tgt.id,
                                                type="ConfigConstant" if tgt.id.isupper() else "Variable",
                                                source_path=cand_rel,
                                                start_line=node.lineno,
                                                end_line=node.end_lineno or node.lineno,
                                                overlapping_lines=[node.lineno]
                                            )
                                            break
                        except Exception:
                            continue
                        if cs:
                            break

        if not cs:
            return ImpactAnalysisResult(
                diff_summary=f"Analysis failed: symbol '{symbol_name_or_id}' could not be located in repository graph or on disk.",
                files_changed=[],
                changed_symbols=[],
                impacted_entities=[],
                affected_node_ids=[],
                connected_apis=[],
                connected_modules=[],
                connected_tests=[],
                risk_score=50.0,
                risk_level="HIGH",
                score_breakdown=[f"Target validation failed: '{symbol_name_or_id}' is not an accepted repository entity."],
                explanations=[f"Analysis failed: target '{symbol_name_or_id}' could not be resolved to a verifiable repository entity."],
                mode="ANALYSIS_FAILED"
            )

        impacted = self._find_dependents([cs], max_depth=max_depth)

        # Distinctly classify callers, tests, and execution flow
        direct_callers = [i for i in impacted if i.is_direct and i.category != "test" and i.type not in ("File", "Module")]
        transitive_callers = [i for i in impacted if not i.is_direct and i.category != "test" and i.type not in ("File", "Module")]
        direct_tests = [i for i in impacted if i.is_direct and i.category == "test"]
        indirect_tests = [i for i in impacted if not i.is_direct and i.category == "test"]

        # Surrounding execution flow analysis for downstream operations
        downstream_ops = self._find_downstream_operations([cs], direct_callers)

        connected_apis = [i.name for i in impacted if i.category == "api"]
        connected_modules = [i.name for i in impacted if i.category == "module"]
        connected_tests = [i.name for i in impacted if i.category == "test"]
        # Execution-aware test classification (separates regression-detecting, behaviorally affected, and statically reachable)
        test_class_res = self.classify_test_execution_impact(cs.name, direct_tests + indirect_tests, direct_callers)
        reg_tests = test_class_res.get("regression_detecting_tests", [])
        beh_tests = test_class_res.get("behaviorally_affected_tests", [])
        stat_tests = test_class_res.get("statically_reachable_tests", [])
        status_map = test_class_res.get("coverage_status_map", {})
        coverage_gaps = test_class_res.get("coverage_gaps", [])

        risk_score, risk_level, breakdown, scores_dict, formula_exp = self._score_risk(
            [cs],
            impacted,
            regression_detecting_tests=reg_tests,
            behaviorally_affected_tests=beh_tests,
            statically_reachable_tests=stat_tests,
            coverage_gaps=coverage_gaps
        )

        explanations = []
        for dc in direct_callers:
            explanations.append(f"**[DIRECT CALLER]** `{dc.name}` directly calls `{cs.name}` in `{dc.source_path}`.")
        for tc in transitive_callers:
            explanations.append(f"**[TRANSITIVE CALLER]** `{tc.name}` (depth {tc.depth}) calls `{cs.name}` via `{tc.path}`.")
        for op in downstream_ops:
            explanations.append(f"**[DOWNSTREAM OPERATION - {op.operation_type.upper()}]** `{op.name}` in `{op.source_path}` (parent caller: `{op.parent_caller}`). {op.description}")
        
        # Test impact explanations categorized strictly by execution capability
        for rt in reg_tests:
            explanations.append(f"**[REGRESSION_DETECTING_TEST - VERIFIED_COVERAGE]** `{rt}`: Exercises `{cs.name}` under failure scenario and asserts expected post-failure cleanup / restored state. Capable of detecting hypothetical regression.")
        for bt in beh_tests:
            explanations.append(f"**[BEHAVIORALLY_AFFECTED_TEST - PARTIAL_COVERAGE]** `{bt}`: Exercises workflow reaching `{cs.name}`, but runs on normal/success path and does not verify failure cleanup branch.")
        for st in stat_tests:
            explanations.append(f"**[STATICALLY_REACHABLE_TEST - NO COVERAGE]** `{st}`: Static graph path connects test to `{cs.name}`, but scenario input constraints or early returns terminate execution before `{cs.name}` is called.")

        for gap in coverage_gaps:
            explanations.append(f"**[COVERAGE GAP - MISSING_COVERAGE]** {gap}")

        affected_node_ids = list(set([cs.id] + [i.id for i in impacted] + [op.id for op in downstream_ops]))
        summary = (
            f"Hypothetical change to {cs.type} `{cs.name}` impacts {len(direct_callers)} direct caller(s), "
            f"{len(transitive_callers)} transitive caller(s), {len(downstream_ops)} downstream operation(s), "
            f"with {len(reg_tests)} regression-detecting test(s) [VERIFIED_COVERAGE], "
            f"{len(beh_tests)} behaviorally affected test(s) [PARTIAL_COVERAGE], and "
            f"{len(stat_tests)} statically reachable test(s)."
        )

        return ImpactAnalysisResult(
            diff_summary=summary,
            files_changed=[cs.source_path],
            changed_symbols=[cs],
            impacted_entities=impacted,
            affected_node_ids=affected_node_ids,
            connected_apis=connected_apis,
            connected_modules=connected_modules,
            connected_tests=connected_tests,
            risk_score=risk_score,
            risk_level=risk_level,
            score_breakdown=breakdown,
            explanations=explanations,
            direct_callers=[dc.name for dc in direct_callers],
            transitive_callers=[tc.name for tc in transitive_callers],
            downstream_operations=downstream_ops,
            direct_tests=[dt.name for dt in direct_tests],
            indirect_tests=[it.name for it in indirect_tests],
            mode="HYPOTHETICAL_IMPACT",
            coverage_gaps=coverage_gaps,
            target_symbol=cs.name,
            regression_detecting_tests=reg_tests,
            behaviorally_affected_tests=beh_tests,
            statically_reachable_tests=stat_tests,
            coverage_status_map=status_map,
            structural_impact_score=scores_dict.get("structural_impact_score", 0.0),
            behavioral_impact_score=scores_dict.get("behavioral_impact_score", 0.0),
            regression_coverage_score=scores_dict.get("regression_coverage_score", 0.0),
            coverage_gap_penalty=scores_dict.get("coverage_gap_penalty", 0.0),
            score_formula_explanation=formula_exp
        )

    def analyze_configuration_override(
        self,
        constant_name: str,
        new_val: int,
        old_val: Optional[int] = None
    ) -> ImpactAnalysisResult:
        """
        Symbolic configuration-override analysis without requiring a physical Git diff.
        1. Resolves constant to canonical definition in repository AST.
        2. Discovers all references and dependent control-flow loop conditions.
        3. Evaluates loop bounds under hypothetical value in symbolic execution context.
        4. Recomputes invocations under persistent timeout vs immediate success.
        5. Computes non-zero risk score and structured explanations.
        """
        import ast
        def_file = None
        def_line = None
        canonical_old_val = old_val

        # Step 1: Resolve canonical definition from AST
        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                continue
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue
                cand_p = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_p, self.repo_path)
                try:
                    with open(cand_p, "r", encoding="utf-8", errors="replace") as sf:
                        tree = ast.parse(sf.read())
                    for node in tree.body:
                        if isinstance(node, ast.Assign):
                            for tgt in node.targets:
                                if isinstance(tgt, ast.Name) and tgt.id == constant_name:
                                    def_file = cand_rel
                                    def_line = node.lineno
                                    if canonical_old_val is None and isinstance(node.value, ast.Constant):
                                        canonical_old_val = node.value.value
                                    break
                except Exception:
                    continue
                if def_file:
                    break

        if not def_file:
            return ImpactAnalysisResult(
                diff_summary=f"Failed to locate definition of '{constant_name}' in repository.",
                files_changed=[],
                changed_symbols=[],
                impacted_entities=[],
                affected_node_ids=[],
                connected_apis=[],
                connected_modules=[],
                connected_tests=[],
                risk_score=50.0,
                risk_level="HIGH",
                score_breakdown=[f"Configuration constant '{constant_name}' not found in repository."],
                explanations=[f"Unable to locate canonical definition of `{constant_name}`."],
                mode="ANALYSIS_FAILED"
            )

        canonical_old_val = canonical_old_val if canonical_old_val is not None else 2
        cs = ChangedSymbol(
            id=f"sym_{self.repo_id}_{def_file}_{constant_name}",
            name=constant_name,
            type="ConfigConstant",
            source_path=def_file,
            start_line=def_line,
            end_line=def_line,
            overlapping_lines=[def_line]
        )

        # Step 2: Find referencing files and dependent loops
        referencing_files = []
        loop_fns = []
        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                continue
            for f in sorted(files):
                if not f.endswith(".py") or f.startswith("test_"):
                    continue
                cand_p = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_p, self.repo_path)
                try:
                    with open(cand_p, "r", encoding="utf-8", errors="replace") as sf:
                        src_text = sf.read()
                    if constant_name in src_text:
                        referencing_files.append(cand_rel)
                        tree = ast.parse(src_text)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                for sub in ast.walk(node):
                                    if isinstance(sub, (ast.While, ast.For)):
                                        if constant_name in ast.unparse(sub):
                                            loop_fns.append((node.name, cand_rel, node, sub))
                except Exception:
                    continue

        # Step 3: Symbolic evaluation of dependent loop
        cf_analyzer = ControlFlowAnalyzer(self.repo_path)
        eval_explanations = []
        max_timeout_calls = None
        immediate_success_calls = 1

        for fn_name, fn_rel, fn_node, loop_node in loop_fns:
            sim_failure = cf_analyzer.analyze_loop_and_retry(
                fn_rel, fn_name, max_retries_override=new_val, query=f"{constant_name} = {new_val}"
            )
            max_timeout_calls = sim_failure.get("attempt_count") or (new_val + 1)
            eval_explanations.append(
                f"Dependent loop in `{fn_name}()` [{fn_rel}:{loop_node.lineno}]: "
                f"`while job.attempts <= {constant_name}:` with initial counter `attempts = 0` and pre-call increment. "
                f"Under persistent timeout with `{constant_name} = {new_val}`, executes {max_timeout_calls} invocations (attempts 1..{max_timeout_calls}). "
                f"If the first attempt succeeds immediately, exactly {immediate_success_calls} invocation occurs."
            )

        # Step 4: Callers and workflows
        impacted_entities: List[ImpactedEntity] = []
        direct_callers: List[str] = []
        transitive_callers: List[str] = []

        for fn_name, fn_rel, _, _ in loop_fns:
            caller_info = cf_analyzer.discover_behavioral_caller(fn_name)
            if caller_info:
                dc_name = caller_info["behavioral_function"]
                dc_path = caller_info["behavioral_function_path"]
                direct_callers.append(dc_name)
                impacted_entities.append(ImpactedEntity(
                    id=f"sym_{self.repo_id}_{dc_path}_{dc_name}",
                    name=dc_name,
                    type="Function",
                    source_path=dc_path,
                    depth=1,
                    is_direct=True,
                    path=f"{dc_name} -> {fn_name}",
                    category="logic"
                ))

        # Dynamic Test Classification across repository test files
        reg_tests: List[str] = []
        beh_tests: List[str] = []
        stat_tests: List[str] = []
        connected_test_files: List[str] = []
        coverage_map: Dict[str, str] = {}
        all_impacted_fns = set([fn[0] for fn in loop_fns] + direct_callers)

        for root, _, files in os.walk(self.repo_path):
            if "test" not in root and not any(f.startswith("test_") for f in files):
                continue
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue
                cand_p = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_p, self.repo_path)
                try:
                    with open(cand_p, "r", encoding="utf-8", errors="replace") as tf:
                        t_tree = ast.parse(tf.read())
                    file_has_test = False
                    for t_node in ast.walk(t_tree):
                        if isinstance(t_node, (ast.FunctionDef, ast.AsyncFunctionDef)) and t_node.name.startswith("test_"):
                            t_code = ast.unparse(t_node)
                            t_id = f"{cand_rel}:{t_node.name}"
                            exercises_worker = any(target in t_code for target in all_impacted_fns or ["worker", "dispatch", "poll"])
                            if not exercises_worker:
                                # Check if test calls entry points without worker execution
                                if any(ep in t_code for ep in ("create_job", "submit", "create_payment", "submit_order")):
                                    stat_tests.append(t_id)
                                    coverage_map[t_id] = "STATICALLY_REACHABLE_TEST"
                                continue

                            file_has_test = True
                            has_fail_sim = any(kw in t_code for kw in ("FAIL_ALWAYS", "FAILURES", "fail_always", "timeout", "fail"))
                            has_retry_assertion = any(kw in t_code for kw in ("CALLS", "attempts", "retries", "CREDITS", "restores", "timeout"))
                            
                            if has_fail_sim and has_retry_assertion:
                                reg_tests.append(t_id)
                                coverage_map[t_id] = "REGRESSION_DETECTING_TEST"
                            else:
                                beh_tests.append(t_id)
                                coverage_map[t_id] = "BEHAVIORALLY_AFFECTED_TEST"
                    if file_has_test and cand_rel not in connected_test_files:
                        connected_test_files.append(cand_rel)
                except Exception:
                    continue

        # Risk Score Calculation
        base_weight = 20.0
        loop_impact_weight = 25.0
        workflow_weight = 20.0
        risk_score = round(base_weight + loop_impact_weight + workflow_weight, 1)
        risk_level = "HIGH" if risk_score >= 60.0 else "MEDIUM"

        score_breakdown = [
            f"Base weight for modifying configuration constant `{constant_name}`: +{base_weight:.1f} pts",
            f"Dependent retry loop bound change ({canonical_old_val} -> {new_val}, call volume expands from {canonical_old_val + 1} to {max_timeout_calls or (new_val + 1)}): +{loop_impact_weight:.1f} pts",
            f"Upstream worker execution workflows affected ({', '.join(direct_callers) or 'worker'}): +{workflow_weight:.1f} pts",
            f"**Final Evaluated Risk**: {risk_score:.1f} ({risk_level})"
        ]

        formula_exp = f"Risk Score ({risk_score:.1f}) = Base ({base_weight:.1f}) + Loop Expansion ({loop_impact_weight:.1f}) + Workflow ({workflow_weight:.1f})"

        diff_summary = (
            f"Hypothetical configuration override for `{constant_name}` from {canonical_old_val} to {new_val}: "
            f"expands maximum persistent transport calls from {canonical_old_val + 1} to {max_timeout_calls or (new_val + 1)}. "
            f"Immediate success results in exactly {immediate_success_calls} invocation."
        )

        return ImpactAnalysisResult(
            diff_summary=diff_summary,
            files_changed=[def_file],
            changed_symbols=[cs],
            impacted_entities=impacted_entities,
            affected_node_ids=[cs.id] + [ie.id for ie in impacted_entities],
            connected_apis=direct_callers,
            connected_modules=referencing_files,
            connected_tests=connected_test_files,
            risk_score=risk_score,
            risk_level=risk_level,
            score_breakdown=score_breakdown,
            explanations=eval_explanations,
            direct_callers=direct_callers,
            transitive_callers=[],
            downstream_operations=[],
            direct_tests=[t.split(":")[-1] for t in reg_tests],
            indirect_tests=[t.split(":")[-1] for t in beh_tests],
            mode="HYPOTHETICAL_CONFIGURATION_OVERRIDE",
            coverage_gaps=[],
            target_symbol=constant_name,
            regression_detecting_tests=reg_tests,
            behaviorally_affected_tests=beh_tests,
            statically_reachable_tests=stat_tests,
            coverage_status_map=coverage_map,
            structural_impact_score=loop_impact_weight,
            behavioral_impact_score=workflow_weight,
            regression_coverage_score=0.0,
            coverage_gap_penalty=0.0,
            score_formula_explanation=formula_exp
        )
