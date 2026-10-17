"""
app/agent/scenario_ledger.py - Canonical Scenario Ledger for State & Execution Reasoning.

Maintains a ground-truth, deterministic ledger of all system state transitions,
resource holds/releases/commits, retry loop executions, exceptions, ordered event logs,
notices, and cumulative counters.

Guarantees that all numbers, statuses, and sequences in answers are derived
from a single canonical source of truth rather than independently regenerated.
"""

from typing import Dict, List, Set, Any, Optional, Tuple
from dataclasses import dataclass, field
import copy
import logging

logger = logging.getLogger(__name__)


@dataclass
class ScenarioEvent:
    entity_id: str
    event: str
    step: int
    details: Optional[Dict[str, Any]] = None

    def to_tuple(self) -> Tuple[str, str]:
        return (self.entity_id, self.event)


@dataclass
class ScenarioNotice:
    entity_id: str
    kind: str
    step: int

    def to_tuple(self) -> Tuple[str, str]:
        return (self.entity_id, self.kind)


class CanonicalScenarioLedger:
    """
    Canonical state machine and event ledger for scenario simulations.
    Supports OrbitOps, SignalForge, RelayMesh, and arbitrary repository models.
    """

    def __init__(self, repo_id: str = "orbitops"):
        self.repo_id = repo_id
        self.step_counter = 0

        # State storage
        self.balance: Dict[str, int] = {"core": 4, "security": 2}
        self.held: Set[str] = set()
        self.records: Dict[str, Dict[str, Any]] = {}
        self.pending_queue: List[str] = []
        self.events: List[ScenarioEvent] = []
        self.notices: List[ScenarioNotice] = []
        self.calls: Dict[str, int] = {}
        self.incidents: List[str] = []
        self.reopened: Dict[str, int] = {}

        # Configuration limits
        self.max_attempts: int = 2
        self.max_reopen: int = 1
        self.review_teams: Set[str] = {"security"}
        self.muted_sources: Set[str] = {"synthetic"}

        # Execution flags for simulation
        self.always_fail: Set[str] = set()
        self.fail_first: Set[str] = set()

        # DeployWeave state engine
        self.dw_slots: Dict[str, int] = {"auth": 2, "ledger": 2, "gateway": 1}
        self.dw_locked: Set[str] = set()
        self.dw_versions: Dict[str, str] = {"auth": "1.0", "ledger": "1.0", "gateway": "1.0"}
        self.dw_changes: List[Tuple[str, str, str]] = []
        self.dw_rollouts: Dict[str, Dict[str, Any]] = {}
        self.dw_events: List[Tuple[str, str]] = []
        self.dw_ready: List[str] = []
        self.dw_audit: List[Tuple[str, str]] = []
        self.dw_notices: List[Tuple[str, str]] = []
        self.dw_rollback_counts: Dict[str, int] = {}
        self.dw_checks: Dict[str, int] = {}
        self.dw_always_bad: Set[str] = set()
        self.dw_bad_first: Set[str] = set()
        self.dw_dependencies: Dict[str, Tuple[str, ...]] = {'gateway': ('auth', 'ledger'), 'auth': ('ledger',), 'ledger': ()}
        self.dw_critical_services: Set[str] = {'gateway'}
        self.dw_muted_envs: Set[str] = {'sandbox'}
        self.dw_max_health_retries: int = 2
        self.dw_max_rollbacks: int = 1

    def emit_event(self, entity_id: str, event_name: str, details: Optional[Dict[str, Any]] = None):
        self.step_counter += 1
        self.events.append(ScenarioEvent(entity_id=entity_id, event=event_name, step=self.step_counter, details=details))

    def emit_notice(self, entity_id: str, kind: str):
        self.step_counter += 1
        self.notices.append(ScenarioNotice(entity_id=entity_id, kind=kind, step=self.step_counter))

    # -------------------------------------------------------------------------
    # DeployWeave State Engine
    # -------------------------------------------------------------------------

    def dw_reset(self, slots=None, versions=None):
        self.dw_slots = copy.deepcopy(slots) if slots else {"auth": 2, "ledger": 2, "gateway": 1}
        self.dw_locked = set()
        self.dw_versions = copy.deepcopy(versions) if versions else {"auth": "1.0", "ledger": "1.0", "gateway": "1.0"}
        self.dw_changes = []
        self.dw_rollouts = {}
        self.dw_events = []
        self.dw_ready = []
        self.dw_audit = []
        self.dw_notices = []
        self.dw_rollback_counts = {}
        self.dw_checks = {}
        self.dw_always_bad = set()
        self.dw_bad_first = set()

    def dw_dependencies_healthy(self, service: str) -> bool:
        for dep in self.dw_dependencies.get(service, ()):
            if self.dw_versions.get(dep) is None:
                return False
        return True

    def dw_classify(self, service: str, environment: str) -> str:
        if environment in self.dw_muted_envs:
            return 'muted'
        if service in self.dw_critical_services or environment == 'production':
            return 'review'
        return 'ready'

    def dw_acquire(self, rollout_id: str, service: str) -> bool:
        if self.dw_slots.get(service, 0) <= 0:
            return False
        self.dw_slots[service] -= 1
        self.dw_locked.add(rollout_id)
        if rollout_id in self.dw_rollouts:
            self.dw_rollouts[rollout_id]["reserved"] = True
        return True

    def dw_refund(self, rollout_id: str, service: str):
        if rollout_id in self.dw_locked:
            self.dw_locked.remove(rollout_id)
            self.dw_slots[service] += 1
        if rollout_id in self.dw_rollouts:
            self.dw_rollouts[rollout_id]["reserved"] = False

    def dw_commit(self, rollout_id: str):
        self.dw_locked.discard(rollout_id)
        if rollout_id in self.dw_rollouts:
            self.dw_rollouts[rollout_id]["reserved"] = False

    def dw_install(self, rollout_id: str, service: str, version: str) -> str:
        old = self.dw_versions[service]
        self.dw_versions[service] = version
        self.dw_changes.append((rollout_id, old, version))
        return old

    def dw_restore(self, rollout_id: str, service: str, old: str):
        curr = self.dw_versions[service]
        self.dw_versions[service] = old
        self.dw_changes.append((rollout_id, curr, old))

    def dw_probe(self, rollout_id: str) -> bool:
        n = self.dw_checks.get(rollout_id, 0) + 1
        self.dw_checks[rollout_id] = n
        if rollout_id in self.dw_always_bad:
            return False
        if rollout_id in self.dw_bad_first and n == 1:
            return False
        return True

    def dw_submit(self, rollout_id: Any, service: Optional[str] = None, environment: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        if isinstance(rollout_id, dict):
            d = rollout_id
            rollout_id = d.get("rollout_id", "r1")
            service = d.get("service", "auth")
            environment = d.get("environment", "staging")
            version = d.get("version", "2.0")
        r = {
            "rollout_id": rollout_id,
            "service": service,
            "environment": environment,
            "version": version,
            "status": "pending",
            "attempts": 0,
            "reserved": False
        }
        choice = self.dw_classify(service, environment)
        if choice == 'muted':
            r["status"] = 'muted'
            self.dw_events.append((rollout_id, 'muted'))
            return r

        if not self.dw_dependencies_healthy(service):
            r["status"] = 'blocked'
            self.dw_events.append((rollout_id, 'missing_dependency'))
            self.dw_rollouts[rollout_id] = r
            return r

        if choice == 'review':
            r["status"] = 'review'
            self.dw_events.append((rollout_id, 'review_requested'))
            self.dw_rollouts[rollout_id] = r
            return r

        if not self.dw_acquire(rollout_id, service):
            r["status"] = 'no_slot'
            self.dw_events.append((rollout_id, 'slot_denied'))
            return r

        r["status"] = 'ready'
        self.dw_rollouts[rollout_id] = r
        self.dw_ready.append(rollout_id)
        self.dw_events.append((rollout_id, 'ready'))
        return r

    def dw_approve(self, rollout_id: str) -> Dict[str, Any]:
        if rollout_id not in self.dw_rollouts:
            raise KeyError(rollout_id)
        r = self.dw_rollouts[rollout_id]
        if r["status"] != 'review':
            raise ValueError('not in review')
        if not self.dw_acquire(rollout_id, r["service"]):
            r["status"] = 'no_slot'
            self.dw_events.append((rollout_id, 'approval_slot_denied'))
            return r
        r["status"] = 'ready'
        self.dw_ready.append(rollout_id)
        self.dw_events.append((rollout_id, 'approved'))
        return r

    def dw_deny(self, rollout_id: str) -> Dict[str, Any]:
        if rollout_id not in self.dw_rollouts:
            raise KeyError(rollout_id)
        r = self.dw_rollouts[rollout_id]
        if r["status"] != 'review':
            raise ValueError('not in review')
        r["status"] = 'denied'
        self.dw_events.append((rollout_id, 'denied'))
        return r

    def dw_drain_one(self, max_health_retries_override: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if not self.dw_ready:
            return None
        k = self.dw_ready.pop(0)
        r = self.dw_rollouts[k]
        if r["status"] != 'ready':
            return r

        # Execute
        retries_limit = max_health_retries_override if max_health_retries_override is not None else self.dw_max_health_retries
        old = self.dw_install(k, r["service"], r["version"])
        self.dw_audit.append((k, 'installed'))

        while r["attempts"] <= retries_limit:
            r["attempts"] += 1
            if self.dw_probe(k):
                self.dw_commit(k)
                r["status"] = 'deployed'
                self.dw_events.append((k, 'deployed'))
                self.dw_notices.append((k, 'deployed'))
                return r
            self.dw_events.append((k, 'health_failed'))

        self.dw_restore(k, r["service"], old)
        self.dw_audit.append((k, 'restored'))
        self.dw_refund(k, r["service"])
        r["status"] = 'rolled_back'
        self.dw_events.append((k, 'rolled_back'))
        self.dw_notices.append((k, 'rolled_back'))
        return r

    def dw_retry_rollback(self, rollout_id: str) -> Dict[str, Any]:
        if rollout_id not in self.dw_rollouts:
            raise KeyError(rollout_id)
        r = self.dw_rollouts[rollout_id]
        if r["status"] != 'rolled_back':
            raise ValueError('not rolled back')
        used = self.dw_rollback_counts.get(rollout_id, 0)
        if used >= self.dw_max_rollbacks:
            raise ValueError('retry budget exhausted')
        self.dw_rollback_counts[rollout_id] = used + 1
        if not self.dw_acquire(rollout_id, r["service"]):
            self.dw_events.append((rollout_id, 'retry_slot_denied'))
            return r
        r["attempts"] = 0
        r["status"] = 'ready'
        self.dw_ready.append(rollout_id)
        self.dw_events.append((rollout_id, 'retried'))
        return r

    def get_dw_summary_dict(self) -> Dict[str, Any]:
        return {
            "SLOTS": copy.deepcopy(self.dw_slots),
            "LOCKED": list(sorted(self.dw_locked)),
            "VERSIONS": copy.deepcopy(self.dw_versions),
            "READY": list(self.dw_ready),
            "CHECKS": copy.deepcopy(self.dw_checks),
            "CHANGES": list(self.dw_changes),
            "EVENTS": list(self.dw_events),
            "AUDIT": list(self.dw_audit),
            "NOTICES": list(self.dw_notices),
            "ROLLBACK_COUNTS": copy.deepcopy(self.dw_rollback_counts),
            "ROLLOUTS": {k: copy.deepcopy(v) for k, v in self.dw_rollouts.items()}
        }
    # OrbitOps Model Execution
    # -------------------------------------------------------------------------

    def create_alert(
        self,
        alert_id: str = "a1",
        service: str = "billing",
        team: str = "core",
        severity: int = 3,
        source: str = "production"
    ) -> Dict[str, Any]:
        """Simulates orbitops.api.create_alert() -> intake.submit()."""
        alert = {
            "alert_id": alert_id,
            "service": service,
            "team": team,
            "severity": severity,
            "source": source,
            "status": "pending",
            "attempts": 0,
            "incident_key": None,
            "reserved": False
        }

        # Policy decision
        if source in self.muted_sources:
            alert["status"] = "muted"
            self.emit_event(alert_id, "muted")
            return alert

        if team in self.review_teams or severity >= 8:
            alert["status"] = "review"
            self.records[alert_id] = alert
            self.emit_event(alert_id, "review_requested")
            return alert

        # Hold check
        if self.balance.get(team, 0) < 1:
            alert["status"] = "no_credit"
            self.emit_event(alert_id, "credit_denied")
            return alert

        self.balance[team] -= 1
        self.held.add(alert_id)
        alert["reserved"] = True
        alert["status"] = "pending"
        self.records[alert_id] = alert
        self.pending_queue.append(alert_id)
        self.emit_event(alert_id, "pending")
        return alert

    def approve_alert(self, alert_id: str) -> Dict[str, Any]:
        """Simulates orbitops.api.approve_alert() -> review.authorize()."""
        alert = self.records.get(alert_id)
        if not alert:
            raise KeyError(f"Alert '{alert_id}' not found")
        if alert.get("status") != "review":
            raise ValueError("not under review")

        team = alert.get("team", "core")
        if self.balance.get(team, 0) < 1:
            alert["status"] = "no_credit"
            self.emit_event(alert_id, "approval_credit_denied")
            return alert

        self.balance[team] -= 1
        self.held.add(alert_id)
        alert["reserved"] = True
        alert["status"] = "pending"
        self.pending_queue.append(alert_id)
        self.emit_event(alert_id, "authorized")
        return alert

    def reject_alert(self, alert_id: str) -> Dict[str, Any]:
        """Simulates orbitops.api.reject_alert() -> review.decline()."""
        alert = self.records.get(alert_id)
        if not alert:
            raise KeyError(f"Alert '{alert_id}' not found")
        if alert.get("status") != "review":
            raise ValueError("not under review")

        alert["status"] = "declined"
        self.emit_event(alert_id, "declined")
        return alert

    def drain_one(
        self,
        custom_always_fail: Optional[bool] = None,
        custom_fail_first: Optional[bool] = None,
        max_attempts_override: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Simulates orbitops.api.run_agent_once() -> consumer.drain_one() -> worker.deliver()."""
        if not self.pending_queue:
            return None

        # Destructive queue pop before deliver()
        alert_id = self.pending_queue.pop(0)
        alert = self.records.get(alert_id)
        if not alert:
            return None

        if alert.get("status") != "pending":
            return alert

        max_att = max_attempts_override if max_attempts_override is not None else self.max_attempts
        return self._deliver(
            alert,
            custom_always_fail=custom_always_fail,
            custom_fail_first=custom_fail_first,
            max_attempts=max_att
        )

    def _deliver(
        self,
        alert: Dict[str, Any],
        custom_always_fail: Optional[bool] = None,
        custom_fail_first: Optional[bool] = None,
        max_attempts: int = 2
    ) -> Dict[str, Any]:
        """Simulates worker.deliver() inclusive while loop and exception handling."""
        alert_id = alert["alert_id"]
        team = alert.get("team", "core")

        while alert["attempts"] <= max_attempts:
            alert["attempts"] += 1
            n = self.calls.get(alert_id, 0) + 1
            self.calls[alert_id] = n

            # Pager failure check
            is_always = custom_always_fail if custom_always_fail is not None else (alert_id in self.always_fail)
            is_first = custom_fail_first if custom_fail_first is not None else (alert_id in self.fail_first)

            if is_always or (is_first and n == 1):
                # TimeoutError caught
                self.emit_event(alert_id, "page_timeout")
                continue

            # Success path
            # commit(alert)
            self.held.discard(alert_id)
            alert["reserved"] = False
            key = f"INC-{alert_id}-{n}"
            self.incidents.append(key)
            alert["incident_key"] = key
            alert["status"] = "sent"
            self.emit_event(alert_id, "sent")
            self.emit_notice(alert_id, "sent")
            return alert

        # Loop exhaustion path
        # release(alert)
        if alert_id in self.held:
            self.held.remove(alert_id)
            self.balance[team] += 1
        alert["reserved"] = False
        alert["status"] = "failed"
        self.emit_event(alert_id, "failed")
        self.emit_notice(alert_id, "failed")
        return alert

    def retry_failed_alert(self, alert_id: str) -> Dict[str, Any]:
        """Simulates orbitops.api.retry_failed_alert() -> reopen.reopen_failed()."""
        alert = self.records.get(alert_id)
        if not alert:
            raise KeyError(f"Alert '{alert_id}' not found")
        if alert.get("status") != "failed":
            raise ValueError("not failed")

        used = self.reopened.get(alert_id, 0)
        if used >= self.max_reopen:
            raise ValueError("reopen budget exceeded")

        # Increment occurs BEFORE hold!
        self.reopened[alert_id] = used + 1

        team = alert.get("team", "core")
        if self.balance.get(team, 0) < 1:
            self.emit_event(alert_id, "reopen_credit_denied")
            return alert

        self.balance[team] -= 1
        self.held.add(alert_id)
        alert["reserved"] = True
        alert["attempts"] = 0  # Resets attempt counter!
        alert["status"] = "pending"
        self.pending_queue.append(alert_id)
        self.emit_event(alert_id, "reopened")
        return alert

    def sweep_holds(self) -> List[str]:
        """Simulates orbitops.maintenance.sweep_holds()."""
        cleaned = []
        for alert_id in list(self.held):
            alert = self.records.get(alert_id)
            if alert and alert.get("status") in ("sent", "failed", "declined"):
                self.held.remove(alert_id)
                team = alert.get("team", "core")
                self.balance[team] += 1
                cleaned.append(alert_id)
        return cleaned

    def get_alert(self, alert_id: str) -> Dict[str, Any]:
        if alert_id not in self.records:
            raise KeyError(alert_id)
        return self.records[alert_id]

    # -------------------------------------------------------------------------
    # Snapshot & Contract Compliance Export
    # -------------------------------------------------------------------------

    def get_summary_dict(self, primary_id: str = "a1") -> Dict[str, Any]:
        """Exports a complete dictionary satisfying all answer contracts."""
        alert = self.records.get(primary_id, {})
        ordered_events_str = [f"({e.entity_id}, {e.event})" for e in self.events]
        ordered_notices_str = [f"({n.entity_id}, {n.kind})" for n in self.notices]

        timeout_count = sum(1 for e in self.events if e.event == "page_timeout" and e.entity_id == primary_id)
        calls_count = self.calls.get(primary_id, 0)

        return {
            "alert_id": primary_id,
            "status": alert.get("status", "unknown"),
            "final_status": alert.get("status", "unknown"),
            "pager_calls": calls_count,
            "call_count": calls_count,
            "timeouts": timeout_count,
            "timeout_count": timeout_count,
            "balance": copy.deepcopy(self.balance),
            "core_balance": self.balance.get("core", 0),
            "security_balance": self.balance.get("security", 0),
            "held": list(self.held),
            "reservation": "empty" if len(self.held) == 0 else f"held {list(self.held)}",
            "pending_queue": list(self.pending_queue),
            "ordered_events": [e.to_tuple() for e in self.events],
            "ordered_events_str": ordered_events_str,
            "notices": [n.to_tuple() for n in self.notices],
            "notices_str": ordered_notices_str,
            "incident_key": alert.get("incident_key"),
            "reopened_count": self.reopened.get(primary_id, 0),
            "attempts": alert.get("attempts", 0)
        }
