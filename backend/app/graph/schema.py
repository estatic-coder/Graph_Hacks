from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class NodeType(str, Enum):
    # Code Intelligence Nodes
    REPOSITORY = "Repository"
    REVISION = "Revision"
    DIRECTORY = "Directory"
    FILE = "File"
    MODULE = "Module"
    CLASS = "Class"
    INTERFACE = "Interface"
    ENUM = "Enum"
    FUNCTION = "Function"
    METHOD = "Method"
    CALLSITE = "CallSite"
    BRANCH = "Branch"
    IMPORT = "Import"
    ENDPOINT = "Endpoint"
    TABLE = "Table"
    CONFIG = "Config"
    CONFIGURATION = "Configuration"
    CONFIG_CONSTANT = "ConfigConstant"
    VARIABLE = "Variable"
    QUEUE = "Queue"
    STATE = "State"
    STATE_STORE = "StateStore"
    EXTERNAL_SERVICE = "ExternalService"
    TEST = "Test"
    CONCEPT = "Concept"

    # Agent Memory Nodes
    AGENT = "Agent"
    SESSION = "Session"
    INVESTIGATION_SESSION = "InvestigationSession"
    INVESTIGATION = "Investigation"
    OBSERVATION = "Observation"
    HYPOTHESIS = "Hypothesis"
    DECISION = "Decision"
    ACTION = "Action"
    OUTCOME = "Outcome"
    EPISODE = "Episode"
    FACT = "Fact"
    FINDING = "Finding"
    PROCEDURE = "Procedure"
    EVIDENCE = "Evidence"
    SOURCE_EVIDENCE = "SourceEvidence"
    AGENTTASK = "AgentTask"

    # Company Knowledge Nodes
    PERSON = "Person"
    TEAM = "Team"
    PROJECT = "Project"
    ISSUE = "Issue"
    PULL_REQUEST = "PullRequest"
    COMMIT = "Commit"
    DOCUMENT = "Document"
    DECISION_RECORD = "DecisionRecord"
    SYSTEM = "System"

class RelType(str, Enum):
    # Structural & Code Relationships
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    DEFINES = "DEFINES"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    READS_FROM = "READS_FROM"
    WRITES_TO = "WRITES_TO"
    EXPOSES = "EXPOSES"
    TESTS = "TESTS"
    COVERS = "COVERS"
    DOCUMENTS = "DOCUMENTS"
    DEPENDS_ON = "DEPENDS_ON"
    AFFECTS = "AFFECTS"
    WRITES_STATE = "WRITES_STATE"
    READS_STATE = "READS_STATE"
    ENQUEUES = "ENQUEUES"
    DEQUEUES = "DEQUEUES"
    STATE_TRANSITION = "STATE_TRANSITION"
    RESUMES_VIA = "RESUMES_VIA"

    # Agent Reasoning & Memory Relationships
    OBSERVED = "OBSERVED"
    OBSERVED_IN = "OBSERVED_IN"
    SUPPORTS = "SUPPORTS"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTS = "CONTRADICTS"
    DECIDED = "DECIDED"
    EXECUTED = "EXECUTED"
    PRODUCED = "PRODUCED"
    LEARNED = "LEARNED"
    REMEMBERS = "REMEMBERS"
    RECORDED = "RECORDED"
    PROPOSED = "PROPOSED"
    EVIDENCED_BY = "EVIDENCED_BY"
    REFERENCES = "REFERENCES"
    TARGETS = "TARGETS"
    FOLLOWED_PROCEDURE = "FOLLOWED_PROCEDURE"
    INVALIDATES = "INVALIDATES"
    SUPERSEDES = "SUPERSEDES"
    HANDOFF_TO = "HANDOFF_TO"

    # Company Knowledge Relationships
    OWNED_BY = "OWNED_BY"
    WORKED_ON = "WORKED_ON"
    DOCUMENTED_IN = "DOCUMENTED_IN"

class NodeBase(BaseModel):
    id: str = Field(..., description="Stable ID for the entity")
    repository_id: str = Field(..., description="ID of the repository this belongs to")
    name: str = Field(..., description="Name of the entity")
    source_path: Optional[str] = Field(None, description="Path to the source file")
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    properties: Dict[str, Any] = Field(default_factory=dict)

class EdgeBase(BaseModel):
    source_id: str
    target_id: str
    type: RelType
    provenance: Optional[str] = Field(None, description="Source file/line or method of extraction")
    confidence: Optional[float] = Field(1.0, description="Confidence of the relationship (0.0 to 1.0)")
    is_inferred: bool = Field(False, description="True if inferred by AI, False if statically extracted")
    properties: Dict[str, Any] = Field(default_factory=dict)

STATIC_REL_TYPES = {
    RelType.CALLS,
    RelType.ENQUEUES,
    RelType.DEQUEUES,
    RelType.READS_STATE,
    RelType.WRITES_STATE,
    RelType.STATE_TRANSITION,
    RelType.DEFINES,
    RelType.IMPORTS,
    RelType.CONTAINS,
    RelType.INHERITS,
    RelType.TESTS,
}

INFERRED_REL_TYPES = {
    RelType.RESUMES_VIA,
    RelType.AFFECTS,
    RelType.DEPENDS_ON,
}

ALL_REL_TYPES = STATIC_REL_TYPES.union(INFERRED_REL_TYPES)

def is_inferred_relationship(rel_type: Any) -> bool:
    """Classifies whether a relationship type is an inferred workflow handoff vs static edge."""
    s = str(rel_type.value if hasattr(rel_type, "value") else rel_type).upper()
    return "RESUMES_VIA" in s or s in {r.value for r in INFERRED_REL_TYPES}

def is_static_relationship(rel_type: Any) -> bool:
    """Classifies whether a relationship type is a verified static graph edge."""
    s = str(rel_type.value if hasattr(rel_type, "value") else rel_type).upper()
    return s in {r.value for r in STATIC_REL_TYPES}

