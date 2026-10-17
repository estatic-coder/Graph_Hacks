from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class RepositoryMetadata(BaseModel):
    id: str = Field(..., description="Unique repository identifier")
    name: str = Field(..., description="Display name of the repository")
    source_type: str = Field(..., description="Source kind: local, upload, or github")
    source_path: str = Field(..., description="Filesystem directory where source files reside")
    source_url: Optional[str] = Field(None, description="Remote URL if imported from GitHub")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    last_indexed_at: Optional[str] = Field(None, description="ISO 8601 last indexing timestamp")
    status: str = Field("empty", description="Current status: ready, indexing, error, empty")
    error_message: Optional[str] = None
    stats: Dict[str, Any] = Field(default_factory=dict)
    is_demo: bool = False

class ImportLocalRequest(BaseModel):
    path: str
    name: Optional[str] = None

class ImportGithubRequest(BaseModel):
    url: str
    name: Optional[str] = None
    branch: Optional[str] = None

class IndexRepoRequest(BaseModel):
    incremental: Optional[bool] = False
