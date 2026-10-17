from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class InvestigationSession(BaseModel):
    id: str = Field(..., description="Unique graph node ID: sess_{repo_id}_{session_id}")
    session_id: str = Field(..., description="Session identifier")
    repo_id: str
    workspace_id: str = "default"
    query: str
    source_revision: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "completed"

class SourceEvidenceItem(BaseModel):
    id: str
    file_path: str
    start_line: int
    end_line: int
    code_snippet: str
    snippet_hash: str

class Finding(BaseModel):
    id: str = Field(..., description="Unique graph node ID: finding_{repo_id}_{finding_id}")
    finding_id: str
    session_id: str
    repo_id: str
    workspace_id: str = "default"
    title: str
    claim: str
    source_revision: str
    source_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    snippet_hash: Optional[str] = None
    graph_paths: List[str] = Field(default_factory=list)
    is_verified: bool = True
    is_stale: bool = False
    stale_reason: Optional[str] = None
    confidence: float = 1.0
    referenced_symbol_ids: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class Hypothesis(BaseModel):
    id: str = Field(..., description="Unique graph node ID: hypo_{repo_id}_{hypo_id}")
    hypo_id: str
    session_id: str
    repo_id: str
    workspace_id: str = "default"
    statement: str
    status: str = "unresolved" # "unresolved" | "validated" | "rejected"
    target_symbol_ids: List[str] = Field(default_factory=list)
    resolution_notes: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class InvestigationProcedure(BaseModel):
    id: str = Field(..., description="Unique graph node ID: proc_{repo_id}_{proc_id}")
    proc_id: str
    repo_id: str
    name: str
    intent_category: str
    description: str
    tool_sequence: List[str] = Field(default_factory=list)
    query_template: str = ""
    success_count: int = 1
