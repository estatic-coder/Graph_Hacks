import os
import uuid
import logging
from typing import Dict
from app.graph.client import falkor_client
from app.graph.schema import NodeBase, EdgeBase, NodeType, RelType
from app.ingestion.parsers.python import PythonParser
from app.ingestion.parsers.typescript import TypeScriptParser
from app.ingestion.parsers.javascript import JavaScriptParser
from app.ingestion.parsers.fallback import RegexFallbackParser
from app.ingestion.parsers.generic import GenericCodeParser, ConfigParser, MarkdownParser
import time

logger = logging.getLogger(__name__)

class IngestionPipeline:
    def __init__(self, repo_path: str, repo_id: str):
        self.repo_path = repo_path
        self.repo_id = repo_id
        self.graph_name = f"workspace_{repo_id}"
        self.parsers = {
            ".py": PythonParser(),
            ".ts": TypeScriptParser(is_tsx=False),
            ".tsx": TypeScriptParser(is_tsx=True),
            ".js": JavaScriptParser(is_jsx=False),
            ".jsx": JavaScriptParser(is_jsx=True),
            ".java": GenericCodeParser(),
            ".c": GenericCodeParser(),
            ".cpp": GenericCodeParser(),
            ".sql": GenericCodeParser(),
            ".json": ConfigParser(),
            ".yaml": ConfigParser(),
            ".yml": ConfigParser(),
            ".md": MarkdownParser(),
        }

    def index(self, incremental: bool = False):
        falkor_client.connect()
        
        # Create repo node
        repo_node = NodeBase(id=f"repo_{self.repo_id}", repository_id=self.repo_id, name=os.path.basename(self.repo_path), properties={"path": self.repo_path})
        
        if not incremental:
            try:
                falkor_client.safe_query(self.graph_name, "MATCH (n) WHERE n.repository_id = $repo_id DETACH DELETE n", {"repo_id": self.repo_id})
            except Exception:
                pass
                
        falkor_client.upsert_node(self.graph_name, NodeType.REPOSITORY, repo_node)
        
        start_time = time.time()
        stats = {"files_scanned": 0, "symbols_extracted": 0, "relationships_created": 0, "files_skipped": 0, "parsing_errors": 0}

        # Pass 1: Scan files, parse symbols, and register nodes
        parsed_files = []
        symbol_table = {}  # name -> list of dict(id, path, type, parent)
        file_symbols = {}  # rel_path -> dict(name, id)
        module_to_file = {}  # module_name -> file_id

        for root, dirs, files in os.walk(self.repo_path):
            if '.git' in dirs: dirs.remove('.git')
            if 'node_modules' in dirs: dirs.remove('node_modules')
            if '.venv' in dirs: dirs.remove('.venv')
            
            for file in files:
                if any(sec in file for sec in ['.env', '.pem', '.key', 'secret', '.db', '.pyc']):
                    stats["files_skipped"] += 1
                    continue
                    
                ext = os.path.splitext(file)[1]
                parser = self.parsers.get(ext)
                if not parser:
                    stats["files_skipped"] += 1
                    continue
                
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.repo_path)
                file_id = f"file_{self.repo_id}_{rel_path}"
                
                # Register module lookup keys (code files have precedence over data/config files)
                mod_name = os.path.splitext(rel_path)[0].replace("/", ".").replace("\\", ".")
                is_code_file = ext in (".py", ".ts", ".tsx", ".js", ".jsx")
                if is_code_file or mod_name not in module_to_file:
                    module_to_file[mod_name] = file_id
                    module_to_file[mod_name.split(".")[-1]] = file_id
                    module_to_file[os.path.basename(mod_name)] = file_id
                module_to_file[rel_path] = file_id
                module_to_file[file] = file_id
                
                # Determine primary language from extension
                lang = ext.lstrip(".").lower()
                lang_map = {"py": "python", "ts": "typescript", "tsx": "tsx", "js": "javascript", "jsx": "jsx"}
                primary_lang = lang_map.get(lang, lang)

                # Upsert File Node
                file_node = NodeBase(
                    id=file_id, 
                    repository_id=self.repo_id,
                    name=file,
                    source_path=rel_path,
                    properties={"language": primary_lang}
                )
                falkor_client.upsert_node(self.graph_name, NodeType.FILE, file_node)
                stats["files_scanned"] += 1
                
                # Link File to Repo
                falkor_client.upsert_edge(self.graph_name, EdgeBase(
                    source_id=f"repo_{self.repo_id}", target_id=file_id, type=RelType.CONTAINS
                ))

                file_symbols[rel_path] = {}
                symbols, relationships = [], []
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    symbols, relationships = parser.parse(file_path, content)
                except Exception as e:
                    logger.error(f"Error parsing {file_path}: {e}")
                    stats["parsing_errors"] += 1

                for sym in symbols:
                    sym_id = f"sym_{self.repo_id}_{rel_path}_{sym.name}"
                    sym_props = {"language": getattr(sym, "language", None) or primary_lang}
                    if getattr(sym, "docstring", None):
                        sym_props["docstring"] = sym.docstring
                    if sym.properties:
                        sym_props.update(sym.properties)

                    sym_node = NodeBase(
                        id=sym_id, repository_id=self.repo_id, name=sym.name, 
                        source_path=rel_path, start_line=sym.start_line, end_line=sym.end_line,
                        properties=sym_props
                    )
                    falkor_client.upsert_node(self.graph_name, sym.type, sym_node)
                    stats["symbols_extracted"] += 1
                    
                    # File defines symbol
                    falkor_client.upsert_edge(self.graph_name, EdgeBase(
                        source_id=file_id, target_id=sym_id, type=RelType.DEFINES
                    ))

                    # If method has class parent, link Class -[:DEFINES]-> Method
                    if getattr(sym, "parent_name", None):
                        parent_id = f"sym_{self.repo_id}_{rel_path}_{sym.parent_name}"
                        falkor_client.upsert_edge(self.graph_name, EdgeBase(
                            source_id=parent_id, target_id=sym_id, type=RelType.DEFINES
                        ))

                    file_symbols[rel_path][sym.name] = sym_id
                    if sym.name not in symbol_table:
                        symbol_table[sym.name] = []
                    symbol_table[sym.name].append({
                        "id": sym_id,
                        "path": rel_path,
                        "type": sym.type,
                        "parent": getattr(sym, "parent_name", None)
                    })

                parsed_files.append((file_path, rel_path, file_id, symbols, relationships))

        # Pass 2: Resolve cross-file references and link caller -> callee
        for file_path, rel_path, file_id, symbols, relationships in parsed_files:
            file_import_map = {}  # imported symbol/module/alias -> module_name
            for rel in relationships:
                if rel.type == RelType.IMPORTS:
                    tgt_mod = getattr(rel, "target_module", None) or rel.target_name
                    rel_level = getattr(rel, "level", 0) or 0
                    if rel_level > 0:
                        cur_dir = os.path.dirname(rel_path).replace("/", ".").replace("\\", ".")
                        candidate_mod = f"{cur_dir}.{tgt_mod}" if tgt_mod else cur_dir
                        if candidate_mod in module_to_file:
                            tgt_mod = candidate_mod

                    full_mod = f"{tgt_mod}.{rel.target_name}" if (tgt_mod and tgt_mod != rel.target_name) else (tgt_mod or rel.target_name)
                    resolved_mod = full_mod if full_mod in module_to_file else (tgt_mod if tgt_mod in module_to_file else full_mod)

                    file_import_map[rel.target_name] = resolved_mod
                    asname = rel.properties.get("asname") if hasattr(rel, "properties") and rel.properties else None
                    if asname:
                        file_import_map[asname] = resolved_mod

            for rel in relationships:
                # 1. Resolve source
                if rel.source_name == "FILE":
                    src_id = file_id
                    src_is_test = False
                elif rel.source_name in file_symbols.get(rel_path, {}):
                    src_id = file_symbols[rel_path][rel.source_name]
                    src_is_test = rel.source_name.startswith("test_")
                else:
                    src_id = f"sym_{self.repo_id}_{rel_path}_{rel.source_name}"
                    src_is_test = rel.source_name.startswith("test_")

                # 2. Resolve target
                target_id = None
                tgt_name = rel.target_name

                if rel.type == RelType.IMPORTS:
                    tgt_mod = getattr(rel, "target_module", None) or tgt_name
                    rel_level = getattr(rel, "level", 0) or 0
                    if rel_level > 0:
                        cur_dir = os.path.dirname(rel_path).replace("/", ".").replace("\\", ".")
                        candidate_mod = f"{cur_dir}.{tgt_mod}" if tgt_mod else cur_dir
                        if candidate_mod in module_to_file:
                            tgt_mod = candidate_mod

                    full_mod = f"{tgt_mod}.{tgt_name}" if (tgt_mod and tgt_mod != tgt_name) else (tgt_mod or tgt_name)
                    if full_mod in module_to_file:
                        target_id = module_to_file[full_mod]
                    elif tgt_mod in module_to_file:
                        target_mod_file_id = module_to_file[tgt_mod]
                        # If importing a specific symbol that exists in that target file
                        if tgt_name in symbol_table:
                            for sym_meta in symbol_table[tgt_name]:
                                if f"file_{self.repo_id}_{sym_meta['path']}" == target_mod_file_id:
                                    target_id = sym_meta["id"]
                                    break
                        if not target_id:
                            target_id = target_mod_file_id
                    elif tgt_name in module_to_file:
                        target_id = module_to_file[tgt_name]
                    elif tgt_name in symbol_table:
                        target_id = symbol_table[tgt_name][0]["id"]
                    else:
                        # External module (e.g. fastapi, sqlite3, os)
                        target_id = f"ext_{self.repo_id}_{tgt_name}"
                        falkor_client.upsert_node(self.graph_name, NodeType.MODULE, NodeBase(
                            id=target_id, repository_id=self.repo_id, name=tgt_name
                        ))

                elif rel.type in (RelType.CALLS, RelType.ENQUEUES, RelType.DEQUEUES, RelType.WRITES_STATE, RelType.READS_STATE):
                    # Check if defined in same file
                    if tgt_name in file_symbols.get(rel_path, {}):
                        target_id = file_symbols[rel_path][tgt_name]
                    else:
                        # Check if called through a receiver (e.g. obj.method())
                        receiver = rel.properties.get("receiver") if hasattr(rel, "properties") and rel.properties else None
                        imported_from = None
                        if receiver and receiver in file_import_map:
                            imported_from = file_import_map[receiver]
                        elif tgt_name in file_import_map:
                            imported_from = file_import_map[tgt_name]

                        if imported_from:
                            target_file_id = module_to_file.get(imported_from)
                            if not target_file_id and f"{imported_from}.{tgt_name}" in module_to_file:
                                target_file_id = module_to_file[f"{imported_from}.{tgt_name}"]

                            if target_file_id and tgt_name in symbol_table:
                                for sym_meta in symbol_table[tgt_name]:
                                    if f"file_{self.repo_id}_{sym_meta['path']}" == target_file_id:
                                        target_id = sym_meta["id"]
                                        break
                            if not target_id and target_file_id:
                                target_id = target_file_id

                    # Check if uniquely defined across repository or matches same service
                    if not target_id and tgt_name in symbol_table:
                        candidates = symbol_table[tgt_name]
                        if len(candidates) == 1:
                            target_id = candidates[0]["id"]
                        else:
                            cur_svc = rel_path.split("/")[1] if rel_path.startswith("services/") else None
                            matching_svc = [c for c in candidates if cur_svc and c["path"].startswith(f"services/{cur_svc}/")]
                            if matching_svc:
                                target_id = matching_svc[0]["id"]
                            else:
                                target_id = candidates[0]["id"]
                    # If state / queue target
                    if not target_id and rel.type in (RelType.ENQUEUES, RelType.DEQUEUES, RelType.WRITES_STATE, RelType.READS_STATE):
                        target_id = f"sym_{self.repo_id}_{tgt_name}"
                        ntype = NodeType.QUEUE if any(q in tgt_name.upper() for q in ("OUTBOX", "QUEUE", "PENDING")) else NodeType.STATE
                        falkor_client.upsert_node(self.graph_name, ntype, NodeBase(
                            id=target_id, repository_id=self.repo_id, name=tgt_name
                        ))
                    # If still unresolved, treat as external concept/function
                    if not target_id:
                        target_id = f"ext_{self.repo_id}_{tgt_name}"
                        falkor_client.upsert_node(self.graph_name, NodeType.CONCEPT, NodeBase(
                            id=target_id, repository_id=self.repo_id, name=tgt_name
                        ))

                elif rel.type == RelType.STATE_TRANSITION:
                    target_id = f"state_{self.repo_id}_{tgt_name}"
                    falkor_client.upsert_node(self.graph_name, NodeType.STATE, NodeBase(
                        id=target_id, repository_id=self.repo_id, name=tgt_name
                    ))

                else:
                    # Generic / inherits
                    if tgt_name in file_symbols.get(rel_path, {}):
                        target_id = file_symbols[rel_path][tgt_name]
                    elif tgt_name in symbol_table:
                        target_id = symbol_table[tgt_name][0]["id"]
                    else:
                        target_id = f"ext_{self.repo_id}_{tgt_name}"
                        falkor_client.upsert_node(self.graph_name, NodeType.CONCEPT, NodeBase(
                            id=target_id, repository_id=self.repo_id, name=tgt_name
                        ))

                # Upsert primary edge
                falkor_client.upsert_edge(self.graph_name, EdgeBase(
                    source_id=src_id, target_id=target_id, type=rel.type,
                    confidence=rel.confidence, is_inferred=rel.is_inferred, provenance=rel.provenance
                ))
                stats["relationships_created"] += 1

                # If this was a call from a test, create a direct TESTS relationship
                if src_is_test and rel.type == RelType.CALLS and not target_id.startswith("ext_"):
                    falkor_client.upsert_edge(self.graph_name, EdgeBase(
                        source_id=src_id, target_id=target_id, type=RelType.TESTS,
                        confidence=1.0, is_inferred=False, provenance="Derived from test invocation"
                    ))
                    stats["relationships_created"] += 1

        stats["duration_seconds"] = round(time.time() - start_time, 2)
        logger.info(f"Indexing complete: {stats}")
        return stats

    def index_files(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        Indexes a targeted subset of files incrementally, integrating into the existing graph.
        """
        falkor_client.connect()
        start_time = time.time()
        stats = {"files_scanned": 0, "symbols_extracted": 0, "relationships_created": 0, "parsing_errors": 0}

        symbol_table: Dict[str, List[Dict[str, Any]]] = {}
        module_to_file: Dict[str, str] = {}
        file_symbols: Dict[str, Dict[str, str]] = {}

        try:
            cypher = """
            MATCH (f:File)-[:DEFINES]->(s)
            WHERE f.repository_id = $repo_id
            RETURN f.source_path, f.id, s.name, s.id, labels(s)[0]
            """
            res = falkor_client.safe_query(self.graph_name, cypher, {"repo_id": self.repo_id})
            rows = getattr(res, "result_set", res) or []
            for r in rows:
                if len(r) >= 5:
                    f_path, f_id, s_name, s_id, s_type = str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4])
                    if f_path not in file_symbols:
                        file_symbols[f_path] = {}
                    file_symbols[f_path][s_name] = s_id
                    if s_name not in symbol_table:
                        symbol_table[s_name] = []
                    symbol_table[s_name].append({"id": s_id, "path": f_path, "type": s_type})
                    mod_name = os.path.splitext(f_path)[0].replace("/", ".").replace("\\", ".")
                    module_to_file[mod_name] = f_id
                    module_to_file[os.path.basename(f_path)] = f_id
        except Exception as e:
            logger.debug(f"Could not preload symbol table: {e}")

        parsed_files = []

        # Pass 1: Parse and upsert symbols for the given files
        for rel_path in file_paths:
            rel_path = os.path.normpath(rel_path).lstrip("/").lstrip("\\")
            full_path = os.path.join(self.repo_path, rel_path)
            if not os.path.isfile(full_path):
                continue

            file = os.path.basename(rel_path)
            ext = os.path.splitext(file)[1]
            parser = self.parsers.get(ext)
            if not parser:
                continue

            file_id = f"file_{self.repo_id}_{rel_path}"
            mod_name = os.path.splitext(rel_path)[0].replace("/", ".").replace("\\", ".")
            is_code_file = ext in (".py", ".ts", ".tsx", ".js", ".jsx")
            if is_code_file or mod_name not in module_to_file:
                module_to_file[mod_name] = file_id
                module_to_file[os.path.basename(mod_name)] = file_id
            module_to_file[rel_path] = file_id
            module_to_file[file] = file_id

            lang = ext.lstrip(".").lower()
            lang_map = {"py": "python", "ts": "typescript", "tsx": "tsx", "js": "javascript", "jsx": "jsx"}
            primary_lang = lang_map.get(lang, lang)

            file_node = NodeBase(
                id=file_id, repository_id=self.repo_id, name=file,
                source_path=rel_path, properties={"language": primary_lang}
            )
            falkor_client.upsert_node(self.graph_name, NodeType.FILE, file_node)
            stats["files_scanned"] += 1

            falkor_client.upsert_edge(self.graph_name, EdgeBase(
                source_id=f"repo_{self.repo_id}", target_id=file_id, type=RelType.CONTAINS
            ))

            if rel_path not in file_symbols:
                file_symbols[rel_path] = {}

            symbols, relationships = [], []
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                symbols, relationships = parser.parse(full_path, content)
            except Exception as e:
                logger.error(f"Error parsing {full_path}: {e}")
                stats["parsing_errors"] += 1

            for sym in symbols:
                sym_id = f"sym_{self.repo_id}_{rel_path}_{sym.name}"
                sym_props = {"language": getattr(sym, "language", None) or primary_lang}
                if getattr(sym, "docstring", None):
                    sym_props["docstring"] = sym.docstring
                if sym.properties:
                    sym_props.update(sym.properties)

                sym_node = NodeBase(
                    id=sym_id, repository_id=self.repo_id, name=sym.name,
                    source_path=rel_path, start_line=sym.start_line, end_line=sym.end_line,
                    properties=sym_props
                )
                falkor_client.upsert_node(self.graph_name, sym.type, sym_node)
                stats["symbols_extracted"] += 1

                falkor_client.upsert_edge(self.graph_name, EdgeBase(
                    source_id=file_id, target_id=sym_id, type=RelType.DEFINES
                ))

                if getattr(sym, "parent_name", None):
                    parent_id = f"sym_{self.repo_id}_{rel_path}_{sym.parent_name}"
                    falkor_client.upsert_edge(self.graph_name, EdgeBase(
                        source_id=parent_id, target_id=sym_id, type=RelType.DEFINES
                    ))

                file_symbols[rel_path][sym.name] = sym_id
                if sym.name not in symbol_table:
                    symbol_table[sym.name] = []
                symbol_table[sym.name].append({
                    "id": sym_id, "path": rel_path, "type": sym.type,
                    "parent": getattr(sym, "parent_name", None)
                })

            parsed_files.append((full_path, rel_path, file_id, symbols, relationships))

        # Pass 2: Resolve references for the parsed files
        for full_path, rel_path, file_id, symbols, relationships in parsed_files:
            file_import_map = {}
            for rel in relationships:
                if rel.type == RelType.IMPORTS:
                    tgt_mod = getattr(rel, "target_module", None) or rel.target_name
                    file_import_map[rel.target_name] = tgt_mod

            for rel in relationships:
                if rel.source_name == "FILE":
                    src_id = file_id
                    src_is_test = False
                elif rel.source_name in file_symbols.get(rel_path, {}):
                    src_id = file_symbols[rel_path][rel.source_name]
                    src_is_test = rel.source_name.startswith("test_")
                else:
                    src_id = f"sym_{self.repo_id}_{rel_path}_{rel.source_name}"
                    src_is_test = rel.source_name.startswith("test_")

                target_id = None
                tgt_name = rel.target_name

                if rel.type == RelType.IMPORTS:
                    tgt_mod = getattr(rel, "target_module", None) or tgt_name
                    if tgt_mod in module_to_file:
                        target_mod_file_id = module_to_file[tgt_mod]
                        if tgt_name in symbol_table:
                            for sym_meta in symbol_table[tgt_name]:
                                if f"file_{self.repo_id}_{sym_meta['path']}" == target_mod_file_id:
                                    target_id = sym_meta["id"]
                                    break
                        if not target_id:
                            target_id = target_mod_file_id
                    elif tgt_name in module_to_file:
                        target_id = module_to_file[tgt_name]
                    elif tgt_name in symbol_table:
                        target_id = symbol_table[tgt_name][0]["id"]
                    else:
                        target_id = f"ext_{self.repo_id}_{tgt_name}"
                        falkor_client.upsert_node(self.graph_name, NodeType.MODULE, NodeBase(
                            id=target_id, repository_id=self.repo_id, name=tgt_name
                        ))
                elif rel.type in (RelType.CALLS, RelType.ENQUEUES, RelType.DEQUEUES, RelType.WRITES_STATE, RelType.READS_STATE):
                    if tgt_name in file_symbols.get(rel_path, {}):
                        target_id = file_symbols[rel_path][tgt_name]
                    elif tgt_name in file_import_map:
                        imported_from = file_import_map[tgt_name]
                        if imported_from in module_to_file:
                            target_file_id = module_to_file[imported_from]
                            if tgt_name in symbol_table:
                                for sym_meta in symbol_table[tgt_name]:
                                    if f"file_{self.repo_id}_{sym_meta['path']}" == target_file_id:
                                        target_id = sym_meta["id"]
                                        break
                    if not target_id and tgt_name in symbol_table:
                        target_id = symbol_table[tgt_name][0]["id"]
                    if not target_id:
                        target_id = f"ext_{self.repo_id}_{tgt_name}"
                        falkor_client.upsert_node(self.graph_name, NodeType.CONCEPT, NodeBase(
                            id=target_id, repository_id=self.repo_id, name=tgt_name
                        ))
                else:
                    if tgt_name in file_symbols.get(rel_path, {}):
                        target_id = file_symbols[rel_path][tgt_name]
                    elif tgt_name in symbol_table:
                        target_id = symbol_table[tgt_name][0]["id"]
                    else:
                        target_id = f"ext_{self.repo_id}_{tgt_name}"
                        falkor_client.upsert_node(self.graph_name, NodeType.CONCEPT, NodeBase(
                            id=target_id, repository_id=self.repo_id, name=tgt_name
                        ))

                falkor_client.upsert_edge(self.graph_name, EdgeBase(
                    source_id=src_id, target_id=target_id, type=rel.type,
                    confidence=rel.confidence, is_inferred=rel.is_inferred, provenance=rel.provenance
                ))
                stats["relationships_created"] += 1

                if src_is_test and rel.type == RelType.CALLS and not target_id.startswith("ext_"):
                    falkor_client.upsert_edge(self.graph_name, EdgeBase(
                        source_id=src_id, target_id=target_id, type=RelType.TESTS,
                        confidence=1.0, is_inferred=False, provenance="Derived from test invocation"
                    ))
                    stats["relationships_created"] += 1

        stats["duration_seconds"] = round(time.time() - start_time, 2)
        return stats
