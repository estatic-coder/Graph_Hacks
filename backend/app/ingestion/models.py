from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from app.graph.schema import NodeType, RelType

@dataclass
class ParsedSymbol:
    type: NodeType
    name: str
    start_line: int
    end_line: int
    parent_name: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ParsedRelationship:
    source_name: str
    target_name: str
    type: RelType
    confidence: float
    is_inferred: bool
    provenance: Optional[str] = None
    target_module: Optional[str] = None
    level: Optional[int] = 0
    properties: Dict[str, Any] = field(default_factory=dict)
