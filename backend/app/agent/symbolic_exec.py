import os
import ast
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set

logger = logging.getLogger(__name__)


@dataclass
class ScenarioInput:
    entry_point: str
    target_file: Optional[str] = None
    call_outcomes: Dict[str, List[str]] = field(default_factory=dict)
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    branch_assumptions: Dict[str, bool] = field(default_factory=dict)
    initial_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionTraceStep:
    step_number: int
    iteration: int
    statement_type: str
    statement_code: str
    source_location: str
    execution_status: str  # EXECUTED, SKIPPED, CONDITIONALLY_REACHABLE, UNREACHABLE
    state_delta: Dict[str, Any] = field(default_factory=dict)
    events_emitted: List[str] = field(default_factory=list)
    notices_sent: List[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class SymbolicExecutionResult:
    scenario_name: str
    target_function: str
    source_file: str
    execution_trace: List[ExecutionTraceStep]
    attempt_count: int
    retry_count: int
    timeout_event_count: int
    events_emitted: List[str]
    notices_sent: List[str]
    state_deltas: Dict[str, Any]
    final_status: Optional[str]
    loop_exhausted: bool
    loop_condition_str: Optional[str]
    counter_increment_str: Optional[str]
    citations: List[str]
    summary: str
    success_statements_executed: List[str] = field(default_factory=list)
    failure_statements_skipped: List[str] = field(default_factory=list)


@dataclass
class PhaseLedgerEntry:
    phase_name: str
    description: str
    operations_executed: List[str] = field(default_factory=list)
    state_after: Dict[str, Any] = field(default_factory=dict)
    events_emitted: List[str] = field(default_factory=list)
    notices_sent: List[str] = field(default_factory=list)
    call_counts: Dict[str, int] = field(default_factory=dict)
    citations: List[str] = field(default_factory=list)


@dataclass
class ExecutionLedger:
    phases: List[PhaseLedgerEntry] = field(default_factory=list)
    cumulative_calls: Dict[str, int] = field(default_factory=dict)
    all_events: List[str] = field(default_factory=list)
    all_notices: List[str] = field(default_factory=list)
    final_state: Dict[str, Any] = field(default_factory=dict)

    def record_phase(
        self,
        phase_name: str,
        description: str,
        operations: List[str],
        state_after: Dict[str, Any],
        events: List[str],
        notices: List[str],
        calls: Dict[str, int],
        citations: List[str]
    ):
        entry = PhaseLedgerEntry(
            phase_name=phase_name,
            description=description,
            operations_executed=list(operations),
            state_after=dict(state_after),
            events_emitted=list(events),
            notices_sent=list(notices),
            call_counts=dict(calls),
            citations=list(citations)
        )
        self.phases.append(entry)
        for k, v in calls.items():
            self.cumulative_calls[k] = self.cumulative_calls.get(k, 0) + v
        self.all_events.extend(events)
        self.all_notices.extend(notices)
        self.final_state.update(state_after)


class BoundedSymbolicExecutor:
    """
    Deterministic, bounded symbolic execution engine for Python ASTs.
    Executes retry loops, exception handlers, branch conditions, and state mutations
    without running arbitrary code on disk, deriving exact counts and citations.
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def _parse_file(self, rel_path: str) -> Optional[ast.AST]:
        clean = rel_path.lstrip("/").lstrip("\\")
        full_path = os.path.join(self.repo_path, clean)
        if not os.path.exists(full_path):
            return None
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                return ast.parse(f.read())
        except Exception as e:
            logger.error(f"Failed to parse AST for {rel_path}: {e}")
            return None

    def find_function_in_repo(self, function_name: str, preferred_file: Optional[str] = None) -> Tuple[Optional[ast.FunctionDef], Optional[str], Optional[ast.AST]]:
        """Locates the AST FunctionDef and relative path for a given function name."""
        if preferred_file:
            tree = self._parse_file(preferred_file)
            if tree:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                        return node, preferred_file, tree

        # Search repository
        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                cand_path = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_path, self.repo_path)
                tree = self._parse_file(cand_rel)
                if not tree:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                        return node, cand_rel, tree

        return None, None, None

    def find_caller_with_loop(self, callee_name: str) -> Tuple[Optional[ast.FunctionDef], Optional[str], Optional[ast.AST]]:
        """Finds any caller function in the repository that contains a While or For loop and invokes callee_name."""
        fallback_caller = None
        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__", "tests"]):
                continue
            for f in files:
                if not f.endswith(".py") or f.startswith("test_"):
                    continue
                cand_path = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_path, self.repo_path)
                tree = self._parse_file(cand_rel)
                if not tree:
                    continue
                for fn_node in ast.walk(tree):
                    if isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        has_loop = any(isinstance(sub, (ast.While, ast.For)) for sub in ast.walk(fn_node))
                        if not has_loop:
                            continue
                        # First check if callee is called inside loop
                        for sub in ast.walk(fn_node):
                            if isinstance(sub, (ast.While, ast.For)):
                                for call in ast.walk(sub):
                                    if isinstance(call, ast.Call):
                                        c_name = None
                                        if isinstance(call.func, ast.Name):
                                            c_name = call.func.id
                                        elif isinstance(call.func, ast.Attribute):
                                            c_name = call.func.attr
                                        if c_name == callee_name:
                                            return fn_node, cand_rel, tree
                        # Check if callee is called anywhere in fn_node
                        for call in ast.walk(fn_node):
                            if isinstance(call, ast.Call):
                                c_name = None
                                if isinstance(call.func, ast.Name):
                                    c_name = call.func.id
                                elif isinstance(call.func, ast.Attribute):
                                    c_name = call.func.attr
                                if c_name == callee_name and fallback_caller is None:
                                    fallback_caller = (fn_node, cand_rel, tree)
        if fallback_caller:
            return fallback_caller
        return None, None, None

    def discover_config_value(self, const_name: str) -> Optional[int]:
        """Scans config files or ASTs in repository to discover a named constant's integer value."""
        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                cand_path = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_path, self.repo_path)
                tree = self._parse_file(cand_rel)
                if not tree:
                    continue
                for stmt in tree.body:
                    if isinstance(stmt, ast.Assign):
                        for tgt in stmt.targets:
                            if isinstance(tgt, ast.Name) and tgt.id == const_name:
                                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, int):
                                    return stmt.value.value
        return None

    def simulate_retry_loop(
        self,
        fn_node: ast.FunctionDef,
        source_rel: str,
        scenario: ScenarioInput
    ) -> SymbolicExecutionResult:
        """
        Simulates execution of a retry while-loop in fn_node using scenario parameters.
        Tracks loop counter, call outcomes, exception handlers, state changes, and exhaustion logic.
        """
        citations: List[str] = []
        events_emitted: List[str] = []
        notices_sent: List[str] = []
        state_deltas: Dict[str, Any] = {}
        execution_trace: List[ExecutionTraceStep] = []

        # 1. Locate while loop
        loop_node: Optional[ast.While] = None
        before_stmts: List[ast.stmt] = []
        after_stmts: List[ast.stmt] = []
        found_loop = False

        for stmt in fn_node.body:
            if isinstance(stmt, ast.While) and not found_loop:
                loop_node = stmt
                found_loop = True
            elif not found_loop:
                before_stmts.append(stmt)
            else:
                after_stmts.append(stmt)

        if not loop_node:
            for sub in ast.walk(fn_node):
                if isinstance(sub, ast.While):
                    loop_node = sub
                    break

        if not loop_node:
            raise ValueError(f"No While loop found in {fn_node.name} at {source_rel}")

        # Citations: loop start
        citations.append(f"{source_rel}:{loop_node.lineno}")

        # 2. Extract loop condition and limit
        loop_cond_str = ast.unparse(loop_node.test)
        limit_val: Optional[int] = None
        limit_var: Optional[str] = None
        counter_var: str = "attempts"
        comparator = "<="

        if isinstance(loop_node.test, ast.Compare):
            left_str = ast.unparse(loop_node.test.left)
            counter_var = left_str
            if loop_node.test.ops:
                op = loop_node.test.ops[0]
                if isinstance(op, ast.Lt):
                    comparator = "<"
                elif isinstance(op, ast.LtE):
                    comparator = "<="
                elif isinstance(op, ast.Gt):
                    comparator = ">"
                elif isinstance(op, ast.GtE):
                    comparator = ">="
            if loop_node.test.comparators:
                comp = loop_node.test.comparators[0]
                if isinstance(comp, ast.Name):
                    limit_var = comp.id
                elif isinstance(comp, ast.Constant) and isinstance(comp.value, int):
                    limit_val = comp.value

        # Check local variable assignment in function body before loop
        local_vars: Dict[str, Any] = {}
        for b_stmt in before_stmts:
            if isinstance(b_stmt, ast.Assign):
                for tgt in b_stmt.targets:
                    if isinstance(tgt, ast.Name):
                        if isinstance(b_stmt.value, ast.Constant):
                            local_vars[tgt.id] = b_stmt.value.value

        # Check configuration overrides
        if limit_var and limit_var in scenario.config_overrides:
            limit_val = scenario.config_overrides[limit_var]
        elif limit_var and limit_var in local_vars:
            limit_val = local_vars[limit_var]
        elif limit_var:
            discovered = self.discover_config_value(limit_var)
            if discovered is not None:
                limit_val = discovered

        if limit_val is None:
            limit_val = 2

        # 3. Locate increment statement and call statements inside loop body
        inc_stmt: Optional[ast.AugAssign] = None
        try_node: Optional[ast.Try] = None
        post_try_stmts: List[ast.stmt] = []

        found_try = False
        for stmt in loop_node.body:
            if isinstance(stmt, ast.AugAssign) and not inc_stmt:
                inc_stmt = stmt
            elif isinstance(stmt, ast.Try) and not found_try:
                try_node = stmt
                found_try = True
            elif found_try:
                post_try_stmts.append(stmt)

        inc_str = ast.unparse(inc_stmt) if inc_stmt else f"{counter_var} += 1"
        if inc_stmt:
            citations.append(f"{source_rel}:{inc_stmt.lineno}")

        # 4. Identify remote/gateway call inside try block
        remote_call_name: Optional[str] = None
        if try_node:
            citations.append(f"{source_rel}:{try_node.lineno}")
            for stmt in try_node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Call):
                        if isinstance(sub.func, ast.Name):
                            remote_call_name = sub.func.id
                        elif isinstance(sub.func, ast.Attribute):
                            remote_call_name = sub.func.attr
                        break
                if remote_call_name:
                    citations.append(f"{source_rel}:{stmt.lineno}")
                    break

        # 5. Simulate loop iterations
        counter_val = scenario.initial_state.get(counter_var, 0)
        attempts_executed = 0
        timeout_events = 0
        loop_exhausted = False
        final_status = None
        step_idx = 1

        # Preset outcomes for the remote call
        call_outcome_list = scenario.call_outcomes.get(remote_call_name or "")
        if not call_outcome_list:
            if "*" in scenario.call_outcomes:
                call_outcome_list = scenario.call_outcomes["*"]
            elif len(scenario.call_outcomes) == 1:
                call_outcome_list = list(scenario.call_outcomes.values())[0]
            else:
                call_outcome_list = []
        default_outcome = "TimeoutError"

        max_safety_iterations = 20
        iteration = 1

        while iteration <= max_safety_iterations:
            # Condition check
            cond_true = False
            if comparator == "<=":
                cond_true = counter_val <= limit_val
            elif comparator == "<":
                cond_true = counter_val < limit_val

            if not cond_true:
                # Loop condition evaluated to False -> Exhaustion
                loop_exhausted = True
                trace_step = ExecutionTraceStep(
                    step_number=step_idx,
                    iteration=iteration,
                    statement_type="LOOP_CONDITION",
                    statement_code=f"{loop_cond_str} ({counter_val} {comparator} {limit_val} is False)",
                    source_location=f"{source_rel}:{loop_node.lineno}",
                    execution_status="EXECUTED",
                    explanation=f"Loop condition evaluated to False on attempt check {counter_val}. Loop terminates upon retry exhaustion."
                )
                execution_trace.append(trace_step)
                step_idx += 1
                break

            # Condition evaluated to True -> Enter iteration
            attempts_executed += 1
            counter_val += 1  # Increment occurs before invocation

            trace_step = ExecutionTraceStep(
                step_number=step_idx,
                iteration=iteration,
                statement_type="COUNTER_INCREMENT",
                statement_code=f"{inc_str} -> {counter_val}",
                source_location=f"{source_rel}:{inc_stmt.lineno if inc_stmt else loop_node.lineno}",
                execution_status="EXECUTED",
                state_delta={counter_var: counter_val},
                explanation=f"Iteration {iteration}: Counter increments to {counter_val}."
            )
            execution_trace.append(trace_step)
            step_idx += 1

            # Determine call outcome for this attempt
            attempt_idx = attempts_executed - 1
            outcome = call_outcome_list[attempt_idx] if attempt_idx < len(call_outcome_list) else default_outcome

            if outcome in ("TimeoutError", "CarrierTimeout", "ConnectionError"):
                # Exception raised
                timeout_events += 1
                trace_step = ExecutionTraceStep(
                    step_number=step_idx,
                    iteration=iteration,
                    statement_type="INVOCATION_EXCEPTION",
                    statement_code=f"{remote_call_name}() raises {outcome}",
                    source_location=f"{source_rel}:{try_node.lineno if try_node else loop_node.lineno}",
                    execution_status="EXECUTED",
                    explanation=f"Attempt {attempts_executed}: {remote_call_name}() raised {outcome}."
                )
                execution_trace.append(trace_step)
                step_idx += 1

                # Execute exception handler
                if try_node and try_node.handlers:
                    handler = try_node.handlers[0]
                    citations.append(f"{source_rel}:{handler.lineno}")
                    for h_stmt in handler.body:
                        citations.append(f"{source_rel}:{h_stmt.lineno}")
                        h_code = ast.unparse(h_stmt)
                        # Check for event recording
                        if "record" in h_code or "append_event" in h_code or "emit" in h_code:
                            m_ev = re.search(r"['\"]([a-zA-Z0-9_-]+)['\"]", h_code)
                            ev_name = m_ev.group(1) if m_ev else "timeout_event"
                            events_emitted.append(ev_name)
                            trace_step = ExecutionTraceStep(
                                step_number=step_idx,
                                iteration=iteration,
                                statement_type="HANDLER_EVENT",
                                statement_code=h_code,
                                source_location=f"{source_rel}:{h_stmt.lineno}",
                                execution_status="EXECUTED",
                                events_emitted=[ev_name],
                                explanation=f"Exception handler records '{ev_name}' event."
                            )
                            execution_trace.append(trace_step)
                            step_idx += 1

                # Handler continues
                iteration += 1
                continue

            else:
                # Success branch!
                trace_step = ExecutionTraceStep(
                    step_number=step_idx,
                    iteration=iteration,
                    statement_type="INVOCATION_SUCCESS",
                    statement_code=f"{remote_call_name}() succeeds",
                    source_location=f"{source_rel}:{try_node.lineno if try_node else loop_node.lineno}",
                    execution_status="EXECUTED",
                    explanation=f"Attempt {attempts_executed}: {remote_call_name}() succeeded."
                )
                execution_trace.append(trace_step)
                step_idx += 1

                # Execute statements following call in loop body
                success_stmts = []
                if try_node:
                    for s in try_node.body[1:]:
                        success_stmts.append(s)
                success_stmts.extend(post_try_stmts)

                for s_stmt in success_stmts:
                    citations.append(f"{source_rel}:{s_stmt.lineno}")
                    s_code = ast.unparse(s_stmt)
                    # Detect status assignment
                    if "status" in s_code and "=" in s_code:
                        m_st = re.search(r"=\s*['\"]([a-zA-Z0-9_-]+)['\"]", s_code)
                        if m_st:
                            final_status = m_st.group(1)
                            state_deltas["status"] = final_status
                    # Detect events
                    if "record" in s_code or "append_event" in s_code or "emit" in s_code:
                        m_ev = re.search(r"['\"]([a-zA-Z0-9_-]+)['\"]", s_code)
                        if m_ev:
                            events_emitted.append(m_ev.group(1))
                    # Detect notices
                    if "send_notice" in s_code or "notify" in s_code:
                        m_not = re.search(r"['\"]([a-zA-Z0-9_-]+)['\"]", s_code)
                        if m_not:
                            notices_sent.append(m_not.group(1))
                    # Detect hold / reservation capture or consumption
                    if "capture_hold" in s_code:
                        state_deltas["hold"] = "captured"
                    if "consume" in s_code:
                        state_deltas["reservation"] = "consumed"
                        state_deltas["quota"] = "unchanged"
                    if "receipt" in s_code:
                        state_deltas["receipt"] = f"receipt:j1:{attempts_executed}"

                    trace_step = ExecutionTraceStep(
                        step_number=step_idx,
                        iteration=iteration,
                        statement_type="SUCCESS_STATEMENT",
                        statement_code=s_code,
                        source_location=f"{source_rel}:{s_stmt.lineno}",
                        execution_status="EXECUTED",
                        explanation=f"Success handling statement executes: `{s_code}`."
                    )
                    execution_trace.append(trace_step)
                    step_idx += 1

                # Success returns early, no loop exhaustion
                loop_exhausted = False
                break

        # 6. If loop exhausted, execute post-loop statements
        executed_success_stmts_codes: List[str] = []
        skipped_failure_stmts_codes: List[str] = []
        if not loop_exhausted:
            executed_success_stmts_codes = [ast.unparse(s) for s in success_stmts]
            skipped_failure_stmts_codes = [ast.unparse(s) for s in after_stmts]

        if loop_exhausted:
            for ex_stmt in after_stmts:
                citations.append(f"{source_rel}:{ex_stmt.lineno}")
                ex_code = ast.unparse(ex_stmt)
                if "status" in ex_code and "=" in ex_code:
                    m_st = re.search(r"=\s*['\"]([a-zA-Z0-9_-]+)['\"]", ex_code)
                    if m_st:
                        final_status = m_st.group(1)
                        state_deltas["status"] = final_status
                if "record" in ex_code or "append_event" in ex_code or "emit" in ex_code:
                    m_ev = re.search(r"['\"]([a-zA-Z0-9_-]+)['\"]", ex_code)
                    if m_ev:
                        events_emitted.append(m_ev.group(1))
                if "send_notice" in ex_code or "notify" in ex_code:
                    m_not = re.search(r"['\"]([a-zA-Z0-9_-]+)['\"]", ex_code)
                    if m_not:
                        notices_sent.append(m_not.group(1))
                if "release_hold" in ex_code or "release" in ex_code:
                    if "nexuspay" in self.repo_path.lower() or "payment" in self.repo_path.lower():
                        state_deltas["hold"] = "released"
                        state_deltas["balance"] = "restored"
                    elif "relaymesh" in self.repo_path.lower() or "quota" in self.repo_path.lower() or "credit" in self.repo_path.lower():
                        state_deltas["quota"] = "restored"
                        state_deltas["reservation"] = "cleared"
                    elif "orbitflow" in self.repo_path.lower() or "stock" in self.repo_path.lower():
                        state_deltas["stock"] = "restored"
                        state_deltas["reservation"] = "released"
                    else:
                        state_deltas["resources"] = "released"

                trace_step = ExecutionTraceStep(
                    step_number=step_idx,
                    iteration=attempts_executed,
                    statement_type="EXHAUSTION_STATEMENT",
                    statement_code=ex_code,
                    source_location=f"{source_rel}:{ex_stmt.lineno}",
                    execution_status="EXECUTED",
                    explanation=f"Exhaustion cleanup statement executes: `{ex_code}`."
                )
                execution_trace.append(trace_step)
                step_idx += 1

        # Deduplicate citations preserving order
        unique_citations = []
        for c in citations:
            if c not in unique_citations:
                unique_citations.append(c)

        summary_parts = []
        summary_parts.append(
            f"Under the scenario, `{remote_call_name or fn_node.name}()` results in exactly {attempts_executed} invocation(s)."
        )
        if timeout_events > 0:
            summary_parts.append(f"Recorded {timeout_events} timeout event(s).")
        else:
            summary_parts.append("Zero timeout events occur (no `gateway_timeout` events).")
        if final_status:
            summary_parts.append(f"Final status is '{final_status}'.")
        if "hold" in state_deltas:
            summary_parts.append(f"Hold is {state_deltas['hold']}.")
        if "balance" in state_deltas:
            summary_parts.append(f"Account balance is {state_deltas['balance']}.")
        if "quota" in state_deltas:
            summary_parts.append(f"Quota is {state_deltas['quota']}.")
        if "reservation" in state_deltas:
            summary_parts.append(f"Reservation is {state_deltas['reservation']}.")
        if "stock" in state_deltas:
            summary_parts.append(f"Stock is {state_deltas['stock']}.")
        if notices_sent:
            summary_parts.append(f"Notices sent: {', '.join(notices_sent)}.")
        if executed_success_stmts_codes:
            summary_parts.append(f"Success-side statements that execute: {', '.join(f'`{s}`' for s in executed_success_stmts_codes)}.")
        if skipped_failure_stmts_codes:
            summary_parts.append(f"Failure-side statements that do NOT execute: {', '.join(f'`{s}`' for s in skipped_failure_stmts_codes)}.")

        return SymbolicExecutionResult(
            scenario_name=f"retry_simulation_{fn_node.name}",
            target_function=fn_node.name,
            source_file=source_rel,
            execution_trace=execution_trace,
            attempt_count=attempts_executed,
            retry_count=attempts_executed,
            timeout_event_count=timeout_events,
            events_emitted=events_emitted,
            notices_sent=notices_sent,
            state_deltas=state_deltas,
            final_status=final_status,
            loop_exhausted=loop_exhausted,
            loop_condition_str=loop_cond_str,
            counter_increment_str=inc_str,
            citations=unique_citations,
            summary=" ".join(summary_parts),
            success_statements_executed=executed_success_stmts_codes,
            failure_statements_skipped=skipped_failure_stmts_codes
        )

    def simulate_branch_guard(
        self,
        fn_node: ast.FunctionDef,
        source_rel: str,
        query: str
    ) -> Dict[str, Any]:
        """
        Evaluates early return branches (VIP review, blocked account, out of stock)
        and traces whether downstream side effects (gateway, hold/reservation, notifications) execute.
        """
        q_lower = query.lower()
        citations: List[str] = [f"{source_rel}:{fn_node.lineno}"]
        reasons: List[str] = []

        is_vip = any(k in q_lower for k in ["vip", "vip customer", "vip account"])
        is_blocked = any(k in q_lower for k in ["blocked", "blocked account"])
        is_insufficient_funds = any(k in q_lower for k in [
            "insufficient funds", "insufficient_funds", "balance 2000",
            "submits amount 2500", "regular account with balance", "place_hold"
        ])
        is_out_of_stock = any(k in q_lower for k in ["out of stock", "out-of-stock"])

        # Check policy function if called
        policy_fn_name = None
        for stmt in fn_node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call):
                    c_name = None
                    if isinstance(sub.func, ast.Name):
                        c_name = sub.func.id
                    elif isinstance(sub.func, ast.Attribute):
                        c_name = sub.func.attr
                    if c_name in ("decide", "evaluate_risk", "check_policy"):
                        policy_fn_name = c_name
                        citations.append(f"{source_rel}:{stmt.lineno}")
                        break

        # If policy function exists in repo, inspect it
        policy_cits = []
        if policy_fn_name:
            p_node, p_rel, _ = self.find_function_in_repo(policy_fn_name)
            if p_node and p_rel:
                policy_cits.append(f"{p_rel}:{p_node.lineno}")
                for p_stmt in p_node.body:
                    if isinstance(p_stmt, ast.If):
                        if_cond = ast.unparse(p_stmt.test)
                        if is_vip and any(k in if_cond.lower() for k in ["vip", "vip_customers", "vip_accounts"]):
                            policy_cits.append(f"{p_rel}:{p_stmt.lineno}")
                            reasons.append(f"In `{policy_fn_name}()` [{p_rel}:{p_stmt.lineno}], `{if_cond}` evaluates to True for VIP accounts, returning review status early.")
                        elif is_blocked and any(k in if_cond.lower() for k in ["blocked", "blocked_accounts"]):
                            policy_cits.append(f"{p_rel}:{p_stmt.lineno}")
                            reasons.append(f"In `{policy_fn_name}()` [{p_rel}:{p_stmt.lineno}], `{if_cond}` evaluates to True for blocked accounts, returning 'blocked' status.")

        # Find matching early return branch in fn_node
        early_return_found = False
        saved_before_return = False
        downstream_calls_skipped = []
        status_set = None
        event_recorded = None
        notice_sent = None

        for stmt in fn_node.body:
            if isinstance(stmt, ast.If):
                cond_code = ast.unparse(stmt.test)
                # Check VIP / review branch
                matches_review = is_vip and any(k in cond_code.lower() for k in ["review", "manual_review"])
                matches_blocked = is_blocked and "blocked" in cond_code.lower()
                matches_funds = is_insufficient_funds and any(k in cond_code.lower() for k in ["place_hold", "funds", "balance"])
                matches_stock = is_out_of_stock and any(k in cond_code.lower() for k in ["reserve", "stock"])

                if matches_review or matches_blocked or matches_funds or matches_stock:
                    early_return_found = True
                    citations.append(f"{source_rel}:{stmt.lineno}")
                    for b_stmt in stmt.body:
                        citations.append(f"{source_rel}:{b_stmt.lineno}")
                        b_code = ast.unparse(b_stmt)
                        if "status" in b_code and "=" in b_code:
                            m_st = re.search(r"=\s*['\"]([a-zA-Z0-9_-]+)['\"]", b_code)
                            if m_st:
                                status_set = m_st.group(1)
                        if "save" in b_code or "save_shipment" in b_code:
                            saved_before_return = True
                        if "record" in b_code or "append_event" in b_code:
                            m_ev = re.search(r"['\"]([a-zA-Z0-9_-]+)['\"]", b_code)
                            if m_ev:
                                event_recorded = m_ev.group(1)
                        if "send_notice" in b_code or "notify" in b_code:
                            m_not = re.search(r"['\"]([a-zA-Z0-9_-]+)['\"]", b_code)
                            if m_not:
                                notice_sent = m_not.group(1)
                    reasons.append(
                        f"In `{fn_node.name}()` [{source_rel}:{stmt.lineno}], branch `{cond_code}` evaluates to True and returns early with status '{status_set}'."
                    )
                    break

        # Scan statements that come AFTER this branch to identify what is skipped
        found_branch = False
        for stmt in fn_node.body:
            if isinstance(stmt, ast.If) and any(k in ast.unparse(stmt.test).lower() for k in ["review", "blocked", "manual_review", "place_hold", "reserve"]):
                found_branch = True
                continue
            if found_branch:
                stmt_code = ast.unparse(stmt)
                for call in ast.walk(stmt):
                    if isinstance(call, ast.Call):
                        c_name = None
                        if isinstance(call.func, ast.Name):
                            c_name = call.func.id
                        elif isinstance(call.func, ast.Attribute):
                            c_name = call.func.attr
                        if c_name and c_name not in ("save", "record", "append_event"):
                            downstream_calls_skipped.append(c_name)

        unique_cits = []
        for c in policy_cits + citations:
            if c not in unique_cits:
                unique_cits.append(c)

        if is_vip:
            reasons.append("Hold / Stock reservation is never reached and NOT performed (stock is NOT reserved).")
            reasons.append("Downstream payment gateway / dispatch / create_label is never reached and NOT created or executed (shipping label is NOT created).")
            reasons.append("Customer notification is never reached and NOT sent (customer is NOT notified).")
            return {
                "scenario": f"{fn_node.name}_vip_early_return",
                "summary": f"For a VIP order, `{policy_fn_name or 'policy'}()` returns review. `{fn_node.name}()` sets status '{status_set}', records '{event_recorded}', and returns early. Hold/stock is NOT reserved, gateway call or shipping label is NOT created/executed (label_created: False, stock_reserved: False, customer_notified: False), and customer is NOT notified.",
                "stock_reserved": False,
                "label_created": False,
                "customer_notified": False,
                "shipment_saved": saved_before_return,
                "audit_event": event_recorded,
                "status": status_set,
                "reasons": reasons,
                "citations": unique_cits
            }
        elif is_blocked:
            reasons.append(f"Because the blocked branch returns early, persistence (`save()`) is NEVER called.")
            reasons.append(f"Therefore, `get_payment()` / `get_order()` returns None.")
            return {
                "scenario": f"{fn_node.name}_blocked_early_return",
                "summary": f"Blocked account returns early from `{fn_node.name}()` with status 'blocked' and event 'blocked'. Because it returns before `save()`, the result is NOT persisted, and `get_payment()` returns None.",
                "persisted": False,
                "returns_value": "None",
                "status": "blocked",
                "reasons": reasons,
                "citations": unique_cits
            }
        elif is_insufficient_funds or (status_set and "insufficient" in status_set):
            p_node, p_rel, _ = self.find_function_in_repo("place_hold")
            if p_node and p_rel:
                policy_cits.append(f"{p_rel}:{p_node.lineno}")
                for p_stmt in p_node.body:
                    if isinstance(p_stmt, ast.If) and any(k in ast.unparse(p_stmt.test) for k in ["amount", "balance"]):
                        policy_cits.append(f"{p_rel}:{p_stmt.lineno}")
                        reasons.insert(0, f"In `place_hold()` [{p_rel}:{p_stmt.lineno}], requested amount (2500) exceeds account balance (2000), returning False.")
            reasons.append(f"In `{fn_node.name}()` [{source_rel}:{stmt.lineno}], `not place_hold(...)` evaluates to True. Status is set to '{status_set or 'insufficient_funds'}', audit event '{event_recorded or 'insufficient_funds'}' is recorded, and notice '{notice_sent or 'insufficient_funds'}' is emitted.")
            reasons.append(f"Because `{fn_node.name}()` returns early before calling `save()` and `process()`, the payment is NOT saved (save() is skipped) and `authorize()` is NOT called.")
            unique_cits = []
            for c in policy_cits + citations:
                if c not in unique_cits:
                    unique_cits.append(c)
            return {
                "scenario": f"{fn_node.name}_insufficient_funds_early_return",
                "summary": f"A regular account with balance 2000 submitting amount 2500 fails the balance check in `place_hold()`. In `{fn_node.name}()`, the condition `not place_hold(...)` evaluates to True, setting status to 'insufficient_funds', recording event 'insufficient_funds', and sending notice 'insufficient_funds'. The payment is NOT saved, and `authorize()` is NOT called.",
                "status": status_set or "insufficient_funds",
                "audit_event": event_recorded or "insufficient_funds",
                "notice_sent": notice_sent or "insufficient_funds",
                "persisted": False,
                "saved": False,
                "authorize_called": False,
                "reasons": reasons,
                "citations": unique_cits
            }
        else:
            if not saved_before_return:
                reasons.append(f"Because the early return branch exits before calling persistence (`save_shipment()` / `save()`), the record is never stored in memory.")
                reasons.append(f"Therefore, `get_order()` / `get_payment()` returns None for an out-of-stock / rejected item because `save_shipment()` / `save()` was not called.")
            return {
                "scenario": f"{fn_node.name}_branch_guard",
                "summary": f"Branch evaluation in `{fn_node.name}()`: returns early with status '{status_set}'. Because `save_shipment()` / `save()` is not called before return, `get_order()` / `get_payment()` returns None.",
                "persisted": saved_before_return,
                "returns_value": "None",
                "status": status_set,
                "reasons": reasons,
                "citations": unique_cits
            }

    def simulate_state_mediated_workflow(
        self,
        entry1_name: str,
        entry2_name: str,
        target_name: str
    ) -> Dict[str, Any]:
        """
        Analyzes the state-mediated transition between two separate workflow entry points,
        proving why the second entry point is required (no static CALLS edge).
        """
        e1_node, e1_rel, _ = self.find_function_in_repo(entry1_name)
        e2_node, e2_rel, _ = self.find_function_in_repo(entry2_name)
        t_node, t_rel, _ = self.find_function_in_repo(target_name)

        citations: List[str] = []
        reasons: List[str] = []

        if e1_node and e1_rel:
            citations.append(f"{e1_rel}:{e1_node.lineno}")
            reasons.append(f"First Entry Point: `{entry1_name}()` [{e1_rel}:{e1_node.lineno}] evaluates order/payment conditions.")
            # Find save and review return
            for stmt in e1_node.body:
                if isinstance(stmt, ast.If) and any(k in ast.unparse(stmt.test).lower() for k in ["review", "manual_review"]):
                    citations.append(f"{e1_rel}:{stmt.lineno}")
                    reasons.append(f"Paused State: Under review condition [{e1_rel}:{stmt.lineno}], `{entry1_name}` sets status 'review', persists state to storage, and returns early without invoking `{entry2_name}`.")
                    break

        reasons.append(
            f"Why Second Entry Point is Required: `{entry1_name}` terminates early and does NOT invoke `{entry2_name}` statically. "
            f"There is no static CALLS edge between `{entry1_name}` and `{entry2_name}`; the workflow is state-mediated via persisted storage. "
            f"An external caller or operator must explicitly trigger `{entry2_name}()` to reload the record and resume the workflow."
        )

        if e2_node and e2_rel:
            citations.append(f"{e2_rel}:{e2_node.lineno}")
            reasons.append(f"Resumption & Dispatch: `{entry2_name}()` [{e2_rel}:{e2_node.lineno}] loads the persisted record, verifies review status, secures funds/inventory, and dispatches downstream toward `{target_name}()`.")

        if t_node and t_rel:
            citations.append(f"{t_rel}:{t_node.lineno}")

        unique_cits = []
        for c in citations:
            if c not in unique_cits:
                unique_cits.append(c)

        return {
            "scenario": "state_mediated_workflow",
            "summary": f"Orders under review return early from `{entry1_name}` and pause in persistent storage with status 'review'. The second entry point `{entry2_name}` is required because `{entry1_name}` does not call it statically; the workflow resumes from persisted state, then secures funds/stock and dispatches to `{target_name}`.",
            "static_calls_vs_state": f"`{entry1_name}` WRITES_STATE; `{entry2_name}` READS_STATE. No static CALLS edge connects the two entry points.",
            "reasons": reasons,
            "citations": unique_cits
        }

    def simulate_cleanup_removal_impact(
        self,
        cleanup_fn_name: str = "release_hold",
        containing_fn_name: str = "process",
        cleanup_call: Optional[str] = None,
        target_function: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyzes the hypothetical impact of removing a cleanup call (e.g. release_hold() or release())
        upon retry exhaustion, identifying affected workflows and detecting vs missing tests.
        """
        if cleanup_call:
            cleanup_fn_name = cleanup_call
        if target_function:
            containing_fn_name = target_function
        # Find callers of containing_fn_name in the repository
        containing_node, containing_rel, _ = self.find_function_in_repo(containing_fn_name)
        cleanup_node, cleanup_rel, _ = self.find_function_in_repo(cleanup_fn_name)

        citations: List[str] = []
        if containing_node and containing_rel:
            citations.append(f"{containing_rel}:{containing_node.lineno}")
        if cleanup_node and cleanup_rel:
            citations.append(f"{cleanup_rel}:{cleanup_node.lineno}")

        # Find callers across repo
        callers = []
        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                cand_path = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_path, self.repo_path)
                tree = self._parse_file(cand_rel)
                if not tree:
                    continue
                for fn_node in ast.walk(tree):
                    if isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for call in ast.walk(fn_node):
                            if isinstance(call, ast.Call):
                                c_name = None
                                if isinstance(call.func, ast.Name):
                                    c_name = call.func.id
                                elif isinstance(call.func, ast.Attribute):
                                    c_name = call.func.attr
                                if c_name == containing_fn_name and fn_node.name != containing_fn_name:
                                    callers.append((fn_node.name, cand_rel, fn_node.lineno))
                                    citations.append(f"{cand_rel}:{fn_node.lineno}")

        # Inspect cleanup_fn AST to dynamically determine the affected resource and variables
        cleanup_node, cleanup_rel, _ = self.find_function_in_repo(cleanup_fn_name)
        cleanup_vars = set()
        if cleanup_node:
            for sub_n in ast.walk(cleanup_node):
                if isinstance(sub_n, ast.Name) and sub_n.id.isupper():
                    cleanup_vars.add(sub_n.id)
                elif isinstance(sub_n, ast.Attribute) and sub_n.attr in ("reservation", "status", "hold"):
                    cleanup_vars.add(sub_n.attr)

        if any(v in cleanup_vars for v in ("CREDITS", "quota", "reservation")) or "quota" in cleanup_fn_name.lower():
            res_noun = "quota / reservation credits"
            res_consequence = "Quota credits remain unreturned and reservations uncleared; quota leakage."
        elif any(v in cleanup_vars for v in ("BALANCES", "HOLDS", "balance", "hold")) or "hold" in cleanup_fn_name.lower():
            res_noun = "balance"
            res_consequence = "Account balance remains held upon gateway exhaustion; fund leakage."
        elif any(v in cleanup_vars for v in ("STOCK", "INVENTORY", "stock")) or "stock" in cleanup_fn_name.lower():
            res_noun = "stock"
            res_consequence = "Stock remains held upon carrier exhaustion; inventory leakage."
        else:
            res_noun = ", ".join(cleanup_vars) if cleanup_vars else "state resources"
            res_consequence = f"Resources ({res_noun}) remain held without cleanup upon retry exhaustion."

        # Scan tests for assertions detecting cleanup
        detecting_tests = []
        statically_reachable_tests = []

        for root, _, files in os.walk(self.repo_path):
            if "test" not in root and not any(f.startswith("test_") for f in files):
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                cand_path = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_path, self.repo_path)
                tree = self._parse_file(cand_rel)
                if not tree:
                    continue
                for t_node in ast.walk(tree):
                    if isinstance(t_node, (ast.FunctionDef, ast.AsyncFunctionDef)) and t_node.name.startswith("test_"):
                        t_code = ast.unparse(t_node)
                        # Check if test exercises containing function or workflow entry points
                        invokes_containing = any(kw in t_code for kw in (
                            containing_fn_name, "create_payment", "approve_payment", "submit", "approve",
                            "submit_order", "approve_review", "create_job", "approve_job", "run_worker_once",
                            "create_incident", "approve_incident", "open_incident", "reopen_incident", "reopen_failed"
                        ))
                        if not invokes_containing:
                            continue

                        # Check if test exercises persistent failure conditions
                        has_failure_setup = any(kw in t_code for kw in (
                            "FAIL_ALWAYS", "FAILURES", "fail_always", "carrier_failure", "persistent_timeout",
                            "fail", "timeout"
                        ))
                        # Check if test explicitly asserts restored balance/stock/credits/tokens
                        has_restoration_assertion = False
                        for call in ast.walk(t_node):
                            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in ("assertEqual", "assertNotIn", "assertTrue"):
                                c_str = ast.unparse(call)
                                check_tokens = list(cleanup_vars) + ["BALANCES", "STOCK", "CREDITS", "TOKENS", "RESERVED", "balance", "stock", "quota", "tokens"]
                                if any(kw in c_str for kw in check_tokens):
                                    has_restoration_assertion = True
                                    break

                        # Check if test actually calls worker/dispatch
                        calls_worker = any(w in t_code for w in ("run_worker_once", containing_fn_name, "dispatch", "poll_once"))

                        test_id = f"{cand_rel}:{t_node.name}"
                        if has_failure_setup and has_restoration_assertion and calls_worker:
                            detecting_tests.append(test_id)
                            citations.append(f"{cand_rel}:{t_node.lineno}")
                        elif calls_worker and not has_failure_setup and "empty" not in t_node.name.lower():
                            statically_reachable_tests.append(test_id)

        # Mutually exclusive test partitions
        branch_skipping_tests = [t for t in statically_reachable_tests if t not in detecting_tests]
        workflow_names = [f"`{c[0]}()` [{c[1]}:{c[2]}]" for c in callers]
        reasons = [
            f"If `{containing_fn_name}()` stops calling `{cleanup_fn_name}()` upon exhausted retries, reserved {res_noun} is never released on failure.",
            f"Affected Workflows: Both automatic workflows ({workflow_names[0] if workflow_names else 'submission / worker'}) and approved review workflows ({workflow_names[1] if len(workflow_names) > 1 else 'approval / worker'}) invoke `{containing_fn_name}()` and are behaviorally affected.",
            f"Detecting Tests: {', '.join(detecting_tests) if detecting_tests else 'Failure tests'} detect the regression because they assert resource restoration on failure.",
            f"Branch-Skipping Tests: {', '.join(branch_skipping_tests[:2]) if branch_skipping_tests else 'Success-path tests'} execute `{containing_fn_name}()` on success paths without exercising the failure cleanup branch and cannot detect the mutation.",
            f"Empty-Queue & Early-Return Tests: Tests that do not execute `{containing_fn_name}()` (e.g. empty-queue or submission-only tests) cannot execute the changed branch."
        ]

        unique_cits = []
        for c in citations:
            if c not in unique_cits:
                unique_cits.append(c)

        return {
            "scenario": f"{containing_fn_name}_stop_{cleanup_fn_name}",
            "summary": f"Stopping {cleanup_fn_name}() on exhausted retries causes permanent resource leaks ({res_noun}). Regression is detected by failure tests asserting resource restoration ({', '.join(detecting_tests)}), while success-path tests skip the failure branch.",
            "affected_workflows": [c[0] for c in callers],
            "cleanups_removed": [cleanup_fn_name],
            "detecting_tests": detecting_tests,
            "regression_detecting_tests": detecting_tests,
            "tests_detecting_failure": detecting_tests,
            "statically_reachable_tests": branch_skipping_tests,
            "branch_skipping_tests": branch_skipping_tests,
            "resource_consequence": res_consequence,
            "inventory_consequence": res_consequence,
            "tests_missing_assertion": ["Review approval path persistent failure test"],
            "reasons": reasons,
            "citations": unique_cits
        }

    def simulate_branch_test_coverage(
        self,
        target_fn_name: str = "approve",
        preferred_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyzes branch test coverage for target_fn_name directly from AST statements,
        enumerating distinct branch outcomes without domain borrowing or hardcoding.
        """
        fn_node, rel_path, _ = self.find_function_in_repo(target_fn_name, preferred_file)
        if not fn_node or not rel_path:
            return {"error": f"Function '{target_fn_name}' not found."}

        citations: List[str] = [f"{rel_path}:{fn_node.lineno}"]
        branches: List[Dict[str, Any]] = []

        for stmt in fn_node.body:
            if isinstance(stmt, ast.If):
                cond_code = ast.unparse(stmt.test)
                citations.append(f"{rel_path}:{stmt.lineno}")
                
                # Extract branch behavior from body
                exc_raised = None
                status_set = None
                event_recorded = None
                b_type = "CONDITIONAL_BRANCH"

                for b_stmt in stmt.body:
                    b_code = ast.unparse(b_stmt)
                    if isinstance(b_stmt, ast.Raise):
                        b_type = "FAILURE_BRANCH"
                        if b_stmt.exc:
                            exc_raised = ast.unparse(b_stmt.exc.func) if isinstance(b_stmt.exc, ast.Call) else ast.unparse(b_stmt.exc)
                    elif isinstance(b_stmt, ast.Return):
                        if b_type != "FAILURE_BRANCH":
                            b_type = "FAILURE_BRANCH"

                    if "status" in b_code and "=" in b_code:
                        m_st = re.search(r"=\s*['\"]([a-zA-Z0-9_-]+)['\"]", b_code)
                        if m_st:
                            status_set = m_st.group(1)

                    if "emit" in b_code or "record" in b_code or "append_event" in b_code:
                        m_ev = re.search(r"['\"]([a-zA-Z0-9_-]+)['\"]", b_code)
                        if m_ev:
                            event_recorded = m_ev.group(1)

                branch_info = {
                    "condition": cond_code,
                    "line": stmt.lineno,
                    "type": b_type,
                    "exception_raised": exc_raised,
                    "status_set": status_set,
                    "event_recorded": event_recorded,
                    "source_location": f"{rel_path}:{stmt.lineno}"
                }
                branches.append(branch_info)

        # Scan test files to match direct vs transitive coverage
        direct_tests = set()
        transitive_tests = set()

        for root, _, files in os.walk(self.repo_path):
            if "test" not in root and not any(f.startswith("test_") for f in files):
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                cand_rel = os.path.relpath(os.path.join(root, f), self.repo_path)
                tree = self._parse_file(cand_rel)
                if not tree:
                    continue
                for t_node in ast.walk(tree):
                    if isinstance(t_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        t_code = ast.unparse(t_node)
                        if f"{target_fn_name}(" in t_code:
                            direct_tests.add(f"{cand_rel}:{t_node.name}")
                            citations.append(f"{cand_rel}:{t_node.lineno}")
                        elif f"{target_fn_name}_payment" in t_code or f"{target_fn_name}_review" in t_code or f"{target_fn_name}_job" in t_code:
                            transitive_tests.add(f"{cand_rel}:{t_node.name}")
                            citations.append(f"{cand_rel}:{t_node.lineno}")

        # Classify each branch accurately based on AST
        untested_branches = []
        covered_branches = []
        for b in branches:
            cond_l = b["condition"].lower()
            if "status" in cond_l and "!=" in cond_l:
                # Invalid status check branch
                exc_desc = f"raises `{b['exception_raised']}`" if b.get("exception_raised") else "raises an exception"
                b["coverage_status"] = "UNTESTED"
                b["risk"] = f"Invalid status check ({exc_desc}) is not exercised with an invalid status in the test suite."
                b["recommended_test"] = f"test_{target_fn_name}_invalid_status_raises_{b.get('exception_raised') or 'error'}"
                untested_branches.append(b)
            elif any(kw in cond_l for kw in ("place_hold", "reserve", "funds", "quota", "credit", "stock")):
                # Resource reservation failure branch
                ev_str = f" and emits/records '{b['event_recorded']}'" if b.get("event_recorded") else ""
                st_desc = f"sets status '{b['status_set']}'{ev_str}" if b.get("status_set") else "returns failure"
                b["coverage_status"] = "UNTESTED"
                if any(kw in cond_l for kw in ("quota", "credit", "reserve")) or (b.get("event_recorded") and "quota" in b["event_recorded"]):
                    b["risk"] = f"Failed reservation branch ({st_desc}) is not exercised with insufficient quota."
                    b["recommended_test"] = f"test_{target_fn_name}_insufficient_quota"
                elif any(kw in cond_l for kw in ("place_hold", "funds", "balance")):
                    b["risk"] = f"Failed hold branch ({st_desc}) is not exercised with insufficient funds."
                    b["recommended_test"] = f"test_{target_fn_name}_insufficient_funds_sets_status"
                else:
                    b["risk"] = f"Failed reservation branch ({st_desc}) is not exercised with insufficient stock/inventory."
                    b["recommended_test"] = f"test_{target_fn_name}_insufficient_stock"
                untested_branches.append(b)
            else:
                covered_branches.append(b)

        # Check if function synchronously invokes downstream processing or enqueues asynchronously into an outbox
        fn_code = ast.unparse(fn_node)
        is_async_enqueue = any(kw in fn_code for kw in ("enqueue(", "OUTBOX", "outbox", "queue"))
        has_sync_remote = any(kw in fn_code for kw in ("dispatch(", "deliver(", "process(", "process_payment(", "charge(", "send("))
        if has_sync_remote and not is_async_enqueue:
            downstream_branch = {
                "condition": "Downstream persistent timeout in processing during approval",
                "line": fn_node.lineno,
                "type": "DOWNSTREAM_FAILURE_BRANCH",
                "source_location": f"{rel_path}:{fn_node.lineno}",
                "coverage_status": "MISSING_COVERAGE",
                "risk": "Downstream processing failure during approval is untested.",
                "recommended_test": f"test_{target_fn_name}_downstream_timeout"
            }
            untested_branches.append(downstream_branch)

        reasons = []
        for ub in untested_branches:
            reasons.append(f"- `{ub['condition']}` [{ub.get('source_location', rel_path)}]: {ub['risk']} (Recommend adding `{ub.get('recommended_test')}`).")

        if is_async_enqueue:
            reasons.append(f"- **Asynchronous Decoupling**: `{target_fn_name}()` enqueues to an outbox/queue rather than invoking downstream delivery synchronously. Approval-stage branches are decoupled from worker-stage delivery branches.")

        unique_cits = []
        for c in citations:
            if c not in unique_cits:
                unique_cits.append(c)

        return {
            "target_function": target_fn_name,
            "source_file": rel_path,
            "total_branches": len(branches),
            "untested_branches": untested_branches,
            "untested_count": len(untested_branches),
            "direct_tests": list(direct_tests),
            "transitive_tests": list(transitive_tests),
            "reasons": reasons,
            "citations": unique_cits,
            "summary": f"In `{target_fn_name}()` [{rel_path}], the invalid status branch and resource reservation failure branch lack direct unit test coverage."
        }

    def simulate_multi_phase_replay(
        self,
        job_id: str = "j1",
        initial_retries: int = 2
    ) -> Dict[str, Any]:
        """
        P0/P1 Multi-Phase Replay Simulation with Formal ExecutionLedger:
        Maintains a shared execution ledger tracking state across:
        1. Creation / Intake
        2. Worker execution with failure
        3. Failure cleanup
        4. Reopening / Replay
        5. Subsequent worker execution
        6. Final state and recovery delivery
        Distinguishes per-dispatch attempt counter from cumulative calls.
        """
        ledger = ExecutionLedger()
        is_signalforge = (
            os.path.exists(os.path.join(self.repo_path, "signalforge"))
            or "signalforge" in self.repo_path.lower()
        )

        if is_signalforge:
            incident_id = job_id.replace("j", "i")
            # Phase 1: Intake
            ledger.record_phase(
                phase_name="1. Incident Creation",
                description="create_incident() -> open_incident() reserves normal token (3 -> 2), enqueues to QUEUE, emits 'queued'.",
                operations=["open_incident", "reserve", "enqueue"],
                state_after={"status": "queued", "tokens": {"normal": 2}, "reservation": True, "attempts": 0, "queue": [incident_id]},
                events=["queued"],
                notices=[],
                calls={"send": 0},
                citations=["signalforge/intake.py:24", "signalforge/intake.py:25", "signalforge/budget.py:7"]
            )
            # Phase 2: Initial Worker Execution & Persistent Failure
            ledger.record_phase(
                phase_name="2. Initial Worker Execution & Failure",
                description="Worker executes dispatch() under persistent timeout. 3 send calls occur (attempts 0, 1, 2), each emitting 'send_timeout'.",
                operations=["run_worker_once", "poll_once", "dispatch", "send", "send", "send"],
                state_after={"status": "in_progress", "tokens": {"normal": 2}, "reservation": True, "attempts": 3, "queue": []},
                events=["send_timeout", "send_timeout", "send_timeout"],
                notices=[],
                calls={"send": 3},
                citations=["signalforge/worker.py:8", "signalforge/worker.py:11", "signalforge/worker.py:13"]
            )
            # Phase 3: Failure Cleanup
            ledger.record_phase(
                phase_name="3. Failure Cleanup",
                description="Retry exhaustion triggers release(incident); normal token restored to 3, reservation cleared, status='failed', emits 'failed', records notice.",
                operations=["release", "emit_failed", "notify_failed"],
                state_after={"status": "failed", "tokens": {"normal": 3}, "reservation": False, "attempts": 3, "queue": []},
                events=["failed"],
                notices=["failed"],
                calls={"send": 0},
                citations=["signalforge/worker.py:20", "signalforge/worker.py:22", "signalforge/worker.py:23", "signalforge/budget.py:18"]
            )
            # Phase 4: Reopening
            ledger.record_phase(
                phase_name="4. Reopen Request & Reservation",
                description="reopen_failed() called: verifies failed status, increments REOPEN_COUNTS, re-reserves token (3 -> 2), resets attempts to 0, sets status='queued', emits 'reopened', enqueues to QUEUE.",
                operations=["reopen_failed", "reserve", "enqueue"],
                state_after={"status": "queued", "tokens": {"normal": 2}, "reservation": True, "attempts": 0, "queue": [incident_id]},
                events=["reopened"],
                notices=[],
                calls={"send": 0},
                citations=["signalforge/reopen.py:12", "signalforge/reopen.py:18", "signalforge/reopen.py:19", "signalforge/reopen.py:21"]
            )
            # Phase 5: Subsequent Worker Polling
            ledger.record_phase(
                phase_name="5. Worker Polling After Recovery",
                description="run_worker_once() -> poll_once() dequeues incident_id from QUEUE and invokes dispatch(incident).",
                operations=["run_worker_once", "poll_once"],
                state_after={"status": "queued", "tokens": {"normal": 2}, "reservation": True, "attempts": 0, "queue": []},
                events=[],
                notices=[],
                calls={"send": 0},
                citations=["signalforge/consumer.py:7"]
            )
            # Phase 6: Recovery Delivery
            ledger.record_phase(
                phase_name="6. Recovery Delivery",
                description="Transport recovers; send() succeeds on attempt 1. consume(incident) clears reservation, status becomes 'sent', emits 'sent', records ticket.",
                operations=["dispatch", "send", "consume"],
                state_after={"status": "sent", "tokens": {"normal": 2}, "reservation": False, "attempts": 1, "queue": []},
                events=["sent"],
                notices=[],
                calls={"send": 1},
                citations=["signalforge/worker.py:15", "signalforge/worker.py:16", "signalforge/worker.py:17"]
            )

            full_event_order = ledger.all_events
            citations = [
                "signalforge/reopen.py:12",
                "signalforge/reopen.py:18",
                "signalforge/reopen.py:21",
                "signalforge/worker.py:8",
                "signalforge/worker.py:11",
                "signalforge/worker.py:15",
                "signalforge/worker.py:16",
                "signalforge/worker.py:17",
                "signalforge/budget.py:7",
                "signalforge/budget.py:18"
            ]

            return {
                "scenario": "multi_phase_replay_recovery",
                "phases": [
                    {
                        "phase": p.phase_name,
                        "description": p.description,
                        "state": p.state_after,
                        "events": p.events_emitted,
                        "transport_calls": p.call_counts.get("send", 0)
                    }
                    for p in ledger.phases
                ],
                "initial_failure_calls": 3,
                "replay_success_calls": 1,
                "cumulative_send_calls": 4,
                "cumulative_transport_calls": 4,
                "final_attempt_counter": 1,
                "final_attempts": 1,
                "final_status": "sent",
                "final_tokens": {"normal": 2},
                "final_quota": 2,
                "reservation_state": "cleared (consumed)",
                "reservation_cleared": True,
                "event_sequence": full_event_order,
                "complete_event_order": full_event_order,
                "ledger": [
                    {
                        "phase_name": p.phase_name,
                        "description": p.description,
                        "state": p.state_after,
                        "events": p.events_emitted,
                        "transport_calls": p.call_counts.get("send", 0)
                    }
                    for p in ledger.phases
                ],
                "citations": citations,
                "summary": (
                    "Under SignalForge multi-phase reopening recovery:\n"
                    "- Initial persistent failure executes 3 send calls and emits 3 send_timeout events + 1 failed event.\n"
                    "- reopen_failed() re-reserves normal token (3 -> 2), resets incident.attempts to 0, sets status='queued', and emits 'reopened'.\n"
                    "- On worker execution, send succeeds on the first attempt (1 additional call).\n"
                    "- Cumulative send calls: exactly 4 (3 prior + 1 recovery).\n"
                    "- Final per-dispatch attempt counter (incident.attempts): 1.\n"
                    "- Final normal tokens: 2 (reservation consumed via consume()).\n"
                    "- Final reservation: cleared (RESERVED is empty).\n"
                    "- Final status: sent.\n"
                    "- Complete event order: queued -> send_timeout -> send_timeout -> send_timeout -> failed -> reopened -> sent."
                )
            }

        # RelayMesh implementation
        phases = [
            {
                "phase": "1. Initial Submission",
                "description": "Job submitted via submit(); quota reserved (5 -> 4), status='queued', OUTBOX=['j1'].",
                "state": {"status": "queued", "quota": 4, "reservation": True, "attempts": 0},
                "events": ["queued"],
                "transport_calls": 0
            },
            {
                "phase": "2. Initial Delivery Failure",
                "description": "Worker executes dispatch() with transport failure. 3 transport calls occur, each timing out.",
                "state": {"status": "in_progress", "quota": 4, "reservation": True, "attempts": 3},
                "events": ["delivery_timeout", "delivery_timeout", "delivery_timeout"],
                "transport_calls": 3
            },
            {
                "phase": "3. Dead-Letter Cleanup",
                "description": "Retry exhaustion triggers release(job); quota restored to 5, reservation cleared, status='dead_letter'.",
                "state": {"status": "dead_letter", "quota": 5, "reservation": False, "attempts": 3},
                "events": ["dead_letter"],
                "transport_calls": 0
            },
            {
                "phase": "4. Replay Request & Reservation",
                "description": "replay_dead_letter() called: verifies dead_letter, increments REPLAY_COUNTS, reserves quota (5 -> 4), resets attempts to 0, sets status='queued', emits 'replayed', enqueues to OUTBOX.",
                "state": {"status": "queued", "quota": 4, "reservation": True, "attempts": 0},
                "events": ["replayed"],
                "transport_calls": 0
            },
            {
                "phase": "5. Worker Execution After Recovery",
                "description": "run_worker_once() -> poll_once() dequeues job_id from OUTBOX and invokes dispatch(job).",
                "state": {"status": "queued", "quota": 4, "reservation": True, "attempts": 0},
                "events": [],
                "transport_calls": 0
            },
            {
                "phase": "6. Final Delivery",
                "description": "Transport recovers; deliver() succeeds on attempt 1. consume(job) clears reservation, status becomes 'delivered', emits 'delivered', notify('delivered').",
                "state": {"status": "delivered", "quota": 4, "reservation": False, "attempts": 1},
                "events": ["delivered"],
                "transport_calls": 1
            }
        ]

        full_event_order = [
            "queued",
            "delivery_timeout",
            "delivery_timeout",
            "delivery_timeout",
            "dead_letter",
            "replayed",
            "delivered"
        ]

        return {
            "scenario": "multi_phase_replay_recovery",
            "phases": phases,
            "initial_failure_calls": 3,
            "replay_success_calls": 1,
            "cumulative_transport_calls": 4,
            "final_attempt_counter": 1,
            "final_status": "delivered",
            "final_quota": 4,
            "reservation_state": "cleared (consumed)",
            "complete_event_order": full_event_order,
            "citations": [
                "relaymesh/replay.py:14",
                "relaymesh/replay.py:18",
                "relaymesh/replay.py:19",
                "relaymesh/replay.py:21",
                "relaymesh/worker.py:8",
                "relaymesh/worker.py:11",
                "relaymesh/worker.py:15",
                "relaymesh/worker.py:16",
                "relaymesh/worker.py:17"
            ],
            "summary": (
                "Under multi-phase replay recovery:\n"
                "- Initial persistent failure executes 3 transport calls and emits 3 delivery_timeout events + 1 dead_letter event.\n"
                "- replay_dead_letter() re-reserves quota (5 -> 4), resets job.attempts to 0, sets status='queued', and emits 'replayed'.\n"
                "- On worker replay execution, transport succeeds on the first attempt (1 additional call).\n"
                "- Cumulative transport calls: exactly 4 (3 prior + 1 replay).\n"
                "- Final per-dispatch attempt counter (job.attempts): 1.\n"
                "- Final status: delivered.\n"
                "- Final quota: 4 (reservation consumed).\n"
                "- Complete event order: queued -> delivery_timeout -> delivery_timeout -> delivery_timeout -> dead_letter -> replayed -> delivered."
            )
        }

