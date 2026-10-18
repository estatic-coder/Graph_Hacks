import os
import re
import logging
from typing import List, Tuple, Optional, Set, Dict, Any
from app.ingestion.parsers.base import BaseParser
from app.ingestion.models import ParsedSymbol, ParsedRelationship
from app.graph.schema import NodeType, RelType

logger = logging.getLogger(__name__)

# Try importing tree_sitter and tree_sitter_typescript
TREE_SITTER_AVAILABLE = False
try:
    import tree_sitter
    import tree_sitter_typescript as tsts
    TS_LANGUAGE = tree_sitter.Language(tsts.language_typescript())
    TSX_LANGUAGE = tree_sitter.Language(tsts.language_tsx())
    TREE_SITTER_AVAILABLE = True
except Exception as e:
    logger.warning(f"tree-sitter-typescript not available ({e}), will fall back to regex.")


class TypeScriptParser(BaseParser):
    """
    AST-based parser for TypeScript (.ts) and TSX (.tsx) using tree-sitter.
    Extracts classes, interfaces, types, enums, functions, methods, imports,
    exports, calls, inheritance, implementations, and JSX component usages.
    """

    def __init__(self, is_tsx: bool = False):
        self.is_tsx = is_tsx
        self._parser_ts = None
        self._parser_tsx = None
        if TREE_SITTER_AVAILABLE:
            try:
                self._parser_ts = tree_sitter.Parser(TS_LANGUAGE)
                self._parser_tsx = tree_sitter.Parser(TSX_LANGUAGE)
            except Exception as e:
                logger.warning(f"Failed to initialize tree-sitter TS parser: {e}")

    def parse(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        if not TREE_SITTER_AVAILABLE or (self._parser_ts is None and self._parser_tsx is None):
            return self._regex_fallback(filepath, content)

        is_tsx = self.is_tsx or filepath.endswith(".tsx") or filepath.endswith(".jsx")
        parser = self._parser_tsx if is_tsx else self._parser_ts
        if parser is None:
            parser = self._parser_ts or self._parser_tsx

        try:
            content_bytes = content.encode("utf-8", errors="replace")
            tree = parser.parse(content_bytes)
            visitor = TypeScriptASTVisitor(content_bytes, filepath, is_tsx=is_tsx)
            visitor.visit(tree.root_node)
            return visitor.symbols, visitor.relationships
        except Exception as e:
            logger.error(f"Tree-sitter parse error for {filepath}: {e}, falling back to regex.")
            return self._regex_fallback(filepath, content)

    def _regex_fallback(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        """Fallback when tree-sitter is unavailable."""
        symbols: List[ParsedSymbol] = []
        relationships: List[ParsedRelationship] = []

        # Functions
        for match in re.finditer(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(', content):
            symbols.append(ParsedSymbol(
                type=NodeType.FUNCTION,
                name=match.group(1),
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1,
                language="typescript",
                properties={"confidence": 0.6, "is_inferred": True}
            ))

        # Classes
        for match in re.finditer(r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', content):
            cls_name = match.group(1)
            symbols.append(ParsedSymbol(
                type=NodeType.CLASS,
                name=cls_name,
                start_line=content[:match.start()].count('\n') + 1,
                end_line=content[:match.end()].count('\n') + 1,
                language="typescript",
                properties={"confidence": 0.6, "is_inferred": True}
            ))
            if match.group(2):
                relationships.append(ParsedRelationship(
                    source_name=cls_name,
                    target_name=match.group(2),
                    type=RelType.INHERITS,
                    confidence=0.7,
                    is_inferred=True,
                    provenance="Regex:class-extends"
                ))

        # Fetch calls
        for match in re.finditer(r'fetch\([\'"`]([^\'"`]+)[\'"`]\)', content):
            relationships.append(ParsedRelationship(
                source_name=os.path.basename(filepath),
                target_name=match.group(1),
                type=RelType.DEPENDS_ON,
                confidence=0.5,
                is_inferred=True,
                provenance="Regex match for fetch"
            ))

        return symbols, relationships


class TypeScriptASTVisitor:
    """Traverses a tree-sitter TypeScript / TSX syntax tree."""

    def __init__(self, content_bytes: bytes, filepath: str, is_tsx: bool = False):
        self.code = content_bytes
        self.filepath = filepath
        self.is_tsx = is_tsx
        self.language = "tsx" if is_tsx else "typescript"
        self.symbols: List[ParsedSymbol] = []
        self.relationships: List[ParsedRelationship] = []
        self.current_scope: List[str] = [os.path.basename(filepath)]
        self.enclosing_class: Optional[str] = None

    def _text(self, node) -> str:
        if node is None:
            return ""
        return self.code[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _lines(self, node) -> Tuple[int, int]:
        return node.start_point.row + 1, node.end_point.row + 1

    def visit(self, node):
        if node is None:
            return

        ntype = node.type

        # Handle top-level export statements: unwrap inner declaration
        if ntype == "export_statement":
            self._handle_export(node)
            return

        # Declarations
        if ntype == "class_declaration":
            self._visit_class(node)
            return
        elif ntype == "interface_declaration":
            self._visit_interface(node)
            return
        elif ntype == "type_alias_declaration":
            self._visit_type_alias(node)
            return
        elif ntype == "enum_declaration":
            self._visit_enum(node)
            return
        elif ntype in ("function_declaration", "generator_function_declaration", "function_expression", "function"):
            self._visit_function(node)
            return
        elif ntype in ("lexical_declaration", "variable_declaration"):
            self._visit_variable_declaration(node)
            return
        elif ntype == "import_statement":
            self._visit_import(node)
            return
        elif ntype == "method_definition":
            self._visit_method(node)
            return
        elif ntype == "call_expression":
            self._visit_call(node)
            # Continue visiting arguments
        elif ntype in ("jsx_element", "jsx_self_closing_element"):
            self._visit_jsx(node)

        # Recurse down children
        for child in node.children:
            self.visit(child)

    def _handle_export(self, node):
        """Processes an export_statement wrapping another declaration or export list."""
        # Check for re-export with source: export { x } from './module'
        source_node = node.child_by_field_name("source")
        if source_node:
            source_module = self._text(source_node).strip("'\"`")
            for child in node.children:
                if child.type == "export_clause":
                    for spec in child.children:
                        if spec.type == "export_specifier":
                            name_node = spec.child_by_field_name("name")
                            if name_node:
                                exp_name = self._text(name_node)
                                self.relationships.append(ParsedRelationship(
                                    source_name=os.path.basename(self.filepath),
                                    target_name=exp_name,
                                    type=RelType.EXPOSES,
                                    confidence=1.0,
                                    is_inferred=False,
                                    target_module=source_module,
                                    provenance="AST:tree-sitter:re-export"
                                ))
        # Visit inner declaration if present
        decl = node.child_by_field_name("declaration")
        if decl:
            self.visit(decl)
        else:
            for child in node.children:
                if child.type not in ("export", ";", "export_clause", "from", "string"):
                    self.visit(child)

    def _visit_class(self, node):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        class_name = self._text(name_node)
        start_l, end_l = self._lines(node)

        symbol = ParsedSymbol(
            type=NodeType.CLASS,
            name=class_name,
            start_line=start_l,
            end_line=end_l,
            language=self.language,
            properties={"confidence": 1.0, "is_inferred": False}
        )
        self.symbols.append(symbol)

        # Process heritage: extends and implements
        for child in node.children:
            if child.type == "class_heritage":
                for clause in child.children:
                    if clause.type == "extends_clause":
                        for id_node in clause.children:
                            if "identifier" in id_node.type:
                                parent_name = self._text(id_node)
                                self.relationships.append(ParsedRelationship(
                                    source_name=class_name,
                                    target_name=parent_name,
                                    type=RelType.INHERITS,
                                    confidence=1.0,
                                    is_inferred=False,
                                    provenance="AST:tree-sitter:extends"
                                ))
                    elif clause.type == "implements_clause":
                        for id_node in clause.children:
                            if "identifier" in id_node.type:
                                iface_name = self._text(id_node)
                                self.relationships.append(ParsedRelationship(
                                    source_name=class_name,
                                    target_name=iface_name,
                                    type=RelType.IMPLEMENTS,
                                    confidence=1.0,
                                    is_inferred=False,
                                    provenance="AST:tree-sitter:implements"
                                ))
                    elif "identifier" in clause.type:
                        parent_name = self._text(clause)
                        self.relationships.append(ParsedRelationship(
                            source_name=class_name,
                            target_name=parent_name,
                            type=RelType.INHERITS,
                            confidence=1.0,
                            is_inferred=False,
                            provenance="AST:tree-sitter:extends"
                        ))

        # Visit class body methods
        old_class = self.enclosing_class
        old_scope = self.current_scope.copy()
        self.enclosing_class = class_name
        self.current_scope.append(class_name)

        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                self.visit(child)

        self.enclosing_class = old_class
        self.current_scope = old_scope

    def _visit_interface(self, node):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        iface_name = self._text(name_node)
        start_l, end_l = self._lines(node)

        self.symbols.append(ParsedSymbol(
            type=NodeType.INTERFACE,
            name=iface_name,
            start_line=start_l,
            end_line=end_l,
            language=self.language,
            properties={"confidence": 1.0, "is_inferred": False}
        ) if hasattr(NodeType, "INTERFACE") else ParsedSymbol(
            type=NodeType.CLASS,
            name=iface_name,
            start_line=start_l,
            end_line=end_l,
            language=self.language,
            properties={"kind": "interface", "confidence": 1.0, "is_inferred": False}
        ))

        # Extends clause on interface
        for child in node.children:
            if child.type in ("extends_clause", "extends_type_clause", "interface_heritage"):
                for id_node in child.children:
                    if "identifier" in id_node.type:
                        super_iface = self._text(id_node)
                        self.relationships.append(ParsedRelationship(
                            source_name=iface_name,
                            target_name=super_iface,
                            type=RelType.INHERITS,
                            confidence=1.0,
                            is_inferred=False,
                            provenance="AST:tree-sitter:interface-extends"
                        ))

    def _visit_type_alias(self, node):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        type_name = self._text(name_node)
        start_l, end_l = self._lines(node)
        self.symbols.append(ParsedSymbol(
            type=NodeType.CONCEPT,
            name=type_name,
            start_line=start_l,
            end_line=end_l,
            language=self.language,
            properties={"kind": "type_alias", "confidence": 1.0, "is_inferred": False}
        ))

    def _visit_enum(self, node):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        enum_name = self._text(name_node)
        start_l, end_l = self._lines(node)
        self.symbols.append(ParsedSymbol(
            type=NodeType.ENUM if hasattr(NodeType, "ENUM") else NodeType.CLASS,
            name=enum_name,
            start_line=start_l,
            end_line=end_l,
            language=self.language,
            properties={"kind": "enum", "confidence": 1.0, "is_inferred": False}
        ))

    def _visit_function(self, node):
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous function / default export
            fn_name = "default"
        else:
            fn_name = self._text(name_node)

        start_l, end_l = self._lines(node)
        is_async = any(c.type == "async" for c in node.children)
        is_component = fn_name[0].isupper() if fn_name and fn_name[0].isalpha() else False

        self.symbols.append(ParsedSymbol(
            type=NodeType.FUNCTION,
            name=fn_name,
            start_line=start_l,
            end_line=end_l,
            language=self.language,
            properties={
                "is_async": is_async,
                "is_component": is_component,
                "confidence": 1.0,
                "is_inferred": False
            }
        ))

        old_scope = self.current_scope.copy()
        self.current_scope.append(fn_name)

        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                self.visit(child)

        self.current_scope = old_scope

    def _visit_method(self, node):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        method_name = self._text(name_node)
        start_l, end_l = self._lines(node)
        is_async = any(c.type == "async" for c in node.children)

        self.symbols.append(ParsedSymbol(
            type=NodeType.METHOD,
            name=method_name,
            start_line=start_l,
            end_line=end_l,
            parent_name=self.enclosing_class,
            language=self.language,
            properties={
                "is_async": is_async,
                "class": self.enclosing_class,
                "confidence": 1.0,
                "is_inferred": False
            }
        ))

        old_scope = self.current_scope.copy()
        self.current_scope.append(method_name)

        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                self.visit(child)

        self.current_scope = old_scope

    def _visit_variable_declaration(self, node):
        """Inspects const / let declarations for arrow functions, components, or constants."""
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")

                if not name_node:
                    continue

                var_name = self._text(name_node)
                start_l, end_l = self._lines(child)

                # Check if value is arrow function or function expression
                if value_node and value_node.type in ("arrow_function", "function_expression"):
                    is_async = any(c.type == "async" for c in value_node.children)
                    is_comp = var_name[0].isupper() if var_name and var_name[0].isalpha() else False

                    self.symbols.append(ParsedSymbol(
                        type=NodeType.FUNCTION,
                        name=var_name,
                        start_line=start_l,
                        end_line=end_l,
                        language=self.language,
                        properties={
                            "is_arrow": True,
                            "is_async": is_async,
                            "is_component": is_comp,
                            "confidence": 1.0,
                            "is_inferred": False
                        }
                    ))

                    old_scope = self.current_scope.copy()
                    self.current_scope.append(var_name)
                    # Visit body of arrow function
                    body = value_node.child_by_field_name("body")
                    if body:
                        self.visit(body)
                    self.current_scope = old_scope

                elif var_name.isupper() and "_" in var_name:
                    self.symbols.append(ParsedSymbol(
                        type=NodeType.CONFIG_CONSTANT,
                        name=var_name,
                        start_line=start_l,
                        end_line=end_l,
                        language=self.language,
                        properties={"confidence": 0.9, "is_inferred": False}
                    ))
                    if value_node:
                        self.visit(value_node)
                else:
                    self.symbols.append(ParsedSymbol(
                        type=NodeType.VARIABLE,
                        name=var_name,
                        start_line=start_l,
                        end_line=end_l,
                        language=self.language,
                        properties={"confidence": 0.8, "is_inferred": False}
                    ))
                    if value_node:
                        self.visit(value_node)

    def _visit_import(self, node):
        """Extracts imported symbols and module path."""
        source_node = node.child_by_field_name("source")
        if not source_node:
            return
        module_path = self._text(source_node).strip("'\"`")
        current_caller = self.current_scope[-1] if self.current_scope else os.path.basename(self.filepath)

        # Look for import clause
        for child in node.children:
            if child.type == "import_clause":
                for sub in child.children:
                    # Default import: import React from 'react'
                    if sub.type == "identifier":
                        def_name = self._text(sub)
                        self.relationships.append(ParsedRelationship(
                            source_name=current_caller,
                            target_name=def_name,
                            type=RelType.IMPORTS,
                            confidence=1.0,
                            is_inferred=False,
                            target_module=module_path,
                            provenance="AST:tree-sitter:import-default"
                        ))
                    # Named imports: import { a, b as c } from '...'
                    elif sub.type == "named_imports":
                        for spec in sub.children:
                            if spec.type == "import_specifier":
                                n_node = spec.child_by_field_name("name")
                                if n_node:
                                    sym_name = self._text(n_node)
                                    self.relationships.append(ParsedRelationship(
                                        source_name=current_caller,
                                        target_name=sym_name,
                                        type=RelType.IMPORTS,
                                        confidence=1.0,
                                        is_inferred=False,
                                        target_module=module_path,
                                        provenance="AST:tree-sitter:import-named"
                                    ))
                    # Namespace import: import * as Foo from '...'
                    elif sub.type == "namespace_import":
                        for id_node in sub.children:
                            if id_node.type == "identifier":
                                ns_name = self._text(id_node)
                                self.relationships.append(ParsedRelationship(
                                    source_name=current_caller,
                                    target_name=ns_name,
                                    type=RelType.IMPORTS,
                                    confidence=1.0,
                                    is_inferred=False,
                                    target_module=module_path,
                                    provenance="AST:tree-sitter:import-namespace"
                                ))

        # If bare import: import './style.css'
        if not any(c.type == "import_clause" for c in node.children):
            self.relationships.append(ParsedRelationship(
                source_name=current_caller,
                target_name=module_path,
                type=RelType.DEPENDS_ON,
                confidence=1.0,
                is_inferred=False,
                target_module=module_path,
                provenance="AST:tree-sitter:import-side-effect"
            ))

    def _visit_call(self, node):
        """Extracts function/method calls and REST endpoint invocations."""
        fn_node = node.child_by_field_name("function")
        if not fn_node:
            return

        caller = self.current_scope[-1] if self.current_scope else os.path.basename(self.filepath)
        fn_text = self._text(fn_node).strip()

        # Handle REST fetch calls
        if fn_text == "fetch" or fn_text.endswith(".get") or fn_text.endswith(".post"):
            args_node = node.child_by_field_name("arguments")
            if args_node:
                arg_text = self._text(args_node)
                m = re.search(r"['\"`]([^'\"`]+)['\"`]", arg_text)
                if m:
                    first_arg = m.group(1)
                    self.relationships.append(ParsedRelationship(
                        source_name=caller,
                        target_name=first_arg,
                        type=RelType.DEPENDS_ON,
                        confidence=0.9,
                        is_inferred=True,
                        provenance="AST:tree-sitter:api-call"
                    ))

        # Standard call or method call
        target_name = fn_text
        if "." in fn_text:
            # Member expression: obj.method() -> target is method
            target_name = fn_text.split(".")[-1]
            conf = 0.8
            inferred = True
        else:
            conf = 1.0
            inferred = False

        if target_name and target_name not in ("fetch", "require", "console"):
            self.relationships.append(ParsedRelationship(
                source_name=caller,
                target_name=target_name,
                type=RelType.CALLS,
                confidence=conf,
                is_inferred=inferred,
                provenance="AST:tree-sitter:call"
            ))

    def _visit_jsx(self, node):
        """Extracts React component usage in JSX as CALLS relationships."""
        caller = self.current_scope[-1] if self.current_scope else os.path.basename(self.filepath)
        tag_name = None

        if node.type == "jsx_element":
            open_elem = node.child_by_field_name("open_tag") or (node.children[0] if node.children else None)
            if open_elem:
                name_child = open_elem.child_by_field_name("name")
                if name_child:
                    tag_name = self._text(name_child)
        elif node.type == "jsx_self_closing_element":
            name_child = node.child_by_field_name("name")
            if name_child:
                tag_name = self._text(name_child)

        if tag_name and tag_name[0].isupper():
            self.relationships.append(ParsedRelationship(
                source_name=caller,
                target_name=tag_name,
                type=RelType.CALLS,
                confidence=1.0,
                is_inferred=False,
                provenance="AST:tree-sitter:jsx-component"
            ))
