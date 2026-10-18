"""
app/agents/approval.py - Human-in-the-Loop Approval Gate (ASTERION V3)

Manages policy checks, risk evaluations, and explicit human authorization
for autonomous agent actions (code modifications, commands, deployments).
"""

import uuid
import time
import logging
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTO_APPROVED = "AUTO_APPROVED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalRequest(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act_{uuid.uuid4().hex[:10]}")
    action_type: str
    description: str
    risk_level: RiskLevel = RiskLevel.LOW
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: float = Field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None


class ApprovalGate:
    """
    Enforces risk-based authorization on agent actions.
    Low-risk actions can be auto-approved while High/Critical actions require human authorization.
    """

    def __init__(self, require_human_approval: bool = True, auto_approve_max_risk: RiskLevel = RiskLevel.LOW):
        self.require_human_approval = require_human_approval
        self.auto_approve_max_risk = auto_approve_max_risk
        self.requests: Dict[str, ApprovalRequest] = {}

    def request_approval(
        self,
        action_type: str,
        description: str,
        risk_level: RiskLevel = RiskLevel.LOW,
        payload: Optional[Dict[str, Any]] = None
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            action_type=action_type,
            description=description,
            risk_level=risk_level,
            payload=payload or {}
        )

        risk_hierarchy = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        req_risk_idx = risk_hierarchy.index(risk_level)
        max_auto_idx = risk_hierarchy.index(self.auto_approve_max_risk)

        if not self.require_human_approval or req_risk_idx <= max_auto_idx:
            req.status = ApprovalStatus.AUTO_APPROVED
            req.resolved_at = time.time()
            req.resolved_by = "SystemPolicyEngine"
            req.resolution_notes = f"Auto-approved within risk threshold ({risk_level.value})"
        else:
            req.status = ApprovalStatus.PENDING
            logger.info(f"Action '{action_type}' ({risk_level.value}) requires explicit approval: {description}")

        self.requests[req.action_id] = req
        return req

    def approve(self, action_id: str, reviewer: str = "admin", notes: Optional[str] = None) -> ApprovalRequest:
        if action_id not in self.requests:
            raise KeyError(f"Approval request '{action_id}' not found.")
        req = self.requests[action_id]
        req.status = ApprovalStatus.APPROVED
        req.resolved_at = time.time()
        req.resolved_by = reviewer
        req.resolution_notes = notes or "Authorized by reviewer"
        return req

    def reject(self, action_id: str, reviewer: str = "admin", reason: str = "Rejected by policy") -> ApprovalRequest:
        if action_id not in self.requests:
            raise KeyError(f"Approval request '{action_id}' not found.")
        req = self.requests[action_id]
        req.status = ApprovalStatus.REJECTED
        req.resolved_at = time.time()
        req.resolved_by = reviewer
        req.resolution_notes = reason
        return req

    def get_pending_requests(self) -> List[ApprovalRequest]:
        return [r for r in self.requests.values() if r.status == ApprovalStatus.PENDING]


default_approval_gate = ApprovalGate(require_human_approval=True, auto_approve_max_risk=RiskLevel.LOW)

