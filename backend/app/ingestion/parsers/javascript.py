import os
import re
import logging
from typing import List, Tuple
from app.ingestion.parsers.base import BaseParser
from app.ingestion.models import ParsedSymbol, ParsedRelationship
from app.ingestion.parsers.typescript import TypeScriptASTVisitor, TREE_SITTER_AVAILABLE

logger = logging.getLogger(__name__)

JS_AVAILABLE = False
try:
    import tree_sitter
    import tree_sitter_javascript as tsjs
    JS_LANGUAGE = tree_sitter.Language(tsjs.language())
    JS_AVAILABLE = True
except Exception as e:
    logger.warning(f"tree-sitter-javascript not available ({e}), will fall back to regex.")


class JavaScriptParser(BaseParser):
    """
    AST-based parser for JavaScript (.js) and JSX (.jsx) using tree-sitter.
    Extracts classes, functions, methods, imports, exports, calls, and JSX usages.
    """

    def __init__(self, is_jsx: bool = False):
        self.is_jsx = is_jsx
        self._parser = None
        if JS_AVAILABLE:
            try:
                self._parser = tree_sitter.Parser(JS_LANGUAGE)
            except Exception as e:
                logger.warning(f"Failed to initialize tree-sitter JS parser: {e}")

    def parse(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        is_jsx = self.is_jsx or filepath.endswith(".jsx")
        
        # If JSX is requested, use TypeScriptParser with TSX grammar (which fully supports JS + JSX)
        if is_jsx and TREE_SITTER_AVAILABLE:
            from app.ingestion.parsers.typescript import TypeScriptParser
            ts_parser = TypeScriptParser(is_tsx=True)
            symbols, rels = ts_parser.parse(filepath, content)
            for s in symbols:
                s.language = "jsx"
            return symbols, rels

        if not JS_AVAILABLE or self._parser is None:
            return self._regex_fallback(filepath, content)

        try:
            content_bytes = content.encode("utf-8", errors="replace")
            tree = self._parser.parse(content_bytes)
            visitor = TypeScriptASTVisitor(content_bytes, filepath, is_tsx=False)
            visitor.language = "javascript"
            visitor.visit(tree.root_node)
            return visitor.symbols, visitor.relationships
        except Exception as e:
            logger.error(f"Tree-sitter JS parse error for {filepath}: {e}, falling back to regex.")
            return self._regex_fallback(filepath, content)

    def _regex_fallback(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        from app.ingestion.parsers.fallback import RegexFallbackParser
        return RegexFallbackParser().parse(filepath, content)
