import os
import uuid
import logging
from typing import Dict
from app.graph.client import falkor_client
from app.graph.schema import NodeBase, EdgeBase, NodeType, RelType
from app.ingestion.parsers.python import PythonParser
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
            ".ts": RegexFallbackParser(),
            ".js": RegexFallbackParser(),
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
                
                # Register module lookup keys
                mod_name = os.path.splitext(rel_path)[0].replace("/", ".").replace("\\", ".")
                module_to_file[mod_name] = file_id
                module_to_file[mod_name.split(".")[-1]] = file_id
                module_to_file[os.path.basename(mod_name)] = file_id
                module_to_file[rel_path] = file_id
                module_to_file[file] = file_id
                
                # Upsert File Node
                file_node = NodeBase(
                    id=file_id, 
                    repository_id=self.repo_id,
                    name=file,
                    source_path=rel_path
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
                    sym_node = NodeBase(
                        id=sym_id, repository_id=self.repo_id, name=sym.name, 
                        source_path=rel_path, start_line=sym.start_line, end_line=sym.end_line
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
            file_import_map = {}  # imported symbol/module -> module_name
            for rel in relationships:
                if rel.type == RelType.IMPORTS:
                    tgt_mod = getattr(rel, "target_module", None) or rel.target_name
                    file_import_map[rel.target_name] = tgt_mod

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

                    if tgt_mod in module_to_file:
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
                    # Check if imported from a known module
                    elif tgt_name in file_import_map:
                        imported_from = file_import_map[tgt_name]
                        if imported_from in module_to_file:
                            target_file_id = module_to_file[imported_from]
                            if tgt_name in symbol_table:
                                for sym_meta in symbol_table[tgt_name]:
                                    if f"file_{self.repo_id}_{sym_meta['path']}" == target_file_id:
                                        target_id = sym_meta["id"]
                                        break
                    # Check if uniquely defined across repository
                    if not target_id and tgt_name in symbol_table:
                        target_id = symbol_table[tgt_name][0]["id"]
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
