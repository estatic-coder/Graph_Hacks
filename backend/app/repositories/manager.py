import os
import re
import json
import uuid
import shutil
import zipfile
import logging
import threading
import subprocess
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.config import settings
from app.graph.client import falkor_client
from app.ingestion.pipeline import IngestionPipeline
from app.repositories.models import RepositoryMetadata

logger = logging.getLogger(__name__)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
REPOS_DIR = os.path.join(DATA_DIR, "repos")
METADATA_FILE = os.path.join(DATA_DIR, "repositories.json")

# Forbidden directories for local folder imports
FORBIDDEN_ROOTS = {"/", "/etc", "/dev", "/proc", "/sys", "/boot", "/root", "/bin", "/sbin", "/usr", "/var"}

class RepositoryManager:
    """
    Manages multi-repository lifecycle, persistent metadata,
    safe local imports, secure ZIP extractions, GitHub cloning,
    indexing dispatch, and graph deletion.
    """
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RepositoryManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        os.makedirs(REPOS_DIR, exist_ok=True)
        self.metadata_file = METADATA_FILE
        self._repos: Dict[str, RepositoryMetadata] = {}
        self._load_or_initialize()
        self._initialized = True

    def _load_or_initialize(self):
        """Loads repository metadata from disk or initializes default sample-repo."""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for r_id, r_dict in data.items():
                    self._repos[r_id] = RepositoryMetadata(**r_dict)
            except Exception as e:
                logger.error(f"Error loading {self.metadata_file}: {e}")

        # Ensure default demo sample-repo is always registered
        if "sample_1" not in self._repos:
            sample_repo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../sample-repo"))
            self._repos["sample_1"] = RepositoryMetadata(
                id="sample_1",
                name="sample-repo",
                source_type="local",
                source_path=sample_repo_path,
                created_at=datetime.now(timezone.utc).isoformat(),
                last_indexed_at=datetime.now(timezone.utc).isoformat(),
                status="ready",
                is_demo=True,
                stats={
                    "files_scanned": 4,
                    "symbols_extracted": 6,
                    "relationships_created": 24
                }
            )
            self._save()

    def _save(self):
        """Persists metadata safely to JSON disk."""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.metadata_file), exist_ok=True)
                data = {r_id: r.model_dump() for r_id, r in self._repos.items()}
                temp_file = self.metadata_file + ".tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.replace(temp_file, self.metadata_file)
            except Exception as e:
                logger.error(f"Failed to persist {self.metadata_file}: {e}")

    # -------------------------------------------------------------
    # Repository Queries
    # -------------------------------------------------------------

    def list_repositories(self) -> List[RepositoryMetadata]:
        """Returns all registered repositories."""
        return list(self._repos.values())

    def get_repository(self, repo_id: str) -> Optional[RepositoryMetadata]:
        """Gets a repository by ID."""
        return self._repos.get(repo_id)

    # -------------------------------------------------------------
    # Imports
    # -------------------------------------------------------------

    def import_local(self, path: str, name: Optional[str] = None) -> RepositoryMetadata:
        """
        Imports a local filesystem repository.
        Validates path traversal and forbids dangerous system directories.
        """
        clean_path = os.path.realpath(os.path.expanduser(path.strip()))
        if not os.path.exists(clean_path):
            raise ValueError(f"Path does not exist: {clean_path}")
        if not os.path.isdir(clean_path):
            raise ValueError(f"Path is not a directory: {clean_path}")

        # Check for forbidden system directories
        for forbidden in FORBIDDEN_ROOTS:
            if clean_path == forbidden or clean_path.startswith(forbidden + "/"):
                if not clean_path.startswith(os.path.expanduser("~")):
                    raise ValueError(f"Importing system directory '{forbidden}' is restricted.")

        base_name = name.strip() if name and name.strip() else os.path.basename(clean_path)
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", base_name).lower()[:16]
        repo_id = f"repo_{slug}_{uuid.uuid4().hex[:6]}"

        repo = RepositoryMetadata(
            id=repo_id,
            name=base_name,
            source_type="local",
            source_path=clean_path,
            created_at=datetime.now(timezone.utc).isoformat(),
            status="empty",
            is_demo=False
        )

        with self._lock:
            self._repos[repo_id] = repo
            self._save()

        # Run indexing
        self.index_repository(repo_id)
        return self._repos[repo_id]

    def import_zip(self, file_bytes: bytes, filename: str, name: Optional[str] = None) -> RepositoryMetadata:
        """
        Safely extracts uploaded ZIP archive.
        Protects against ZipSlip (directory traversal) and ZipBomb (size limits).
        """
        MAX_ZIP_SIZE = 50 * 1024 * 1024       # 50MB compressed
        MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024  # 100MB uncompressed
        MAX_FILES = 5000

        if len(file_bytes) > MAX_ZIP_SIZE:
            raise ValueError(f"Archive exceeds maximum size limit of 50MB ({len(file_bytes)} bytes).")

        base_name = name.strip() if name and name.strip() else os.path.splitext(filename)[0]
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", base_name).lower()[:16]
        repo_id = f"repo_{slug}_{uuid.uuid4().hex[:6]}"
        target_dir = os.path.join(REPOS_DIR, repo_id)
        os.makedirs(target_dir, exist_ok=True)

        import io
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                total_size = 0
                total_files = 0
                for info in z.infolist():
                    total_files += 1
                    total_size += info.file_size
                    if total_files > MAX_FILES:
                        raise ValueError(f"Archive contains too many files (max {MAX_FILES}).")
                    if total_size > MAX_UNCOMPRESSED_SIZE:
                        raise ValueError(f"Uncompressed archive exceeds size limit (max 100MB).")

                    # ZipSlip verification
                    extracted_path = os.path.realpath(os.path.join(target_dir, info.filename))
                    if not extracted_path.startswith(os.path.realpath(target_dir) + os.sep) and extracted_path != os.path.realpath(target_dir):
                        raise ValueError(f"Insecure archive: Path traversal detected in {info.filename}")

                z.extractall(target_dir)

            # If archive contained a single top-level folder, use that as source_path
            entries = [e for e in os.listdir(target_dir) if not e.startswith("__MACOSX") and not e.startswith(".")]
            actual_source = target_dir
            if len(entries) == 1 and os.path.isdir(os.path.join(target_dir, entries[0])):
                actual_source = os.path.join(target_dir, entries[0])

            repo = RepositoryMetadata(
                id=repo_id,
                name=base_name,
                source_type="zip",
                source_path=actual_source,
                created_at=datetime.now(timezone.utc).isoformat(),
                status="empty",
                is_demo=False
            )

            with self._lock:
                self._repos[repo_id] = repo
                self._save()

            # Index extracted repository
            self.index_repository(repo_id)
            return self._repos[repo_id]

        except zipfile.BadZipFile as e:
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            raise ValueError(f"Invalid or corrupted ZIP archive: {e}")
        except Exception as e:
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            raise e

    def import_github(self, url: str, name: Optional[str] = None, branch: Optional[str] = None) -> RepositoryMetadata:
        """
        Clones a public GitHub repository using shallow clone with timeout.
        """
        url = url.strip()
        # Validate GitHub URL
        match = re.match(r"^https://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?/?$", url)
        if not match:
            raise ValueError(f"Invalid GitHub URL: '{url}'. Expected format: https://github.com/owner/repo")

        owner, repo_name = match.group(1), match.group(2)
        base_name = name.strip() if name and name.strip() else repo_name
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", base_name).lower()[:16]
        repo_id = f"repo_{slug}_{uuid.uuid4().hex[:6]}"
        target_dir = os.path.join(REPOS_DIR, repo_id)
        os.makedirs(target_dir, exist_ok=True)

        cmd = ["git", "clone", "--depth", "1"]
        if branch and branch.strip():
            cmd.extend(["--branch", branch.strip()])
        cmd.extend([url, target_dir])

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=45
            )
            if res.returncode != 0:
                err_msg = res.stderr.strip() or "Git clone failed"
                shutil.rmtree(target_dir, ignore_errors=True)
                raise ValueError(f"GitHub import failed: {err_msg}")

            repo = RepositoryMetadata(
                id=repo_id,
                name=base_name,
                source_type="github",
                source_path=target_dir,
                source_url=url,
                created_at=datetime.now(timezone.utc).isoformat(),
                status="empty",
                is_demo=False
            )

            with self._lock:
                self._repos[repo_id] = repo
                self._save()

            self.index_repository(repo_id)
            return self._repos[repo_id]

        except subprocess.TimeoutExpired:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise ValueError("GitHub clone timed out (45s limit exceeded). Repository may be too large.")
        except Exception as e:
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            raise e

    # -------------------------------------------------------------
    # Indexing & Status
    # -------------------------------------------------------------

    def index_repository(self, repo_id: str, incremental: bool = False) -> RepositoryMetadata:
        """
        Executes AST code parsing and cross-file symbol indexing into FalkorDB.
        Updates status and stores performance stats.
        """
        repo = self._repos.get(repo_id)
        if not repo:
            raise ValueError(f"Repository not found: {repo_id}")

        repo.status = "indexing"
        repo.error_message = None
        self._save()

        try:
            pipeline = IngestionPipeline(repo_path=repo.source_path, repo_id=repo_id)
            stats = pipeline.index(incremental=incremental)

            # Query real graph stats from FalkorDB
            graph_stats = {}
            try:
                raw_stats = falkor_client.get_graph_stats(f"workspace_{repo_id}")
                nodes_count = sum(r[1] for r in raw_stats.get("nodes", []))
                rels_count = sum(r[1] for r in raw_stats.get("relationships", []))
                graph_stats = {"nodes_count": nodes_count, "relationships_count": rels_count}
            except Exception:
                pass

            combined_stats = {**stats, **graph_stats}

            repo.status = "ready"
            repo.last_indexed_at = datetime.now(timezone.utc).isoformat()
            repo.stats = combined_stats
            self._save()
            return repo

        except Exception as e:
            logger.error(f"Failed to index repository {repo_id}: {e}")
            repo.status = "error"
            repo.error_message = str(e)
            self._save()
            raise e

    # -------------------------------------------------------------
    # Deletion
    # -------------------------------------------------------------

    def delete_repository(self, repo_id: str) -> bool:
        """
        Removes a repository, its FalkorDB graph workspace, and local files (if managed).
        """
        repo = self._repos.get(repo_id)
        if not repo:
            return False

        if repo.is_demo:
            raise ValueError("Cannot delete preloaded demo repository")

        # Drop or clear FalkorDB graph
        graph_name = f"workspace_{repo_id}"
        try:
            falkor_client.delete_graph(graph_name)
        except Exception as e:
            logger.warning(f"Could not delete FalkorDB graph {graph_name}: {e}")

        # If files were saved in managed REPOS_DIR, delete from filesystem
        if repo.source_path.startswith(REPOS_DIR):
            try:
                shutil.rmtree(repo.source_path, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Could not remove repository directory {repo.source_path}: {e}")

        with self._lock:
            del self._repos[repo_id]
            self._save()

        return True
