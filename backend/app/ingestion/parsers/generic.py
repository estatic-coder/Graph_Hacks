import re
import json
import yaml
from typing import List, Tuple
from app.ingestion.parsers.base import BaseParser
from app.ingestion.models import ParsedSymbol, ParsedRelationship
from app.graph.schema import NodeType, RelType

class GenericCodeParser(BaseParser):
    """Regex fallback parser for Java, C/C++, SQL, etc."""
    def parse(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        symbols = []
        relationships = []
        
        # Simple heuristic for functions/methods in C-like languages
        for match in re.finditer(r'(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(', content):
            name = match.group(1)
            # Ignore common control flow words
            if name in ["if", "for", "while", "switch", "catch"]:
                continue
            symbols.append(ParsedSymbol(
                type=NodeType.FUNCTION,
                name=name,
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1
            ))
            
        return symbols, relationships

class ConfigParser(BaseParser):
    """Parser for JSON and YAML."""
    def parse(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        symbols = []
        relationships = []
        
        try:
            if filepath.endswith('.json'):
                data = json.loads(content)
            elif filepath.endswith(('.yaml', '.yml')):
                data = yaml.safe_load(content)
            else:
                return symbols, relationships
                
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, (str, int, float, bool)):
                        symbols.append(ParsedSymbol(
                            type=NodeType.CONFIG,
                            name=k,
                            start_line=1,
                            end_line=1
                        ))
        except Exception:
            pass
            
        return symbols, relationships

class MarkdownParser(BaseParser):
    """Parser for Markdown documentation."""
    def parse(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        symbols = []
        relationships = []
        
        for match in re.finditer(r'^#+\s+(.+)$', content, re.MULTILINE):
            symbols.append(ParsedSymbol(
                type=NodeType.CONCEPT,
                name=match.group(1).strip(),
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1
            ))
            
        return symbols, relationships
