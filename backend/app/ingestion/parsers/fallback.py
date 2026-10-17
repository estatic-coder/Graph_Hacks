import re
from typing import List, Tuple
from app.ingestion.parsers.base import BaseParser
from app.ingestion.models import ParsedSymbol, ParsedRelationship
from app.graph.schema import NodeType, RelType

class RegexFallbackParser(BaseParser):
    """Fallback parser for JS/TS using regex."""
    def parse(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        symbols = []
        relationships = []
        
        # Simple heuristic for functions
        for match in re.finditer(r'function\s+(\w+)\s*\(', content):
            symbols.append(ParsedSymbol(
                type=NodeType.FUNCTION,
                name=match.group(1),
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1
            ))
            
        # Simple heuristic for fetch calls (API dependencies)
        for match in re.finditer(r'fetch\([\'"`]([^\'"`]+)[\'"`]\)', content):
            relationships.append(ParsedRelationship(
                source_name="FILE",
                target_name=match.group(1),
                type=RelType.DEPENDS_ON,
                confidence=0.5,
                is_inferred=True,
                provenance="Regex match for fetch"
            ))
            
        return symbols, relationships
