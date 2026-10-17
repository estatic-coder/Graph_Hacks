import ast
from typing import List, Tuple, Optional
from app.ingestion.parsers.base import BaseParser
from app.ingestion.models import ParsedSymbol, ParsedRelationship
from app.graph.schema import NodeType, RelType

class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, content: str):
        self.content = content
        self.symbols: List[ParsedSymbol] = []
        self.relationships: List[ParsedRelationship] = []
        self.scope_stack: List[str] = []
        self.class_stack: List[str] = []

    @property
    def current_scope(self) -> str:
        return self.scope_stack[-1] if self.scope_stack else "FILE"

    def visit_ClassDef(self, node: ast.ClassDef):
        sym = ParsedSymbol(
            type=NodeType.CLASS,
            name=node.name,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            parent_name=self.class_stack[-1] if self.class_stack else None
        )
        self.symbols.append(sym)

        # Base classes (inheritance)
        for base in node.bases:
            base_name = None
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr
            if base_name:
                self.relationships.append(ParsedRelationship(
                    source_name=node.name,
                    target_name=base_name,
                    type=RelType.INHERITS,
                    confidence=1.0,
                    is_inferred=False,
                    provenance=f"Line {node.lineno}"
                ))

        self.class_stack.append(node.name)
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node)

    def _handle_function(self, node):
        is_method = bool(self.class_stack)
        is_test = node.name.startswith("test_")
        
        # Check endpoint decorators (e.g. @app.get, @router.post, etc.)
        is_endpoint = False
        for dec in node.decorator_list:
            dec_id = ""
            if isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Attribute):
                    dec_id = dec.func.attr
                elif isinstance(dec.func, ast.Name):
                    dec_id = dec.func.id
            elif isinstance(dec, ast.Attribute):
                dec_id = dec.attr
            elif isinstance(dec, ast.Name):
                dec_id = dec.id
            if dec_id.lower() in ("get", "post", "put", "delete", "patch", "api_route"):
                is_endpoint = True

        if is_test:
            sym_type = NodeType.TEST
        elif is_endpoint:
            sym_type = NodeType.ENDPOINT
        elif is_method:
            sym_type = NodeType.METHOD
        else:
            sym_type = NodeType.FUNCTION

        sym = ParsedSymbol(
            type=sym_type,
            name=node.name,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            parent_name=self.class_stack[-1] if self.class_stack else None
        )
        self.symbols.append(sym)

        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Assign(self, node: ast.Assign):
        # Top-level constants and variables
        if not self.scope_stack and not self.class_stack:
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    var_name = tgt.id
                    if any(q in var_name.upper() for q in ("OUTBOX", "QUEUE", "PENDING")):
                        sym_type = NodeType.QUEUE
                    elif var_name.isupper():
                        sym_type = NodeType.CONFIG_CONSTANT
                    else:
                        sym_type = NodeType.VARIABLE

                    self.symbols.append(ParsedSymbol(
                        type=sym_type,
                        name=var_name,
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno
                    ))

        # Check for state transitions inside functions, e.g. job.status = "review"
        if self.scope_stack:
            for tgt in node.targets:
                if isinstance(tgt, ast.Attribute) and tgt.attr == "status":
                    val_str = ""
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        val_str = node.value.value
                    if val_str:
                        self.relationships.append(ParsedRelationship(
                            source_name=self.current_scope,
                            target_name=val_str,
                            type=RelType.STATE_TRANSITION,
                            confidence=1.0,
                            is_inferred=False,
                            provenance=f"Line {node.lineno}",
                            properties={"target_state": val_str, "attribute": "status"}
                        ))

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if not self.scope_stack and not self.class_stack and isinstance(node.target, ast.Name):
            var_name = node.target.id
            if any(q in var_name.upper() for q in ("OUTBOX", "QUEUE", "PENDING")):
                sym_type = NodeType.QUEUE
            elif var_name.isupper():
                sym_type = NodeType.CONFIG_CONSTANT
            else:
                sym_type = NodeType.VARIABLE

            self.symbols.append(ParsedSymbol(
                type=sym_type,
                name=var_name,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno
            ))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.relationships.append(ParsedRelationship(
                source_name=self.current_scope,
                target_name=alias.name,
                type=RelType.IMPORTS,
                confidence=1.0,
                is_inferred=False,
                provenance=f"Line {node.lineno}",
                target_module=alias.name,
                level=0
            ))

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        for alias in node.names:
            self.relationships.append(ParsedRelationship(
                source_name=self.current_scope,
                target_name=alias.name,
                type=RelType.IMPORTS,
                confidence=1.0,
                is_inferred=False,
                provenance=f"Line {node.lineno}",
                target_module=mod,
                level=node.level or 0
            ))

    def visit_Call(self, node: ast.Call):
        target_name = None
        attr_name = None
        obj_name = None

        if isinstance(node.func, ast.Name):
            target_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            target_name = node.func.attr
            attr_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id

        if target_name:
            # Default direct static call
            self.relationships.append(ParsedRelationship(
                source_name=self.current_scope,
                target_name=target_name,
                type=RelType.CALLS,
                confidence=1.0,
                is_inferred=False,
                provenance=f"Line {node.lineno}"
            ))

            # Typed queue and state operations
            if obj_name and any(q in obj_name.upper() for q in ("OUTBOX", "QUEUE", "PENDING")):
                if attr_name == "append":
                    self.relationships.append(ParsedRelationship(
                        source_name=self.current_scope,
                        target_name=obj_name,
                        type=RelType.ENQUEUES,
                        confidence=1.0,
                        is_inferred=False,
                        provenance=f"Line {node.lineno}",
                        properties={"operation": "append", "queue": obj_name}
                    ))
                elif attr_name in ("pop", "get"):
                    self.relationships.append(ParsedRelationship(
                        source_name=self.current_scope,
                        target_name=obj_name,
                        type=RelType.DEQUEUES,
                        confidence=1.0,
                        is_inferred=False,
                        provenance=f"Line {node.lineno}",
                        properties={"operation": attr_name, "queue": obj_name}
                    ))
            elif target_name.lower() in ("enqueue", "enqueue_job"):
                self.relationships.append(ParsedRelationship(
                    source_name=self.current_scope,
                    target_name="OUTBOX",
                    type=RelType.ENQUEUES,
                    confidence=1.0,
                    is_inferred=False,
                    provenance=f"Line {node.lineno}",
                    properties={"operation": target_name, "queue": "OUTBOX"}
                ))
            elif target_name.lower() in ("save", "save_job", "emit"):
                self.relationships.append(ParsedRelationship(
                    source_name=self.current_scope,
                    target_name="JOBS" if "save" in target_name.lower() else "EVENTS",
                    type=RelType.WRITES_STATE,
                    confidence=1.0,
                    is_inferred=False,
                    provenance=f"Line {node.lineno}",
                    properties={"operation": target_name}
                ))
            elif target_name.lower() in ("load", "load_job", "get_job"):
                self.relationships.append(ParsedRelationship(
                    source_name=self.current_scope,
                    target_name="JOBS",
                    type=RelType.READS_STATE,
                    confidence=1.0,
                    is_inferred=False,
                    provenance=f"Line {node.lineno}",
                    properties={"operation": target_name}
                ))

        self.generic_visit(node)

class PythonParser(BaseParser):
    def parse(self, filepath: str, content: str) -> Tuple[List[ParsedSymbol], List[ParsedRelationship]]:
        try:
            tree = ast.parse(content)
        except Exception:
            return [], []
            
        visitor = PythonASTVisitor(content)
        visitor.visit(tree)
        return visitor.symbols, visitor.relationships
