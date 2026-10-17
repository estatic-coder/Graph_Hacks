"""
tests/test_reconciliation_and_branch_semantics.py - Automated Regression Tests

Comprehensive suite verifying ASTERION's:
1. Canonical InvestigationResult & Reconciliation (eliminating contradictory outputs)
2. Scenario Selection (persistent failure vs transient success vs config overrides)
3. Retry Loop State and Numerical Rendering (inclusive conditions, correct exit counters, no phantom increments)
4. AST-Derived Branch Semantics (invalid status -> ValueError, failed hold -> insufficient_funds, no domain borrowing)
5. Branch-Level Test Verification (REGRESSION_DETECTING vs STATICALLY_REACHABLE_ONLY)
6. Interprocedural State-Effect Summaries (refund_payment does not restore balance, exact comparison with release_hold)
7. Generalization across unfamiliar codebases with renamed symbols and custom constants
"""

import ast
import os
import pytest
from app.agent.investigator import GraphInvestigator
from app.agent.pipeline import ReasoningPipeline
from app.agent.reconciler import InvestigationReconciler
from app.agent.state_effects import StateEffectAnalyzer
from app.agent.models import (
    InvestigationResult,
    ScenarioType,
    TestCoverageClassification,
)

NEXUS_REPO_ID = "repo_nexuspay_asterio_b0bfd5"
NEXUS_REPO_PATH = "/home/zeraphynx/Projects/asterion/backend/data/repos/repo_nexuspay_asterio_b0bfd5"


@pytest.fixture
def investigator():
    return GraphInvestigator(repo_id=NEXUS_REPO_ID)


@pytest.fixture
def pipeline():
    return ReasoningPipeline(repo_id=NEXUS_REPO_ID)


@pytest.fixture
def reconciler():
    return InvestigationReconciler(repo_id=NEXUS_REPO_ID, repo_path=NEXUS_REPO_PATH)


@pytest.fixture
def state_analyzer():
    return StateEffectAnalyzer(repo_path=NEXUS_REPO_PATH)


# ==============================================================================
# 1. Persistent Timeout: 3 calls, 3 events, hold release, balance restore, failed status
# ==============================================================================

def test_persistent_timeout_reconciliation(investigator):
    """
    Validates persistent timeout under MAX_GATEWAY_RETRIES=2:
    - 3 calls with limit 2
    - 3 timeout events
    - Hold released, balance restored
    - Failed status & notification
    - InvestigationResult structure populated
    - No contradictory transient success section
    """
    q = "If authorize() always raises TimeoutError and MAX_GATEWAY_RETRIES=2, how many gateway calls occur? List event counts, hold/balance changes, status, and notices."
    ans, report = investigator.investigate_with_report(q)

    # Verifications on rendered answer
    assert "3 gateway attempt(s)" in ans or "3 attempts" in ans
    assert "3 times" in ans or "3 gateway_timeout" in ans
    assert "release_hold" in ans or "released" in ans.lower()
    assert "balance" in ans.lower()
    assert "failed" in ans
    assert "notification" in ans.lower() or "customer" in ans.lower()

    # Contradiction check: persistent failure answer MUST NOT assert transient success
    assert "transient" not in ans.lower() or "persistent" in ans.lower()
    assert "captured" not in ans.lower() or "not captured" in ans.lower() or "skipped" in ans.lower()

    # Structural verification on canonical InvestigationResult
    inv_res = investigator.last_pipeline_data.get("investigation_result")
    assert inv_res is not None
    assert inv_res["active_repository"] == NEXUS_REPO_ID
    assert inv_res["final_status"] == "failed"
    assert "attempts" in inv_res["resolved_metrics"]
    assert inv_res["resolved_metrics"]["attempts"] == 3


# ==============================================================================
# 2. Transient Timeout: 2 calls, 1 timeout event, hold captured, paid status, no failure cleanup
# ==============================================================================

def test_transient_timeout_reconciliation(investigator):
    """
    Validates transient timeout (1 timeout then success):
    - 2 calls
    - 1 timeout event
    - Hold captured
    - Paid status & notification
    - Failure cleanup (release_hold) skipped
    - No contradictory persistent-failure section
    """
    q = "If the gateway times out exactly once and then succeeds, how many calls happen and which events, holds, and notices result?"
    ans, report = investigator.investigate_with_report(q)

    # Verifications on rendered answer
    assert "2 gateway attempt(s)" in ans or "2 attempts" in ans
    assert "1 `gateway_timeout` event" in ans or "1 gateway_timeout" in ans or "1 timeout" in ans
    assert "capture_hold" in ans or "captured" in ans.lower()
    assert "paid" in ans
    assert "skipped" in ans.lower() or "not executed" in ans.lower() or "bypassed" in ans.lower()

    # Contradiction check: MUST NOT render persistent 3-call failure trace as actual
    assert "3 gateway attempt(s) occur" not in ans
    assert "3 attempts occur" not in ans

    # Structural verification on canonical InvestigationResult
    inv_res = investigator.last_pipeline_data.get("investigation_result")
    assert inv_res is not None
    assert inv_res["final_status"] == "paid"
    assert ScenarioType.TRANSIENT_FAILURE_SUCCESS.value in inv_res["requested_scenarios"]


# ==============================================================================
# 3. Configuration Override: Limit 3 yields 4 calls, first success yields 1 call, exit counter 4
# ==============================================================================

def test_configuration_override_loop_state(investigator):
    """
    Validates configuration override (MAX_GATEWAY_RETRIES changed from 2 to 3):
    - Limit 3 yields maximum 4 calls under persistent failure
    - First success yields exactly 1 call
    - Exit counter remains 4 under persistent failure (4 <= 3 is False, no phantom 5th increment)
    - Two separated scenario sections
    - No blank sequences or unresolved None
    """
    q = "If MAX_GATEWAY_RETRIES changes from 2 to 3, what is the maximum number of gateway calls? Does the answer change if the first call succeeds?"
    ans, report = investigator.investigate_with_report(q)

    # Both scenarios clearly distinguished
    assert "Scenario 1" in ans
    assert "Scenario 2" in ans
    assert "4 gateway attempt(s)" in ans or "4 attempts" in ans or "maximum 4" in ans
    assert "1 gateway attempt" in ans or "1 attempt" in ans or "exactly 1" in ans

    # Exact exit condition without phantom 5th increment
    assert "4 <= 3" in ans
    assert "exit counter = 4" in ans or "exit counter at 4" in ans
    assert "counter reaches 5" not in ans
    assert "reaches 5" not in ans

    # Schema & rendering sanity
    assert "counter values , , ," not in ans
    assert "None" not in ans or "KeyError" in ans or "NoneType" in ans  # No unresolved 'None' placeholders


# ==============================================================================
# 4. Approval Branches: AST-derived ValueError, insufficient_funds, zero out-of-stock
# ==============================================================================

def test_approval_branch_semantics_and_test_classification(investigator, reconciler):
    """
    Validates AST-derived branch outcomes for approve():
    - Invalid status raises ValueError
    - Insufficient funds sets insufficient_funds & records review_funds_failed
    - No invented out-of-stock outcome in NexusPay
    - Accurate direct and transitive test coverage classifications
    """
    q = "Which failure branches in approve() are not directly tested? Distinguish invalid status, insufficient funds, and downstream persistent gateway timeout."
    ans, report = investigator.investigate_with_report(q)

    # Direct outcomes from AST
    assert "ValueError" in ans or "valueerror" in ans.lower()
    assert "insufficient_funds" in ans

    # Absolute domain purity: no OrbitFlow out-of-stock leakage
    assert "out_of_stock" not in ans
    assert "out of stock" not in ans.lower()

    # Direct branch AST extraction via reconciler
    review_path = os.path.join(NEXUS_REPO_PATH, "nexuspay/review.py")
    branches = reconciler.extract_branch_outcomes_from_ast("approve", review_path)
    assert len(branches) >= 2

    # Verify invalid status branch raises ValueError
    status_branch = next((b for b in branches if "status" in b.condition), None)
    assert status_branch is not None
    assert status_branch.branch_type == "RAISE"
    assert status_branch.exception_raised == "ValueError"

    # Verify hold branch sets insufficient_funds
    hold_branch = next((b for b in branches if "hold" in b.condition or "place_hold" in b.condition), None)
    assert hold_branch is not None
    assert hold_branch.status_set == "insufficient_funds"


# ==============================================================================
# 5. Cleanup Removal: Regression detection, non-detection of success test, coverage gaps
# ==============================================================================

def test_cleanup_removal_change_impact(investigator, reconciler):
    """
    Validates change-impact analysis for removing release_hold():
    - Affected upstream workflows: automatic (submit/create_payment) and approved review (approve/approve_payment)
    - test_persistent_timeout_restores_balance classified as REGRESSION_DETECTING
    - test_successful_payment NOT classified as regression-detecting (STATICALLY_REACHABLE_ONLY)
    - Missing manual-approval failure coverage identified
    - Change-impact is primary, retry trace is supporting context
    """
    q = "Hypothetically remove release_hold() from process() on gateway exhaustion. Which automatic and approved-review workflows are affected? Which tests would detect it, and which gaps remain?"
    ans, report = investigator.investigate_with_report(q)

    # Workflows identified
    assert "submit" in ans or "create_payment" in ans or "Automatic" in ans
    assert "approve" in ans or "approve_payment" in ans or "Approved" in ans

    # Test classifications
    assert "test_persistent_timeout_restores_balance" in ans
    assert "REGRESSION_DETECTING" in ans or "Regression Detecting" in ans or "detect" in ans.lower()

    # Reconciler test impact verification
    tests_classified = reconciler.classify_test_impacts("release_hold", "process")
    timeout_test = next((t for t in tests_classified.values() if "persistent_timeout" in t.test_name), None)
    assert timeout_test is not None
    assert timeout_test.classification == TestCoverageClassification.REGRESSION_DETECTING

    success_test = next((t for t in tests_classified.values() if "successful_payment" in t.test_name), None)
    if success_test:
        assert success_test.classification != TestCoverageClassification.REGRESSION_DETECTING


# ==============================================================================
# 6. Refund Comparison: Actual source inspect, does NOT restore balance, compares release_hold
# ==============================================================================

def test_refund_comparison_state_effects(investigator, state_analyzer):
    """
    Validates interprocedural state-effect analysis for refund_payment vs release_hold:
    - refund_payment() does NOT restore account balance (appends to REFUNDS only)
    - release_hold() DOES restore account balance (mutates BALANCES and clears HOLDS)
    - Side effects, events, and citations derived from actual AST
    """
    q = "Does refund_payment() restore the account balance? Trace the functions and explain the difference between refunding and releasing a hold."
    ans, report = investigator.investigate_with_report(q)

    # Direct answer clarity
    assert "does NOT restore" in ans or "does not restore" in ans.lower() or "No," in ans or "not restore the account balance" in ans.lower()

    # Both operations analyzed and contrasted
    assert "refund" in ans.lower()
    assert "release_hold" in ans
    assert "BALANCES" in ans or "balance" in ans.lower()
    assert "REFUNDS" in ans or "refunds" in ans.lower()
    assert "nexuspay" in ans

    # StateEffectAnalyzer AST comparison verification
    comp = state_analyzer.compare_operations("refund", "release_hold")
    assert comp["comparison_available"] is True
    assert comp["op1_summary"].balance_restored is False
    assert comp["op2_summary"].balance_restored is True
    assert any("REFUNDS" in m for m in comp["op1_summary"].collection_mutations)
    assert any("BALANCES" in w for w in comp["op2_summary"].state_writes)


# ==============================================================================
# 7. Generalization: Renamed functions, custom constants, alternate branch outcomes
# ==============================================================================

def test_generalization_synthetic_codebase(tmp_path):
    """
    Validates that reconciliation, AST branch extraction, and state-effect summaries
    generalize to unfamiliar repositories without hardcoding any NexusPay strings.
    """
    synthetic_code = '''
MAX_TRANSACTION_RETRIES = 4

ACCOUNTS = {}
ESCROWS = {}
AUDIT_LOG = []

def release_escrow(tx_id: str, account_id: str, amount: float):
    ACCOUNTS[account_id] += amount
    del ESCROWS[tx_id]
    AUDIT_LOG.append({"event": "escrow_released", "tx_id": tx_id})

def void_transaction(tx_id: str):
    AUDIT_LOG.append({"event": "tx_voided", "tx_id": tx_id})
    return {"status": "voided"}

def execute_settlement(account_id: str, amount: float):
    if amount <= 0:
        raise ValueError("Invalid settlement amount")
    if ACCOUNTS.get(account_id, 0) < amount:
        return {"status": "insufficient_settlement_funds"}
    ACCOUNTS[account_id] -= amount
    return {"status": "settled"}
'''
    module_path = tmp_path / "settlement.py"
    module_path.write_text(synthetic_code)

    analyzer = StateEffectAnalyzer(repo_path=str(tmp_path))

    # Test AST state effects on unfamiliar functions
    escrow_summary = analyzer.analyze_function("release_escrow", "settlement.py")
    assert escrow_summary is not None
    assert escrow_summary.balance_restored is True
    assert any("ACCOUNTS" in w for w in escrow_summary.state_writes)
    assert any("ESCROWS" in m for m in escrow_summary.collection_mutations)

    void_summary = analyzer.analyze_function("void_transaction", "settlement.py")
    assert void_summary is not None
    assert void_summary.balance_restored is False
    assert any("AUDIT_LOG" in m for m in void_summary.collection_mutations)

    # Test operation comparison
    comp = analyzer.compare_operations("void_transaction", "release_escrow")
    assert comp["comparison_available"] is True
    assert comp["op1_summary"].balance_restored is False
    assert comp["op2_summary"].balance_restored is True

    # Test AST branch outcome extraction on unfamiliar function
    gen_reconciler = InvestigationReconciler(repo_id="repo_synthetic_fintech", repo_path=str(tmp_path))
    branches = gen_reconciler.extract_branch_outcomes_from_ast("execute_settlement", str(module_path))
    assert len(branches) >= 2

    # Branch 1: amount <= 0 -> raises ValueError
    val_branch = next((b for b in branches if "amount <= 0" in b.condition), None)
    assert val_branch is not None
    assert val_branch.branch_type == "RAISE"
    assert val_branch.exception_raised == "ValueError"

    # Branch 2: ACCOUNTS < amount -> returns status = 'insufficient_settlement_funds'
    fund_branch = next((b for b in branches if "ACCOUNTS" in b.condition), None)
    assert fund_branch is not None
    assert fund_branch.status_set == "insufficient_settlement_funds"
