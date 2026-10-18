"""
app/agents/__init__.py - Specialized Agent Roles & Human-in-the-Loop Approval (ASTERION V3)
"""

from app.agents.approval import (
    ApprovalGate,
    ApprovalRequest,
    ApprovalStatus,
    RiskLevel
)
from app.agents.base_agent import BaseAgent
from app.agents.code_navigator import CodeNavigatorAgent
from app.agents.impact_evaluator import ImpactEvaluatorAgent
from app.agents.test_strategist import TestStrategistAgent
from app.agents.audit_reviewer import AuditReviewerAgent

__all__ = [
    "ApprovalGate",
    "ApprovalRequest",
    "ApprovalStatus",
    "RiskLevel",
    "BaseAgent",
    "CodeNavigatorAgent",
    "ImpactEvaluatorAgent",
    "TestStrategistAgent",
    "AuditReviewerAgent"
]
