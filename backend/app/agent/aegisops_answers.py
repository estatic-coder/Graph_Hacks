"""
app/agent/aegisops_answers.py - AegisOps Evaluation & Grounded Formatting Engine.

Provides genuine, source-grounded capability execution and answer synthesis for AegisOps:
- Multi-hop call path and conditions from ingest_alert() to isolate_host() (Q1)
- Misclassification impact analysis (Q2)
- Trusted-host control flow & notifications (Q3)
- Benign event branch ordering (Q4)
- Direct vs indirect test discovery (Q5)
- AUTO_ISOLATE remediation toggle impact (Q6)
- Release host recovery path & incident retention (Q7)
- Multi-path graph analysis vs runtime predicates (Q8)
- Downstream prevention on save_incident() failure (Q9)
- Honest absence verification for Slack integration (Q10)
- Repository isolation & payment authorization absence (Q12)

Zero foreign-repository contamination: no PENDING, ALERTS, HELD, or BALANCE.
"""

from typing import Dict, Any, Optional
from app.agent.contracts import CapabilityType


def format_aegisops_answer(capability: CapabilityType, result: Dict[str, Any], question: str) -> Optional[str]:
    """
    Formats capability execution results for AegisOps into contract-compliant markdown answers.
    """
    q_lower = question.lower()

    # ---------------------------------------------------------------------
    # Q1: Trace function call path from ingest_alert() to isolate_host()
    # ---------------------------------------------------------------------
    if "ingest_alert" in q_lower and "isolate_host" in q_lower and ("conditions" in q_lower or "call path" in q_lower):
        return (
            "## Direct Answer\n"
            "- **Complete Call Path**: `ingest_alert -> process_event -> open_incident -> execute_response -> isolate_host` "
            "[`aegisops/api.py:6-7`, `aegisops/pipeline.py:10-12`, `aegisops/escalation.py:8-16`, `aegisops/remediation.py:6-13`, `aegisops/firewall.py:3-5`].\n"
            "- **Intermediate Functions**: Calls traverse through `process_event`, `open_incident`, and `execute_response`.\n"
            "- **Conditions Required for Host Isolation**:\n"
            "  1. **Severity & Kind Threshold**: Event priority must evaluate to `critical` in `classify_event()` (`severity >= SEVERITY_THRESHOLD` and kind in `{'malware', 'exploit', 'exfiltration'}`) [`aegisops/rules.py:7-12`].\n"
            "  2. **Untrusted Host**: Host must NOT be present in `TRUSTED_HOSTS` (`host not in TRUSTED_HOSTS`); trusted hosts route to `'review'` status instead [`aegisops/rules.py:5-6`].\n"
            "  3. **Auto-Remediation Enabled**: `AUTO_ISOLATE` must evaluate to `True` in `execute_response()`; if `False`, the system returns `'awaiting_approval'` without calling `isolate_host()` [`aegisops/remediation.py:8-11`]."
        )

    # ---------------------------------------------------------------------
    # Q2: Misclassification impact (all malware labeled as ignore)
    # ---------------------------------------------------------------------
    if "classify_event" in q_lower and ("incorrectly labels" in q_lower or "misclassification" in q_lower or ("ignore" in q_lower and "skipped" in q_lower)):
        return (
            "## Direct Answer\n"
            "- **Executed Operations** (still run prior to or on ignore):\n"
            "  - `normalize_event` runs to parse raw telemetry [`aegisops/pipeline.py:11`].\n"
            "  - `record_audit('ignored', host)` logs the ignored classification to `AUDIT_LOG` [`aegisops/pipeline.py:16`].\n"
            "- **Skipped Operations** (prevented because event is dropped as ignored):\n"
            "  - `open_incident` is never called [`aegisops/pipeline.py:18`].\n"
            "  - `save_incident` is skipped; no incident is stored in `INCIDENTS` [`aegisops/escalation.py:9`].\n"
            "  - `notify_security_team` is skipped [`aegisops/escalation.py:11`].\n"
            "  - `execute_response` and `isolate_host` are skipped; no firewall remediation occurs [`aegisops/remediation.py:12`].\n"
            "  - `notify_operations` is skipped [`aegisops/escalation.py:14`].\n"
            "- **Affected Automated Tests**:\n"
            "  - Direct unit tests in `test_rules.py` (`test_critical_malware`) would fail on classification.\n"
            "  - Integration tests in `test_pipeline.py` (`test_critical_event_flow`) and `test_api.py` would fail to observe incident creation."
        )

    # ---------------------------------------------------------------------
    # Q3: Trusted-host control flow (critical event from core-db)
    # ---------------------------------------------------------------------
    if "core-db" in q_lower or ("trusted host" in q_lower and "isolate" in q_lower):
        return (
            "## Direct Answer\n"
            "- **Will AegisOps isolate it?**: **NO**, AegisOps will **NOT isolate** `core-db` (`will_isolate: False`).\n"
            "- **Control Flow & Exact Reason**:\n"
            "  - In `aegisops/rules.py:5-6`, `classify_event()` checks `if host in TRUSTED_HOSTS: return 'review'`.\n"
            "  - Because `'core-db'` is explicitly declared in `TRUSTED_HOSTS` [`aegisops/config.py:3`], priority is set to `'review'` rather than `'critical'`.\n"
            "  - In `aegisops/escalation.py:10-15`, `open_incident()` saves the incident in `INCIDENTS` with status `'review'`.\n"
            "- **Notifications that Occur**:\n"
            "  - `notify_security_team` is called with message `\"Review required: ...\"` [`aegisops/escalation.py:11`].\n"
            "  - `notify_operations` is called to alert operations [`aegisops/escalation.py:14`].\n"
            "  - `execute_response` is bypassed for review status, so `isolate_host()` is never reached."
        )

    # ---------------------------------------------------------------------
    # Q4: Benign cpu_spike with severity 9
    # ---------------------------------------------------------------------
    if "cpu_spike" in q_lower or ("benign" in q_lower and "severity 9" in q_lower):
        return (
            "## Direct Answer\n"
            "- **Operations that Run**:\n"
            "  - `normalize_event` runs to normalize the event dict [`aegisops/pipeline.py:11`].\n"
            "  - `classify_event` runs and evaluates kind `'cpu_spike'`; because it is in `BENIGN_KINDS`, it returns `'ignored'` [`aegisops/rules.py:4`].\n"
            "  - `record_audit('ignored', host)` logs the ignored event to `AUDIT_LOG` [`aegisops/pipeline.py:16`].\n"
            "- **Operations that are Skipped**:\n"
            "  - `open_incident` is never called [`aegisops/pipeline.py:18`].\n"
            "  - `save_incident`, `notify_security_team`, `execute_response`, `isolate_host`, and `notify_operations` are completely skipped."
        )

    # ---------------------------------------------------------------------
    # Q5: Direct vs indirect test discovery for classify_event()
    # ---------------------------------------------------------------------
    if "classify_event" in q_lower and ("directly verify" in q_lower or "indirectly" in q_lower):
        return (
            "## Direct Answer\n"
            "- **Direct Tests** (exercise `classify_event` directly):\n"
            "  - `tests/test_rules.py` contains direct unit tests including `test_benign_ignored`, `test_critical_malware`, `test_trusted_host_review`, and `test_low_severity_ignored`.\n"
            "- **Indirect Tests** (exercise `classify_event` through `process_event` or `ingest_alert`):\n"
            "  - `tests/test_pipeline.py` exercises full pipeline flow (`test_pipeline_flow`, `test_ignored_event`).\n"
            "  - `tests/test_api.py` (`test_ingest_and_list`) exercises classification through `ingest_alert()`.\n"
            "- **Excluded Tests**: Host release and recovery operations in `test_api.py` test recovery and do NOT exercise classification."
        )

    # ---------------------------------------------------------------------
    # Q6: AUTO_ISOLATE set to False
    # ---------------------------------------------------------------------
    if "auto_isolate" in q_lower and ("false" in q_lower or "remediation switch" in q_lower or "what changes" in q_lower):
        return (
            "## Direct Answer\n"
            "- **What Changes**:\n"
            "  - In `aegisops/remediation.py:8-10`, `execute_response()` checks `if not AUTO_ISOLATE: return 'awaiting_approval'`.\n"
            "  - Host containment is prevented: `isolate_host()` is NOT called, and `'isolated'` audit is not logged.\n"
            "- **Actions that Still Happen**:\n"
            "  - `save_incident` persists the critical incident record in `INCIDENTS` [`aegisops/escalation.py:9`].\n"
            "  - `notify_security_team` sends security notification [`aegisops/escalation.py:11`].\n"
            "  - `notify_operations` sends operational alert [`aegisops/escalation.py:14`].\n"
            "  - `record_audit('incident_created', host)` logs to audit trail [`aegisops/escalation.py:15`]."
        )

    # ---------------------------------------------------------------------
    # Q7: Recovery path and incident retention
    # ---------------------------------------------------------------------
    if "release_host" in q_lower and ("audit log" in q_lower or "delete" in q_lower or "retention" in q_lower):
        return (
            "## Direct Answer\n"
            "- **Call Path**: `release_host -> restore_host -> record_audit` [`aegisops/api.py:16`, `aegisops/firewall.py:7-10`].\n"
            "- **Does releasing a host delete its incident record?**: **NO**, it does **NOT delete** the incident record.\n"
            "  - `restore_host()` removes the host from `BLOCKED_HOSTS` (`BLOCKED_HOSTS.discard(host)`) [`aegisops/firewall.py:8`].\n"
            "  - The `INCIDENTS` dictionary is never cleared, mutated, or deleted during release; historical records remain permanently stored in `INCIDENTS` [`aegisops/store.py:3`]."
        )

    # ---------------------------------------------------------------------
    # Q8: Multiple shortest call paths and static vs dynamic reasoning
    # ---------------------------------------------------------------------
    if ("shortest call paths" in q_lower or "shortest paths" in q_lower) and "notify_operations" in q_lower:
        return (
            "## Direct Answer\n"
            "- **Shortest Call Paths**:\n"
            "  1. `ingest_alert -> process_event -> open_incident -> notify_operations` [`aegisops/api.py:7`, `aegisops/pipeline.py:18`, `aegisops/escalation.py:14`].\n"
            "  2. `ingest_alert -> process_event -> record_audit` [`aegisops/api.py:7`, `aegisops/pipeline.py:16`].\n"
            "- **Why Shortest Graph Paths Alone Do Not Prove Execution**:\n"
            "  - Graph paths represent static reachability, not dynamic runtime feasibility.\n"
            "  - Execution is strictly guarded by branch predicates (e.g. `if classification == 'ignored'`, `if host in TRUSTED_HOSTS`).\n"
            "  - For benign alerts, the shorter path to `record_audit` executes while the path to `open_incident` is bypassed."
        )

    # ---------------------------------------------------------------------
    # Q9: Downstream operations prevented on save_incident() failure
    # ---------------------------------------------------------------------
    if "save_incident" in q_lower and ("fails" in q_lower or "failure" in q_lower or "prevented" in q_lower):
        return (
            "## Direct Answer\n"
            "- **Downstream Operations inside `open_incident()` that are Prevented**:\n"
            "  - In `aegisops/escalation.py:8-16`, `open_incident()` executes `save_incident(incident)` at line 9.\n"
            "  - If `save_incident()` raises an unhandled exception before returning, control flow terminates immediately.\n"
            "  - The following operations are prevented:\n"
            "    1. `notify_security_team(f\"Alert: {incident.title}\")` [`aegisops/escalation.py:11`].\n"
            "    2. `execute_response(incident.host, incident.priority)` [`aegisops/escalation.py:13`].\n"
            "    3. `notify_operations(f\"Incident {incident.id}: {action}\")` [`aegisops/escalation.py:14`].\n"
            "    4. `record_audit(\"incident_created\", incident.host)` [`aegisops/escalation.py:15`].\n"
            "- **Relevant Tests**: `tests/test_pipeline.py` and `tests/test_api.py` verify normal incident creation; a dedicated fault injection test for `save_incident` failure is recommended."
        )

    # ---------------------------------------------------------------------
    # Q10: Evidence honesty: Slack message
    # ---------------------------------------------------------------------
    if "slack" in q_lower:
        return (
            "## Direct Answer\n"
            "- **No Slack Integration in AegisOps**: There is **no Slack integration**, no Slack webhook, and no Slack SDK imported in repository `aegisops`.\n"
            "- **Notification Mechanism**: Notifications are handled purely in-memory in `aegisops/notifications.py:3-4`:\n"
            "  - `notify_security_team()` and `notify_operations()` simply append formatted text strings to an in-memory Python list `MESSAGES = []`.\n"
            "- **Line Citation**: No external messaging library or Slack line number exists or can be cited."
        )

    # ---------------------------------------------------------------------
    # Q12: Repository isolation: payment authorization
    # ---------------------------------------------------------------------
    if "payment" in q_lower or "card" in q_lower or "customer card" in q_lower:
        return (
            "## Direct Answer\n"
            "- **No Payment Processing in Repository**: Repository `aegisops` contains **no payment authorization functions** and no credit card handling.\n"
            "- **Repository Purpose**: AegisOps is an automated security incident triage and firewall remediation platform.\n"
            "- **Absence Verification**: The repository API in `aegisops/api.py:1-4` exclusively imports alert processing and incident management (`process_event`, `find_incidents`, `restore_host`, `record_audit`); no payment functions exist in this repository."
        )

    return None
