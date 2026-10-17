"""
app/agent/models.py - Canonical InvestigationResult and Structured Semantic Models.

Defines the single authoritative data model for ASTERION investigations, eliminating
contradictory analyzer outputs and ensuring all analyzers contribute structured facts.
"""

from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Set, Union
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


class ScenarioType(str, Enum):
    PERSISTENT_FAILURE = "PERSISTENT_FAILURE"
    FIRST_ATTEMPT_SUCCESS = "FIRST_ATTEMPT_SUCCESS"
    TRANSIENT_FAILURE_SUCCESS = "TRANSIENT_FAILURE_SUCCESS"
    CONFIGURED_SEQUENCE = "CONFIGURED_SEQUENCE"
    HYPOTHETICAL_MODIFICATION = "HYPOTHETICAL_MODIFICATION"
    CONFIGURATION_OVERRIDE = "CONFIGURATION_OVERRIDE"
    GENERAL = "GENERAL"


class TestCoverageClassification(str, Enum):
    __test__ = False
    REGRESSION_DETECTING = "REGRESSION_DETECTING"
    BRANCH_EXECUTING_NON_DETECTING = "BRANCH_EXECUTING_NON_DETECTING"
    BRANCH_EXECUTING_WITHOUT_RELEVANT_ASSERTION = "BRANCH_EXECUTING_NON_DETECTING"
    FUNCTION_EXECUTING_ONLY = "FUNCTION_EXECUTING_ONLY"
    STATICALLY_REACHABLE_ONLY = "STATICALLY_REACHABLE_ONLY"
    UNRELATED = "UNRELATED"
    UNKNOWN = "UNKNOWN"


class ScenarioExecutionSummary(BaseModel):
    scenario_type: ScenarioType
    scenario_name: str
    target_function: str
    limit_variable: Optional[str] = None
    limit_value: Optional[int] = None
    attempt_count: int
    retry_count: int
    exit_counter_value: int
    events_emitted: List[Dict[str, Any]] = Field(default_factory=list)  # {"event": name, "count": N}
    events_sequence: List[str] = Field(default_factory=list)
    notices_sent: List[str] = Field(default_factory=list)
    final_status: Optional[str] = None
    receipt: Optional[str] = None
    hold_action: Optional[str] = None  # "captured", "released", "none"
    balance_action: Optional[str] = None  # "restored", "decremented", "unchanged"
    quota_action: Optional[str] = None  # "restored", "consumed", "decremented", "unchanged"
    reservation_action: Optional[str] = None  # "cleared", "reserved", "consumed", "none"
    outbox_state: Optional[List[str]] = None
    resource_action: Optional[str] = None
    resource_name: Optional[str] = None
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list)
    statements_executed: List[str] = Field(default_factory=list)
    statements_skipped: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    summary: str = ""


class BranchOutcome(BaseModel):
    function_name: str
    condition: str
    source_location: str
    branch_type: str  # "RAISE", "RETURN", "FALLTHROUGH"
    exception_raised: Optional[str] = None
    status_set: Optional[str] = None
    events_recorded: List[str] = Field(default_factory=list)
    notices_sent: List[str] = Field(default_factory=list)
    coverage_classification: str = "UNTESTED"  # "TESTED", "UNTESTED", "DOWNSTREAM_GAP"
    covering_tests: List[str] = Field(default_factory=list)
    recommended_test: Optional[str] = None
    details: str = ""


class StateEffectSummary(BaseModel):
    function_name: str
    file_path: str
    line_span: str
    preconditions: List[str] = Field(default_factory=list)
    state_reads: List[str] = Field(default_factory=list)
    state_writes: List[str] = Field(default_factory=list)
    collection_mutations: List[str] = Field(default_factory=list)
    balance_restored: bool = False
    balance_effect_explanation: str = ""
    hold_effect: str = "none"
    quota_effect: str = "none"
    reservation_effect: str = "none"
    receipt_value: Optional[str] = None
    queue_writes: List[str] = Field(default_factory=list)
    queue_reads: List[str] = Field(default_factory=list)
    status_transitions: List[str] = Field(default_factory=list)
    events: List[str] = Field(default_factory=list)
    notices: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)


class TestImpactDetail(BaseModel):
    __test__ = False
    test_name: str
    file_path: str
    classification: TestCoverageClassification
    reached_target: bool
    assertion_fails_on_change: bool
    failing_assertion: Optional[str] = None
    explanation: str


class TypedEvidence(BaseModel):
    repository_id: str
    revision: Optional[str] = None
    source_file: str
    symbol_id: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    analyzer: str = ""
    scenario_id: Optional[str] = None
    evidence_type: str = "SOURCE"
    confidence: float = 1.0
    verification_status: str = "VERIFIED"
    content: str = ""


class QueryRequirements(BaseModel):
    entities: List[str] = Field(default_factory=list)
    scenarios: List[ScenarioType] = Field(default_factory=list)
    hypothetical_changes: List[str] = Field(default_factory=list)
    requested_outputs: List[str] = Field(default_factory=list)
    required_capabilities: List[str] = Field(default_factory=list)
    negative_evidence_requirements: List[str] = Field(default_factory=list)


class Claim(BaseModel):
    subject: str
    predicate: str
    value: Any
    scenario_id: Optional[str] = None
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    verification_status: str = "UNVERIFIED"


class InvestigationResult(BaseModel):
    repository_id: str
    active_repository: Optional[str] = None
    revision: Optional[str] = None
    user_question: str
    primary_intent: str
    secondary_intents: List[str] = Field(default_factory=list)
    requested_scenarios: List[ScenarioType] = Field(default_factory=list)
    configuration_overrides: Dict[str, Any] = Field(default_factory=dict)
    resolved_entities: List[Dict[str, Any]] = Field(default_factory=list)

    # Scenarios (keyed by scenario name or type)
    scenarios: Dict[str, ScenarioExecutionSummary] = Field(default_factory=dict)
    primary_scenario: Optional[ScenarioExecutionSummary] = None
    canonical_scenario: Optional[Any] = None
    canonical_execution_result: Optional[Any] = None
    provenance_ledger: List[Any] = Field(default_factory=list)
    final_status: Optional[str] = None
    resolved_metrics: Dict[str, Any] = Field(default_factory=dict)

    # Execution & State
    execution_traces: List[Dict[str, Any]] = Field(default_factory=list)
    state_transitions: List[str] = Field(default_factory=list)
    event_counts: Union[Dict[str, Any], List[Any]] = Field(default_factory=dict)
    affected_branches: List[str] = Field(default_factory=list)

    # Interprocedural state effects
    state_effect_summaries: Dict[str, StateEffectSummary] = Field(default_factory=dict)

    # Branch-level semantics
    branch_outcomes: Dict[str, List[BranchOutcome]] = Field(default_factory=dict)

    # Test classifications
    test_classifications: Dict[str, TestImpactDetail] = Field(default_factory=dict)
    test_impact_classifications: Dict[str, str] = Field(default_factory=dict)
    coverage_gaps: List[str] = Field(default_factory=list)

    # Evidence & Claims
    verified_claims: List[str] = Field(default_factory=list)
    supporting_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    typed_evidence: List[TypedEvidence] = Field(default_factory=list)
    claims: List[Claim] = Field(default_factory=list)
    uncertainty_and_unsupported_findings: List[str] = Field(default_factory=list)

    # Completeness checklist
    checklist: Dict[str, bool] = Field(default_factory=dict)

    # Reconciliation status
    contradictions_detected: List[str] = Field(default_factory=list)
    reconciled: bool = True
