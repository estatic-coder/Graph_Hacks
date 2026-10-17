"""
app/agent/planner.py - Composable multi-capability investigation planner.

Replaces rigid single-intent routing with typed dependency DAGs.
Decomposes user inquiries into composable analysis capabilities:
- SYMBOL_RESOLUTION
- CALL_GRAPH_TRAVERSAL
- REVERSE_CALLER_DISCOVERY
- CONTROL_FLOW_ANALYSIS
- LOOP_EXECUTION_ANALYSIS
- EXCEPTION_FLOW_ANALYSIS
- SCENARIO_SIMULATION
- STATE_MUTATION_ANALYSIS
- STATE_TRANSITION_ANALYSIS
- CONFIGURATION_IMPACT
- HYPOTHETICAL_CHANGE_IMPACT
- TEST_DISCOVERY
- BRANCH_TEST_COVERAGE
- NEGATIVE_EVIDENCE_SEARCH
- SOURCE_EVIDENCE
- ANSWER_SYNTHESIS
"""

import uuid
import re
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.agent.context import InvestigationContext
from app.agent.intent import IntentResult, IntentResult as QueryIntent
from app.agent.resolver import ResolvedEntity, EntityOrigin


class InvestigationCapability(str, Enum):
    SYMBOL_RESOLUTION = "SYMBOL_RESOLUTION"
    CALL_GRAPH_TRAVERSAL = "CALL_GRAPH_TRAVERSAL"
    REVERSE_CALLER_DISCOVERY = "REVERSE_CALLER_DISCOVERY"
    CONTROL_FLOW_ANALYSIS = "CONTROL_FLOW_ANALYSIS"
    LOOP_EXECUTION_ANALYSIS = "LOOP_EXECUTION_ANALYSIS"
    EXCEPTION_FLOW_ANALYSIS = "EXCEPTION_FLOW_ANALYSIS"
    SCENARIO_SIMULATION = "SCENARIO_SIMULATION"
    STATE_MUTATION_ANALYSIS = "STATE_MUTATION_ANALYSIS"
    STATE_TRANSITION_ANALYSIS = "STATE_TRANSITION_ANALYSIS"
    CONFIGURATION_IMPACT = "CONFIGURATION_IMPACT"
    HYPOTHETICAL_CHANGE_IMPACT = "HYPOTHETICAL_CHANGE_IMPACT"
    TEST_DISCOVERY = "TEST_DISCOVERY"
    BRANCH_TEST_COVERAGE = "BRANCH_TEST_COVERAGE"
    NEGATIVE_EVIDENCE_SEARCH = "NEGATIVE_EVIDENCE_SEARCH"
    SOURCE_EVIDENCE = "SOURCE_EVIDENCE"
    ANSWER_SYNTHESIS = "ANSWER_SYNTHESIS"


class PlanStep(BaseModel):
    step_id: str
    capability: InvestigationCapability
    description: str
    target_symbol: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, SKIPPED, FAILED
    result: Optional[Dict[str, Any]] = None


class InvestigationPlan(BaseModel):
    query_id: str
    query_text: str
    repository_id: str
    steps: List[PlanStep] = Field(default_factory=list)
    execution_order: List[str] = Field(default_factory=list)

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def mark_completed(self, step_id: str, result: Dict[str, Any]):
        step = self.get_step(step_id)
        if step:
            step.status = "COMPLETED"
            step.result = result

    def mark_failed(self, step_id: str, error: str):
        step = self.get_step(step_id)
        if step:
            step.status = "FAILED"
            step.result = {"error": error}


class InvestigationPlanner:
    """
    Constructs typed dependency DAGs for queries requiring multiple simultaneous capabilities.
    Distinguishes user intent from analyzer implementation details.
    """

    def __init__(self, repo_id: str, repo_path: str):
        self.repo_id = repo_id
        self.repo_path = repo_path

    def compile_plan(
        self,
        question: str,
        intent: QueryIntent,
        resolved_entities: List[ResolvedEntity],
        context: Optional[InvestigationContext] = None,
    ) -> InvestigationPlan:
        q_id = str(uuid.uuid4())[:8]
        q_lower = question.lower()
        steps: List[PlanStep] = []
        exec_order: List[str] = []

        # Step 1: Entity Resolution & Grounding
        s1 = PlanStep(
            step_id="step_resolve_symbols",
            capability=InvestigationCapability.SYMBOL_RESOLUTION,
            description="Ground mentioned and implicit domain entities against active repository graph",
            parameters={"candidates": intent.candidate_entities},
            depends_on=[],
        )
        steps.append(s1)
        exec_order.append(s1.step_id)

        # Check for Negative Evidence Intent
        is_negative = intent.primary_intent == "NEGATIVE_EVIDENCE_SEARCH" or any(
            t in q_lower for t in ("kafka", "rabbitmq", "celery", "slack", "external database")
        )
        if is_negative:
            s_neg = PlanStep(
                step_id="step_negative_evidence",
                capability=InvestigationCapability.NEGATIVE_EVIDENCE_SEARCH,
                description="Systematically verify absence of unintegrated external technology",
                parameters={"query": question},
                depends_on=["step_resolve_symbols"],
            )
            steps.append(s_neg)
            exec_order.append(s_neg.step_id)

        # Check for Loop / Retry / Exception Analysis
        is_retry = intent.primary_intent in ("LOOP_EXECUTION_ANALYSIS", "CONFIGURATION_IMPACT") or any(
            kw in q_lower for kw in ("timeout", "retry", "retries", "attempts", "how many calls", "how many attempts")
        )
        if is_retry:
            s_loop = PlanStep(
                step_id="step_loop_execution",
                capability=InvestigationCapability.LOOP_EXECUTION_ANALYSIS,
                description="Perform bounded symbolic execution of retry loops and catch handlers",
                parameters={"query": question},
                depends_on=["step_resolve_symbols"],
            )
            steps.append(s_loop)
            exec_order.append(s_loop.step_id)

            s_state = PlanStep(
                step_id="step_state_mutation",
                capability=InvestigationCapability.STATE_MUTATION_ANALYSIS,
                description="Trace balance/stock, hold, and audit event mutations under loop exhaustion or transient success",
                parameters={"query": question},
                depends_on=["step_loop_execution"],
            )
            steps.append(s_state)
            exec_order.append(s_state.step_id)

        # Check for State-Mediated Workflow / Branch Transition
        is_workflow = intent.primary_intent == "STATE_TRANSITION_ANALYSIS" or any(
            kw in q_lower for kw in (
                "second entry point", "submit_order to approve", "create_payment through",
                "state-mediated", "from create_", "trace a vip", "trace a vip job",
                "from create_job() to approve_job()", "to run_worker_once",
                "crosses an outbox", "outbox/state handoff", "queue producer/consumer"
            )
        )
        if is_workflow:
            s_wf = PlanStep(
                step_id="step_workflow_transition",
                capability=InvestigationCapability.STATE_TRANSITION_ANALYSIS,
                description="Model multi-entrypoint resumption through persisted storage versus static call edges",
                parameters={"query": question},
                depends_on=["step_resolve_symbols"],
            )
            steps.append(s_wf)
            exec_order.append(s_wf.step_id)

        # Check for Branch Guard / VIP / Blocked
        is_guard = any(kw in q_lower for kw in ("vip", "blocked", "out of stock", "insufficient funds"))
        if is_guard and not is_retry:
            s_guard = PlanStep(
                step_id="step_branch_guard",
                capability=InvestigationCapability.CONTROL_FLOW_ANALYSIS,
                description="Trace policy evaluation, early return branches, and absence of downstream actions",
                parameters={"query": question},
                depends_on=["step_resolve_symbols"],
            )
            steps.append(s_guard)
            exec_order.append(s_guard.step_id)

        # Check for Hypothetical Change Impact
        is_change = intent.primary_intent == "CHANGE_IMPACT_ANALYSIS" or any(
            kw in q_lower for kw in ("remove", "stops calling", "change", "hypothetically")
        )
        if is_change:
            s_chg = PlanStep(
                step_id="step_change_impact",
                capability=InvestigationCapability.HYPOTHETICAL_CHANGE_IMPACT,
                description="Analyze behavioral delta of statement removal across feasible callers and detecting tests",
                parameters={"query": question},
                depends_on=["step_resolve_symbols"],
            )
            steps.append(s_chg)
            exec_order.append(s_chg.step_id)

        # Check for Branch-Level Test Coverage
        is_cov = intent.primary_intent == "BRANCH_TEST_COVERAGE" or any(
            kw in q_lower for kw in ("untested", "lack direct test", "coverage", "missing tests")
        )
        if is_cov:
            s_cov = PlanStep(
                step_id="step_branch_coverage",
                capability=InvestigationCapability.BRANCH_TEST_COVERAGE,
                description="Enumerate failure branches and evaluate test inputs and assertion effectiveness",
                parameters={"query": question},
                depends_on=["step_resolve_symbols"],
            )
            steps.append(s_cov)
            exec_order.append(s_cov.step_id)

        # Call Graph Traversal (always useful when call paths are asked)
        is_call_path = "CALL_PATH_ANALYSIS" in intent.primary_intent or "path" in q_lower or "call" in q_lower
        if is_call_path and not any(s.capability == InvestigationCapability.CALL_GRAPH_TRAVERSAL for s in steps):
            s_call = PlanStep(
                step_id="step_call_graph",
                capability=InvestigationCapability.CALL_GRAPH_TRAVERSAL,
                description="Traverse static caller/callee relationships in FalkorDB",
                parameters={"query": question},
                depends_on=["step_resolve_symbols"],
            )
            steps.append(s_call)
            exec_order.append(s_call.step_id)

        # Source Evidence Collection (verifying physical files)
        s_ev = PlanStep(
            step_id="step_source_evidence",
            capability=InvestigationCapability.SOURCE_EVIDENCE,
            description="Collect AST-grounded source code snippets and exact line ranges",
            parameters={},
            depends_on=[s.step_id for s in steps if s.step_id != "step_resolve_symbols"],
        )
        steps.append(s_ev)
        exec_order.append(s_ev.step_id)

        # Answer Synthesis & Final Claim-Level Verification
        s_synth = PlanStep(
            step_id="step_answer_synthesis",
            capability=InvestigationCapability.ANSWER_SYNTHESIS,
            description="Synthesize structured facts into natural-language report and verify claim citations",
            parameters={},
            depends_on=[s.step_id for s in steps],
        )
        steps.append(s_synth)
        exec_order.append(s_synth.step_id)

        return InvestigationPlan(
            query_id=q_id,
            query_text=question,
            repository_id=self.repo_id,
            steps=steps,
            execution_order=exec_order,
        )
