from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
import logging
from app.config import settings
from app.ingestion.pipeline import IngestionPipeline
from app.graph.client import falkor_client
from app.repositories.models import (
    ImportLocalRequest,
    ImportGithubRequest,
    IndexRepoRequest
)

# Structured logging
logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.graph.client import falkor_client, MockFalkorClient

@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.app_name} in {settings.environment} mode")
    # Initialize repository manager to ensure sample-repo is registered
    try:
        from app.repositories.manager import RepositoryManager
        RepositoryManager()
    except Exception as e:
        logger.error(f"Error initializing RepositoryManager on startup: {e}")

@app.get("/health")
@app.get("/api/health")
def health_check():
    is_live = falkor_client.check_health() and not isinstance(falkor_client, MockFalkorClient)
    falkor_status = "connected" if is_live else ("mock" if isinstance(falkor_client, MockFalkorClient) else "disconnected")
    return {
        "status": "healthy",
        "environment": settings.environment,
        "falkordb": falkor_status
    }

# ==========================================
# Repository Management Endpoints
# ==========================================

@app.get("/api/repositories")
def list_repositories():
    from app.repositories.manager import RepositoryManager
    repos = RepositoryManager().list_repositories()
    return {"status": "success", "repositories": [r.model_dump() for r in repos]}

@app.post("/api/repositories/import")
def import_local_repository(request: ImportLocalRequest):
    from app.repositories.manager import RepositoryManager
    try:
        repo = RepositoryManager().import_local(request.path, request.name)
        return {"status": "success", "repository": repo.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error importing local repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/repositories/upload")
async def upload_zip_repository(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None)
):
    from app.repositories.manager import RepositoryManager
    try:
        content = await file.read()
        repo = RepositoryManager().import_zip(content, file.filename, name=name)
        return {"status": "success", "repository": repo.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading ZIP repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/repositories/github")
def import_github_repository(request: ImportGithubRequest):
    from app.repositories.manager import RepositoryManager
    try:
        repo = RepositoryManager().import_github(request.url, request.name, request.branch)
        return {"status": "success", "repository": repo.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error importing GitHub repository: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/repositories/{repo_id}")
def get_repository_metadata(repo_id: str):
    from app.repositories.manager import RepositoryManager
    repo = RepositoryManager().get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")
    return {"status": "success", "repository": repo.model_dump()}

@app.post("/api/repositories/{repo_id}/index")
def index_repository(repo_id: str, request: Optional[IndexRepoRequest] = None):
    from app.repositories.manager import RepositoryManager
    try:
        inc = request.incremental if request else False
        repo = RepositoryManager().index_repository(repo_id, incremental=inc)
        return {"status": "success", "repository": repo.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error indexing repository {repo_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/repositories/{repo_id}/status")
def get_repository_status(repo_id: str):
    from app.repositories.manager import RepositoryManager
    repo = RepositoryManager().get_repository(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")
    return {
        "status": "success",
        "repo_id": repo.id,
        "repo_status": repo.status,
        "error_message": repo.error_message,
        "last_indexed_at": repo.last_indexed_at,
        "stats": repo.stats
    }

@app.delete("/api/repositories/{repo_id}")
def delete_repository(repo_id: str):
    from app.repositories.manager import RepositoryManager
    try:
        deleted = RepositoryManager().delete_repository(repo_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")
        return {"status": "success", "deleted_repo_id": repo_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting repository {repo_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class IngestRequest(BaseModel):
    repo_path: str
    repo_id: str

@app.post("/api/ingest")
def ingest_repo(request: IngestRequest):
    import os
    if not os.path.exists(request.repo_path):
        raise HTTPException(status_code=400, detail="Repository path does not exist")
        
    pipeline = IngestionPipeline(repo_path=request.repo_path, repo_id=request.repo_id)
    stats = pipeline.index()
    return {"status": "success", "repo_id": request.repo_id, "stats": stats}

@app.get("/api/graph/{repo_id}")
def get_graph(repo_id: str):
    from app.repositories.manager import RepositoryManager
    if repo_id != "sample_1" and not RepositoryManager().get_repository(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")
    graph_name = f"workspace_{repo_id}"
    try:
        falkor_client.connect()
        data = falkor_client.get_all_elements(graph_name)
        
        # Helper to get clean human-readable name without 'Unknown'
        def _node_name(node):
            props = node.properties
            if props.get('name'):
                return props['name']
            if props.get('title'):
                return props['title']
            nid = props.get('id', '')
            parts = nid.split('_')
            return parts[-1] if len(parts) > 1 else (nid or node.labels[0])

        # Format for cytoscape UI
        elements = []
        node_ids = set()
        
        for row in data:
            n = row[0]
            r = row[1]
            m = row[2]

            # Filter internal memory/session telemetry from the code architecture view
            if n and n.labels and n.labels[0] in ("InvestigationSession", "SourceEvidence"):
                continue
            if m and m.labels and m.labels[0] in ("InvestigationSession", "SourceEvidence"):
                continue
            
            if n and n.properties['id'] not in node_ids:
                elements.append({
                    "data": {
                        "id": n.properties['id'],
                        "label": n.labels[0] if n.labels else "Node",
                        "name": _node_name(n),
                        "type": n.properties.get("type", n.labels[0] if n.labels else "Node")
                    },
                    "classes": n.labels[0].lower() if n.labels else "node"
                })
                node_ids.add(n.properties['id'])
                
            if m and m.properties['id'] not in node_ids:
                elements.append({
                    "data": {
                        "id": m.properties['id'],
                        "label": m.labels[0] if m.labels else "Node",
                        "name": _node_name(m),
                        "type": m.properties.get("type", m.labels[0] if m.labels else "Node")
                    },
                    "classes": m.labels[0].lower() if m.labels else "node"
                })
                node_ids.add(m.properties['id'])
                
            if r and n and m:
                elements.append({
                    "data": {
                        "source": n.properties['id'],
                        "target": m.properties['id'],
                        "label": r.relation,
                        "id": f"{n.properties['id']}-{r.relation}-{m.properties['id']}"
                    },
                    "classes": f"edge edge-{r.relation.lower()} {r.relation.lower()}"
                })
                
        return {"elements": elements}
    except Exception as e:
        logger.error(f"Error fetching graph: {e}")
        return {"elements": []}

from typing import List, Dict, Optional

class InvestigateRequest(BaseModel):
    repo_id: str
    query: str
    session_id: Optional[str] = None
    workspace_id: Optional[str] = "default"
    context_node: Optional[dict] = None
    history: Optional[List[Dict[str, str]]] = None

@app.post("/api/investigate")
def investigate_graph(request: InvestigateRequest):
    if not request.repo_id or not request.repo_id.strip():
        raise HTTPException(status_code=400, detail="Repository ID is required")
    from app.repositories.manager import RepositoryManager
    repo = RepositoryManager().get_repository(request.repo_id)
    if not repo and request.repo_id != "sample_1":
        raise HTTPException(status_code=404, detail=f"Repository '{request.repo_id}' not found")

    from app.agent.investigator import GraphInvestigator
    
    investigator = GraphInvestigator(repo_id=request.repo_id, workspace_id=request.workspace_id or "default")
    answer, report = investigator.investigate_with_report(
        request.query, request.context_node, request.history, session_id=request.session_id
    )
    
    pdata = getattr(investigator, "last_pipeline_data", {}) or {}

    return {
        "status": "success",
        "answer": answer,
        "session_id": request.session_id,
        "investigation_plan": pdata.get("investigation_plan"),
        "trace": pdata.get("trace"),
        "verification": {
            "is_verified": report.is_verified,
            "source_verified": report.source_verified,
            "graph_verified": report.graph_verified,
            "scenario_verified": report.scenario_verified,
            "question_completeness_verified": getattr(report, "question_completeness_verified", False),
            "execution_verified": report.execution_verified,
            "memory_persistence_verified": report.memory_persistence_verified,
            "multi_agent_handoff_verified": report.multi_agent_handoff_verified,
            "execution_receipt": report.execution_receipt,
            "memory_receipt": report.memory_receipt,
            "multi_agent_receipt": report.multi_agent_receipt,
            "citations_checked": report.citations_checked,
            "citations_valid": report.citations_valid,
            "fabricated_citations": [c.raw_citation for c in report.fabricated_citations],
            "paths_checked": report.paths_checked,
            "paths_valid": report.paths_valid,
            "fabricated_paths": [p.raw_path for p in report.fabricated_paths],
            "insufficient_evidence_flags": report.insufficient_evidence_flags,
            "missing_required_fields": getattr(report, "missing_required_fields", []),
            "summary": report.summary
        }
    }

class ImpactRequest(BaseModel):
    repo_id: str
    diff_text: Optional[str] = None
    max_depth: Optional[int] = 3

@app.post("/api/impact")
def analyze_git_impact(request: ImpactRequest):
    if not request.repo_id or not request.repo_id.strip():
        raise HTTPException(status_code=400, detail="Repository ID is required")
    from app.repositories.manager import RepositoryManager
    repo = RepositoryManager().get_repository(request.repo_id)
    if not repo and request.repo_id != "sample_1":
        raise HTTPException(status_code=404, detail=f"Repository '{request.repo_id}' not found")

    from app.agent.impact import ImpactAnalyzer
    
    analyzer = ImpactAnalyzer(repo_id=request.repo_id)
    result = analyzer.analyze(diff_text=request.diff_text, max_depth=request.max_depth or 3)
    
    return {
        "status": "success",
        "diff_summary": result.diff_summary,
        "files_changed": result.files_changed,
        "changed_symbols": [
            {
                "id": s.id, "name": s.name, "type": s.type, 
                "source_path": s.source_path, "overlapping_lines": s.overlapping_lines
            } for s in result.changed_symbols
        ],
        "impacted_entities": [
            {
                "id": i.id, "name": i.name, "type": i.type, "source_path": i.source_path,
                "depth": i.depth, "is_direct": i.is_direct, "path": i.path, "category": i.category
            } for i in result.impacted_entities
        ],
        "affected_node_ids": result.affected_node_ids,
        "connected_apis": result.connected_apis,
        "connected_modules": result.connected_modules,
        "connected_tests": result.connected_tests,
        "risk_score": result.risk_score,
        "risk_level": result.risk_level,
        "score_breakdown": result.score_breakdown,
        "explanations": result.explanations
    }

@app.get("/api/memory/sessions")
def get_memory_sessions(repo_id: str = "sample_1", workspace_id: str = "default", limit: int = 50):
    from app.repositories.manager import RepositoryManager
    if repo_id != "sample_1" and not RepositoryManager().get_repository(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")
    from app.memory.manager import GraphMemoryManager
    mem = GraphMemoryManager(repo_id=repo_id, workspace_id=workspace_id)
    sessions = mem.list_sessions(limit=limit)
    return {"status": "success", "sessions": [s.model_dump() for s in sessions]}

@app.get("/api/memory/findings")
def get_memory_findings(
    repo_id: str = "sample_1",
    workspace_id: str = "default",
    symbol_id: Optional[str] = None,
    query: Optional[str] = None,
    include_stale: bool = False,
    limit: int = 50
):
    from app.repositories.manager import RepositoryManager
    if repo_id != "sample_1" and not RepositoryManager().get_repository(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")
    from app.memory.manager import GraphMemoryManager
    mem = GraphMemoryManager(repo_id=repo_id, workspace_id=workspace_id)
    findings = mem.query_semantic_memory(
        query_text=query or "",
        symbol_id=symbol_id,
        include_stale=include_stale,
        limit=limit
    )
    return {"status": "success", "findings": [f.model_dump() for f in findings]}

@app.get("/api/memory/hypotheses")
def get_memory_hypotheses(repo_id: str = "sample_1", workspace_id: str = "default", status: Optional[str] = "unresolved"):
    from app.repositories.manager import RepositoryManager
    if repo_id != "sample_1" and not RepositoryManager().get_repository(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")
    from app.memory.manager import GraphMemoryManager
    mem = GraphMemoryManager(repo_id=repo_id, workspace_id=workspace_id)
    hypotheses = mem.list_hypotheses(status=status)
    return {"status": "success", "hypotheses": [h.model_dump() for h in hypotheses]}

class InvalidateMemoryRequest(BaseModel):
    repo_id: str
    workspace_id: Optional[str] = "default"
    current_revision: Optional[str] = None

@app.post("/api/memory/invalidate")
def invalidate_stale_memory(request: InvalidateMemoryRequest):
    from app.repositories.manager import RepositoryManager
    if request.repo_id != "sample_1" and not RepositoryManager().get_repository(request.repo_id):
        raise HTTPException(status_code=404, detail=f"Repository '{request.repo_id}' not found")
    from app.memory.manager import GraphMemoryManager
    mem = GraphMemoryManager(repo_id=request.repo_id, workspace_id=request.workspace_id or "default")
    invalidated = mem.invalidate_stale_findings(current_revision=request.current_revision)
    return {
        "status": "success",
        "invalidated_count": len(invalidated),
        "invalidated_findings": invalidated
    }

# ==========================================
# Hybrid Retrieval Endpoints (ASTERION V3)
# ==========================================

class RetrieveRequest(BaseModel):
    repo_id: str
    query: str
    limit: Optional[int] = 10
    max_tokens: Optional[int] = 4000
    alpha: Optional[float] = 0.6
    expand_graph: Optional[bool] = True

@app.get("/api/retrieve")
def retrieve_context_get(
    repo_id: str,
    query: str,
    limit: int = 10,
    max_tokens: int = 4000,
    alpha: float = 0.6,
    expand_graph: bool = True
):
    from app.repositories.manager import RepositoryManager
    from app.services.retrieval import HybridRetriever
    repo = RepositoryManager().get_repository(repo_id)
    repo_path = repo.path if repo else None
    retriever = HybridRetriever(repo_id=repo_id, repo_path=repo_path)
    result = retriever.retrieve(
        query=query,
        limit=limit,
        max_tokens=max_tokens,
        alpha=alpha,
        expand_graph=expand_graph
    )
    return {"status": "success", "data": result}

@app.post("/api/retrieve")
def retrieve_context_post(request: RetrieveRequest):
    from app.repositories.manager import RepositoryManager
    from app.services.retrieval import HybridRetriever
    repo = RepositoryManager().get_repository(request.repo_id)
    repo_path = repo.path if repo else None
    retriever = HybridRetriever(repo_id=request.repo_id, repo_path=repo_path)
    result = retriever.retrieve(
        query=request.query,
        limit=request.limit or 10,
        max_tokens=request.max_tokens or 4000,
        alpha=request.alpha if request.alpha is not None else 0.6,
        expand_graph=request.expand_graph if request.expand_graph is not None else True
    )
    return {"status": "success", "data": result}


# ==========================================
# Human-in-the-Loop Approval Endpoints (ASTERION V3)
# ==========================================

class CreateApprovalRequest(BaseModel):
    action_type: str
    description: str
    risk_level: Optional[str] = "LOW"
    payload: Optional[dict] = None

class ResolveApprovalRequest(BaseModel):
    reviewer: Optional[str] = "admin"
    notes: Optional[str] = None

@app.get("/api/approvals")
def list_approvals(status: Optional[str] = None):
    from app.agents.approval import default_approval_gate, ApprovalStatus
    reqs = list(default_approval_gate.requests.values())
    if status:
        reqs = [r for r in reqs if r.status.value.upper() == status.upper()]
    return {
        "status": "success",
        "requests": [r.model_dump() for r in reqs]
    }

@app.post("/api/approvals/request")
def create_approval_request(request: CreateApprovalRequest):
    from app.agents.approval import default_approval_gate, RiskLevel
    risk = RiskLevel(request.risk_level.upper()) if request.risk_level and request.risk_level.upper() in RiskLevel.__members__ else RiskLevel.LOW
    req = default_approval_gate.request_approval(
        action_type=request.action_type,
        description=request.description,
        risk_level=risk,
        payload=request.payload or {}
    )
    return {"status": "success", "request": req.model_dump()}

@app.post("/api/approvals/{action_id}/approve")
def approve_action(action_id: str, request: Optional[ResolveApprovalRequest] = None):
    from app.agents.approval import default_approval_gate
    try:
        reviewer = request.reviewer if request and request.reviewer else "admin"
        notes = request.notes if request and request.notes else "Authorized via API"
        req = default_approval_gate.approve(action_id=action_id, reviewer=reviewer, notes=notes)
        return {"status": "success", "request": req.model_dump()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/approvals/{action_id}/reject")
def reject_action(action_id: str, request: Optional[ResolveApprovalRequest] = None):
    from app.agents.approval import default_approval_gate
    try:
        reviewer = request.reviewer if request and request.reviewer else "admin"
        reason = request.notes if request and request.notes else "Rejected via API"
        req = default_approval_gate.reject(action_id=action_id, reviewer=reviewer, reason=reason)
        return {"status": "success", "request": req.model_dump()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))



