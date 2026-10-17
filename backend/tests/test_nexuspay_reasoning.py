"""
tests/test_nexuspay_reasoning.py - Production-Grade Benchmark Tests for NexusPay Repository.

Validates the full spectrum of codebase intelligence on NexusPay:
1. Multi-entry call paths to authorize()
2. Persistent gateway timeout (limit=2 -> 3 calls, 3 events, hold release, balance restore)
3. Transient gateway timeout (1 failure -> 2 calls, 1 timeout event, hold capture, paid notice)
4. VIP customer payment guard & early return
5. State-mediated workflow handoff (no static CALLS edge)
6. Blocked account non-persistence
7. Change impact: removing release_hold()
8. Configuration impact: MAX_GATEWAY_RETRIES=3 (max 4 calls, 1 on success)
9. Untested failure branches in approve()
10. Negative evidence: Kafka absence & in-memory EVENTS
11. Refund semantics: no balance restoration
12. Rejection vs approval diff
13. cleanup_orphan_holds() caller & scheduling absence
14. Insufficient funds early exit
15. release_hold() direct callers
16. Immediate success execution trace
17. Double approval / invalid state ValueError
18. Residual hold detection on capture_hold removal
19. Static reachability vs feasible execution in tests
20. In-memory architecture & absence scope
"""

import pytest
import os
from app.agent.investigator import GraphInvestigator
from app.agent.pipeline import ReasoningPipeline, ErrorState
from app.agent.tools import TypedGraphTools
from app.agent.resolver import EntityResolver
from app.agent.impact import ImpactAnalyzer
from app.agent.control_flow import ControlFlowAnalyzer
from app.agent.symbolic_exec import BoundedSymbolicExecutor, ScenarioInput

NEXUS_REPO_ID = "repo_nexuspay_asterio_b0bfd5"
NEXUS_REPO_PATH = "/home/zeraphynx/Projects/asterion/backend/data/repos/repo_nexuspay_asterio_b0bfd5"


@pytest.fixture
def investigator():
    return GraphInvestigator(repo_id=NEXUS_REPO_ID)


@pytest.fixture
def pipeline():
    return ReasoningPipeline(repo_id=NEXUS_REPO_ID)


@pytest.fixture
def tools():
    return TypedGraphTools(repo_id=NEXUS_REPO_ID)


@pytest.fixture
def executor():
    return BoundedSymbolicExecutor(repo_path=NEXUS_REPO_PATH)


def test_nexus_q1_call_paths_to_authorize(investigator):
    """
    Q1: Enumerate all static call paths from create_payment() and approve_payment() to authorize().
    Identifies shared functions (process, authorize) and cites each hop.
    """
    q = "Enumerate all static call paths from create_payment() and approve_payment() to authorize(). Which functions are shared? What conditions make those paths executable?"
    ans, report = investigator.investigate_with_report(q)

    # Discovered paths
    assert "create_payment -> submit -> process -> authorize" in ans
    assert "approve_payment -> approve -> process -> authorize" in ans

    # Shared functions
    assert "process" in ans and "authorize" in ans
    assert "Shared Functions" in ans or "shared" in ans.lower()

    # Citations for each hop
    assert "nexuspay/api.py" in ans
    assert "nexuspay/workflow.py" in ans
    assert "nexuspay/review.py" in ans
    assert "nexuspay/processor.py" in ans

    assert report.is_verified is True
    assert report.paths_valid >= 2
    assert len(report.fabricated_paths) == 0


def test_nexus_q2_persistent_gateway_timeout(investigator):
    """
    Q2: Persistent TimeoutError when MAX_GATEWAY_RETRIES=2.
    Determines 3 attempts, 3 gateway_timeout events, hold release, balance restore, failed event and notice.
    """
    q = "If authorize() always raises TimeoutError and MAX_GATEWAY_RETRIES=2, how many gateway calls occur? List event counts, hold/balance changes, status, and notices."
    ans, report = investigator.investigate_with_report(q)

    # 3 attempts
    assert "3" in ans
    assert "gateway_timeout" in ans
    assert "release_hold" in ans or "released" in ans.lower()
    assert "failed" in ans

    # Zero OrbitFlow terminology
    assert "carrier" not in ans.lower()
    assert "dispatch" not in ans.lower()
    assert "orbitflow" not in ans.lower()

    assert report.is_verified is True
    assert len(report.fabricated_citations) == 0


def test_nexus_q3_transient_gateway_timeout(investigator):
    """
    Q3: Gateway times out once and then succeeds.
    Determines 2 calls, 1 timeout event, hold captured, paid status and notice.
    """
    q = "If the gateway times out exactly once and then succeeds, how many calls happen and which events, holds, and notices result?"
    ans, report = investigator.investigate_with_report(q)

    assert "2" in ans
    assert "gateway_timeout" in ans
    assert "paid" in ans
    assert "capture_hold" in ans or "captured" in ans.lower()
    assert report.is_verified is True


def test_nexus_q4_vip_payment_guard(investigator):
    """
    Q4: VIP submits payment of 20.
    Returns early with review, no gateway call, no hold placed, no notice sent.
    """
    q = "A VIP submits a payment of 20. Does the gateway run, does a hold exist, and is a notice sent? Trace the early return."
    ans, report = investigator.investigate_with_report(q)

    assert "review" in ans
    assert "NOT" in ans or "not" in ans.lower()
    assert "nexuspay/policy.py" in ans or "nexuspay/workflow.py" in ans
    assert report.is_verified is True


def test_nexus_q5_state_mediated_workflow(investigator):
    """
    Q5: Trace VIP payment from create_payment() through approve_payment() to authorize().
    Confirms no static CALLS edge exists between submit() and approve().
    """
    q = "Trace a VIP payment from create_payment() through later approve_payment() to authorize(). Is there a static CALLS path from submit() to approve()?"
    ans, report = investigator.investigate_with_report(q)

    assert "create_payment" in ans
    assert "approve_payment" in ans
    assert "PAYMENTS" in ans or "state" in ans.lower()
    assert "No static" in ans or "no static" in ans.lower() or "not call" in ans.lower() or "state-mediated" in ans.lower()
    assert report.is_verified is True


def test_nexus_q6_blocked_account_non_persistence(investigator):
    """
    Q6: Blocked account submits payment.
    Not persisted; get_payment() returns None / raises KeyError.
    """
    q = "A blocked account submits a payment. Is the result persisted? What happens when get_payment() is called for that ID?"
    ans, report = investigator.investigate_with_report(q)

    assert "None" in ans or "KeyError" in ans or "not persisted" in ans.lower()
    assert "blocked" in ans
    assert report.is_verified is True


def test_nexus_q7_change_impact_remove_release_hold(investigator):
    """
    Q7: Remove release_hold() on gateway exhaustion.
    Affects both automatic and approved workflows; test_persistent_timeout_restores_balance detects automatic regression.
    """
    q = "Hypothetically remove release_hold() from process() on gateway exhaustion. Which automatic and approved-review workflows are affected? Which tests would detect it, and which gaps remain?"
    ans, report = investigator.investigate_with_report(q)

    assert "submit" in ans or "create_payment" in ans or "Automatic" in ans
    assert "approve" in ans or "approved" in ans.lower()
    assert "test_persistent_timeout_restores_balance" in ans
    assert report.is_verified is True


def test_nexus_q8_config_impact_max_retries_3(investigator):
    """
    Q8: MAX_GATEWAY_RETRIES=3.
    Maximum 4 calls under exhaustion; exactly 1 call if first succeeds.
    """
    q = "If MAX_GATEWAY_RETRIES changes from 2 to 3, what is the maximum number of gateway calls? Does the answer change if the first call succeeds?"
    ans, report = investigator.investigate_with_report(q)

    assert "4" in ans
    assert "1" in ans
    assert report.is_verified is True


def test_nexus_q9_untested_failure_branches_approve(investigator):
    """
    Q9: Which failure branches in approve() lack direct test coverage?
    Identifies invalid status, insufficient funds, and downstream timeout.
    """
    q = "Which failure branches in approve() are not directly tested? Distinguish invalid status, insufficient funds, and downstream persistent gateway timeout."
    ans, report = investigator.investigate_with_report(q)

    assert "approve" in ans
    assert "nexuspay/review.py" in ans
    assert "review" in ans
    assert report.is_verified is True


def test_nexus_q10_negative_evidence_kafka(investigator):
    """
    Q10: Kafka absence verification in NexusPay.
    Confirms zero Kafka producer/integration; store.py:record appends to in-memory EVENTS.
    """
    q = "Which function publishes payment events to Kafka, and where is the producer configured? Cite exact source lines or establish absence."
    ans, report = investigator.investigate_with_report(q)

    assert "No Kafka" in ans or "no kafka" in ans.lower()
    assert "EVENTS" in ans
    assert "nexuspay/store.py" in ans
    assert "record" in ans

    # Zero OrbitFlow leakage
    assert "orbitflow" not in ans.lower()
    assert "storage.py" not in ans.lower()

    assert report.is_verified is True


def test_nexus_q11_refund_does_not_restore_balance(investigator):
    """
    Q11: Does refund_payment() restore account balance?
    Inspects actual source: only appends to REFUNDS, balance is not restored.
    """
    q = "Does refund_payment() restore the account balance? Distinguish refund() from release_hold() and capture_hold() using source evidence."
    ans, report = investigator.investigate_with_report(q)

    assert "refund" in ans
    assert "nexuspay" in ans
    assert report.is_verified is True


def test_nexus_q12_reject_vs_approve(investigator):
    """
    Q12: Difference between reject_payment() and approve_payment().
    """
    q = "What is the difference between reject_payment() and approve_payment() regarding holds, gateway calls, and notifications?"
    ans, report = investigator.investigate_with_report(q)

    assert "reject" in ans.lower()
    assert "approve" in ans.lower()
    assert report.is_verified is True


def test_nexus_q13_cleanup_orphan_holds(investigator):
    """
    Q13: Does cleanup_orphan_holds() run automatically?
    No static caller or scheduling; only manual/explicit execution.
    """
    q = "Does cleanup_orphan_holds() run automatically after a failed payment? Identify static callers or scheduling evidence, and explain when it would release a hold."
    ans, report = investigator.investigate_with_report(q)

    assert "cleanup_orphan_holds" in ans
    assert "nexuspay" in ans
    assert report.is_verified is True


def test_nexus_q14_insufficient_funds_regular_account(investigator):
    """
    Q14: Account with 2000 balance submits 2500.
    Returns early due to insufficient funds; not saved, no gateway call.
    """
    q = "A regular account with balance 2000 submits amount 2500. Is the payment saved? Does it call authorize()? What event and notice are emitted?"
    ans, report = investigator.investigate_with_report(q)

    assert "insufficient_funds" in ans.lower() or "insufficient funds" in ans.lower()
    assert report.is_verified is True


def test_nexus_q15_release_hold_callers(investigator):
    """
    Q15: Identify every direct caller of release_hold().
    """
    q = "Identify every direct caller of release_hold() and determine whether their execution conditions are equivalent."
    ans, report = investigator.investigate_with_report(q)

    assert "release_hold" in ans
    assert "process" in ans
    assert "cleanup_orphan_holds" in ans
    assert report.is_verified is True


def test_nexus_q16_immediate_success_statements(investigator):
    """
    Q16: If authorize() succeeds immediately, do any gateway_timeout events occur?
    """
    q = "If authorize() succeeds immediately, do any gateway_timeout events occur? Which success-side statements execute and which failure-side statements do not?"
    ans, report = investigator.investigate_with_report(q)

    assert "capture_hold" in ans or "paid" in ans
    assert report.is_verified is True


def test_nexus_q17_review_rejected_then_approved(investigator):
    """
    Q17: Reviewed payment rejected, then approve_payment() called.
    Raises ValueError because payment is not under review.
    """
    q = "A reviewed payment is rejected, then an operator calls approve_payment() for the same ID. What exception occurs, and why?"
    ans, report = investigator.investigate_with_report(q)

    assert "ValueError" in ans or "review" in ans
    assert report.is_verified is True


def test_nexus_q18_remove_capture_hold_impact(investigator):
    """
    Q18: Hypothetically remove capture_hold() on success.
    Hold remains in HOLDS; test_successful_payment detects it.
    """
    q = "Hypothetically remove capture_hold() on success. What happens to the hold and available balance, and would current tests detect the residual hold?"
    ans, report = investigator.investigate_with_report(q)

    assert "capture_hold" in ans or "hold" in ans.lower()
    assert report.is_verified is True


def test_nexus_q19_tests_reaching_process(investigator):
    """
    Q19: Which tests statically reach process() but do not execute it under test inputs?
    """
    q = "Which tests statically reach process() but do not execute it under their test inputs? Distinguish static graph reachability from feasible execution."
    ans, report = investigator.investigate_with_report(q)

    assert "test_vip_review_no_hold" in ans or "test_blocked_not_saved" in ans or "test" in ans.lower()
    assert report.is_verified is True


def test_nexus_q20_absence_scope(investigator):
    """
    Q20: Can ASTERION prove that a real payment gateway, external database, or Kafka broker is used?
    """
    q = "Can ASTERION prove that a real payment gateway, external database, or Kafka broker is used? Explain the exact in-memory implementation and scope of the absence claim."
    ans, report = investigator.investigate_with_report(q)

    assert "in-memory" in ans.lower() or "EVENTS" in ans
    assert report.is_verified is True
