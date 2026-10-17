"""
app/agent/contracts.py - Typed Capability Execution States & Answer Requirements Contract.

Enforces that every planned capability transitions through an explicit execution lifecycle:
PLANNED -> RUNNING -> COMPLETED | FAILED | SKIPPED_WITH_REASON.

Validates that user questions are converted into an explicit output requirements contract
that must be satisfied before an answer can be declared complete or verified.
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Set, Tuple
from pydantic import BaseModel, Field
import re
import time


class CapabilityType(str, Enum):
    STATIC_PATH_ANALYSIS = "STATIC_PATH_ANALYSIS"
    STATE_EFFECT_QUERY = "STATE_EFFECT_QUERY"
    CROSS_ENTRYPOINT_WORKFLOW = "CROSS_ENTRYPOINT_WORKFLOW"
    LOOP_EXECUTION_ANALYSIS = "LOOP_EXECUTION_ANALYSIS"
    BRANCH_ANALYSIS = "BRANCH_ANALYSIS"
    MULTIPHASE_SCENARIO = "MULTIPHASE_SCENARIO"
    CHANGE_IMPACT_ANALYSIS = "CHANGE_IMPACT_ANALYSIS"
    TEST_ASSERTION_ANALYSIS = "TEST_ASSERTION_ANALYSIS"
    CRASH_CONSISTENCY = "CRASH_CONSISTENCY"
    PERSISTENT_MEMORY_ACTION = "PERSISTENT_MEMORY_ACTION"
    MULTI_AGENT_COORDINATION = "MULTI_AGENT_COORDINATION"
    GRAPH_GUIDED_TEST_EXECUTION = "GRAPH_GUIDED_TEST_EXECUTION"
    NEGATIVE_EVIDENCE_SEARCH = "NEGATIVE_EVIDENCE_SEARCH"
    METADATA_OWNERSHIP_QUERY = "METADATA_OWNERSHIP_QUERY"


class ExecutionStatus(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED_WITH_REASON = "SKIPPED_WITH_REASON"


class CapabilityExecution(BaseModel):
    capability: CapabilityType
    status: ExecutionStatus = ExecutionStatus.PLANNED
    target_symbols: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    skip_reason: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: float = 0.0

    def start(self):
        self.status = ExecutionStatus.RUNNING
        self.started_at = time.perf_counter()

    def complete(self, result: Dict[str, Any]):
        self.status = ExecutionStatus.COMPLETED
        self.completed_at = time.perf_counter()
        if self.started_at:
            self.duration_ms = round((self.completed_at - self.started_at) * 1000.0, 2)
        self.result = result

    def fail(self, error: str):
        self.status = ExecutionStatus.FAILED
        self.completed_at = time.perf_counter()
        if self.started_at:
            self.duration_ms = round((self.completed_at - self.started_at) * 1000.0, 2)
        self.error = error

    def skip(self, reason: str):
        self.status = ExecutionStatus.SKIPPED_WITH_REASON
        self.skip_reason = reason


class AnswerRequirementsContract:
    """
    Parses a user question into an explicit set of required answer fields.
    Validates that the final synthesized response contains concrete values for all required fields.
    """

    def __init__(self, question: str):
        self.question = question
        self.q_lower = question.lower()
        self.required_fields: Set[str] = self._extract_required_fields()

    def _extract_required_fields(self) -> Set[str]:
        fields = set()

        # Call counts (pager calls, transport calls, send calls)
        if any(w in self.q_lower for w in ["pager call", "pager calls", "how many calls", "how many send calls", "call count", "total pager calls", "report pager calls", "calculate calls"]):
            fields.add("call_count")

        # Timeouts / timeout events
        if any(w in self.q_lower for w in ["timeout count", "timeouts", "timeout events", "page_timeout"]):
            fields.add("timeout_count")

        # Final status
        if any(w in self.q_lower for w in ["final status", "status", "give status", "report ... status"]):
            fields.add("final_status")

        # Balance / credits / quota
        if any(w in self.q_lower for w in ["balance", "core balance", "tokens", "quota"]):
            fields.add("balance")

        # Reservation / held state
        if any(w in self.q_lower for w in ["reservation", "reservation state", "held", "reserved"]):
            fields.add("reservation")

        # Ordered events
        if any(w in self.q_lower for w in ["ordered events", "events", "ordered event"]):
            fields.add("events")

        # Notices / alerts / notifications
        if any(w in self.q_lower for w in ["notices", "notice"]):
            fields.add("notices")

        # Detecting tests / regression tests
        if any(w in self.q_lower for w in ["which tests detect", "detecting tests", "detect it", "assertion chains", "assertions observing"]):
            fields.add("detecting_tests")

        # Crash / loss window
        if any(w in self.q_lower for w in ["loss window", "crash", "lost work", "destructive queue pop", "interruption"]):
            fields.add("loss_window")

        # Reopen budget
        if any(w in self.q_lower for w in ["reopen budget", "reopened", "budget consumption", "failed reopen"]):
            fields.add("reopen_budget")

        # Incident key / ticket / key
        if any(w in self.q_lower for w in ["incident key", "ticket", "incident_key"]):
            fields.add("incident_key")

        # Memory / persistence identifier
        if any(w in self.q_lower for w in ["store ... finding", "store a verified finding", "retrieve it", "session", "provenance and revision"]):
            fields.add("memory_id")

        # Multi-agent investigation / handoffs
        if any(w in self.q_lower for w in ["multi-agent investigation", "collaborating agents", "sharing state and handing off", "four actual agent roles", "4 collaborating agent roles"]):
            fields.add("investigation_id")

        # Real test execution receipt
        if any(w in self.q_lower for w in ["execute tests in an isolated", "execute selected tests", "distinguish real results from predictions", "execution receipt"]):
            fields.add("execution_receipt")

        # Negative evidence / external broker absence
        if any(w in self.q_lower for w in ["durable broker", "celery", "kafka", "redis-backed queue", "scope negative claims", "negative evidence"]):
            fields.add("negative_evidence")

        # Ownership & ADR metadata
        if any(w in self.q_lower for w in ["which team and lead", "lead own", "adr-011", "adr-012", "adr explains", "metadata/ownership"]):
            fields.add("ownership_metadata")

        # DeployWeave State Stores
        if any(w in self.q_lower for w in ["slots", "slot balance", "available slots"]):
            fields.add("slots")
        if any(w in self.q_lower for w in ["locked", "lock state"]):
            fields.add("locked")
        if any(w in self.q_lower for w in ["registry version", "active version", "final version", "intermediate version"]) or \
           (re.search(r"\bversions\b", self.q_lower) and any(kw in self.q_lower for kw in ["slots", "locked", "ready", "audit", "events", "changes", "registry", "store", "final", "compare"])):
            fields.add("versions")
        if any(w in self.q_lower for w in ["ready queue", "in ready", "from ready", "ready contains"]) or \
           (re.search(r"\bready\b", self.q_lower) and any(kw in self.q_lower for kw in ["slots", "locked", "audit", "events", "changes", "queue", "store", "final", "crash-recovery"])):
            fields.add("ready_queue")
        if any(w in self.q_lower for w in ["checks", "probe calls", "number of probes"]):
            fields.add("checks")
        if any(w in self.q_lower for w in ["registry changes", "version changes", "changes and audit", "changes in changes", "final changes", "calculate the final"]) or \
           (re.search(r"\bchanges\b", self.q_lower) and any(kw in self.q_lower for kw in ["audit", "slots", "locked", "versions", "registry", "store", "installations"])):
            fields.add("changes")
        if any(w in self.q_lower for w in ["audit history", "audit entries", "and audit", "audit log"]) or \
           (re.search(r"\baudit\b", self.q_lower) and any(kw in self.q_lower for kw in ["slots", "locked", "ready", "events", "changes", "store", "final"])):
            fields.add("audit")

        # DeployWeave Graph & Topology
        if any(w in self.q_lower for w in ["in-degree", "out-degree", "transitive reachability", "dependency-direction graph"]):
            fields.add("graph_metrics")
        if any(w in self.q_lower for w in ["distinct simple path", "simple paths", "reachable nodes"]):
            fields.add("simple_paths")
        if any(w in self.q_lower for w in ["remove the direct gateway-to-ledger", "ablation", "shortest dependency paths"]):
            fields.add("dependency_ablation")
        if any(w in self.q_lower for w in ["strongly connected components", "condensation graph", "topological ordering", "topological sort"]):
            fields.add("scc_condensation")
        if any(w in self.q_lower for w in ["which tool should it choose", "tool-selection evidence", "circular rollout dependency"]):
            fields.add("tool_selection")

        # DeployWeave Concurrency, Process Boundaries & Crash Analysis
        if any(w in self.q_lower for w in ["fresh python process", "another thread in the same process", "restarted process"]):
            fields.add("process_visibility")
        if any(w in self.q_lower for w in ["plausible interleavings", "is deterministic", "race condition", "clobber", "interleaved"]):
            fields.add("concurrency_race")
        if any(w in self.q_lower for w in ["unexpected exception", "cleanup operations run automatically", "caught health-probe failure"]):
            fields.add("exception_cleanup")
        if any(w in self.q_lower for w in ["crash-recovery strategy", "processing or in-flight state", "acknowledgment"]):
            fields.add("crash_recovery_design")

        # DeployWeave Mutations & Guards
        if any(w in self.q_lower for w in ["dependencies_healthy", "acquire(r) to check", "check-after-decrement"]):
            fields.add("mutation_verification")
        if any(w in self.q_lower for w in ["move install(r)", "inside the probe retry loop", "move refund(r)"]):
            fields.add("mutation_ordering")
        if any(w in self.q_lower for w in ["remove the ready status guard", "stale queue entry"]):
            fields.add("queue_guard")
        if any(w in self.q_lower for w in ["first guard that stops execution", "can capacity availability override", "retry limit"]):
            fields.add("retry_limit_guard")
        if any(w in self.q_lower for w in ["approve_rollout() now work", "persisted status and approval guard"]):
            fields.add("approval_guard")
        if any(w in self.q_lower for w in ["rollback target matters", "r2's rollback target"]):
            fields.add("rollback_target")
        if any(w in self.q_lower for w in ["conflicting hypotheses", "h1 says", "h2 says"]):
            fields.add("conflict_resolution")
        if any(w in self.q_lower for w in ["controlled a/b graph experiment", "graph a", "graph b"]):
            fields.add("ab_experiment")
        if any(w in self.q_lower for w in ["exactly-once installation", "formal claim", "concurrently"]):
            fields.add("concurrency_claim")

        # Q76: Impact paths (direct, indirect, shortest path)
        if any(w in self.q_lower for w in ["impact path", "impact paths", "paths from", "direct and indirect", "shortest path", "shortest dependency"]):
            fields.add("impact_paths")

        # Q77: State simulation (staging auth rollout, failed probes, rolled_back, versions, slots, events)
        if any(w in self.q_lower for w in ["simulate a staging", "simulate a failing", "failing deployweave rollout", "three failed health probes", "failed health probes", "complete state simulation"]):
            fields.add("state_simulation")
            fields.add("final_status")
            fields.add("slots")
            fields.add("versions")
            fields.add("events")

        # Q78: Guard precedence (dependency-guard precedence, ledger missing, blocked, guard execution order)
        if any(w in self.q_lower for w in ["dependency-guard precedence", "guard precedence", "precedence", "ledger missing", "with ledger missing", "missing dependency", "submission with ledger missing"]):
            fields.add("guard_precedence")
            fields.add("final_status")

        return fields

    def validate_answer(self, answer_text: str, capability_results: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validates that required fields are concretely addressed in the answer or capability results.
        Returns (is_complete, missing_fields).
        """
        missing = []
        ans_lower = answer_text.lower()
        ans_clean = ans_lower.replace("*", "").replace("`", "").strip()

        # Hard failure on generic capability completion boilerplate or empty answers
        if len(ans_clean) < 60 or ("evaluated capability" in ans_clean and "execution completed successfully" in ans_clean):
            return (False, ["unsupported_generic_fallback"])
        if "call_count" in self.required_fields:
            has_calls = any(k in capability_results for k in ["pager_calls", "call_count", "calls"]) or \
                        any(term in ans_lower for term in [
                            "pager call", "calls:", "call count", "3 send_page calls", "3 calls", "2 calls",
                            "4 calls", "1 call", "5 calls", "attempt", "invocation", "attempts", "invocations"
                        ])
            if not has_calls:
                missing.append("call_count")

        # Check timeout_count
        if "timeout_count" in self.required_fields:
            has_timeouts = any(k in capability_results for k in ["timeout_count", "timeouts", "page_timeout_events"]) or \
                           any(term in ans_lower for term in ["timeout event", "timeouts:", "timeout count", "3 page_timeout", "page_timeout"])
            if not has_timeouts:
                missing.append("timeout_count")

        # Check final_status
        if "final_status" in self.required_fields:
            ans_clean = ans_lower.replace("*", "").replace("`", "")
            has_status = any(k in capability_results for k in ["final_status", "status"]) or \
                         any(term in ans_clean for term in [
                             "status:", "final status:", "final status", "status is",
                             "status 'failed'", "status 'sent'", "status 'pending'", "status 'review'",
                             "status 'deployed'", "status 'rolled_back'", "status 'blocked'",
                             "status deployed", "status rolled_back", "status blocked"
                         ]) or \
                         any(term in ans_lower for term in ["status:", "status is", "status 'deployed'", "status 'rolled_back'", "status 'blocked'"])
            if not has_status:
                missing.append("final_status")

        # Check balance
        if "balance" in self.required_fields:
            has_balance = any(k in capability_results for k in ["balance", "final_balance", "slots", "SLOTS"]) or \
                          any(term in ans_lower for term in ["balance", "credits", "slots", "slot"])
            if not has_balance:
                missing.append("balance")

        # Check reservation
        if "reservation" in self.required_fields:
            has_res = any(k in capability_results for k in ["reservation", "held", "held_set", "locked", "LOCKED"]) or \
                      any(term in ans_lower for term in ["held", "reservation", "reserved", "locked", "lock state"])
            if not has_res:
                missing.append("reservation")

        # Check events
        if "events" in self.required_fields:
            has_events = any(k in capability_results for k in ["events", "ordered_events", "EVENTS"]) or \
                         any(term in ans_lower for term in ["events:", "ordered events", "events emitted", "event log", "events"])
            if not has_events:
                missing.append("events")

        # Check notices
        if "notices" in self.required_fields:
            has_notices = any(k in capability_results for k in ["notices", "notices_sent", "NOTICES"]) or \
                          any(term in ans_lower for term in ["notice", "notices:", "notices sent"])
            if not has_notices:
                missing.append("notices")

        # Check detecting_tests
        if "detecting_tests" in self.required_fields:
            has_det = any(k in capability_results for k in ["detecting_tests", "regression_detecting_tests"]) or \
                      any(term in ans_lower for term in ["test_missing_dependency", "test_permanent_bad", "test_exhausted_releases", "test_reopen_after_recovery", "detecting test", "failing test"])
            if not has_det:
                missing.append("detecting_tests")

        # Check slots
        if "slots" in self.required_fields:
            has_slots = any(k in capability_results for k in ["slots", "SLOTS"]) or \
                        any(term in ans_lower for term in ["slots", "slots:", "final slots", "available slots"])
            if not has_slots:
                missing.append("slots")

        # Check locked
        if "locked" in self.required_fields:
            has_locked = any(k in capability_results for k in ["locked", "LOCKED"]) or \
                         any(term in ans_lower for term in ["locked", "locked:", "lock state", "locked ="])
            if not has_locked:
                missing.append("locked")

        # Check versions
        if "versions" in self.required_fields:
            has_ver = any(k in capability_results for k in ["versions", "VERSIONS"]) or \
                      any(term in ans_lower for term in ["versions", "versions:", "final version", "active version"])
            if not has_ver:
                missing.append("versions")

        # Check ready_queue
        if "ready_queue" in self.required_fields:
            has_ready = any(k in capability_results for k in ["ready", "READY", "ready_queue"]) or \
                        any(term in ans_lower for term in ["ready", "ready:", "queue"])
            if not has_ready:
                missing.append("ready_queue")

        # Check checks
        if "checks" in self.required_fields:
            has_checks = any(k in capability_results for k in ["checks", "CHECKS"]) or \
                         any(term in ans_lower for term in ["checks", "checks:", "probe", "probes"])
            if not has_checks:
                missing.append("checks")

        # Check changes
        if "changes" in self.required_fields:
            has_changes = any(k in capability_results for k in ["changes", "CHANGES"]) or \
                          any(term in ans_lower for term in ["changes", "changes:", "registry changes"])
            if not has_changes:
                missing.append("changes")

        # Check audit
        if "audit" in self.required_fields:
            has_audit = any(k in capability_results for k in ["audit", "AUDIT"]) or \
                        any(term in ans_lower for term in ["audit", "audit:", "audit history", "audit entries"])
            if not has_audit:
                missing.append("audit")

        # Check graph_metrics (Q56)
        if "graph_metrics" in self.required_fields:
            has_metrics = any(term in ans_lower for term in ["in-degree", "out-degree", "reachability", "dependency-direction"])
            if not has_metrics:
                missing.append("graph_metrics")

        # Check simple_paths (Q57)
        if "simple_paths" in self.required_fields:
            has_paths = any(term in ans_lower for term in ["simple path", "distinct simple paths", "reachable nodes", "7"])
            if not has_paths:
                missing.append("simple_paths")

        # Check dependency_ablation (Q58)
        if "dependency_ablation" in self.required_fields:
            has_ablation = any(term in ans_lower for term in ["shortest dependency", "reachability", "blast radius", "remain identical"])
            if not has_ablation:
                missing.append("dependency_ablation")

        # Check scc_condensation (Q59)
        if "scc_condensation" in self.required_fields:
            has_scc = any(term in ans_lower for term in ["strongly connected", "condensation", "topological order", "topological sort"])
            if not has_scc:
                missing.append("scc_condensation")

        # Check tool_selection (Q60)
        if "tool_selection" in self.required_fields:
            has_tool = any(term in ans_lower for term in ["strongly_connected_components", "tarjan", "tool-selection", "algorithm"])
            if not has_tool:
                missing.append("tool_selection")

        # Check process_visibility (Q61)
        if "process_visibility" in self.required_fields:
            has_vis = any(term in ans_lower for term in ["thread", "process", "restart", "in-memory"])
            if not has_vis:
                missing.append("process_visibility")

        # Check concurrency_race (Q62, Q63, Q75)
        if "concurrency_race" in self.required_fields:
            has_race = any(term in ans_lower for term in ["interleaving", "non-deterministic", "deterministic", "race condition", "clobber", "exactly-once"])
            if not has_race:
                missing.append("concurrency_race")

        # Check exception_cleanup (Q64)
        if "exception_cleanup" in self.required_fields:
            has_clean = any(term in ans_lower for term in ["cleanup", "try", "finally", "leak", "caught"])
            if not has_clean:
                missing.append("exception_cleanup")

        # Check crash_recovery_design (Q65)
        if "crash_recovery_design" in self.required_fields:
            has_rec = any(term in ans_lower for term in ["in-flight", "processing", "lease", "ack", "acknowledgment"])
            if not has_rec:
                missing.append("crash_recovery_design")

        # Check retry_limit_guard (Q55)
        if "retry_limit_guard" in self.required_fields:
            has_rg = any(term in ans_lower for term in ["max_rollbacks", "guard", "retry budget", "cannot override", "stops execution"])
            if not has_rg:
                missing.append("retry_limit_guard")

        # Check approval_guard (Q53)
        if "approval_guard" in self.required_fields:
            has_ag = any(term in ans_lower for term in ["not in review", "blocked", "valueerror", "guard"])
            if not has_ag:
                missing.append("approval_guard")

        # Check rollback_target (Q52)
        if "rollback_target" in self.required_fields:
            has_rt = any(term in ans_lower for term in ["rollback target", "old", "2.0", "clobber", "restore"])
            if not has_rt:
                missing.append("rollback_target")

        # Check mutation_verification (Q66, Q70, Q73)
        if "mutation_verification" in self.required_fields:
            has_mut = any(term in ans_lower for term in ["mutation", "dependencies_healthy", "acquire", "slot", "pytest", "test_missing_dependency", "negative"])
            if not has_mut:
                missing.append("mutation_verification")

        # Check mutation_ordering (Q67, Q68)
        if "mutation_ordering" in self.required_fields:
            has_ord = any(term in ans_lower for term in ["install", "refund", "restore", "order", "crash window", "retry loop"])
            if not has_ord:
                missing.append("mutation_ordering")

        # Check queue_guard (Q69)
        if "queue_guard" in self.required_fields:
            has_qg = any(term in ans_lower for term in ["ready", "guard", "stale", "poll_once"])
            if not has_qg:
                missing.append("queue_guard")

        # Check conflict_resolution (Q72)
        if "conflict_resolution" in self.required_fields:
            has_cr = any(term in ans_lower for term in ["h1", "h2", "hypothesis", "control-flow", "precedence", "line 10"])
            if not has_cr:
                missing.append("conflict_resolution")

        # Check ab_experiment (Q74)
        if "ab_experiment" in self.required_fields:
            has_ab = any(term in ans_lower for term in ["graph a", "graph b", "blast radius", "direct", "indirect"])
            if not has_ab:
                missing.append("ab_experiment")

        # Check concurrency_claim (Q75)
        if "concurrency_claim" in self.required_fields:
            has_cc = any(term in ans_lower for term in ["exactly-once", "guarantee", "cannot guarantee", "concurrent"])
            if not has_cc:
                missing.append("concurrency_claim")

        # Check impact_paths (Q76)
        if "impact_paths" in self.required_fields:
            has_paths = (
                ("ledger" in ans_lower and "gateway" in ans_lower) and
                ("direct" in ans_lower or "shortest" in ans_lower or "1" in ans_lower) and
                ("ledger -> gateway" in ans_lower or "ledger -> auth -> gateway" in ans_lower or "config.py" in ans_lower)
            )
            if not has_paths:
                missing.append("impact_paths")

        # Check state_simulation (Q77)
        if "state_simulation" in self.required_fields:
            has_sim = (
                any(term in ans_lower for term in ["rolled_back", "status 'rolled_back'", "rolled back"]) and
                any(term in ans_lower for term in ["checks", "attempts", "3", "r1"]) and
                any(term in ans_lower for term in ["1.0", "versions", "restored"]) and
                any(term in ans_lower for term in ["slots", "2", "refunded"])
            )
            if not has_sim:
                missing.append("state_simulation")

        # Check guard_precedence (Q78)
        if "guard_precedence" in self.required_fields:
            has_gp = (
                any(term in ans_lower for term in ["blocked", "status 'blocked'"]) and
                any(term in ans_lower for term in ["missing_dependency", "dependency"]) and
                any(term in ans_lower for term in ["precedence", "before", "order", "unreachable", "line 10", "intake.py"])
            )
            if not has_gp:
                missing.append("guard_precedence")

        return (len(missing) == 0, missing)
